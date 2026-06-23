from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


DEFAULT_FEATURE_COLUMNS = [
    "rsi6",
    "rsi14",
    "kdj_k",
    "kdj_j",
    "bb_percent_b",
    "bb_z",
    "vwap_dev",
    "ret_1bar",
    "ret_3bar",
    "ret_5bar",
    "ema9_ema21_spread_pct",
    "ema9_slope_3bar",
    "macd_hist",
    "macd_hist_delta_1",
    "atr14_pct",
    "volume_ratio_20",
    "volume_z_20",
    "relative_volume_time_20",
    "opening_relative_volume_15",
    "gap_pct",
    "range_pos_10",
    "lower_wick_ratio",
    "upper_wick_ratio",
]


@dataclass(frozen=True)
class RuleCondition:
    feature: str
    operator: str
    threshold: float

    def matches(self, frame: pd.DataFrame) -> pd.Series:
        values = pd.to_numeric(frame[self.feature], errors="coerce")
        if self.operator == "<=":
            return values <= self.threshold
        if self.operator == ">=":
            return values >= self.threshold
        raise ValueError(f"Unsupported operator: {self.operator}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature": self.feature,
            "operator": self.operator,
            "threshold": self.threshold,
        }

    def label(self) -> str:
        return f"{self.feature} {self.operator} {_compact_number(self.threshold)}"


def resample_intraday_rows(
    rows: Iterable[dict[str, Any]],
    *,
    interval_minutes: int = 3,
) -> pd.DataFrame:
    interval_minutes = max(1, int(interval_minutes))
    records = []
    for row in rows:
        timestamp = pd.to_datetime(
            row.get("time_key") or row.get("time") or row.get("datetime"),
            errors="coerce",
        )
        close = _number(row.get("close"))
        if pd.isna(timestamp) or close is None:
            continue
        timestamp = pd.Timestamp(timestamp)
        minute_of_day = timestamp.hour * 60 + timestamp.minute
        session_minute = minute_of_day - (9 * 60 + 30)
        if session_minute < 0 or session_minute >= 390:
            continue
        records.append(
            {
                "time": timestamp,
                "date": timestamp.date().isoformat(),
                "session_minute": session_minute,
                "bucket": session_minute // interval_minutes,
                "open": _number(row.get("open")) or close,
                "high": _number(row.get("high")) or close,
                "low": _number(row.get("low")) or close,
                "close": close,
                "volume": _number(row.get("volume")) or 0.0,
                "turnover": _number(row.get("turnover")) or 0.0,
            }
        )
    if not records:
        return pd.DataFrame()
    raw = pd.DataFrame(records).sort_values("time")
    frame = (
        raw.groupby(["date", "bucket"], as_index=False)
        .agg(
            time=("time", "last"),
            session_minute=("session_minute", "last"),
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
            turnover=("turnover", "sum"),
            source_rows=("close", "size"),
        )
        .sort_values("time")
        .reset_index(drop=True)
    )
    frame["bar_index"] = frame.groupby("date").cumcount()
    return frame


def build_feature_matrix(
    rows: Iterable[dict[str, Any]] | pd.DataFrame,
    *,
    interval_minutes: int = 3,
) -> pd.DataFrame:
    frame = rows.copy() if isinstance(rows, pd.DataFrame) else resample_intraday_rows(rows, interval_minutes=interval_minutes)
    if frame.empty:
        return frame
    frame = frame.sort_values("time").reset_index(drop=True)
    groups = []
    for _, day in frame.groupby("date", sort=True):
        groups.append(_feature_day(day.copy()))
    result = _cross_session_features(pd.concat(groups, ignore_index=True))
    return result.replace([np.inf, -np.inf], np.nan)


def label_turning_zones(
    frame: pd.DataFrame,
    *,
    window_bars: int = 5,
    prominence_atr: float = 2.0,
    plateau_tolerance_atr: float = 0.18,
    merge_gap_bars: int = 2,
) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    result = frame.copy()
    result["turn_zone"] = "none"
    result["pivot_label"] = "none"
    result["pivot_strength"] = np.nan
    result["turn_zone_id"] = None
    result["turn_zone_start"] = None
    result["turn_zone_end"] = None
    zones = []
    for date, day in result.groupby("date", sort=True):
        candidates = _turn_candidates(
            day,
            window_bars=window_bars,
            prominence_atr=prominence_atr,
            plateau_tolerance_atr=plateau_tolerance_atr,
        )
        merged = _merge_turn_candidates(
            candidates,
            merge_gap_bars=merge_gap_bars,
            plateau_tolerance_atr=plateau_tolerance_atr,
        )
        expanded = [
            _expand_turn_zone(day, zone, plateau_tolerance_atr=plateau_tolerance_atr)
            for zone in merged
        ]
        for sequence, zone in enumerate(expanded, start=1):
            zone_id = f"{date}-{zone['kind']}-{sequence}"
            zone_indices = list(range(zone["start_index"], zone["end_index"] + 1))
            result.loc[zone_indices, "turn_zone"] = zone["kind"]
            result.loc[zone_indices, "turn_zone_id"] = zone_id
            result.loc[zone_indices, "turn_zone_start"] = result.loc[zone["start_index"], "time"]
            result.loc[zone_indices, "turn_zone_end"] = result.loc[zone["end_index"], "time"]
            result.loc[zone["representative_index"], "pivot_label"] = zone["kind"]
            result.loc[zone["representative_index"], "pivot_strength"] = zone["strength"]
            zones.append({**zone, "zone_id": zone_id, "date": date})
    result.attrs["turning_zones"] = zones
    return result


