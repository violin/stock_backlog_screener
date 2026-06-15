from __future__ import annotations

import math
import os
import time
from contextlib import AbstractContextManager
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

import pandas as pd

from .models import CandidateMetrics
from .settings import PROJECT_ROOT


def futu_code(ticker: str, market: str = "US") -> str:
    ticker = ticker.strip().upper()
    if "." in ticker:
        return ticker
    return f"{market.upper()}.{ticker}"


class FutuProvider(AbstractContextManager["FutuProvider"]):
    def __init__(self, *, host: str = "127.0.0.1", port: int = 11111, market: str = "US"):
        self.host = host
        self.port = int(port)
        self.market = market
        log_home = PROJECT_ROOT / "logs"
        log_home.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("HOME", str(log_home))
        from futu import OpenQuoteContext, RET_OK

        self._ret_ok = RET_OK
        self.quote_ctx = OpenQuoteContext(host=self.host, port=self.port)

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def close(self) -> None:
        self.quote_ctx.close()

    def snapshots(self, tickers: Iterable[str]) -> list[dict]:
        codes = [futu_code(ticker, self.market) for ticker in tickers]
        ret, data = self.quote_ctx.get_market_snapshot(codes)
        if ret != self._ret_ok:
            raise RuntimeError(str(data))
        if data is None or data.empty:
            return []
        return [_clean_record(record) for record in data.to_dict(orient="records")]

    def owner_plates(
        self,
        tickers: Iterable[str],
        *,
        batch_size: int = 100,
        delay_seconds: float = 0.35,
    ) -> dict[str, list[dict]]:
        codes = [futu_code(ticker, self.market) for ticker in tickers]
        batch_size = max(1, int(batch_size))
        result: dict[str, list[dict]] = {}
        for index in range(0, len(codes), batch_size):
            batch = codes[index : index + batch_size]
            ret, data = self.quote_ctx.get_owner_plate(batch)
            if ret != self._ret_ok:
                if len(batch) > 1:
                    self._collect_owner_plates_one_by_one(batch, result)
                else:
                    result.setdefault(_ticker_from_code(batch[0]), [])
                if index + batch_size < len(codes) and delay_seconds > 0:
                    time.sleep(delay_seconds)
                continue
            if data is not None and not data.empty:
                for record in data.to_dict(orient="records"):
                    cleaned = _clean_record(record)
                    ticker = _ticker_from_code(cleaned.get("code"))
                    if ticker:
                        result.setdefault(ticker, []).append(cleaned)
            if index + batch_size < len(codes) and delay_seconds > 0:
                time.sleep(delay_seconds)
        return result

    def _collect_owner_plates_one_by_one(self, codes: list[str], result: dict[str, list[dict]]) -> None:
        for code in codes:
            ret, data = self.quote_ctx.get_owner_plate([code])
            ticker = _ticker_from_code(code)
            if ret != self._ret_ok:
                result.setdefault(ticker, [])
                continue
            if data is None or data.empty:
                result.setdefault(ticker, [])
                continue
            for record in data.to_dict(orient="records"):
                cleaned = _clean_record(record)
                row_ticker = _ticker_from_code(cleaned.get("code")) or ticker
                result.setdefault(row_ticker, []).append(cleaned)

    def basicinfo(self) -> list[dict]:
        from futu import Market

        ret, data = self.quote_ctx.get_stock_basicinfo(
            market=getattr(Market, self.market),
            stock_type="STOCK",
        )
        if ret != self._ret_ok:
            raise RuntimeError(str(data))
        if data is None or data.empty:
            return []
        return [_clean_record(record) for record in data.to_dict(orient="records")]

    def attention_flow(self, ticker: str, *, flow_days: int = 20, kline_days: int = 80) -> dict:
        code = futu_code(ticker, self.market)
        payload = {
            "ticker": _ticker_from_code(code),
            "code": code,
            "capital_distribution": self.capital_distribution(code),
            "capital_flow": self.capital_flow(code, days=flow_days),
        }
        try:
            payload["kline"] = self.history_kline(code, days=kline_days)
        except RuntimeError as exc:
            if not _is_history_quota_message(str(exc)):
                raise
            payload["kline"] = []
            payload["kline_error"] = str(exc)
        return payload

    def capital_distribution(self, code: str) -> dict:
        ret, data = self.quote_ctx.get_capital_distribution(code)
        if ret != self._ret_ok:
            raise RuntimeError(str(data))
        if data is None or data.empty:
            return {}
        return _clean_record(data.to_dict(orient="records")[0])

    def capital_flow(self, code: str, *, days: int = 20) -> list[dict]:
        from futu import PeriodType

        end = date.today()
        start = end - timedelta(days=max(14, int(days) * 3))
        ret, data = self._get_capital_flow_with_retry(
            code,
            period_type=PeriodType.DAY,
            start=start.isoformat(),
            end=end.isoformat(),
        )
        if ret != self._ret_ok:
            raise RuntimeError(str(data))
        if data is None or data.empty:
            return []
        rows = [_clean_record(record) for record in data.to_dict(orient="records")]
        return rows[-max(1, int(days)) :]

    def _get_capital_flow_with_retry(self, code: str, **kwargs):
        ret, data = self.quote_ctx.get_capital_flow(code, **kwargs)
        if ret == self._ret_ok:
            return ret, data
        message = str(data)
        if _is_rate_limit_message(message):
            time.sleep(31)
            return self.quote_ctx.get_capital_flow(code, **kwargs)
        return ret, data

    def history_kline(self, code: str, *, days: int = 80) -> list[dict]:
        from futu import AuType, KLType

        end = date.today()
        start = end - timedelta(days=max(120, int(days) * 3))
        ret, data, _ = self.quote_ctx.request_history_kline(
            code,
            start=start.isoformat(),
            end=end.isoformat(),
            ktype=KLType.K_DAY,
            autype=AuType.QFQ,
            max_count=1000,
        )
        if ret != self._ret_ok:
            raise RuntimeError(str(data))
        if data is None or data.empty:
            return []
        rows = [_clean_record(record) for record in data.to_dict(orient="records")]
        return rows[-max(1, int(days)) :]

    def subscribe_minute_kline(self, ticker: str, *, session: str = "ALL") -> str:
        from futu import Session, SubType

        code = futu_code(ticker, self.market)
        session_value = getattr(Session, session.upper(), Session.ALL)
        try:
            ret, data = self.quote_ctx.subscribe(
                [code],
                [SubType.K_1M],
                is_first_push=True,
                subscribe_push=True,
                session=session_value,
            )
        except TypeError:
            ret, data = self.quote_ctx.subscribe(
                [code],
                [SubType.K_1M],
                is_first_push=True,
                subscribe_push=True,
            )
        if ret != self._ret_ok:
            raise RuntimeError(str(data))
        return code

    def unsubscribe_minute_kline(self, ticker: str) -> None:
        from futu import SubType

        code = futu_code(ticker, self.market)
        ret, data = self.quote_ctx.unsubscribe([code], [SubType.K_1M])
        if ret != self._ret_ok:
            raise RuntimeError(str(data))

    def current_minute_kline(self, ticker: str, *, num: int = 160) -> tuple[str, list[dict]]:
        from futu import AuType, SubType

        code = futu_code(ticker, self.market)
        count = max(20, min(1000, int(num)))
        ret, data = self.quote_ctx.get_cur_kline(
            code,
            count,
            SubType.K_1M,
            AuType.QFQ,
        )
        if ret != self._ret_ok:
            raise RuntimeError(str(data))
        if data is None or data.empty:
            return code, []
        return code, [_clean_record(record) for record in data.to_dict(orient="records")]

    def price_trend(self, ticker: str, *, max_points: int = 420) -> dict:
        from futu import AuType, KLType

        code = futu_code(ticker, self.market)
        end = date.today().isoformat()
        rows = []
        page_req_key = None
        for _ in range(20):
            ret, data, page_req_key = self.quote_ctx.request_history_kline(
                code,
                start="1980-01-01",
                end=end,
                ktype=KLType.K_WEEK,
                autype=AuType.QFQ,
                max_count=1000,
                page_req_key=page_req_key,
            )
            if ret != self._ret_ok:
                raise RuntimeError(str(data))
            if data is not None and not data.empty:
                rows.extend(_clean_record(record) for record in data.to_dict(orient="records"))
            if not page_req_key:
                break
            time.sleep(0.15)
        return _price_trend_from_kline_rows(code, rows, max_points=max_points)

    def stock_filter(
        self,
        *,
        min_market_cap: float | None = None,
        max_market_cap: float | None = None,
        min_pe_ttm: float | None = None,
        max_pe_ttm: float | None = None,
        page_size: int = 200,
        limit: int | None = None,
        strict_common: bool = True,
        page_delay_seconds: float = 3.2,
        rate_limit_wait_seconds: float = 30,
    ) -> tuple[list[dict], int]:
        from futu import Market, SimpleFilter, SortDir, StockField

        basicinfo_by_code = {}
        if strict_common:
            try:
                basicinfo_by_code = {row.get("code"): row for row in self.basicinfo()}
            except Exception:
                basicinfo_by_code = {}

        filters = []
        market_cap_filter = SimpleFilter()
        market_cap_filter.stock_field = StockField.MARKET_VAL
        market_cap_filter.filter_min = min_market_cap
        market_cap_filter.filter_max = max_market_cap
        market_cap_filter.is_no_filter = False
        market_cap_filter.sort = SortDir.ASCEND
        filters.append(market_cap_filter)

        pe_filter = SimpleFilter()
        pe_filter.stock_field = StockField.PE_TTM
        pe_filter.filter_min = min_pe_ttm
        pe_filter.filter_max = max_pe_ttm
        pe_filter.is_no_filter = False if min_pe_ttm is not None or max_pe_ttm is not None else None
        filters.append(pe_filter)

        pb_filter = SimpleFilter()
        pb_filter.stock_field = StockField.PB_RATE
        pb_filter.is_no_filter = None
        filters.append(pb_filter)

        page_size = max(1, min(200, int(page_size)))
        results: list[dict] = []
        seen_tickers: set[str] = set()
        all_count = 0
        begin = 0
        while True:
            ret, payload = self.quote_ctx.get_stock_filter(
                market=getattr(Market, self.market),
                filter_list=filters,
                begin=begin,
                num=page_size,
            )
            if ret != self._ret_ok:
                message = str(payload)
                if "high frequency" in message.lower() or "maximum 10 times per 30 seconds" in message.lower():
                    time.sleep(max(0, rate_limit_wait_seconds))
                    continue
                raise RuntimeError(str(payload))
            last_page, all_count, page_items = payload
            for item in page_items:
                basicinfo = basicinfo_by_code.get(getattr(item, "stock_code", ""))
                record = _filter_stock_record(item, basicinfo=basicinfo)
                if not strict_common or _is_common_us_stock(record):
                    if record["ticker"] in seen_tickers:
                        continue
                    seen_tickers.add(record["ticker"])
                    results.append(record)
                if limit is not None and len(results) >= limit:
                    return results[:limit], int(all_count)
            if last_page or not page_items:
                break
            begin += len(page_items)
            if page_delay_seconds > 0:
                time.sleep(page_delay_seconds)
        return results, int(all_count)


