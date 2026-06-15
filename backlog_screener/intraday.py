from __future__ import annotations

import math
from statistics import mean
from typing import Any


def intraday_payload(
    *,
    ticker: str,
    rows: list[dict[str, Any]],
    code: str | None = None,
    tracking: bool = False,
    active_since: str | None = None,
    source: str = "futu_opend",
    source_label: str = "Futu 1m K-line",
    error: str | None = None,
) -> dict[str, Any]:
    points = normalize_intraday_rows(rows)
    indicators = intraday_indicators(points)
    latest = points[-1] if points else None
    return {
        "ticker": ticker.upper(),
        "code": code,
        "tracking": tracking,
        "active_since": active_since,
        "source": source,
        "source_label": source_label,
        "interval": "1m",
        "as_of": latest.get("time") if latest else None,
        "points": points,
        "point_count": len(points),
        "indicators": indicators,
        "error": error,
    }


def normalize_intraday_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    points = []
    for row in rows:
        close = _to_float(row.get("close"))
        if close is None:
            continue
        high = _to_float(row.get("high"))
        low = _to_float(row.get("low"))
        point = {
            "time": _time_key(row),
            "open": _to_float(row.get("open")) or close,
            "high": high if high is not None else close,
            "low": low if low is not None else close,
            "close": close,
            "volume": _to_float(row.get("volume")),
            "turnover": _to_float(row.get("turnover")),
        }
        points.append(point)
    points.sort(key=lambda item: item.get("time") or "")
    _attach_vwap(points)
    return points


def intraday_indicators(points: list[dict[str, Any]]) -> dict[str, Any]:
    closes = [_to_float(point.get("close")) for point in points]
    closes = [value for value in closes if value is not None]
    volumes = [_to_float(point.get("volume")) for point in points]
    latest_close = closes[-1] if closes else None
    latest_vwap = _to_float(points[-1].get("vwap")) if points else None
    rsi14 = _rsi(closes, 14)
    kdj = _kdj(points, period=9)
    volume = _volume_profile(volumes)
    ema = _ema_profile(closes)
    atr = _atr_profile(points, period=14)
    opening_range = _opening_range(points, minutes=15)
    signal = _signal(
        latest_close=latest_close,
        vwap=latest_vwap,
        rsi14=rsi14,
        kdj=kdj,
        volume=volume,
        ema=ema,
        atr=atr,
        opening_range=opening_range,
        points=points,
    )
    return {
        "price": latest_close,
        "return_1m": _period_return(closes, 1),
        "return_5m": _period_return(closes, 5),
        "return_15m": _period_return(closes, 15),
        "vwap": latest_vwap,
        "vwap_deviation": _safe_pct_diff(latest_close, latest_vwap),
        "ema": ema,
        "rsi14": rsi14,
        "kdj": kdj,
        "volume": volume,
        "atr": atr,
        "opening_range": opening_range,
        "signal": signal,
        "indicator_guide": _indicator_guide(),
    }


def _rsi(closes: list[float], period: int) -> float | None:
    if len(closes) <= period:
        return None
    deltas = [closes[index] - closes[index - 1] for index in range(1, len(closes))]
    tail = deltas[-period:]
    gains = [max(delta, 0.0) for delta in tail]
    losses = [abs(min(delta, 0.0)) for delta in tail]
    avg_gain = mean(gains)
    avg_loss = mean(losses)
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def _kdj(points: list[dict[str, Any]], *, period: int) -> dict[str, float | None]:
    if len(points) < period:
        return {"k": None, "d": None, "j": None}
    k = 50.0
    d = 50.0
    for index in range(period - 1, len(points)):
        window = points[index - period + 1 : index + 1]
        highs = [_to_float(point.get("high")) for point in window]
        lows = [_to_float(point.get("low")) for point in window]
        highs = [value for value in highs if value is not None]
        lows = [value for value in lows if value is not None]
        close = _to_float(points[index].get("close"))
        if not highs or not lows or close is None:
            continue
        high = max(highs)
        low = min(lows)
        rsv = 50.0 if high <= low else ((close - low) / (high - low)) * 100
        k = (2 / 3) * k + (1 / 3) * rsv
        d = (2 / 3) * d + (1 / 3) * k
    j = 3 * k - 2 * d
    return {"k": round(k, 2), "d": round(d, 2), "j": round(j, 2)}


