from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class RadarTarget:
    key: str
    label: str
    symbol: str
    role: str
    volatility_symbol: str | None = None


OPENING_RADAR_TARGETS = [
    RadarTarget(
        key="nasdaq",
        label="Nasdaq 100",
        symbol="QQQ",
        role="index_proxy",
        volatility_symbol="^VXN",
    ),
    RadarTarget(
        key="space",
        label="Space",
        symbol="NASA",
        role="sector_etf",
    ),
]


def opening_radar_snapshot(*, period: str = "9mo", history_fetcher=None) -> dict[str, Any]:
    snapshots = [technical_snapshot(target, period=period, history_fetcher=history_fetcher) for target in OPENING_RADAR_TARGETS]
    return {
        "as_of": datetime.now().isoformat(timespec="seconds"),
        "menu_name": "Opening Radar",
        "primary": snapshots[0],
        "sectors": snapshots[1:],
        "method": {
            "goal": "Use daily technical evidence to classify market regime, avoid chasing exhaustion, and prepare a directional plan before the US open.",
            "signals": [
                "Trend and regime: 20/50/200 day moving averages, Bollinger bandwidth, and ADX.",
                "Momentum: MACD histogram and slope, RSI, and KDJ.",
                "Risk: ATR percentage, gap from 20 day average, and volatility proxy.",
            ],
        },
    }


def technical_snapshot(target: RadarTarget, *, period: str = "9mo", history_fetcher=None) -> dict[str, Any]:
    try:
        frame = _history(target.symbol, period=period, history_fetcher=history_fetcher)
    except Exception as exc:
        return _error_snapshot(target, f"Daily history unavailable for {target.symbol}: {_short_error(exc)}")
    if frame.empty:
        return _error_snapshot(target, f"No daily history for {target.symbol}.")
    latest = _latest_indicators(frame)
    volatility = _volatility_snapshot(target.volatility_symbol, frame) if target.volatility_symbol else None
    facts = _facts(target, latest, volatility)
    regime = _classify_regime(latest)
    directional_bias = _directional_bias(latest, regime)
    return {
        "key": target.key,
        "label": target.label,
        "symbol": target.symbol,
        "role": target.role,
        "source": frame.attrs.get("source") or "yfinance",
        "latest_date": latest.get("date"),
        "latest_close": latest.get("close"),
        "regime": regime,
        "directional_bias": directional_bias,
        "facts": facts,
        "indicators": latest,
        "volatility": volatility,
    }


def ai_prompt(snapshot: dict[str, Any]) -> str:
    return f"""
你是美股开盘前半小时的技术面交易顾问。目标不是预测神谕，而是基于日线事实给出今天开盘前的操作预案：判断当前更像震荡市、单边上行、单边下行，评估今天追涨/抄底/观望/减仓的风险。

只使用输入事实，不编造外部新闻。先给结论，再给触发条件。请输出 JSON：
{{
  "market_call": "Range / Uptrend / Downtrend / Inflection 中的一种，并说明一句理由",
  "today_plan": ["3-5条中文操作建议，偏可执行，比如仓位、开盘前30分钟观察点、突破/跌破条件"],
  "risk_controls": ["2-4条风控条件"],
  "watch_levels": ["关键价位或指标阈值"],
  "confidence_score": 0-100
}}

事实快照：
{snapshot}
""".strip()


def _history(symbol: str, *, period: str, history_fetcher=None) -> pd.DataFrame:
    import yfinance as yf

    try:
        frame = yf.Ticker(symbol).history(period=period, interval="1d", auto_adjust=True)
        frame.attrs["source"] = "yfinance"
    except Exception:
        if history_fetcher is None:
            raise
        frame = _frame_from_rows(history_fetcher(symbol))
        frame.attrs["source"] = "futu_opend"
    if frame is None or frame.empty:
        return pd.DataFrame()
    frame = frame.rename(columns={column: str(column).title() for column in frame.columns})
    needed = [column for column in ["Open", "High", "Low", "Close", "Volume"] if column in frame.columns]
    frame = frame[needed].dropna(subset=["Close"])
    return frame


