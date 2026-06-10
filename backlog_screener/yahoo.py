from __future__ import annotations

import json
import math
import sys
import time
from datetime import date, datetime
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import pandas as pd
import requests

from .config import DEFAULT_EXCHANGES, ScreenThresholds
from .models import CandidateMetrics


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip().replace(",", "").replace("%", "").replace("$", "")
        if not value or value.lower() in {"nan", "none", "n/a", "--"}:
            return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _normalize_ratio(value) -> Optional[float]:
    number = _to_float(value)
    if number is None:
        return None
    return number / 100 if abs(number) > 1.5 else number


def _get_mapping_value(mapping, *keys):
    for key in keys:
        try:
            value = mapping.get(key)
        except AttributeError:
            try:
                value = mapping[key]
            except Exception:
                value = None
        except Exception:
            value = None
        if value is not None:
            return value
    return None


def _major_holder_pct(frame: pd.DataFrame, needle: str) -> Optional[float]:
    if frame is None or frame.empty:
        return None
    lower_needle = needle.lower()
    for _, row in frame.iterrows():
        cells = [str(item) for item in row.tolist()]
        if any(lower_needle in cell.lower() for cell in cells):
            for cell in cells:
                parsed = _normalize_ratio(cell)
                if parsed is not None:
                    return parsed
    return None


def _quarterly_revenue_yoy(ticker) -> Optional[float]:
    try:
        frame = ticker.quarterly_income_stmt
    except Exception:
        return None
    if frame is None or frame.empty:
        return None

    row_name = None
    for index_value in frame.index:
        normalized = str(index_value).replace(" ", "").lower()
        if normalized in {"totalrevenue", "revenue"}:
            row_name = index_value
            break
    if row_name is None:
        return None

    series = frame.loc[row_name].dropna()
    values = []
    for column, raw_value in series.items():
        value = _to_float(raw_value)
        if value is None:
            continue
        date = pd.to_datetime(column, errors="coerce")
        values.append((date, value))

    if len(values) < 5:
        return None
    values.sort(key=lambda item: item[0], reverse=True)
    latest = values[0][1]
    prior_year_quarter = values[4][1]
    if prior_year_quarter == 0:
        return None
    return (latest - prior_year_quarter) / abs(prior_year_quarter)


def fetch_candidate_metrics(
    symbol: str,
    cache_dir: Optional[Path] = None,
    cache_ttl_hours: float = 24,
    force_refresh: bool = False,
    retries: int = 1,
    retry_wait_seconds: float = 15,
) -> CandidateMetrics:
    symbol = symbol.strip().upper()
    cache_path = _cache_path(cache_dir, symbol)
    cached = _read_cached_metrics(cache_path, max_age_seconds=cache_ttl_hours * 3600)
    if cached is not None and not force_refresh:
        cached.source = "yfinance-cache"
        return cached

    last_error = None
    for attempt in range(max(0, retries) + 1):
        try:
            metrics = _fetch_live_candidate_metrics(symbol)
            _write_cached_metrics(cache_path, metrics)
            return metrics
        except Exception as exc:
            last_error = exc
            if not _looks_rate_limited(exc) or attempt >= retries:
                break
            time.sleep(max(0, retry_wait_seconds) * (attempt + 1))

    stale = _read_cached_metrics(cache_path, max_age_seconds=None)
    if stale is not None:
        stale.source = "yfinance-cache-stale"
        stale.warnings.append(f"Using stale yfinance cache for {symbol}; live fetch failed: {last_error}")
        return stale

    metrics = CandidateMetrics(ticker=symbol)
    metrics.warnings.append(f"yfinance fetch failed for {symbol}: {last_error}")
    return metrics


def fetch_price_trend(symbol: str, *, period: str = "max", max_points: int = 420) -> dict:
    import yfinance as yf

    clean_symbol = symbol.strip().upper()
    ticker = yf.Ticker(clean_symbol)
    frame = ticker.history(period=period, interval="1d", auto_adjust=True)
    if frame is None or frame.empty or "Close" not in frame:
        return {
            "ticker": clean_symbol,
            "source": "yfinance",
            "period": period,
            "points": [],
            "error": "No yFinance daily close history found.",
        }

    points = []
    for raw_date, raw_row in frame.iterrows():
        close = _to_float(raw_row.get("Close"))
        if close is None:
            continue
        timestamp = pd.to_datetime(raw_date, errors="coerce")
        if pd.isna(timestamp):
            continue
        points.append({"date": timestamp.date().isoformat(), "close": close})

    points = _sample_points(points, max_points=max_points)
    closes = [point["close"] for point in points]
    first = points[0] if points else None
    latest = points[-1] if points else None
    first_close = first["close"] if first else None
    latest_close = latest["close"] if latest else None
    total_return = None
    if first_close not in (None, 0) and latest_close is not None:
        total_return = (latest_close - first_close) / abs(first_close)
    return {
        "ticker": clean_symbol,
        "source": "yfinance",
        "period": period,
        "points": points,
        "point_count": len(points),
        "first_date": first["date"] if first else None,
        "latest_date": latest["date"] if latest else None,
        "first_close": first_close,
        "latest_close": latest_close,
        "min_close": min(closes) if closes else None,
        "max_close": max(closes) if closes else None,
        "total_return": total_return,
    }