def metrics_from_futu_snapshot(record: dict) -> CandidateMetrics:
    code = str(record.get("code", ""))
    ticker = code.split(".", 1)[1] if "." in code else code
    return CandidateMetrics(
        ticker=ticker.upper(),
        name=str(record.get("name") or ""),
        market_cap=_to_float(record.get("total_market_val")),
        trailing_pe=_to_float(record.get("pe_ttm_ratio")) or _to_float(record.get("pe_ratio")),
        price=_to_float(record.get("last_price")),
        source="futu_opend",
    )


def information_from_futu_snapshot(record: dict) -> list[dict]:
    code = str(record.get("code", ""))
    ticker = code.split(".", 1)[1] if "." in code else code
    update_time = record.get("update_time")
    name = str(record.get("name") or ticker)
    market_cap = _to_float(record.get("total_market_val"))
    pe_ttm = _to_float(record.get("pe_ttm_ratio")) or _to_float(record.get("pe_ratio"))
    pb = _to_float(record.get("pb_ratio"))
    price = _to_float(record.get("last_price"))
    volume = _to_float(record.get("volume"))
    turnover = _to_float(record.get("turnover"))
    high_52w = _to_float(record.get("highest52weeks_price"))
    low_52w = _to_float(record.get("lowest52weeks_price"))

    return [
        {
            "ticker": ticker.upper(),
            "dimension": "valuation",
            "event_date": update_time,
            "title": f"{name} valuation snapshot",
            "summary": _valuation_summary(market_cap, pe_ttm, pb, price),
            "importance_score": 70,
            "quality_score": 82,
            "confidence_score": 86,
            "evidence": {
                "market_cap": market_cap,
                "pe_ttm": pe_ttm,
                "pb": pb,
                "price": price,
            },
        },
        {
            "ticker": ticker.upper(),
            "dimension": "market",
            "event_date": update_time,
            "title": f"{name} market activity",
            "summary": _market_summary(volume, turnover, high_52w, low_52w),
            "importance_score": 45,
            "quality_score": 78,
            "confidence_score": 84,
            "evidence": {
                "volume": volume,
                "turnover": turnover,
                "highest52weeks_price": high_52w,
                "lowest52weeks_price": low_52w,
            },
        },
    ]


