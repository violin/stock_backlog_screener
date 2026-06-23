from __future__ import annotations

import itertools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .strategy_research import RuleCondition, backtest_signal


@dataclass(frozen=True)
class RuleStrategySpec:
    id: str
    label: str
    direction: str
    conditions: tuple[RuleCondition, ...]
    mechanism: str
    entry_neighbor_rate: float = 0.0


def tune_individual_strategy(
    frame: pd.DataFrame,
    spec: RuleStrategySpec,
    *,
    train_fraction: float = 0.7,
    round_trip_cost: float = 0.001,
) -> dict[str, Any]:
    dates = sorted(str(value) for value in frame["date"].dropna().unique())
    split_index = min(max(1, int(len(dates) * train_fraction)), max(1, len(dates) - 1))
    train_dates = dates[:split_index]
    test_dates = dates[split_index:]
    train = frame[frame["date"].isin(train_dates)]
    test = frame[frame["date"].isin(test_dates)]
    signal = _condition_signal(frame, spec.conditions)
    best = None
    for target, stop, hold, cooldown, max_trades in itertools.product(
        (0.01, 0.015, 0.02),
        (0.006, 0.008, 0.01),
        (5, 8, 12),
        (2, 4),
        (2, 3),
    ):
        metrics = backtest_signal(
            train,
            signal,
            direction=spec.direction,
            target_return=target,
            stop_return=stop,
            max_hold_bars=hold,
            round_trip_cost=round_trip_cost,
            cooldown_bars=cooldown,
            max_trades_per_day=max_trades,
        )
        if metrics["trades"] < 20:
            continue
        score = _train_execution_score(metrics)
        if best is None or score > best["score"]:
            best = {
                "score": score,
                "execution": {
                    "target_return": target,
                    "stop_return": stop,
                    "max_hold_bars": hold,
                    "cooldown_bars": cooldown,
                    "max_trades_per_day": max_trades,
                    "round_trip_cost": round_trip_cost,
                },
                "train": metrics,
            }
    if best is None:
        return {
            "id": spec.id,
            "label": spec.label,
            "direction": spec.direction,
            "status": "reject",
            "reason": "No execution parameter set produced at least 20 training trades.",
        }
    execution = best["execution"]
    test_metrics = _run_execution(test, signal, spec.direction, execution)
    time_blocks = []
    for start in range(0, len(dates), 14):
        block_dates = dates[start : start + 14]
        if len(block_dates) < 10:
            continue
        block = frame[frame["date"].isin(block_dates)]
        metrics = _run_execution(block, signal, spec.direction, execution)
        time_blocks.append(
            {
                "start": block_dates[0],
                "end": block_dates[-1],
                "metrics": _summary_metrics(metrics),
            }
        )
    positive_blocks = [
        block
        for block in time_blocks
        if block["metrics"]["trades"] > 0
        and block["metrics"]["total_net_return"] > 0
        and block["metrics"]["profit_factor"] >= 1.0
    ]
    block_rate = len(positive_blocks) / len(time_blocks) if time_blocks else 0.0
    status = _individual_status(
        best["train"],
        test_metrics,
        positive_block_rate=block_rate,
        entry_neighbor_rate=spec.entry_neighbor_rate,
    )
    latest = time_blocks[-1]["metrics"] if time_blocks else {}
    if status == "candidate" and latest.get("total_net_return", 0.0) > 0:
        current_posture = "enabled_for_paper_validation"
    elif status == "watch" and latest.get("total_net_return", 0.0) > 0:
        current_posture = "watch_sample_size"
    elif status in {"candidate", "watch"}:
        current_posture = "watch_current_regime"
    else:
        current_posture = "reject"
    return {
        "id": spec.id,
        "label": spec.label,
        "direction": spec.direction,
        "conditions": [condition.to_dict() for condition in spec.conditions],
        "rule": " & ".join(condition.label() for condition in spec.conditions),
        "mechanism": spec.mechanism,
        "entry_neighbor_rate": spec.entry_neighbor_rate,
        "execution": execution,
        "train_dates": train_dates,
        "test_dates": test_dates,
        "train": _summary_metrics(best["train"]),
        "test": _summary_metrics(test_metrics),
        "time_blocks": time_blocks,
        "positive_time_blocks": len(positive_blocks),
        "positive_time_block_rate": block_rate,
        "status": status,
        "current_posture": current_posture,
    }