def fetch_nasdaq_price_trend(
    symbol: str,
    *,
    max_points: int = 420,
    from_date: str = "1990-01-01",
    to_date: str | None = None,
) -> dict:
    clean_symbol = symbol.strip().upper()
    params = {
        "assetclass": "stocks",
        "fromdate": from_date,
        "todate": to_date or date.today().isoformat(),
        "limit": "9999",
    }
    response = requests.get(
        f"https://api.nasdaq.com/api/quote/{clean_symbol}/historical",
        params=params,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
        },
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    rows = (((payload.get("data") or {}).get("tradesTable") or {}).get("rows") or [])
    points = []
    for row in rows:
        close = _to_float(row.get("close"))
        if close is None:
            continue
        parsed_date = _parse_nasdaq_date(row.get("date"))
        if parsed_date is None:
            continue
        points.append({"date": parsed_date.isoformat(), "close": close})
    points.sort(key=lambda item: item["date"])
    points = _sample_points(points, max_points=max_points)
    closes = [point["close"] for point in points]
    first = points[0] if points else None
    latest = points[-1] if points else None
    first_close = first["close"] if first else None
    latest_close = latest["close"] if latest else None
    total_return = None
    if first_close not in (None, 0) and latest_close is not None:
        total_return = (latest_close - first_close) / abs(first_close)
    return {
        "ticker": clean_symbol,
        "source": "nasdaq",
        "source_label": "Nasdaq daily close",
        "period": "max",
        "points": points,
        "point_count": len(points),
        "first_date": first["date"] if first else None,
        "latest_date": latest["date"] if latest else None,
        "first_close": first_close,
        "latest_close": latest_close,
        "min_close": min(closes) if closes else None,
        "max_close": max(closes) if closes else None,
        "total_return": total_return,
        "query_window": {"from": from_date, "to": params["todate"]},
    }


def _fetch_live_candidate_metrics(symbol: str) -> CandidateMetrics:
    import yfinance as yf

    symbol = symbol.strip().upper()
    metrics = CandidateMetrics(ticker=symbol)
    ticker = yf.Ticker(symbol)

    info: Dict = {}
    try:
        info = ticker.get_info() or {}
    except Exception as exc:
        if _looks_retryable(exc):
            raise
        metrics.warnings.append(f"yfinance get_info failed for {symbol}: {exc}")

    fast_info = {}
    try:
        fast_info = ticker.fast_info or {}
    except Exception:
        fast_info = {}

    metrics.name = _get_mapping_value(info, "shortName", "longName", "displayName") or ""
    metrics.sector = _get_mapping_value(info, "sector") or ""
    metrics.industry = _get_mapping_value(info, "industry") or ""
    metrics.market_cap = _to_float(_get_mapping_value(info, "marketCap"))
    if metrics.market_cap is None:
        metrics.market_cap = _to_float(_get_mapping_value(fast_info, "market_cap", "marketCap"))
    metrics.institutional_ownership = _normalize_ratio(
        _get_mapping_value(info, "heldPercentInstitutions", "institutionPercentHeld")
    )
    metrics.insider_ownership = _normalize_ratio(
        _get_mapping_value(info, "heldPercentInsiders", "insiderPercentHeld")
    )
    metrics.quarterly_revenue_yoy = _normalize_ratio(_get_mapping_value(info, "revenueGrowth"))
    if metrics.quarterly_revenue_yoy is None:
        metrics.quarterly_revenue_yoy = _quarterly_revenue_yoy(ticker)
    metrics.trailing_pe = _to_float(_get_mapping_value(info, "trailingPE"))
    metrics.forward_pe = _to_float(_get_mapping_value(info, "forwardPE"))
    metrics.price = _to_float(_get_mapping_value(info, "currentPrice", "regularMarketPrice"))
    if metrics.price is None:
        metrics.price = _to_float(_get_mapping_value(fast_info, "last_price", "lastPrice"))

    if metrics.institutional_ownership is None or metrics.insider_ownership is None:
        try:
            holders = ticker.major_holders
        except Exception:
            holders = None
        if metrics.institutional_ownership is None:
            metrics.institutional_ownership = _major_holder_pct(holders, "institutions")
        if metrics.insider_ownership is None:
            metrics.insider_ownership = _major_holder_pct(holders, "insider")

    return metrics