def _volume_profile(volumes: list[float | None]) -> dict[str, float | str | None]:
    latest = _last_present(volumes)
    previous = [value for value in volumes[-21:-1] if value is not None and value >= 0]
    avg20 = mean(previous) if previous else None
    ratio = latest / avg20 if latest is not None and avg20 and avg20 > 0 else None
    stdev20 = _stdev(previous)
    zscore = (latest - avg20) / stdev20 if latest is not None and avg20 is not None and stdev20 else None
    if ratio is None:
        state = "unknown"
    elif ratio >= 2.0:
        state = "spike"
    elif ratio <= 0.5:
        state = "dry"
    else:
        state = "normal"
    return {
        "latest": latest,
        "avg20": round(avg20, 2) if avg20 is not None else None,
        "ratio": round(ratio, 2) if ratio is not None else None,
        "zscore": round(zscore, 2) if zscore is not None else None,
        "state": state,
    }


def _signal(
    *,
    latest_close: float | None,
    vwap: float | None,
    rsi14: float | None,
    kdj: dict[str, float | None],
    volume: dict[str, Any],
    ema: dict[str, Any],
    atr: dict[str, Any],
    opening_range: dict[str, Any],
    points: list[dict[str, Any]],
) -> dict[str, Any]:
    tags = []
    k = _to_float(kdj.get("k"))
    d = _to_float(kdj.get("d"))
    j = _to_float(kdj.get("j"))
    volume_state = str(volume.get("state") or "unknown")
    rules = _rule_checks(
        latest_close=latest_close,
        vwap=vwap,
        rsi14=rsi14,
        kdj=kdj,
        volume=volume,
        ema=ema,
        atr=atr,
        opening_range=opening_range,
        points=points,
    )

    overbought = (rsi14 is not None and rsi14 >= 70) or (
        k is not None and d is not None and j is not None and k >= 80 and d >= 75 and j >= 90
    )
    oversold = (rsi14 is not None and rsi14 <= 30) or (
        k is not None and d is not None and j is not None and k <= 20 and d <= 25 and j <= 10
    )
    if overbought:
        tags.append("overbought")
    if oversold:
        tags.append("oversold")
    if volume_state == "spike":
        tags.append("volume_spike")
    elif volume_state == "dry":
        tags.append("low_volume")

    if overbought and volume_state == "spike":
        label = "overbought_volume"
    elif oversold and volume_state == "spike":
        label = "oversold_reversal_watch"
    elif overbought:
        label = "overbought"
    elif oversold:
        label = "oversold"
    elif volume_state == "spike":
        label = "volume_spike"
    else:
        label = "neutral"
    bias_score = sum(int(rule.get("score", 0) or 0) for rule in rules)
    if bias_score >= 4:
        bias = "strong_long_bias"
    elif bias_score >= 2:
        bias = "long_bias"
    elif bias_score <= -4:
        bias = "strong_short_bias"
    elif bias_score <= -2:
        bias = "short_bias"
    else:
        bias = "neutral"
    return {
        "label": label,
        "bias": bias,
        "bias_score": bias_score,
        "summary": _bias_summary(bias, rules),
        "tags": tags,
        "rules": rules,
    }


def _attach_vwap(points: list[dict[str, Any]]) -> None:
    current_day = None
    cumulative_volume = 0.0
    cumulative_value = 0.0
    for point in points:
        day = _session_day(point)
        if day != current_day:
            current_day = day
            cumulative_volume = 0.0
            cumulative_value = 0.0
        volume = _to_float(point.get("volume"))
        if volume is None or volume <= 0:
            point["vwap"] = cumulative_value / cumulative_volume if cumulative_volume > 0 else None
            continue
        turnover = _to_float(point.get("turnover"))
        typical_price = _typical_price(point)
        value = turnover if turnover is not None and turnover > 0 else typical_price * volume
        cumulative_volume += volume
        cumulative_value += value
        point["vwap"] = round(cumulative_value / cumulative_volume, 6) if cumulative_volume > 0 else None
        point["cum_volume"] = cumulative_volume


def _ema_profile(closes: list[float]) -> dict[str, float | str | None]:
    ema9_values = _ema_series(closes, 9)
    ema21_values = _ema_series(closes, 21)
    ema9 = ema9_values[-1] if ema9_values else None
    ema21 = ema21_values[-1] if ema21_values else None
    slope9 = _series_return(ema9_values, 5)
    slope21 = _series_return(ema21_values, 5)
    spread = _safe_pct_diff(ema9, ema21)
    if ema9 is None or ema21 is None:
        state = "unknown"
    elif ema9 > ema21 and (slope9 or 0) > 0:
        state = "bullish"
    elif ema9 < ema21 and (slope9 or 0) < 0:
        state = "bearish"
    else:
        state = "mixed"
    return {
        "ema9": round(ema9, 6) if ema9 is not None else None,
        "ema21": round(ema21, 6) if ema21 is not None else None,
        "spread": spread,
        "slope9_5m": slope9,
        "slope21_5m": slope21,
        "state": state,
    }