def classification_from_futu_plates(ticker: str, plates: list[dict]) -> dict:
    industry_plate = _first_plate(plates, "INDUSTRY")
    concept_plates = _plates_by_type(plates, "CONCEPT")
    region_plates = _plates_by_type(plates, "REGION")
    primary_plate = industry_plate or (concept_plates[0] if concept_plates else None) or (plates[0] if plates else None)
    industry = str(industry_plate.get("plate_name") or "").strip() if industry_plate else ""
    sector = industry or (str(primary_plate.get("plate_name") or "").strip() if primary_plate else "")
    concepts = [str(item.get("plate_name") or "").strip() for item in concept_plates if item.get("plate_name")]
    regions = [str(item.get("plate_name") or "").strip() for item in region_plates if item.get("plate_name")]
    return {
        "ticker": ticker.upper(),
        "sector": sector,
        "industry": industry,
        "primary_plate": primary_plate or {},
        "concepts": concepts,
        "regions": regions,
        "plates": plates,
    }


def information_from_futu_plates(classification: dict) -> dict:
    ticker = classification["ticker"]
    sector = classification.get("sector") or "Unclassified"
    industry = classification.get("industry") or ""
    concepts = classification.get("concepts") or []
    summary = f"Futu OpenD 将 {ticker} 归入 {sector} 板块。"
    if industry and industry != sector:
        summary += f" 行业为 {industry}。"
    if concepts:
        summary += f" 同时命中概念板块：{', '.join(concepts[:4])}。"
    return {
        "ticker": ticker,
        "dimension": "sector",
        "event_date": None,
        "title": f"{ticker} sector classification",
        "summary": summary,
        "importance_score": 36,
        "quality_score": 82,
        "confidence_score": 84,
        "evidence": {
            "sector": classification.get("sector"),
            "industry": classification.get("industry"),
            "primary_plate": classification.get("primary_plate"),
            "concepts": concepts,
            "regions": classification.get("regions") or [],
            "plates": classification.get("plates") or [],
        },
    }