def _frame_from_rows(rows: list[dict[str, Any]]) -> pd.DataFrame:
    normalized = []
    for row in rows or []:
        raw_date = row.get("time_key") or row.get("date") or row.get("time")
        parsed_date = pd.to_datetime(raw_date, errors="coerce")
        if pd.isna(parsed_date):
            continue
        normalized.append(
            {
                "Date": parsed_date,
                "Open": row.get("open"),
                "High": row.get("high"),
                "Low": row.get("low"),
                "Close": row.get("close"),
                "Volume": row.get("volume"),
            }
        )
    if not normalized:
        return pd.DataFrame()
    frame = pd.DataFrame(normalized).set_index("Date").sort_index()
    for column in ["Open", "High", "Low", "Close", "Volume"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def _latest_indicators(frame: pd.DataFrame) -> dict[str, Any]:
    data = frame.copy()
    close = data["Close"]
    high = data["High"] if "High" in data else close
    low = data["Low"] if "Low" in data else close

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    macd_hist = macd - signal

    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rsi = 100 - (100 / (1 + gain / loss.replace(0, math.nan)))

    low9 = low.rolling(9).min()
    high9 = high.rolling(9).max()
    rsv = (close - low9) / (high9 - low9).replace(0, math.nan) * 100
    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()
    j = 3 * k - 2 * d

    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()
    ma200 = close.rolling(200).mean()
    std20 = close.rolling(20).std()
    upper = ma20 + 2 * std20
    lower = ma20 - 2 * std20
    bandwidth = (upper - lower) / ma20.replace(0, math.nan)

    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()

    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0)
    plus_di = 100 * plus_dm.ewm(alpha=1 / 14, adjust=False).mean() / tr.ewm(alpha=1 / 14, adjust=False).mean()
    minus_di = 100 * minus_dm.ewm(alpha=1 / 14, adjust=False).mean() / tr.ewm(alpha=1 / 14, adjust=False).mean()
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, math.nan)) * 100
    adx = dx.ewm(alpha=1 / 14, adjust=False).mean()

    returns = close.pct_change()
    realized_vol = returns.rolling(20).std() * math.sqrt(252) * 100
    latest_pos = len(data) - 1
    prev_pos = max(0, latest_pos - 1)
    latest_date = pd.to_datetime(data.index[latest_pos], errors="coerce")
    latest_close = _clean_number(close.iloc[latest_pos])
    latest_ma20 = _clean_number(ma20.iloc[latest_pos])
    return {
        "date": latest_date.date().isoformat() if not pd.isna(latest_date) else "",
        "close": latest_close,
        "return_1d": _clean_number(close.pct_change().iloc[latest_pos] * 100),
        "return_5d": _clean_number((close.iloc[latest_pos] / close.iloc[max(0, latest_pos - 5)] - 1) * 100),
        "return_20d": _clean_number((close.iloc[latest_pos] / close.iloc[max(0, latest_pos - 20)] - 1) * 100),
        "ma20": latest_ma20,
        "ma50": _clean_number(ma50.iloc[latest_pos]),
        "ma200": _clean_number(ma200.iloc[latest_pos]),
        "distance_ma20_pct": _clean_number((latest_close / latest_ma20 - 1) * 100 if latest_close and latest_ma20 else None),
        "macd": _clean_number(macd.iloc[latest_pos]),
        "macd_signal": _clean_number(signal.iloc[latest_pos]),
        "macd_hist": _clean_number(macd_hist.iloc[latest_pos]),
        "macd_hist_prev": _clean_number(macd_hist.iloc[prev_pos]),
        "rsi14": _clean_number(rsi.iloc[latest_pos]),
        "kdj_k": _clean_number(k.iloc[latest_pos]),
        "kdj_d": _clean_number(d.iloc[latest_pos]),
        "kdj_j": _clean_number(j.iloc[latest_pos]),
        "bollinger_bandwidth_pct": _clean_number(bandwidth.iloc[latest_pos] * 100),
        "atr14_pct": _clean_number(atr.iloc[latest_pos] / close.iloc[latest_pos] * 100),
        "adx14": _clean_number(adx.iloc[latest_pos]),
        "plus_di14": _clean_number(plus_di.iloc[latest_pos]),
        "minus_di14": _clean_number(minus_di.iloc[latest_pos]),
        "realized_vol_20d": _clean_number(realized_vol.iloc[latest_pos]),
    }