def _atr_profile(points: list[dict[str, Any]], *, period: int) -> dict[str, float | str | None]:
    if len(points) < 2:
        return {"atr": None, "atr_pct": None, "state": "unknown"}
    ranges = []
    start = max(0, len(points) - period)
    for index in range(start, len(points)):
        point = points[index]
        high = _to_float(point.get("high"))
        low = _to_float(point.get("low"))
        prev_close = _to_float(points[index - 1].get("close")) if index > 0 else None
        if high is None or low is None:
            continue
        candidates = [high - low]
        if prev_close is not None:
            candidates.extend([abs(high - prev_close), abs(low - prev_close)])
        ranges.append(max(candidates))
    atr_value = mean(ranges) if ranges else None
    latest_close = _to_float(points[-1].get("close")) if points else None
    atr_pct = atr_value / latest_close if atr_value is not None and latest_close else None
    if atr_pct is None:
        state = "unknown"
    elif atr_pct < 0.001:
        state = "compressed"
    elif atr_pct > 0.006:
        state = "wide"
    else:
        state = "tradable"
    return {
        "atr": round(atr_value, 6) if atr_value is not None else None,
        "atr_pct": round(atr_pct, 6) if atr_pct is not None else None,
        "state": state,
    }


def _opening_range(points: list[dict[str, Any]], *, minutes: int) -> dict[str, Any]:
    day_points = _latest_day_points(points)
    if len(day_points) < max(2, minutes):
        return {"minutes": minutes, "high": None, "low": None, "state": "forming"}
    opening = day_points[:minutes]
    highs = [_to_float(point.get("high")) for point in opening]
    lows = [_to_float(point.get("low")) for point in opening]
    highs = [value for value in highs if value is not None]
    lows = [value for value in lows if value is not None]
    latest = _to_float(day_points[-1].get("close"))
    if not highs or not lows or latest is None:
        return {"minutes": minutes, "high": None, "low": None, "state": "unknown"}
    high = max(highs)
    low = min(lows)
    if latest > high:
        state = "above"
    elif latest < low:
        state = "below"
    else:
        state = "inside"
    return {
        "minutes": minutes,
        "high": round(high, 6),
        "low": round(low, 6),
        "state": state,
        "distance_high": _safe_pct_diff(latest, high),
        "distance_low": _safe_pct_diff(latest, low),
    }