def information_from_futu_attention(raw: dict) -> dict | None:
    metrics = attention_metrics(raw)
    ticker = str(raw.get("ticker") or "").upper()
    if not ticker or not metrics:
        return None
    update_time = metrics.get("distribution_update_time") or metrics.get("latest_kline_date")
    label = metrics.get("attention_flow_label") or "neutral"
    return {
        "ticker": ticker,
        "dimension": "attention_flow",
        "event_date": update_time,
        "title": f"{ticker} main-money attention and pullback risk",
        "summary": _attention_summary(metrics),
        "importance_score": _attention_importance(label),
        "quality_score": 72,
        "sentiment_score": _attention_sentiment(label),
        "confidence_score": 62 if metrics.get("large_buy_sell_ratio") is not None else 48,
        "evidence": metrics,
    }


def attention_metrics(raw: dict) -> dict:
    distribution = raw.get("capital_distribution") or {}
    flow_rows = raw.get("capital_flow") or []
    kline_rows = raw.get("kline") or []

    capital_in_super = _to_float(distribution.get("capital_in_super"))
    capital_in_big = _to_float(distribution.get("capital_in_big"))
    capital_out_super = _to_float(distribution.get("capital_out_super"))
    capital_out_big = _to_float(distribution.get("capital_out_big"))
    large_in = _sum_present(capital_in_super, capital_in_big)
    large_out = _sum_present(capital_out_super, capital_out_big)
    large_ratio = _safe_ratio(large_in, large_out)
    super_ratio = _safe_ratio(capital_in_super, capital_out_super)
    large_net = None
    large_net_ratio = None
    if large_in is not None and large_out is not None:
        large_net = large_in - large_out
        denominator = abs(large_in) + abs(large_out)
        large_net_ratio = large_net / denominator if denominator else None

    flow_tail = flow_rows[-20:]
    super_net_20d = _sum_flow(flow_tail, "super_in_flow")
    big_net_20d = _sum_flow(flow_tail, "big_in_flow")
    main_net_20d = _sum_flow(flow_tail, "main_in_flow")
    large_net_flow_20d = None
    if super_net_20d is not None or big_net_20d is not None:
        large_net_flow_20d = (super_net_20d or 0) + (big_net_20d or 0)

    latest_close = _last_close(kline_rows)
    return_5d = _period_return(kline_rows, 5)
    return_20d = _period_return(kline_rows, 20)
    return_60d = _period_return(kline_rows, 60)
    range_position_60d = _range_position(kline_rows, 60)
    label = _attention_label(large_ratio, large_net_flow_20d, return_20d)

    metrics = {
        "capital_in_super": capital_in_super,
        "capital_out_super": capital_out_super,
        "capital_in_big": capital_in_big,
        "capital_out_big": capital_out_big,
        "large_buy_sell_ratio": large_ratio,
        "super_buy_sell_ratio": super_ratio,
        "large_net_amount": large_net,
        "large_net_ratio": large_net_ratio,
        "large_net_flow_20d": large_net_flow_20d,
        "super_net_flow_20d": super_net_20d,
        "big_net_flow_20d": big_net_20d,
        "main_net_flow_20d": main_net_20d,
        "capital_flow_days": len(flow_tail),
        "return_5d": return_5d,
        "return_20d": return_20d,
        "return_60d": return_60d,
        "price_range_position_60d": range_position_60d,
        "latest_close": latest_close,
        "distribution_update_time": distribution.get("update_time"),
        "latest_kline_date": _latest_kline_date(kline_rows),
        "attention_flow_label": label,
        "kline_error": raw.get("kline_error"),
    }
    return {key: value for key, value in metrics.items() if value is not None}