def event_feature_differences(
    frame: pd.DataFrame,
    *,
    event: str,
    feature_columns: list[str] | None = None,
    lead_bars: int = 1,
) -> list[dict[str, Any]]:
    feature_columns = feature_columns or DEFAULT_FEATURE_COLUMNS
    event_mask = frame["pivot_label"].eq(event)
    event_rows = frame.groupby("date", group_keys=False).apply(
        lambda day: day.shift(max(0, int(lead_bars))).where(event_mask.loc[day.index]).dropna(how="all"),
        include_groups=False,
    )
    baseline = frame[feature_columns].apply(pd.to_numeric, errors="coerce")
    rows = []
    for feature in feature_columns:
        if feature not in frame or feature not in event_rows:
            continue
        event_values = pd.to_numeric(event_rows[feature], errors="coerce").dropna()
        base_values = baseline[feature].dropna()
        if len(event_values) < 5 or len(base_values) < 20:
            continue
        std = float(base_values.std(ddof=1) or 0.0)
        event_median = float(event_values.median())
        base_median = float(base_values.median())
        rows.append(
            {
                "feature": feature,
                "event_count": int(len(event_values)),
                "event_median": event_median,
                "baseline_median": base_median,
                "standardized_difference": (event_median - base_median) / std if std else 0.0,
            }
        )
    rows.sort(key=lambda item: abs(item["standardized_difference"]), reverse=True)
    return rows


def mine_threshold_rules(
    frame: pd.DataFrame,
    *,
    direction: str = "long",
    feature_columns: list[str] | None = None,
    train_fraction: float = 0.7,
    target_return: float = 0.015,
    stop_return: float = 0.008,
    max_hold_bars: int = 7,
    round_trip_cost: float = 0.001,
    cooldown_bars: int = 2,
    min_train_trades: int = 12,
    min_test_trades: int = 5,
    max_seed_conditions: int = 10,
) -> dict[str, Any]:
    if frame.empty:
        return {"train_dates": [], "test_dates": [], "candidates": []}
    if direction not in {"long", "short"}:
        raise ValueError(f"Unsupported research direction: {direction}")
    feature_columns = [column for column in (feature_columns or DEFAULT_FEATURE_COLUMNS) if column in frame]
    dates = sorted(str(value) for value in frame["date"].dropna().unique())
    split_index = min(max(1, int(len(dates) * train_fraction)), max(1, len(dates) - 1))
    train_dates = dates[:split_index]
    test_dates = dates[split_index:]
    train = frame[frame["date"].isin(train_dates)].copy()
    test = frame[frame["date"].isin(test_dates)].copy()
    singles = _candidate_conditions(train, feature_columns)
    scored_singles = []
    for condition in singles:
        metrics = backtest_conditions(
            train,
            [condition],
            direction=direction,
            target_return=target_return,
            stop_return=stop_return,
            max_hold_bars=max_hold_bars,
            round_trip_cost=round_trip_cost,
            cooldown_bars=cooldown_bars,
        )
        if metrics["trades"] >= min_train_trades:
            scored_singles.append((condition, metrics))
    scored_singles.sort(key=lambda item: _rule_score(item[1], item[1]), reverse=True)
    seed_conditions = [item[0] for item in scored_singles[: max(1, int(max_seed_conditions))]]
    condition_sets: list[list[RuleCondition]] = [[condition] for condition in seed_conditions]
    for left_index, left in enumerate(seed_conditions):
        for right in seed_conditions[left_index + 1 :]:
            if left.feature == right.feature:
                continue
            condition_sets.append([left, right])
    candidates = []
    seen = set()
    for conditions in condition_sets:
        key = tuple((item.feature, item.operator, round(item.threshold, 8)) for item in conditions)
        if key in seen:
            continue
        seen.add(key)
        train_metrics = backtest_conditions(
            train,
            conditions,
            direction=direction,
            target_return=target_return,
            stop_return=stop_return,
            max_hold_bars=max_hold_bars,
            round_trip_cost=round_trip_cost,
            cooldown_bars=cooldown_bars,
        )
        if train_metrics["trades"] < min_train_trades:
            continue
        test_metrics = backtest_conditions(
            test,
            conditions,
            direction=direction,
            target_return=target_return,
            stop_return=stop_return,
            max_hold_bars=max_hold_bars,
            round_trip_cost=round_trip_cost,
            cooldown_bars=cooldown_bars,
        )
        if test_metrics["trades"] < min_test_trades:
            continue
        candidates.append(
            {
                "rule": " & ".join(condition.label() for condition in conditions),
                "direction": direction,
                "conditions": [condition.to_dict() for condition in conditions],
                "train": train_metrics,
                "test": test_metrics,
                "score": _rule_score(train_metrics, test_metrics),
                "status": _candidate_status(train_metrics, test_metrics),
            }
        )
    candidates.sort(key=lambda item: item["score"], reverse=True)
    for candidate in candidates[:10]:
        conditions = [RuleCondition(**item) for item in candidate["conditions"]]
        stability = _threshold_stability(
            train,
            test,
            conditions,
            direction=direction,
            target_return=target_return,
            stop_return=stop_return,
            max_hold_bars=max_hold_bars,
            round_trip_cost=round_trip_cost,
            cooldown_bars=cooldown_bars,
        )
        candidate["threshold_stability"] = stability
        if candidate["status"] == "candidate" and stability["positive_neighbor_rate"] < 2 / 3:
            candidate["status"] = "experiment"
    return {
        "train_dates": train_dates,
        "test_dates": test_dates,
        "assumptions": {
            "direction": direction,
            "target_return": target_return,
            "stop_return": stop_return,
            "max_hold_bars": max_hold_bars,
            "round_trip_cost": round_trip_cost,
            "cooldown_bars": cooldown_bars,
            "max_seed_conditions": max_seed_conditions,
        },
        "candidates": candidates[:40],
    }