def _volatility_snapshot(symbol: str | None, frame: pd.DataFrame) -> dict[str, Any] | None:
    if not symbol:
        return None
    try:
        vol = _history(symbol, period="3mo")
    except Exception as exc:
        return {"symbol": symbol, "label": "volatility proxy", "error": _short_error(exc)}
    if vol.empty:
        return {"symbol": symbol, "label": "volatility proxy", "error": "No volatility proxy history."}
    close = vol["Close"].dropna()
    if close.empty:
        return {"symbol": symbol, "label": "volatility proxy", "error": "No volatility proxy close."}
    latest = _clean_number(close.iloc[-1])
    average = _clean_number(close.tail(20).mean())
    return {
        "symbol": symbol,
        "label": "VXN proxy for Nasdaq implied volatility",
        "latest": latest,
        "average_20d": average,
        "distance_20d_pct": _clean_number((latest / average - 1) * 100 if latest and average else None),
    }


def _facts(target: RadarTarget, latest: dict[str, Any], volatility: dict[str, Any] | None) -> list[str]:
    facts = [
        f"{target.label} uses {target.symbol} daily candles; latest close {latest.get('close')} on {latest.get('date')}.",
        f"Trend stack: close vs MA20 {latest.get('distance_ma20_pct')}%, MA20 {latest.get('ma20')}, MA50 {latest.get('ma50')}, MA200 {latest.get('ma200')}.",
        f"MACD histogram {latest.get('macd_hist')} vs prior {latest.get('macd_hist_prev')}; RSI14 {latest.get('rsi14')}.",
        f"KDJ K/D/J {latest.get('kdj_k')}/{latest.get('kdj_d')}/{latest.get('kdj_j')}.",
        f"ADX14 {latest.get('adx14')} with +DI {latest.get('plus_di14')} and -DI {latest.get('minus_di14')}; Bollinger bandwidth {latest.get('bollinger_bandwidth_pct')}%.",
        f"ATR14 {latest.get('atr14_pct')}% and 20D realized volatility {latest.get('realized_vol_20d')}%.",
    ]
    if volatility:
        if volatility.get("error"):
            facts.append(f"Volatility proxy {volatility.get('symbol')} unavailable: {volatility.get('error')}")
        else:
            facts.append(
                f"Volatility proxy {volatility.get('symbol')} latest {volatility.get('latest')}, {volatility.get('distance_20d_pct')}% vs 20D average."
            )
    return facts


def _classify_regime(latest: dict[str, Any]) -> str:
    close = latest.get("close")
    ma20 = latest.get("ma20")
    ma50 = latest.get("ma50")
    ma200 = latest.get("ma200")
    adx = latest.get("adx14") or 0
    plus_di = latest.get("plus_di14") or 0
    minus_di = latest.get("minus_di14") or 0
    bandwidth = latest.get("bollinger_bandwidth_pct") or 0
    if close and ma20 and ma50 and ma200 and close > ma20 > ma50 > ma200 and adx >= 20 and plus_di > minus_di:
        return "Uptrend"
    if close and ma20 and ma50 and close < ma20 < ma50 and adx >= 20 and minus_di > plus_di:
        return "Downtrend"
    if adx < 18 or bandwidth < 8:
        return "Range"
    return "Inflection"


def _directional_bias(latest: dict[str, Any], regime: str) -> str:
    macd_hist = latest.get("macd_hist") or 0
    macd_prev = latest.get("macd_hist_prev") or 0
    rsi = latest.get("rsi14") or 50
    k = latest.get("kdj_k") or 50
    d = latest.get("kdj_d") or 50
    if regime == "Uptrend" and macd_hist >= macd_prev and rsi < 75:
        return "Bullish, avoid chasing hot gaps"
    if regime == "Downtrend" and macd_hist <= macd_prev:
        return "Bearish, treat rebounds as repairs first"
    if regime == "Range":
        if rsi > 65 or k > 80:
            return "Range high, poor chase setup"
        if rsi < 40 or k < 25:
            return "Range low, wait for stabilization"
        return "Neutral range, wait for open-range break"
    if macd_hist > macd_prev and k > d:
        return "Turning stronger, price confirmation needed"
    return "Turning weaker, control exposure first"


def _error_snapshot(target: RadarTarget, error: str) -> dict[str, Any]:
    return {
        "key": target.key,
        "label": target.label,
        "symbol": target.symbol,
        "role": target.role,
        "facts": [],
        "indicators": {},
        "regime": "Unknown",
        "directional_bias": "Insufficient data",
        "error": error,
    }


def _clean_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return round(number, 4)


def _short_error(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    if "Too Many Requests" in message or "Rate limited" in message:
        return "Rate limited"
    return message[:120]