def _valuation_summary(market_cap, pe_ttm, pb, price) -> str:
    parts = []
    if market_cap is not None:
        parts.append(f"市值约 {_money(market_cap)}")
    if pe_ttm is not None:
        parts.append(f"TTM P/E {pe_ttm:.1f}")
    if pb is not None:
        parts.append(f"P/B {pb:.1f}")
    if price is not None:
        parts.append(f"最新价 {price:.2f}")
    return "，".join(parts) if parts else "Futu OpenD 返回估值快照，但关键字段缺失。"


def _market_summary(volume, turnover, high_52w, low_52w) -> str:
    parts = []
    if volume is not None:
        parts.append(f"成交量 {volume:,.0f}")
    if turnover is not None:
        parts.append(f"成交额 {_money(turnover)}")
    if high_52w is not None and low_52w is not None:
        parts.append(f"52周区间 {low_52w:.2f}-{high_52w:.2f}")
    return "，".join(parts) if parts else "Futu OpenD 返回行情活跃度快照，但关键字段缺失。"


def _attention_summary(metrics: dict) -> str:
    parts = []
    ratio = metrics.get("large_buy_sell_ratio")
    super_ratio = metrics.get("super_buy_sell_ratio")
    return_20d = metrics.get("return_20d")
    return_5d = metrics.get("return_5d")
    large_net_flow = metrics.get("large_net_flow_20d")
    label = metrics.get("attention_flow_label")
    if ratio is not None:
        parts.append(f"特大+大单买入/卖出比约 {ratio:.2f}")
    if super_ratio is not None:
        parts.append(f"特大单买入/卖出比约 {super_ratio:.2f}")
    if large_net_flow is not None:
        parts.append(f"近20日特大+大单净流入 {_money(large_net_flow)}")
    if return_20d is not None:
        parts.append(f"近20日涨幅 {_pct(return_20d)}")
    if return_5d is not None:
        parts.append(f"近5日涨幅 {_pct(return_5d)}")
    if metrics.get("kline_error"):
        parts.append("近期涨幅因 Futu 历史 K 线额度不足暂缺")
    if label == "quiet_accumulation":
        parts.append("组合更接近“主力吸筹但价格未明显扩散”的低关注度信号")
    elif label == "crowded_momentum":
        parts.append("主力买入和短期涨幅同时偏高，需要警惕拥挤交易与回撤")
    elif label == "distribution_risk":
        parts.append("短期涨幅较高但主力买卖比不足，偏分歧或派发风险")
    else:
        parts.append("暂未形成明确的低关注度吸筹信号")
    return "，".join(parts) + "。"