def backtest_conditions(
    frame: pd.DataFrame,
    conditions: list[RuleCondition],
    *,
    direction: str = "long",
    target_return: float,
    stop_return: float,
    max_hold_bars: int,
    round_trip_cost: float,
    cooldown_bars: int,
) -> dict[str, Any]:
    if frame.empty:
        return _empty_backtest_metrics()
    if direction not in {"long", "short"}:
        raise ValueError(f"Unsupported research direction: {direction}")
    signal = pd.Series(True, index=frame.index)
    for condition in conditions:
        signal &= condition.matches(frame).fillna(False)
    return backtest_signal(
        frame,
        signal,
        direction=direction,
        target_return=target_return,
        stop_return=stop_return,
        max_hold_bars=max_hold_bars,
        round_trip_cost=round_trip_cost,
        cooldown_bars=cooldown_bars,
    )


def backtest_signal(
    frame: pd.DataFrame,
    signal: pd.Series,
    *,
    direction: str = "long",
    target_return: float,
    stop_return: float,
    max_hold_bars: int,
    round_trip_cost: float,
    cooldown_bars: int,
    max_trades_per_day: int | None = None,
) -> dict[str, Any]:
    if frame.empty:
        return _empty_backtest_metrics()
    if direction not in {"long", "short"}:
        raise ValueError(f"Unsupported research direction: {direction}")
    signal = signal.reindex(frame.index).fillna(False).astype(bool)
    trades = []
    for date, day in frame.groupby("date", sort=True):
        day = day.sort_values("time")
        day_indices = list(day.index)
        position = 0
        day_trade_count = 0
        while position < len(day_indices) - 1:
            if max_trades_per_day is not None and day_trade_count >= max(0, int(max_trades_per_day)):
                break
            index = day_indices[position]
            if not bool(signal.loc[index]):
                position += 1
                continue
            entry_position = position + 1
            entry_index = day_indices[entry_position]
            entry_price = _number(frame.loc[entry_index, "open"])
            if entry_price is None or entry_price <= 0:
                position += 1
                continue
            exit_position = min(len(day_indices) - 1, entry_position + max_hold_bars)
            exit_price = _number(frame.loc[day_indices[exit_position], "close"]) or entry_price
            exit_reason = "time"
            for cursor in range(entry_position, exit_position + 1):
                row_index = day_indices[cursor]
                low = _number(frame.loc[row_index, "low"]) or entry_price
                high = _number(frame.loc[row_index, "high"]) or entry_price
                if direction == "long":
                    if low <= entry_price * (1 - stop_return):
                        exit_position = cursor
                        exit_price = entry_price * (1 - stop_return)
                        exit_reason = "stop"
                        break
                    if high >= entry_price * (1 + target_return):
                        exit_position = cursor
                        exit_price = entry_price * (1 + target_return)
                        exit_reason = "target"
                        break
                else:
                    if high >= entry_price * (1 + stop_return):
                        exit_position = cursor
                        exit_price = entry_price * (1 + stop_return)
                        exit_reason = "stop"
                        break
                    if low <= entry_price * (1 - target_return):
                        exit_position = cursor
                        exit_price = entry_price * (1 - target_return)
                        exit_reason = "target"
                        break
            gross_return = exit_price / entry_price - 1 if direction == "long" else entry_price / exit_price - 1
            net_return = gross_return - round_trip_cost
            trades.append(
                {
                    "date": date,
                    "signal_time": str(frame.loc[index, "time"]),
                    "entry_time": str(frame.loc[entry_index, "time"]),
                    "exit_time": str(frame.loc[day_indices[exit_position], "time"]),
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "gross_return": gross_return,
                    "net_return": net_return,
                    "exit_reason": exit_reason,
                    "direction": direction,
                }
            )
            day_trade_count += 1
            position = exit_position + 1 + max(0, int(cooldown_bars))
    return _trade_metrics(trades)


def run_strategy_research(
    rows: Iterable[dict[str, Any]],
    *,
    ticker: str,
    interval_minutes: int = 3,
    include_threshold_mining: bool = True,
) -> dict[str, Any]:
    features = build_feature_matrix(rows, interval_minutes=interval_minutes)
    labeled = label_turning_zones(features)
    long_mined = mine_threshold_rules(labeled, direction="long") if include_threshold_mining else {}
    short_mined = mine_threshold_rules(labeled, direction="short") if include_threshold_mining else {}
    combined_candidates = (
        sorted(
            [*(long_mined.get("candidates") or []), *(short_mined.get("candidates") or [])],
            key=lambda item: item.get("score") or 0.0,
            reverse=True,
        )[:60]
        if include_threshold_mining
        else []
    )
    mined = {
        "enabled": include_threshold_mining,
        "candidates": combined_candidates,
        "long": long_mined,
        "short": short_mined,
    }
    individual_tuning = _tune_top_mined_rules(labeled, combined_candidates) if include_threshold_mining else []
    from .strategy_archetypes import evaluate_industry_strategies

    industry_strategies = evaluate_industry_strategies(labeled)
    return {
        "ticker": ticker.upper(),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "interval_minutes": interval_minutes,
        "rows": int(len(labeled)),
        "dates": sorted(str(value) for value in labeled["date"].dropna().unique()) if not labeled.empty else [],
        "turning_zone_assumptions": {
            "window_bars": 5,
            "prominence_atr": 2.0,
            "plateau_tolerance_atr": 0.18,
            "merge_gap_bars": 2,
        },
        "turn_counts": labeled["pivot_label"].value_counts().to_dict() if not labeled.empty else {},
        "stock_profile": _stock_research_profile(labeled),
        "pre_trough_features": event_feature_differences(labeled, event="trough")[:15] if not labeled.empty else [],
        "pre_peak_features": event_feature_differences(labeled, event="peak")[:15] if not labeled.empty else [],
        "rule_mining": mined,
        "individual_tuning": individual_tuning,
        "industry_strategies": industry_strategies,
        "feature_frame": labeled,
    }