def _rule_checks(
    *,
    latest_close: float | None,
    vwap: float | None,
    rsi14: float | None,
    kdj: dict[str, float | None],
    volume: dict[str, Any],
    ema: dict[str, Any],
    atr: dict[str, Any],
    opening_range: dict[str, Any],
    points: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    recent_low = _recent_low(points, 5)
    vwap_buffer = vwap * 0.997 if vwap is not None else None
    volume_ratio = _to_float(volume.get("ratio"))
    volume_zscore = _to_float(volume.get("zscore"))
    ema_state = str(ema.get("state") or "unknown")
    or_state = str(opening_range.get("state") or "unknown")
    atr_state = str(atr.get("state") or "unknown")
    k = _to_float(kdj.get("k"))
    j = _to_float(kdj.get("j"))

    rules = []
    if latest_close is not None and vwap is not None and recent_low is not None and vwap_buffer is not None:
        passed = latest_close > vwap and recent_low >= vwap_buffer
        failed = latest_close < vwap and recent_low < vwap
        rules.append(
            _rule(
                "vwap_hold",
                "VWAP hold",
                "价格站上 VWAP，且最近 5 根 1 分钟线的回踩没有有效跌破 VWAP。",
                "pass" if passed else "fail" if failed else "watch",
                2 if passed else -2 if failed else 0,
                "VWAP 守住，日内偏强结构成立。"
                if passed
                else "VWAP 已经失守，反弹需要重新确认。"
                if failed
                else "价格贴近 VWAP，等一次明确站稳或被压回。",
                {"price": latest_close, "vwap": vwap, "recent_low_5m": recent_low},
            )
        )
    else:
        rules.append(_rule("vwap_hold", "VWAP hold", "需要有成交量的 1 分钟 K 线才能计算 VWAP。", "pending", 0, "数据还不够，先等待。", {}))

    if ema_state == "bullish":
        status, score, conclusion = "pass", 2, "EMA9 在 EMA21 上方并向上，短线趋势支持做多。"
    elif ema_state == "bearish":
        status, score, conclusion = "fail", -2, "EMA9 在 EMA21 下方并向下，短线趋势偏弱。"
    else:
        status, score, conclusion = "watch", 0, "EMA 排列混杂，小波动不宜当成趋势。"
    rules.append(
        _rule(
            "ema_stack",
            "EMA trend",
            "EMA9 高于 EMA21 且斜率向上偏多；反过来则偏空。",
            status,
            score,
            conclusion,
            {"ema9": ema.get("ema9"), "ema21": ema.get("ema21"), "slope9_5m": ema.get("slope9_5m")},
        )
    )

    if or_state == "above":
        status, score, conclusion = "pass", 1, "价格在开盘 15 分钟区间上沿之上，突破结构仍在。"
    elif or_state == "below":
        status, score, conclusion = "fail", -1, "价格在开盘 15 分钟区间下沿之下，空方控制更强。"
    elif or_state == "inside":
        status, score, conclusion = "watch", 0, "价格仍在开盘区间内，更像震荡。"
    else:
        status, score, conclusion = "pending", 0, "开盘区间还在形成。"
    rules.append(
        _rule(
            "opening_range",
            "OR15 location",
            "站上 OR15 高点偏突破；跌破 OR15 低点偏风险释放；区间内偏震荡。",
            status,
            score,
            conclusion,
            {"or15_high": opening_range.get("high"), "or15_low": opening_range.get("low")},
        )
    )

    volume_confirmed = (volume_ratio is not None and volume_ratio >= 1.3) or (
        volume_zscore is not None and volume_zscore >= 1.0
    )
    volume_dry = volume_ratio is not None and volume_ratio <= 0.55
    rules.append(
        _rule(
            "volume_confirm",
            "Volume confirm",
            "最新 1 分钟成交量达到近 20 根均量 1.3 倍以上，或 z-score >= 1，说明有真实参与。",
            "pass" if volume_confirmed else "fail" if volume_dry else "watch",
            1 if volume_confirmed else -1 if volume_dry else 0,
            "这波价格动作有量能确认。"
            if volume_confirmed
            else "量能偏干，突破或反抽信号可靠性下降。"
            if volume_dry
            else "量能普通，优先看价格结构。",
            {"volume_ratio": volume_ratio, "volume_zscore": volume_zscore},
        )
    )

    overheat = (rsi14 is not None and rsi14 >= 72) or (k is not None and j is not None and k >= 82 and j >= 95)
    oversold = (rsi14 is not None and rsi14 <= 28) or (k is not None and j is not None and k <= 18 and j <= 8)
    if overheat:
        status, score, conclusion = "warn", -1, "动量过热，追涨性价比下降，更适合等冲高失败。"
    elif oversold:
        status, score, conclusion = "watch", 1, "动量偏冷，可以观察，但买入最好等重新站回 VWAP/EMA。"
    else:
        status, score, conclusion = "pass", 0, "动量没有处在极端区间。"
    rules.append(
        _rule(
            "momentum_extreme",
            "RSI/KDJ extreme",
            "RSI >= 72 或 KDJ 过热提示追高风险；RSI <= 28 或 KDJ 过冷提示反弹观察。",
            status,
            score,
            conclusion,
            {"rsi14": rsi14, "kdj_k": k, "kdj_j": j},
        )
    )

    if atr_state == "compressed":
        status, score, conclusion = "watch", -1, "波动被压缩，日内做 T 的空间可能不够。"
    elif atr_state == "wide":
        status, score, conclusion = "watch", 0, "波动偏大，仓位要更轻，止损也要放宽。"
    else:
        status, score, conclusion = "pass", 0, "1 分钟波动空间适合做 T。"
    rules.append(
        _rule(
            "atr_space",
            "ATR space",
            "ATR1m 用来判断当前 1 分钟波动是否足够覆盖滑点和止损成本。",
            status,
            score,
            conclusion,
            {"atr": atr.get("atr"), "atr_pct": atr.get("atr_pct")},
        )
    )

    return rules


def _rule(
    rule_id: str,
    label: str,
    condition: str,
    status: str,
    score: int,
    conclusion: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": rule_id,
        "label": label,
        "condition": condition,
        "status": status,
        "score": score,
        "conclusion": conclusion,
        "evidence": evidence,
    }


def _bias_summary(bias: str, rules: list[dict[str, Any]]) -> str:
    if not rules:
        return "1 分钟数据还不够，暂时不评分。"
    passed = [rule["label"] for rule in rules if rule.get("status") == "pass"]
    failed = [rule["label"] for rule in rules if rule.get("status") == "fail"]
    if bias == "strong_long_bias":
        return f"强多：{', '.join(passed[:3])} 同时满足。"
    if bias == "long_bias":
        return f"偏多：{', '.join(passed[:2])} 支持。"
    if bias == "strong_short_bias":
        return f"强空：{', '.join(failed[:3])} 不满足。"
    if bias == "short_bias":
        return f"偏空：{', '.join(failed[:2])} 不满足。"
    return "中性：等待 VWAP、EMA 或 OR15 出现一致方向。"


def _indicator_guide() -> list[dict[str, str]]:
    return [
        {
            "label": "VWAP",
            "meaning": "VWAP 是日内成交量加权均价，可理解为当天的主战场成本线。",
            "condition": "价格在 VWAP 上方且回踩不破，偏强；跌破 VWAP 后反弹需要重新确认。",
        },
        {
            "label": "EMA9/21",
            "meaning": "EMA9/21 是快慢短均线，用来判断 1 分钟级别趋势是否顺。",
            "condition": "EMA9 在 EMA21 上方且斜率向上偏多；EMA9 在下方且继续下行偏空。",
        },
        {
            "label": "OR15",
            "meaning": "OR15 是开盘前 15 分钟形成的高低区间。",
            "condition": "站上区间高点偏突破，跌破区间低点偏转弱，区间内通常更容易震荡。",
        },
        {
            "label": "Volume z",
            "meaning": "Volume z 衡量最新 1 分钟成交量相对最近 20 根的异常程度。",
            "condition": "z >= 1 或量比 >= 1.3x，说明这次价格动作更有参与度；缩量时信号要打折。",
        },
        {
            "label": "ATR1m",
            "meaning": "ATR1m 是最近 1 分钟 K 线的平均波动范围。",
            "condition": "ATR 太低说明做 T 空间不够；ATR 太高说明波动大，要降低仓位或放宽止损。",
        },
        {
            "label": "RSI/KDJ",
            "meaning": "RSI/KDJ 用来观察动量是否过热、过冷，以及短线拐头风险。",
            "condition": "过热不适合追，过冷只代表观察反弹，最好等重新站回 VWAP/EMA 再确认。",
        },
    ]


def _period_return(closes: list[float], periods: int) -> float | None:
    if len(closes) <= periods:
        return None
    previous = closes[-periods - 1]
    latest = closes[-1]
    if previous == 0:
        return None
    return round(latest / previous - 1, 6)


def _ema_series(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    multiplier = 2 / (period + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append((value - result[-1]) * multiplier + result[-1])
    return result


def _series_return(values: list[float], periods: int) -> float | None:
    if len(values) <= periods:
        return None
    previous = values[-periods - 1]
    latest = values[-1]
    if previous == 0:
        return None
    return round(latest / previous - 1, 6)


def _safe_pct_diff(value: float | None, base: float | None) -> float | None:
    if value is None or base is None or base == 0:
        return None
    return round(value / base - 1, 6)


def _typical_price(point: dict[str, Any]) -> float:
    high = _to_float(point.get("high"))
    low = _to_float(point.get("low"))
    close = _to_float(point.get("close"))
    values = [value for value in (high, low, close) if value is not None]
    return mean(values) if values else 0.0


def _recent_low(points: list[dict[str, Any]], count: int) -> float | None:
    lows = [_to_float(point.get("low")) for point in points[-count:]]
    lows = [value for value in lows if value is not None]
    return min(lows) if lows else None


def _latest_day_points(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not points:
        return []
    latest_day = _session_day(points[-1])
    return [point for point in points if _session_day(point) == latest_day]


def _session_day(point: dict[str, Any]) -> str | None:
    value = str(point.get("time") or "")
    if not value:
        return None
    return value.split("T", 1)[0].split(" ", 1)[0]


def _stdev(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    center = mean(values)
    variance = sum((value - center) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(variance)


def _time_key(row: dict[str, Any]) -> str | None:
    value = row.get("time_key") or row.get("time") or row.get("datetime") or row.get("date")
    return str(value) if value else None


def _last_present(values: list[float | None]) -> float | None:
    for value in reversed(values):
        if value is not None:
            return value
    return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number