def _attention_importance(label: str) -> int:
    if label == "quiet_accumulation":
        return 72
    if label == "crowded_momentum":
        return 66
    if label == "distribution_risk":
        return 62
    return 48


def _attention_sentiment(label: str) -> int:
    if label == "quiet_accumulation":
        return 18
    if label == "crowded_momentum":
        return -16
    if label == "distribution_risk":
        return -12
    return 0


def _attention_label(large_ratio: float | None, large_net_flow_20d: float | None, return_20d: float | None) -> str:
    if large_ratio is not None:
        has_buy_pressure = large_ratio >= 1.2
    else:
        has_buy_pressure = large_net_flow_20d is not None and large_net_flow_20d > 0
    if has_buy_pressure and return_20d is not None and return_20d <= 0.12:
        return "quiet_accumulation"
    if has_buy_pressure and return_20d is not None and return_20d >= 0.30:
        return "crowded_momentum"
    if large_ratio is not None and large_ratio < 0.9 and return_20d is not None and return_20d >= 0.20:
        return "distribution_risk"
    return "neutral"


def _is_history_quota_message(message: str) -> bool:
    clean = message.lower()
    return "historical candlestick quota" in clean or "quota is released" in clean


def _price_trend_from_kline_rows(code: str, rows: list[dict], *, max_points: int) -> dict:
    points = []
    for row in rows:
        close = _to_float(row.get("close"))
        timestamp = pd.to_datetime(row.get("time_key") or row.get("date"), errors="coerce")
        if close is None or pd.isna(timestamp):
            continue
        points.append({"date": timestamp.date().isoformat(), "close": close})
    points.sort(key=lambda point: point["date"])
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
        "ticker": _ticker_from_code(code),
        "code": code,
        "source": "futu_opend",
        "source_label": "Futu weekly close",
        "period": "max",
        "interval": "week",
        "points": points,
        "point_count": len(points),
        "first_date": first["date"] if first else None,
        "latest_date": latest["date"] if latest else None,
        "first_close": first_close,
        "latest_close": latest_close,
        "min_close": min(closes) if closes else None,
        "max_close": max(closes) if closes else None,
        "total_return": total_return,
        "error": None if len(points) >= 2 else "No Futu weekly close history found.",
    }


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