def write_strategy_research_outputs(
    research: dict[str, Any],
    *,
    output_dir: Path,
    stem: str,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    frame = research.get("feature_frame")
    csv_path = output_dir / f"{stem}_features.csv"
    json_path = output_dir / f"{stem}.json"
    markdown_path = output_dir / f"{stem}.md"
    if isinstance(frame, pd.DataFrame):
        frame.to_csv(csv_path, index=False)
    payload = {key: value for key, value in research.items() if key != "feature_frame"}
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    markdown_path.write_text(_research_markdown(payload), encoding="utf-8")
    return {
        "features_csv": str(csv_path),
        "json": str(json_path),
        "markdown": str(markdown_path),
    }


def _feature_day(day: pd.DataFrame) -> pd.DataFrame:
    close = pd.to_numeric(day["close"], errors="coerce")
    high = pd.to_numeric(day["high"], errors="coerce")
    low = pd.to_numeric(day["low"], errors="coerce")
    open_price = pd.to_numeric(day["open"], errors="coerce")
    volume = pd.to_numeric(day["volume"], errors="coerce").fillna(0.0)
    turnover = pd.to_numeric(day.get("turnover", 0.0), errors="coerce").fillna(0.0)
    day["ret_1bar"] = close.pct_change(1)
    day["ret_2bar"] = close.pct_change(2)
    day["ret_3bar"] = close.pct_change(3)
    day["ret_5bar"] = close.pct_change(5)
    day["ret_10bar"] = close.pct_change(10)
    day["body_pct"] = (close - open_price) / open_price.replace(0, np.nan)
    day["range_pct"] = (high - low) / close.replace(0, np.nan)
    body_high = pd.concat([open_price, close], axis=1).max(axis=1)
    body_low = pd.concat([open_price, close], axis=1).min(axis=1)
    full_range = (high - low).replace(0, np.nan)
    day["upper_wick_ratio"] = (high - body_high) / full_range
    day["lower_wick_ratio"] = (body_low - low) / full_range
    cumulative_volume = volume.cumsum()
    typical = (high + low + close) / 3
    value = turnover.where(turnover > 0, typical * volume)
    day["vwap"] = value.cumsum() / cumulative_volume.replace(0, np.nan)
    day["vwap_dev"] = close / day["vwap"] - 1
    for period in (5, 10, 20, 50):
        day[f"sma{period}"] = close.rolling(period).mean()
        day[f"close_sma{period}_pct"] = close / day[f"sma{period}"] - 1
    for period in (5, 9, 21, 50):
        day[f"ema{period}"] = close.ewm(span=period, adjust=False).mean()
    day["ema9_ema21_spread_pct"] = day["ema9"] / day["ema21"] - 1
    day["ema21_ema50_spread_pct"] = day["ema21"] / day["ema50"] - 1
    day["ema9_slope_3bar"] = day["ema9"].pct_change(3)
    day["ema21_slope_3bar"] = day["ema21"].pct_change(3)
    day["rsi6"] = _rsi_series(close, 6)
    day["rsi14"] = _rsi_series(close, 14)
    low9 = low.rolling(9).min()
    high9 = high.rolling(9).max()
    rsv = (close - low9) / (high9 - low9).replace(0, np.nan) * 100
    day["kdj_k"] = rsv.ewm(com=2, adjust=False).mean()
    day["kdj_d"] = day["kdj_k"].ewm(com=2, adjust=False).mean()
    day["kdj_j"] = 3 * day["kdj_k"] - 2 * day["kdj_d"]
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    day["macd_dif"] = ema12 - ema26
    day["macd_dea"] = day["macd_dif"].ewm(span=9, adjust=False).mean()
    day["macd_hist"] = day["macd_dif"] - day["macd_dea"]
    day["macd_hist_delta_1"] = day["macd_hist"].diff(1)
    day["macd_hist_delta_3"] = day["macd_hist"].diff(3)
    mid = close.rolling(20).mean()
    std = close.rolling(20).std()
    day["bb_mid20"] = mid
    day["bb_upper20"] = mid + 2 * std
    day["bb_lower20"] = mid - 2 * std
    day["bb_z"] = (close - mid) / std.replace(0, np.nan)
    day["bb_percent_b"] = (close - day["bb_lower20"]) / (day["bb_upper20"] - day["bb_lower20"]).replace(0, np.nan)
    previous_close = close.shift(1)
    true_range = pd.concat(
        [(high - low), (high - previous_close).abs(), (low - previous_close).abs()],
        axis=1,
    ).max(axis=1)
    day["true_range"] = true_range
    day["atr14"] = true_range.rolling(14).mean()
    day["atr14_pct"] = day["atr14"] / close.replace(0, np.nan)
    day["realized_vol_10"] = day["ret_1bar"].rolling(10).std()
    day["realized_vol_20"] = day["ret_1bar"].rolling(20).std()
    day["volume_avg20"] = volume.rolling(20).mean()
    day["volume_ratio_20"] = volume / day["volume_avg20"].replace(0, np.nan)
    day["volume_z_20"] = (volume - day["volume_avg20"]) / volume.rolling(20).std().replace(0, np.nan)
    direction = np.sign(close.diff()).fillna(0)
    day["obv"] = (direction * volume).cumsum()
    day["obv_slope_5"] = day["obv"].diff(5) / day["volume_avg20"].replace(0, np.nan)
    rolling_low = low.rolling(10).min()
    rolling_high = high.rolling(10).max()
    day["range_pos_10"] = (close - rolling_low) / (rolling_high - rolling_low).replace(0, np.nan)
    opening = day.head(5)
    opening_high = opening["high"].max() if not opening.empty else np.nan
    opening_low = opening["low"].min() if not opening.empty else np.nan
    day["or15_high"] = opening_high
    day["or15_low"] = opening_low
    day["dist_or_high"] = close / opening_high - 1 if opening_high else np.nan
    day["dist_or_low"] = close / opening_low - 1 if opening_low else np.nan
    day["day_high_so_far"] = high.cummax()
    day["day_low_so_far"] = low.cummin()
    day["dist_day_high"] = close / day["day_high_so_far"] - 1
    day["dist_day_low"] = close / day["day_low_so_far"] - 1
    day["minutes_from_open"] = pd.to_numeric(day["session_minute"], errors="coerce")
    angle = 2 * math.pi * day["minutes_from_open"] / 390
    day["time_sin"] = np.sin(angle)
    day["time_cos"] = np.cos(angle)
    return day


def _cross_session_features(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.sort_values(["date", "bar_index"]).reset_index(drop=True).copy()
    daily = (
        result.groupby("date", sort=True)
        .agg(
            session_open=("open", "first"),
            session_close=("close", "last"),
            session_high=("high", "max"),
            session_low=("low", "min"),
        )
    )
    daily["prior_close"] = daily["session_close"].shift(1)
    daily["prior_session_range_pct"] = (
        (daily["session_high"].shift(1) - daily["session_low"].shift(1))
        / daily["session_close"].shift(1).replace(0, np.nan)
    )
    daily["gap_pct"] = daily["session_open"] / daily["prior_close"].replace(0, np.nan) - 1
    result["prior_close"] = result["date"].map(daily["prior_close"])
    result["prior_session_range_pct"] = result["date"].map(daily["prior_session_range_pct"])
    result["gap_pct"] = result["date"].map(daily["gap_pct"])
    result["relative_volume_time_20"] = (
        result.groupby("bar_index", sort=False)["volume"]
        .transform(
            lambda values: values
            / values.shift(1).rolling(20, min_periods=5).median().replace(0, np.nan)
        )
    )
    opening_volume = (
        result[result["bar_index"] < 5]
        .groupby("date", sort=True)["volume"]
        .sum()
    )
    opening_median = opening_volume.shift(1).rolling(20, min_periods=5).median()
    opening_relative = opening_volume / opening_median.replace(0, np.nan)
    result["opening_relative_volume_15"] = result["date"].map(opening_relative)
    return result


def _turn_candidates(
    day: pd.DataFrame,
    *,
    window_bars: int,
    prominence_atr: float,
    plateau_tolerance_atr: float,
) -> list[dict[str, Any]]:
    positions = list(day.index)
    candidates = []
    for local_index in range(window_bars, len(positions) - window_bars):
        index = positions[local_index]
        window_indices = positions[local_index - window_bars : local_index + window_bars + 1]
        left_indices = positions[local_index - window_bars : local_index]
        right_indices = positions[local_index + 1 : local_index + window_bars + 1]
        high = float(day.loc[index, "high"])
        low = float(day.loc[index, "low"])
        close = float(day.loc[index, "close"])
        atr = _number(day.loc[index, "atr14"]) or max(close * 0.001, high - low)
        tolerance = max(atr * plateau_tolerance_atr, close * 0.0001)
        local_high = float(day.loc[window_indices, "high"].max())
        local_low = float(day.loc[window_indices, "low"].min())
        peak_strength = min(
            high - float(day.loc[left_indices, "low"].min()),
            high - float(day.loc[right_indices, "low"].min()),
        ) / atr
        trough_strength = min(
            float(day.loc[left_indices, "high"].max()) - low,
            float(day.loc[right_indices, "high"].max()) - low,
        ) / atr
        peak = high >= local_high - tolerance and peak_strength >= prominence_atr
        trough = low <= local_low + tolerance and trough_strength >= prominence_atr
        if peak and trough:
            continue
        if peak:
            candidates.append({"index": index, "kind": "peak", "price": high, "atr": atr, "strength": peak_strength})
        elif trough:
            candidates.append({"index": index, "kind": "trough", "price": low, "atr": atr, "strength": trough_strength})
    return candidates


def _merge_turn_candidates(
    candidates: list[dict[str, Any]],
    *,
    merge_gap_bars: int,
    plateau_tolerance_atr: float,
) -> list[dict[str, Any]]:
    groups: list[list[dict[str, Any]]] = []
    for candidate in candidates:
        if not groups:
            groups.append([candidate])
            continue
        previous = groups[-1][-1]
        tolerance = max(previous["atr"], candidate["atr"]) * plateau_tolerance_atr
        if (
            candidate["kind"] == previous["kind"]
            and candidate["index"] - previous["index"] <= merge_gap_bars + 1
            and abs(candidate["price"] - previous["price"]) <= tolerance
        ):
            groups[-1].append(candidate)
        else:
            groups.append([candidate])
    zones = []
    for group in groups:
        kind = group[0]["kind"]
        representative = max(group, key=lambda item: item["price"]) if kind == "peak" else min(group, key=lambda item: item["price"])
        zones.append(
            {
                "kind": kind,
                "start_index": min(item["index"] for item in group),
                "end_index": max(item["index"] for item in group),
                "representative_index": representative["index"],
                "price": representative["price"],
                "strength": max(item["strength"] for item in group),
                "duration_bars": max(item["index"] for item in group) - min(item["index"] for item in group) + 1,
            }
        )
    return zones


def _expand_turn_zone(
    day: pd.DataFrame,
    zone: dict[str, Any],
    *,
    plateau_tolerance_atr: float,
) -> dict[str, Any]:
    positions = list(day.index)
    start_position = positions.index(zone["start_index"])
    end_position = positions.index(zone["end_index"])
    kind = zone["kind"]
    price_column = "high" if kind == "peak" else "low"
    representative_price = float(zone["price"])
    representative_atr = _number(day.loc[zone["representative_index"], "atr14"]) or 0.0
    tolerance = max(representative_atr * plateau_tolerance_atr, abs(representative_price) * 0.0001)
    while start_position > 0:
        candidate_index = positions[start_position - 1]
        price = _number(day.loc[candidate_index, price_column])
        if price is None or abs(price - representative_price) > tolerance:
            break
        start_position -= 1
    while end_position < len(positions) - 1:
        candidate_index = positions[end_position + 1]
        price = _number(day.loc[candidate_index, price_column])
        if price is None or abs(price - representative_price) > tolerance:
            break
        end_position += 1
    return {
        **zone,
        "start_index": positions[start_position],
        "end_index": positions[end_position],
        "duration_bars": end_position - start_position + 1,
    }


def _candidate_conditions(train: pd.DataFrame, feature_columns: list[str]) -> list[RuleCondition]:
    conditions = []
    for feature in feature_columns:
        values = pd.to_numeric(train[feature], errors="coerce").dropna()
        if len(values) < 30 or values.nunique() < 8:
            continue
        for quantile in (0.1, 0.2, 0.3):
            conditions.append(RuleCondition(feature, "<=", float(values.quantile(quantile))))
        for quantile in (0.7, 0.8, 0.9):
            conditions.append(RuleCondition(feature, ">=", float(values.quantile(quantile))))
    return conditions


def _trade_metrics(trades: list[dict[str, Any]]) -> dict[str, Any]:
    if not trades:
        return _empty_backtest_metrics()
    returns = [float(item["net_return"]) for item in trades]
    wins = [value for value in returns if value > 0]
    losses = [value for value in returns if value < 0]
    daily: dict[str, float] = {}
    for trade in trades:
        daily[trade["date"]] = daily.get(trade["date"], 0.0) + float(trade["net_return"])
    cumulative = np.cumsum(returns)
    running_peak = np.maximum.accumulate(np.concatenate(([0.0], cumulative)))
    drawdowns = np.concatenate(([0.0], cumulative)) - running_peak
    profit_factor = sum(wins) / abs(sum(losses)) if losses else (math.inf if wins else 0.0)
    count = len(trades)
    win_rate = len(wins) / count
    absolute_total = sum(abs(value) for value in daily.values())
    largest_day_share = max((abs(value) for value in daily.values()), default=0.0) / absolute_total if absolute_total else 0.0
    return {
        "trades": count,
        "winning_trades": len(wins),
        "win_rate": win_rate,
        "win_rate_wilson_lower": _wilson_lower(len(wins), count),
        "average_net_return": float(np.mean(returns)),
        "median_net_return": float(np.median(returns)),
        "total_net_return": float(sum(returns)),
        "profit_factor": float(profit_factor),
        "max_drawdown": float(drawdowns.min()),
        "active_days": len(daily),
        "profitable_days": sum(1 for value in daily.values() if value > 0),
        "profitable_day_rate": sum(1 for value in daily.values() if value > 0) / len(daily),
        "trades_per_active_day": count / len(daily),
        "target_rate": sum(1 for item in trades if item["exit_reason"] == "target") / count,
        "stop_rate": sum(1 for item in trades if item["exit_reason"] == "stop") / count,
        "largest_day_abs_pnl_share": largest_day_share,
        "daily_returns": daily,
        "trade_returns": returns,
    }


def _empty_backtest_metrics() -> dict[str, Any]:
    return {
        "trades": 0,
        "winning_trades": 0,
        "win_rate": 0.0,
        "win_rate_wilson_lower": 0.0,
        "average_net_return": 0.0,
        "median_net_return": 0.0,
        "total_net_return": 0.0,
        "profit_factor": 0.0,
        "max_drawdown": 0.0,
        "active_days": 0,
        "profitable_days": 0,
        "profitable_day_rate": 0.0,
        "trades_per_active_day": 0.0,
        "target_rate": 0.0,
        "stop_rate": 0.0,
        "largest_day_abs_pnl_share": 0.0,
        "daily_returns": {},
        "trade_returns": [],
    }


def _rule_score(train: dict[str, Any], test: dict[str, Any]) -> float:
    test_pf = min(float(test.get("profit_factor") or 0.0), 5.0)
    train_pf = min(float(train.get("profit_factor") or 0.0), 5.0)
    frequency = float(test.get("trades_per_active_day") or 0.0)
    frequency_penalty = abs(frequency - 2.5) * 0.08
    degradation = abs(float(train.get("win_rate") or 0.0) - float(test.get("win_rate") or 0.0))
    return (
        float(test.get("total_net_return") or 0.0) * 8
        + min(float(train.get("total_net_return") or 0.0), float(test.get("total_net_return") or 0.0)) * 4
        + float(test.get("win_rate_wilson_lower") or 0.0)
        + test_pf * 0.18
        + train_pf * 0.05
        - degradation
        - frequency_penalty
    )


def _candidate_status(train: dict[str, Any], test: dict[str, Any]) -> str:
    if (
        train["total_net_return"] > 0
        and test["total_net_return"] > 0
        and train["profit_factor"] >= 1.15
        and test["profit_factor"] >= 1.15
    ):
        return "candidate"
    if train["total_net_return"] > 0 and test["total_net_return"] > 0:
        return "experiment"
    return "reject"


def _threshold_stability(
    train: pd.DataFrame,
    test: pd.DataFrame,
    conditions: list[RuleCondition],
    *,
    direction: str,
    target_return: float,
    stop_return: float,
    max_hold_bars: int,
    round_trip_cost: float,
    cooldown_bars: int,
) -> dict[str, Any]:
    neighborhoods: list[tuple[str, list[RuleCondition]]] = [("base", conditions)]
    for variant_name, multiplier in (("tighter", 1.0), ("looser", -1.0)):
        adjusted = []
        for condition in conditions:
            values = pd.to_numeric(train[condition.feature], errors="coerce").dropna()
            spread = float(values.std(ddof=1) or 0.0)
            delta = spread * 0.1
            operator_sign = 1.0 if condition.operator == ">=" else -1.0
            adjusted.append(
                RuleCondition(
                    condition.feature,
                    condition.operator,
                    condition.threshold + operator_sign * multiplier * delta,
                )
            )
        neighborhoods.append((variant_name, adjusted))
    results = []
    for name, variant in neighborhoods:
        metrics = backtest_conditions(
            test,
            variant,
            direction=direction,
            target_return=target_return,
            stop_return=stop_return,
            max_hold_bars=max_hold_bars,
            round_trip_cost=round_trip_cost,
            cooldown_bars=cooldown_bars,
        )
        results.append(
            {
                "variant": name,
                "rule": " & ".join(condition.label() for condition in variant),
                "trades": metrics["trades"],
                "win_rate": metrics["win_rate"],
                "total_net_return": metrics["total_net_return"],
                "profit_factor": metrics["profit_factor"],
            }
        )
    positive = [
        item
        for item in results
        if item["trades"] > 0 and item["total_net_return"] > 0 and item["profit_factor"] >= 1.0
    ]
    return {
        "positive_neighbor_rate": len(positive) / len(results),
        "positive_neighbors": len(positive),
        "evaluated_neighbors": len(results),
        "variants": results,
    }


def _wilson_lower(wins: int, total: int, z: float = 1.96) -> float:
    if total <= 0:
        return 0.0
    p = wins / total
    denominator = 1 + z * z / total
    center = p + z * z / (2 * total)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total)
    return max(0.0, (center - margin) / denominator)


def _rsi_series(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    relative = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + relative))
    return rsi.where(loss > 0, np.where(gain > 0, 100.0, 50.0))