def write_individual_strategy_report(
    payload: dict[str, Any],
    *,
    output_dir: Path,
    stem: str,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{stem}.json"
    markdown_path = output_dir / f"{stem}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_individual_markdown(payload), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(markdown_path)}


def _condition_signal(frame: pd.DataFrame, conditions: tuple[RuleCondition, ...]) -> pd.Series:
    signal = pd.Series(True, index=frame.index)
    for condition in conditions:
        signal &= condition.matches(frame).fillna(False)
    return signal


def _run_execution(
    frame: pd.DataFrame,
    signal: pd.Series,
    direction: str,
    execution: dict[str, Any],
) -> dict[str, Any]:
    return backtest_signal(
        frame,
        signal,
        direction=direction,
        target_return=execution["target_return"],
        stop_return=execution["stop_return"],
        max_hold_bars=execution["max_hold_bars"],
        round_trip_cost=execution["round_trip_cost"],
        cooldown_bars=execution["cooldown_bars"],
        max_trades_per_day=execution["max_trades_per_day"],
    )


def _train_execution_score(metrics: dict[str, Any]) -> float:
    return (
        metrics["total_net_return"] * 8
        + min(metrics["profit_factor"], 4.0) * 0.25
        + metrics["win_rate_wilson_lower"]
        - abs(metrics["trades_per_active_day"] - 2.5) * 0.08
        - metrics["largest_day_abs_pnl_share"] * 0.2
    )


def _individual_status(
    train: dict[str, Any],
    test: dict[str, Any],
    *,
    positive_block_rate: float,
    entry_neighbor_rate: float,
) -> str:
    common = (
        train["total_net_return"] > 0
        and test["total_net_return"] > 0
        and test["profitable_day_rate"] >= 0.55
        and 0.5 <= test["trades_per_active_day"] <= 3.5
        and test["largest_day_abs_pnl_share"] <= 0.35
        and entry_neighbor_rate >= 2 / 3
    )
    if (
        common
        and train["trades"] >= 30
        and test["trades"] >= 12
        and train["profit_factor"] >= 1.3
        and test["profit_factor"] >= 1.3
        and positive_block_rate >= 0.75
    ):
        return "candidate"
    if (
        common
        and train["trades"] >= 20
        and test["trades"] >= 10
        and train["profit_factor"] >= 1.15
        and test["profit_factor"] >= 1.15
        and positive_block_rate >= 0.6
    ):
        return "watch"
    return "reject"


def _summary_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in metrics.items()
        if key not in {"daily_returns", "trade_returns"}
    }


def _individual_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload.get('ticker', '-')} Individual Strategy Tuning",
        "",
        f"- Sessions: {payload.get('sessions', 0)}",
        "- Execution parameters are selected on the chronological training segment only.",
        "- The final test segment is not used to choose exits.",
        "",
    ]
    for item in payload.get("strategies") or []:
        lines.extend(
            [
                f"## {item.get('status', 'reject').upper()} - {item.get('label', item.get('id', '-'))}",
                "",
                f"- Direction: {item.get('direction', '-')}",
                f"- Rule: `{item.get('rule', '-')}`",
                f"- Mechanism: {item.get('mechanism', '-')}",
                f"- Current posture: `{item.get('current_posture', 'reject')}`",
                f"- Entry-neighbor stability: {item.get('entry_neighbor_rate', 0):.0%}",
            ]
        )
        if item.get("execution"):
            execution = item["execution"]
            lines.append(
                f"- Execution: target {execution['target_return']:.2%}, stop {execution['stop_return']:.2%}, "
                f"hold {execution['max_hold_bars']} bars, cooldown {execution['cooldown_bars']} bars, "
                f"max {execution['max_trades_per_day']} trades/day."
            )
        for split in ("train", "test"):
            metrics = item.get(split) or {}
            if not metrics:
                continue
            lines.append(
                f"- {split.title()}: {metrics.get('trades', 0)} trades, "
                f"{metrics.get('win_rate', 0):.1%} win, "
                f"{metrics.get('total_net_return', 0):.2%} net, "
                f"PF {metrics.get('profit_factor', 0):.2f}, "
                f"{metrics.get('profitable_day_rate', 0):.1%} profitable days, "
                f"{metrics.get('trades_per_active_day', 0):.2f} trades/active day."
            )
        lines.append(
            f"- Time blocks: {item.get('positive_time_blocks', 0)}/{len(item.get('time_blocks') or [])} positive."
        )
        if item.get("time_blocks"):
            latest = item["time_blocks"][-1]
            metrics = latest["metrics"]
            lines.append(
                f"- Latest block {latest['start']} to {latest['end']}: "
                f"{metrics.get('trades', 0)} trades, {metrics.get('total_net_return', 0):.2%} net, "
                f"PF {metrics.get('profit_factor', 0):.2f}."
            )
        lines.append("")
    lines.extend(
        [
            "## Guardrail",
            "",
            "Candidate status authorizes paper validation only. Long rules still require actual bid/ask and slippage checks. "
            "Short rules additionally require borrow availability or a validated inverse execution instrument.",
            "",
        ]
    )
    return "\n".join(lines)