def _sample_points(points: list[dict], *, max_points: int) -> list[dict]:
    if max_points <= 0 or len(points) <= max_points:
        return points
    last_index = len(points) - 1
    sampled = []
    seen: set[int] = set()
    for index in range(max_points):
        source_index = round(index * last_index / (max_points - 1))
        if source_index in seen:
            continue
        seen.add(source_index)
        sampled.append(points[source_index])
    return sampled


def _parse_nasdaq_date(value) -> date | None:
    try:
        return datetime.strptime(str(value), "%m/%d/%Y").date()
    except (TypeError, ValueError):
        return None


def _cache_path(cache_dir: Optional[Path], symbol: str) -> Optional[Path]:
    if cache_dir is None:
        return None
    return Path(cache_dir) / f"{symbol.upper()}.json"


def _read_cached_metrics(cache_path: Optional[Path], max_age_seconds: Optional[float]) -> Optional[CandidateMetrics]:
    if cache_path is None or not cache_path.exists():
        return None
    if max_age_seconds is not None and time.time() - cache_path.stat().st_mtime > max_age_seconds:
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        data = payload.get("metrics", payload)
        allowed = CandidateMetrics.__dataclass_fields__.keys()
        filtered = {key: value for key, value in data.items() if key in allowed}
        return CandidateMetrics(**filtered)
    except Exception:
        return None


def _write_cached_metrics(cache_path: Optional[Path], metrics: CandidateMetrics) -> None:
    if cache_path is None:
        return
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "cached_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "metrics": asdict(metrics),
    }
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _looks_retryable(exc: Exception) -> bool:
    text = str(exc).lower()
    retryable_terms = (
        "too many requests",
        "rate limit",
        "429",
        "ssl",
        "tls",
        "timeout",
        "timed out",
        "connection",
        "curl",
    )
    return any(term in text for term in retryable_terms)


def _looks_rate_limited(exc: Exception) -> bool:
    text = str(exc).lower()
    return "too many requests" in text or "rate limit" in text or "429" in text


def seed_yfinance_universe(
    thresholds: ScreenThresholds,
    limit: int = 100,
    exchanges: Sequence[str] = DEFAULT_EXCHANGES,
) -> List[str]:
    import yfinance as yf
    from yfinance import EquityQuery

    size = max(1, min(int(limit), 250))

    def build_query(percent_scale: float):
        return EquityQuery(
            "and",
            [
                EquityQuery("eq", ["region", "us"]),
                EquityQuery("is-in", ["exchange", *exchanges]),
                EquityQuery("btwn", ["intradaymarketcap", thresholds.min_market_cap, thresholds.max_market_cap]),
                EquityQuery("gte", ["pctheldinst", thresholds.min_institutional_ownership * percent_scale]),
                EquityQuery("gte", ["pctheldinsider", thresholds.min_insider_ownership * percent_scale]),
                EquityQuery("gte", ["quarterlyrevenuegrowth.quarterly", thresholds.min_quarterly_revenue_yoy * 100]),
                EquityQuery("btwn", ["peratio.lasttwelvemonths", 0.01, thresholds.max_trailing_pe]),
            ],
        )

    responses = []
    for percent_scale in (100, 1):
        query = build_query(percent_scale)
        try:
            response = yf.screen(
                query,
                size=size,
                sortField="quarterlyrevenuegrowth.quarterly",
                sortAsc=False,
            )
        except Exception as exc:
            print(f"yfinance screen failed with percent scale {percent_scale}: {exc}", file=sys.stderr)
            continue
        symbols = _symbols_from_screen_response(response)
        responses.append(symbols)
        if symbols:
            return symbols
    return responses[-1] if responses else []


def _symbols_from_screen_response(response) -> List[str]:
    if not response:
        return []
    quotes = response.get("quotes", []) if isinstance(response, dict) else []
    symbols = []
    for quote in quotes:
        symbol = quote.get("symbol") if isinstance(quote, dict) else None
        if symbol:
            symbols.append(symbol.upper())
    return _dedupe(symbols)


def _dedupe(values: Iterable[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        key = value.strip().upper()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(key)
    return result
