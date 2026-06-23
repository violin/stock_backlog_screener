from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .strategy_research import backtest_signal


INDUSTRY_STRATEGY_REFERENCES = [
    {
        "id": "intraday_momentum",
        "title": "Intraday Momentum: The First Half-Hour Return Predicts the Last Half-Hour Return",
        "url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2552752",
        "use": "Opening return as a directional filter for the final half-hour.",
    },
    {
        "id": "liquidity_reversal",
        "title": "Evaporating Liquidity",
        "url": "https://www.nber.org/papers/w17653",
        "use": "Short-horizon reversal as compensation for liquidity provision; condition on volatility and flow.",
    },
    {
        "id": "opening_range_breakout",
        "title": "A Profitable Day Trading Strategy for the U.S. Equity Market",
        "url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4729284",
        "use": "Opening-range breakout template, treated as a working-paper hypothesis.",
    },
    {
        "id": "bollinger",
        "title": "Bollinger Band Rules",
        "url": "https://www.bollingerbands.com/bollinger-band-rules",
        "use": "Relative high/low, bandwidth compression, and confirmation with independent indicators.",
    },
    {
        "id": "pairs",
        "title": "Pairs Trading: Performance of a Relative-Value Arbitrage Rule",
        "url": "https://academic.oup.com/rfs/article-abstract/19/3/797/1646694",
        "use": "Future benchmark/pair extension; not evaluated without synchronized comparison data.",
    },
]


@dataclass(frozen=True)
class StrategyVariant:
    id: str
    family: str
    label: str
    direction: str
    params: dict[str, Any]
    target_return: float
    stop_return: float
    max_hold_bars: int
    cooldown_bars: int
    max_trades_per_day: int
    mechanism: str
    evidence: str


def evaluate_industry_strategies(
    frame: pd.DataFrame,
    *,
    train_fraction: float = 0.7,
    round_trip_cost: float = 0.001,
) -> dict[str, Any]:
    if frame.empty:
        return {"references": INDUSTRY_STRATEGY_REFERENCES, "candidates": [], "families": []}
    working = frame.copy()
    working["time"] = pd.to_datetime(working["time"], errors="coerce")
    dates = sorted(str(value) for value in working["date"].dropna().unique())
    split_index = min(max(1, int(len(dates) * train_fraction)), max(1, len(dates) - 1))
    train_dates = dates[:split_index]
    test_dates = dates[split_index:]
    train = working[working["date"].isin(train_dates)]
    test = working[working["date"].isin(test_dates)]
    variants = _strategy_variants()
    candidates = []
    for variant in variants:
        signal = build_archetype_signal(working, variant)
        train_metrics = _run_variant(train, signal, variant, round_trip_cost)
        test_metrics = _run_variant(test, signal, variant, round_trip_cost)
        walk_forward = _walk_forward(working, signal, variant, round_trip_cost)
        score = _variant_score(train_metrics, test_metrics, walk_forward)
        status = _variant_status(train_metrics, test_metrics, walk_forward)
        candidates.append(
            {
                "id": variant.id,
                "family": variant.family,
                "label": variant.label,
                "direction": variant.direction,
                "params": variant.params,
                "mechanism": variant.mechanism,
                "evidence": variant.evidence,
                "train": _summary_metrics(train_metrics),
                "test": _summary_metrics(test_metrics),
                "walk_forward": walk_forward,
                "score": score,
                "status": status,
            }
        )
    family_rows = []
    for (family, direction), group in _group_candidates(candidates).items():
        robust = [
            item
            for item in group
            if item["train"]["trades"] >= 20
            and item["test"]["trades"] >= 12
            and item["train"]["total_net_return"] > 0
            and item["test"]["total_net_return"] > 0
            and item["train"]["profit_factor"] >= 1.0
            and item["test"]["profit_factor"] >= 1.2
            and item["walk_forward"]["positive_fold_rate"] >= 0.5
        ]
        robust_rate = len(robust) / len(group)
        for item in group:
            item["family_parameter_stability"] = robust_rate
            if item["status"] == "candidate" and robust_rate < 0.3:
                item["status"] = "experiment"
        family_rows.append(
            {
                "family": family,
                "direction": direction,
                "variants": len(group),
                "robust_variants": len(robust),
                "robust_variant_rate": robust_rate,
                "best_variant_id": max(group, key=lambda item: item["score"])["id"],
            }
        )
    candidates.sort(key=lambda item: item["score"], reverse=True)
    return {
        "references": INDUSTRY_STRATEGY_REFERENCES,
        "assumptions": {
            "train_fraction": train_fraction,
            "round_trip_cost": round_trip_cost,
            "entry": "next 3-minute bar open",
            "same_bar_collision": "stop before target",
            "walk_forward": "35-session initial train, then 12-session expanding test folds",
        },
        "train_dates": train_dates,
        "test_dates": test_dates,
        "families": sorted(family_rows, key=lambda item: (item["family"], item["direction"])),
        "candidates": candidates,
    }