def _tune_top_mined_rules(
    frame: pd.DataFrame,
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    from .strategy_tuning import RuleStrategySpec, tune_individual_strategy

    selected = []
    for candidate in candidates:
        stability = candidate.get("threshold_stability") or {}
        neighbor_rate = float(stability.get("positive_neighbor_rate") or 0.0)
        if (
            candidate["train"]["total_net_return"] <= 0
            or candidate["test"]["total_net_return"] <= 0
            or neighbor_rate < 2 / 3
        ):
            continue
        conditions = tuple(RuleCondition(**item) for item in candidate["conditions"])
        spec = RuleStrategySpec(
            id=f"mined-{candidate['direction']}-{'-'.join(item.feature for item in conditions)}",
            label=f"Mined {candidate['direction'].title()} Rule",
            direction=candidate["direction"],
            conditions=conditions,
            mechanism=_mined_rule_mechanism(conditions, candidate["direction"]),
            entry_neighbor_rate=neighbor_rate,
        )
        selected.append(tune_individual_strategy(frame, spec))
        if len(selected) >= 6:
            break
    return sorted(
        selected,
        key=lambda item: (
            {"candidate": 2, "watch": 1, "reject": 0}.get(item.get("status"), 0),
            (item.get("test") or {}).get("total_net_return", 0.0),
        ),
        reverse=True,
    )


def _mined_rule_mechanism(
    conditions: tuple[RuleCondition, ...],
    direction: str,
) -> str:
    features = {condition.feature for condition in conditions}
    if direction == "long" and "relative_volume_time_20" in features and "vwap_dev" in features:
        return "Abnormal same-time volume below VWAP may mark a temporary liquidity shock and rebound."
    if direction == "long" and {"ema9_ema21_spread_pct", "relative_volume_time_20"} <= features:
        return "Negative trend separation with abnormal participation may identify an exhaustion rebound."
    if direction == "long" and ("bb_percent_b" in features or "bb_z" in features):
        return "A lower volatility-envelope extreme is tested as a ticker-specific mean-reversion entry."
    if direction == "short" and {"ema9_ema21_spread_pct", "volume_ratio_20"} <= features:
        return "An extended positive trend with depleted current volume may be vulnerable to reversal."
    return "A transparent ticker-specific rule selected from training quantiles; mechanism requires review before promotion."


def _stock_research_profile(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {
            "eligible": False,
            "reasons": ["no regular-session bars"],
            "sessions": 0,
        }
    grouped = frame.groupby("date", sort=True)
    bars_per_session = grouped.size()
    close = pd.to_numeric(frame["close"], errors="coerce")
    volume = pd.to_numeric(frame["volume"], errors="coerce").fillna(0.0)
    turnover = pd.to_numeric(frame.get("turnover", 0.0), errors="coerce").fillna(0.0)
    dollar_value = turnover.where(turnover > 0, close * volume)
    daily_dollar_value = dollar_value.groupby(frame["date"]).sum()
    atr_pct = pd.to_numeric(frame.get("atr14_pct"), errors="coerce").dropna()
    reasons = []
    sessions = int(bars_per_session.size)
    median_bars = float(bars_per_session.median())
    median_daily_dollar_value = float(daily_dollar_value.median() or 0.0)
    if sessions < 60:
        reasons.append("fewer than 60 complete research sessions")
    if median_bars < 120:
        reasons.append("incomplete regular-session bar coverage")
    if median_daily_dollar_value < 5_000_000:
        reasons.append("median daily traded value below $5M research floor")
    return {
        "eligible": not reasons,
        "reasons": reasons,
        "sessions": sessions,
        "median_bars_per_session": median_bars,
        "median_price": float(close.median()),
        "median_daily_dollar_value": median_daily_dollar_value,
        "median_atr_pct": float(atr_pct.median()) if not atr_pct.empty else 0.0,
        "high_volatility_atr_pct": float(atr_pct.quantile(0.75)) if not atr_pct.empty else 0.0,
        "execution_caveat": "OHLCV eligibility does not replace bid/ask spread, borrow, halt, and actual execution-ticker checks.",
    }


def _research_markdown(payload: dict[str, Any]) -> str:
    mining = payload.get("rule_mining") or {}
    industry = payload.get("industry_strategies") or {}
    lines = [
        f"# {payload.get('ticker', '-')} Intraday Strategy Research",
        "",
        f"- Generated: {payload.get('generated_at', '-')}",
        f"- Interval: {payload.get('interval_minutes', '-')} minutes",
        f"- Rows: {payload.get('rows', 0)}",
        f"- Sessions: {len(payload.get('dates') or [])}",
        f"- Turning points: {payload.get('turn_counts') or {}}",
        "",
        "## Strongest Pre-Trough Features",
        "",
    ]
    for item in (payload.get("pre_trough_features") or [])[:10]:
        lines.append(
            f"- `{item['feature']}`: event median {_compact_number(item['event_median'])}, "
            f"baseline {_compact_number(item['baseline_median'])}, "
            f"standardized difference {item['standardized_difference']:.2f}."
        )
    lines.extend(["", "## Strongest Pre-Peak Features", ""])
    for item in (payload.get("pre_peak_features") or [])[:10]:
        lines.append(
            f"- `{item['feature']}`: event median {_compact_number(item['event_median'])}, "
            f"baseline {_compact_number(item['baseline_median'])}, "
            f"standardized difference {item['standardized_difference']:.2f}."
        )
    lines.extend(["", "## Rule Candidates", ""])
    for item in (mining.get("candidates") or [])[:15]:
        train = item["train"]
        test = item["test"]
        direction = str(item.get("direction") or "long").upper()
        stability = item.get("threshold_stability") or {}
        stability_text = (
            f", neighboring thresholds {int(stability.get('positive_neighbors', 0))}/"
            f"{int(stability.get('evaluated_neighbors', 0))} positive"
            if stability
            else ""
        )
        lines.append(
            f"- **{item['status'].upper()} {direction}** `{item['rule']}` — "
            f"train {train['trades']} trades, {train['win_rate']:.1%} win, {train['total_net_return']:.2%} net; "
            f"test {test['trades']} trades, {test['win_rate']:.1%} win, {test['total_net_return']:.2%} net, "
            f"PF {test['profit_factor']:.2f}{stability_text}."
        )
    lines.extend(["", "## Industry Strategy Archetypes", ""])
    for item in (industry.get("candidates") or [])[:20]:
        train = item["train"]
        test = item["test"]
        walk_forward = item.get("walk_forward") or {}
        lines.append(
            f"- **{item['status'].upper()} {item['direction'].upper()}** `{item['label']}` — "
            f"train {train['trades']} trades, {train['win_rate']:.1%} win, {train['total_net_return']:.2%} net; "
            f"test {test['trades']} trades, {test['win_rate']:.1%} win, {test['total_net_return']:.2%} net, "
            f"PF {test['profit_factor']:.2f}, {test['trades_per_active_day']:.2f} trades/active day; "
            f"walk-forward positive folds {walk_forward.get('positive_fold_rate', 0):.0%}."
        )
    lines.extend(["", "## Individually Tuned Rules", ""])
    for item in payload.get("individual_tuning") or []:
        train = item.get("train") or {}
        test = item.get("test") or {}
        lines.append(
            f"- **{item.get('status', 'reject').upper()} {item.get('direction', '').upper()}** "
            f"`{item.get('rule', '-')}` — "
            f"train {train.get('trades', 0)} trades, {train.get('total_net_return', 0):.2%} net, "
            f"PF {train.get('profit_factor', 0):.2f}; "
            f"test {test.get('trades', 0)} trades, {test.get('win_rate', 0):.1%} win, "
            f"{test.get('total_net_return', 0):.2%} net, PF {test.get('profit_factor', 0):.2f}; "
            f"{item.get('positive_time_blocks', 0)}/{len(item.get('time_blocks') or [])} positive blocks; "
            f"posture `{item.get('current_posture', 'reject')}`."
        )
    lines.extend(
        [
            "",
            "## Interpretation Guardrail",
            "",
            "These are research candidates, not trade recommendations. Promotion requires additional walk-forward folds, "
            "neighboring-threshold stability, and execution checks using the actual ticker pair.",
            "",
        ]
    )
    return "\n".join(lines)


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _compact_number(value: float) -> str:
    if abs(value) >= 100:
        return f"{value:.1f}"
    if abs(value) >= 1:
        return f"{value:.2f}"
    return f"{value:.4f}"


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    raise TypeError(f"Cannot serialize {type(value).__name__}")