def _ticker_from_code(code) -> str:
    value = str(code or "").strip().upper()
    if "." in value:
        value = value.split(".", 1)[1]
    return value


def _first_plate(plates: list[dict], plate_type: str) -> dict | None:
    matches = _plates_by_type(plates, plate_type)
    return matches[0] if matches else None


def _plates_by_type(plates: list[dict], plate_type: str) -> list[dict]:
    target = plate_type.upper()
    return [plate for plate in plates if str(plate.get("plate_type") or "").upper() == target]


def _clean_record(record: dict) -> dict:
    cleaned = {}
    for key, value in record.items():
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            cleaned[key] = None
        elif isinstance(value, pd.Timestamp):
            cleaned[key] = value.isoformat()
        else:
            cleaned[key] = value
    return cleaned


def _to_float(value):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _is_rate_limit_message(message: str) -> bool:
    lowered = message.lower()
    return "high frequency" in lowered or "maximum" in lowered and "30 seconds" in lowered


def _sum_present(*values: float | None) -> float | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return sum(present)


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def _sum_flow(rows: list[dict], key: str) -> float | None:
    values = [_to_float(row.get(key)) for row in rows]
    values = [value for value in values if value is not None]
    if not values:
        return None
    return sum(values)


def _last_close(rows: list[dict]) -> float | None:
    if not rows:
        return None
    return _to_float(rows[-1].get("close"))


def _period_return(rows: list[dict], periods: int) -> float | None:
    if len(rows) <= periods:
        return None
    latest = _to_float(rows[-1].get("close"))
    prior = _to_float(rows[-periods - 1].get("close"))
    if latest is None or prior is None or prior <= 0:
        return None
    return latest / prior - 1


def _range_position(rows: list[dict], periods: int) -> float | None:
    tail = rows[-periods:]
    if not tail:
        return None
    closes = [_to_float(row.get("close")) for row in tail]
    closes = [value for value in closes if value is not None]
    if not closes:
        return None
    high = max(closes)
    low = min(closes)
    latest = closes[-1]
    if high <= low:
        return None
    return (latest - low) / (high - low)


def _latest_kline_date(rows: list[dict]) -> str | None:
    if not rows:
        return None
    value = rows[-1].get("time_key")
    return str(value)[:10] if value else None


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _money(value: float) -> str:
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    return f"${value:,.0f}"


def _filter_stock_record(item, *, basicinfo: dict | None = None) -> dict:
    code = str(getattr(item, "stock_code", "") or "")
    ticker = code.split(".", 1)[1] if "." in code else code
    return {
        "ticker": ticker.upper(),
        "code": code,
        "name": str(getattr(item, "stock_name", "") or ""),
        "market_cap": _to_float(getattr(item, "market_val", None)),
        "pe_ttm": _to_float(getattr(item, "pe_ttm", None)),
        "pb": _to_float(getattr(item, "pb_rate", None)),
        "exchange_type": (basicinfo or {}).get("exchange_type", ""),
        "listing_date": (basicinfo or {}).get("listing_date", ""),
    }


def _is_common_us_stock(record: dict) -> bool:
    ticker = str(record.get("ticker") or "")
    if not ticker:
        return False
    if any(char in ticker for char in (".", "-", "$", "/")):
        return False
    if len(ticker) > 5:
        return False
    exchange_type = str(record.get("exchange_type") or "").upper()
    if exchange_type and exchange_type not in {"US_NASDAQ", "US_NYSE", "US_AMEX"}:
        return False
    name = str(record.get("name") or "").upper()
    excluded_name_terms = (
        " ADR ",
        " ADS ",
        "PREFERRED",
        " PREF ",
        " PFD ",
        "NOTE",
        "NOTES",
        "DEBENTURE",
        "BOND",
        "WARRANT",
        "RIGHT",
        "UNIT",
        "ACQUISITION",
        "SPAC",
    )
    padded_name = f" {name} "
    if any(term in padded_name for term in excluded_name_terms):
        return False
    return True