def build_archetype_signal(frame: pd.DataFrame, variant: StrategyVariant) -> pd.Series:
    signal = pd.Series(False, index=frame.index)
    for _, day in frame.groupby("date", sort=True):
        local = _day_signal(day.sort_values("time"), variant)
        signal.loc[local.index] = local
    return signal


def _day_signal(day: pd.DataFrame, variant: StrategyVariant) -> pd.Series:
    close = pd.to_numeric(day["close"], errors="coerce")
    high = pd.to_numeric(day["high"], errors="coerce")
    low = pd.to_numeric(day["low"], errors="coerce")
    volume_ratio = pd.to_numeric(day.get("volume_ratio_20"), errors="coerce")
    volume_z = pd.to_numeric(day.get("volume_z_20"), errors="coerce")
    minute = pd.to_numeric(day["session_minute"], errors="coerce")
    direction_sign = 1 if variant.direction == "long" else -1
    params = variant.params

    if variant.family == "opening_range_breakout":
        opening_bars = max(1, int(params["opening_minutes"]) // 3)
        opening_high = float(high.iloc[:opening_bars].max())
        opening_low = float(low.iloc[:opening_bars].min())
        threshold = opening_high if variant.direction == "long" else opening_low
        crossed = (
            (close > threshold) & (close.shift(1) <= threshold)
            if variant.direction == "long"
            else (close < threshold) & (close.shift(1) >= threshold)
        )
        trend = (
            pd.to_numeric(day["ema9"], errors="coerce") > pd.to_numeric(day["ema21"], errors="coerce")
            if variant.direction == "long"
            else pd.to_numeric(day["ema9"], errors="coerce") < pd.to_numeric(day["ema21"], errors="coerce")
        )
        return (
            crossed
            & (minute >= params["opening_minutes"])
            & (minute <= 240)
            & (
                pd.to_numeric(day["opening_relative_volume_15"], errors="coerce")
                >= params["opening_relative_volume_min"]
            )
            & (
                pd.to_numeric(day["gap_pct"], errors="coerce").abs()
                >= params["gap_min"]
            )
            & (trend if params["trend_filter"] else True)
        ).fillna(False)

    if variant.family == "late_day_intraday_momentum":
        opening_bars = 10
        first_return = close.iloc[min(opening_bars - 1, len(close) - 1)] / float(day["open"].iloc[0]) - 1
        directional = first_return * direction_sign >= params["opening_return_min"]
        trigger_bar = (minute >= 360) & (minute < 363)
        volatility = pd.to_numeric(day["realized_vol_20"], errors="coerce")
        vol_gate = volatility >= volatility.expanding(min_periods=20).median()
        return (trigger_bar & directional & vol_gate).fillna(False)

    if variant.family == "liquidity_exhaustion_reversal":
        band = pd.to_numeric(day["bb_percent_b"], errors="coerce")
        rsi = pd.to_numeric(day["rsi6"], errors="coerce")
        macd_delta = pd.to_numeric(day["macd_hist_delta_1"], errors="coerce")
        if variant.direction == "long":
            location = (band <= params["band_threshold"]) & (rsi <= params["rsi_threshold"])
            confirmation = macd_delta > 0
        else:
            location = (band >= 1 - params["band_threshold"]) & (rsi >= 100 - params["rsi_threshold"])
            confirmation = macd_delta < 0
        raw = location & (volume_z >= params["volume_z_min"]) & minute.between(18, 330)
        return (raw & confirmation if params["confirmation"] else raw).fillna(False)

    if variant.family == "vwap_reclaim":
        vwap = pd.to_numeric(day["vwap"], errors="coerce")
        rsi = pd.to_numeric(day["rsi14"], errors="coerce")
        ema_slope = pd.to_numeric(day["ema9_slope_3bar"], errors="coerce")
        if variant.direction == "long":
            crossed = (close >= vwap) & (close.shift(1) < vwap.shift(1))
            momentum = (rsi <= params["rsi_bound"]) & (ema_slope > 0)
        else:
            crossed = (close <= vwap) & (close.shift(1) > vwap.shift(1))
            momentum = (rsi >= 100 - params["rsi_bound"]) & (ema_slope < 0)
        return (
            crossed
            & momentum
            & (volume_ratio >= params["volume_min"])
            & minute.between(18, 300)
        ).fillna(False)

    if variant.family == "bollinger_squeeze_breakout":
        mid = pd.to_numeric(day["bb_mid20"], errors="coerce")
        upper = pd.to_numeric(day["bb_upper20"], errors="coerce")
        lower = pd.to_numeric(day["bb_lower20"], errors="coerce")
        bandwidth = (upper - lower) / mid.replace(0, np.nan)
        threshold = bandwidth.rolling(50, min_periods=30).quantile(params["squeeze_quantile"])
        prior_squeeze = bandwidth.shift(1) <= threshold.shift(1)
        prior_high = high.shift(1).rolling(10, min_periods=8).max()
        prior_low = low.shift(1).rolling(10, min_periods=8).min()
        breakout = close > prior_high if variant.direction == "long" else close < prior_low
        trend = (
            pd.to_numeric(day["ema9"], errors="coerce") > pd.to_numeric(day["ema21"], errors="coerce")
            if variant.direction == "long"
            else pd.to_numeric(day["ema9"], errors="coerce") < pd.to_numeric(day["ema21"], errors="coerce")
        )
        return (
            prior_squeeze
            & breakout
            & trend
            & (volume_ratio >= params["volume_min"])
            & minute.between(30, 300)
        ).fillna(False)

    if variant.family == "trend_pullback_reclaim":
        ema9 = pd.to_numeric(day["ema9"], errors="coerce")
        ema21 = pd.to_numeric(day["ema21"], errors="coerce")
        ema50 = pd.to_numeric(day["ema50"], errors="coerce")
        rsi = pd.to_numeric(day["rsi14"], errors="coerce")
        if variant.direction == "long":
            trend = (ema9 > ema21) & (ema21 > ema50)
            reclaimed = (close >= ema9) & (close.shift(1) < ema9.shift(1))
            rsi_gate = rsi.between(params["rsi_low"], params["rsi_high"])
        else:
            trend = (ema9 < ema21) & (ema21 < ema50)
            reclaimed = (close <= ema9) & (close.shift(1) > ema9.shift(1))
            rsi_gate = rsi.between(100 - params["rsi_high"], 100 - params["rsi_low"])
        return (
            trend
            & reclaimed
            & rsi_gate
            & (volume_ratio >= params["volume_min"])
            & minute.between(30, 300)
        ).fillna(False)

    raise ValueError(f"Unsupported strategy family: {variant.family}")


def _run_variant(
    frame: pd.DataFrame,
    signal: pd.Series,
    variant: StrategyVariant,
    round_trip_cost: float,
) -> dict[str, Any]:
    return backtest_signal(
        frame,
        signal,
        direction=variant.direction,
        target_return=variant.target_return,
        stop_return=variant.stop_return,
        max_hold_bars=variant.max_hold_bars,
        round_trip_cost=round_trip_cost,
        cooldown_bars=variant.cooldown_bars,
        max_trades_per_day=variant.max_trades_per_day,
    )


def _walk_forward(
    frame: pd.DataFrame,
    signal: pd.Series,
    variant: StrategyVariant,
    round_trip_cost: float,
) -> dict[str, Any]:
    dates = sorted(str(value) for value in frame["date"].dropna().unique())
    initial_train = min(35, max(20, len(dates) // 2))
    test_size = 12
    folds = []
    test_start = initial_train
    while test_start < len(dates):
        test_dates = dates[test_start : test_start + test_size]
        if len(test_dates) < 6:
            break
        test_frame = frame[frame["date"].isin(test_dates)]
        metrics = _run_variant(test_frame, signal, variant, round_trip_cost)
        folds.append(
            {
                "train_start": dates[0],
                "train_end": dates[test_start - 1],
                "test_start": test_dates[0],
                "test_end": test_dates[-1],
                "metrics": _summary_metrics(metrics),
            }
        )
        test_start += test_size
    positive = [
        fold
        for fold in folds
        if fold["metrics"]["total_net_return"] > 0 and fold["metrics"]["profit_factor"] >= 1.0
    ]
    return {
        "fold_count": len(folds),
        "positive_folds": len(positive),
        "positive_fold_rate": len(positive) / len(folds) if folds else 0.0,
        "total_net_return": sum(fold["metrics"]["total_net_return"] for fold in folds),
        "folds": folds,
    }


def _summary_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in metrics.items()
        if key not in {"daily_returns", "trade_returns"}
    }


def _variant_score(train: dict[str, Any], test: dict[str, Any], walk_forward: dict[str, Any]) -> float:
    frequency = float(test.get("trades_per_active_day") or 0.0)
    frequency_penalty = abs(frequency - 2.5) * 0.08
    concentration_penalty = max(0.0, float(test.get("largest_day_abs_pnl_share") or 0.0) - 0.25)
    degradation = abs(float(train.get("win_rate") or 0.0) - float(test.get("win_rate") or 0.0))
    return (
        float(test.get("total_net_return") or 0.0) * 8
        + min(float(train.get("total_net_return") or 0.0), float(test.get("total_net_return") or 0.0)) * 4
        + min(float(test.get("profit_factor") or 0.0), 4.0) * 0.18
        + float(test.get("win_rate_wilson_lower") or 0.0)
        + float(walk_forward.get("positive_fold_rate") or 0.0) * 0.5
        - frequency_penalty
        - concentration_penalty
        - degradation
    )


def _variant_status(train: dict[str, Any], test: dict[str, Any], walk_forward: dict[str, Any]) -> str:
    if (
        train["trades"] >= 20
        and test["trades"] >= 12
        and train["total_net_return"] > 0
        and test["total_net_return"] > 0
        and train["profit_factor"] >= 1.15
        and test["profit_factor"] >= 1.2
        and walk_forward["positive_fold_rate"] >= 0.75
        and test["trades_per_active_day"] <= 4.0
        and test["largest_day_abs_pnl_share"] <= 0.35
    ):
        return "candidate"
    if (
        train["total_net_return"] > 0
        and test["total_net_return"] > 0
        and walk_forward["positive_fold_rate"] >= 0.5
    ):
        return "experiment"
    return "reject"


def _group_candidates(candidates: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for candidate in candidates:
        grouped.setdefault((candidate["family"], candidate["direction"]), []).append(candidate)
    return grouped


def _strategy_variants() -> list[StrategyVariant]:
    rows = []
    for direction in ("long", "short"):
        for opening_minutes in (15, 30):
            for opening_relative_volume_min in (1.0, 1.5):
                for gap_min in (0.0, 0.01):
                    rows.append(
                        _variant(
                            "opening_range_breakout",
                            direction,
                            {
                                "opening_minutes": opening_minutes,
                                "opening_relative_volume_min": opening_relative_volume_min,
                                "gap_min": gap_min,
                                "trend_filter": True,
                            },
                            target=0.015,
                            stop=0.008,
                            hold=15,
                            cooldown=4,
                            max_trades=2,
                            mechanism="Opening price discovery continues when a range break occurs in a stock with unusual same-time volume and trend confirmation.",
                            evidence="opening_range_breakout",
                        )
                    )
        for opening_return_min in (0.005, 0.01):
            rows.append(
                _variant(
                    "late_day_intraday_momentum",
                    direction,
                    {"opening_return_min": opening_return_min},
                    target=0.01,
                    stop=0.006,
                    hold=10,
                    cooldown=0,
                    max_trades=1,
                    mechanism="The first half-hour direction persists into the final half-hour on sufficiently active days.",
                    evidence="intraday_momentum",
                )
            )
        for volume_z_min in (1.0, 1.5):
            for confirmation in (False, True):
                rows.append(
                    _variant(
                        "liquidity_exhaustion_reversal",
                        direction,
                        {
                            "band_threshold": 0.1,
                            "rsi_threshold": 40,
                            "volume_z_min": volume_z_min,
                            "confirmation": confirmation,
                        },
                        target=0.012,
                        stop=0.008,
                        hold=10,
                        cooldown=4,
                        max_trades=2,
                        mechanism="A volume shock at a volatility-envelope extreme may compensate liquidity provision when momentum stabilizes.",
                        evidence="liquidity_reversal",
                    )
                )
        for volume_min in (0.8, 1.2):
            for rsi_bound in (50, 60):
                rows.append(
                    _variant(
                        "vwap_reclaim",
                        direction,
                        {"volume_min": volume_min, "rsi_bound": rsi_bound},
                        target=0.009,
                        stop=0.006,
                        hold=8,
                        cooldown=3,
                        max_trades=3,
                        mechanism="Price reclaims the session's volume-weighted anchor with improving short-term momentum.",
                        evidence="practitioner_hypothesis",
                    )
                )
        for squeeze_quantile in (0.2, 0.3):
            for volume_min in (1.0, 1.3):
                rows.append(
                    _variant(
                        "bollinger_squeeze_breakout",
                        direction,
                        {"squeeze_quantile": squeeze_quantile, "volume_min": volume_min},
                        target=0.015,
                        stop=0.008,
                        hold=15,
                        cooldown=4,
                        max_trades=2,
                        mechanism="Volatility compression is followed by a range break with trend and volume confirmation.",
                        evidence="bollinger",
                    )
                )
        for volume_min in (0.8, 1.2):
            rows.append(
                _variant(
                    "trend_pullback_reclaim",
                    direction,
                    {"rsi_low": 42, "rsi_high": 65, "volume_min": volume_min},
                    target=0.012,
                    stop=0.007,
                    hold=10,
                    cooldown=3,
                    max_trades=3,
                    mechanism="A mature intraday trend resumes after a controlled pullback to the fast average.",
                    evidence="trend_following_practitioner_hypothesis",
                )
            )
    return rows


def _variant(
    family: str,
    direction: str,
    params: dict[str, Any],
    *,
    target: float,
    stop: float,
    hold: int,
    cooldown: int,
    max_trades: int,
    mechanism: str,
    evidence: str,
) -> StrategyVariant:
    suffix = "-".join(f"{key}-{str(value).lower()}" for key, value in sorted(params.items()))
    return StrategyVariant(
        id=f"{family}-{direction}-{suffix}",
        family=family,
        label=f"{family.replace('_', ' ').title()} ({direction})",
        direction=direction,
        params=params,
        target_return=target,
        stop_return=stop,
        max_hold_bars=hold,
        cooldown_bars=cooldown,
        max_trades_per_day=max_trades,
        mechanism=mechanism,
        evidence=evidence,
    )
