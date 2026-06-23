from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .strategy_research import RuleCondition, backtest_signal


@dataclass(frozen=True)
class FixedStrategy:
    id: str
    label: str
    direction: str
    conditions: tuple[RuleCondition, ...]
    target_return: float
    stop_return: float
    max_hold_bars: int
    cooldown_bars: int
    max_trades_per_day: int
    mechanism: str


def validate_fixed_strategy(
    frame: pd.DataFrame,
    strategy: FixedStrategy,
    *,
    round_trip_cost: float = 0.001,
    block_sessions: int = 20,
    named_segments: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    dates = sorted(str(value) for value in frame["date"].dropna().unique())
    signal = strategy_signal(frame, strategy)
    execution = {
        "target_return": strategy.target_return,
        "stop_return": strategy.stop_return,
        "max_hold_bars": strategy.max_hold_bars,
        "cooldown_bars": strategy.cooldown_bars,
        "max_trades_per_day": strategy.max_trades_per_day,
        "round_trip_cost": round_trip_cost,
    }
    full = _run(frame, signal, strategy, execution)
    blocks = []
    for offset in range(0, len(dates), max(1, int(block_sessions))):
        block_dates = dates[offset : offset + max(1, int(block_sessions))]
        if len(block_dates) < max(5, block_sessions // 2):
            continue
        block_frame = frame[frame["date"].isin(block_dates)]
        blocks.append(
            {
                "start": block_dates[0],
                "end": block_dates[-1],
                "sessions": len(block_dates),
                "metrics": _summary_metrics(_run(block_frame, signal, strategy, execution)),
            }
        )
    segments = []
    for segment in named_segments or []:
        start = str(segment["start"])
        end = str(segment["end"])
        segment_frame = frame[(frame["date"] >= start) & (frame["date"] <= end)]
        segments.append(
            {
                "name": segment["name"],
                "start": start,
                "end": end,
                "sessions": int(segment_frame["date"].nunique()),
                "metrics": _summary_metrics(_run(segment_frame, signal, strategy, execution)),
            }
        )
    positive_blocks = [
        block
        for block in blocks
        if block["metrics"]["trades"] > 0
        and block["metrics"]["total_net_return"] > 0
        and block["metrics"]["profit_factor"] >= 1.0
    ]
    return {
        "id": strategy.id,
        "label": strategy.label,
        "direction": strategy.direction,
        "rule": " & ".join(condition.label() for condition in strategy.conditions),
        "conditions": [condition.to_dict() for condition in strategy.conditions],
        "mechanism": strategy.mechanism,
        "execution": execution,
        "sessions": len(dates),
        "date_start": dates[0] if dates else None,
        "date_end": dates[-1] if dates else None,
        "signal_bars": int(signal.sum()),
        "full": _summary_metrics(full),
        "segments": segments,
        "blocks": blocks,
        "positive_blocks": len(positive_blocks),
        "positive_block_rate": len(positive_blocks) / len(blocks) if blocks else 0.0,
    }


def strategy_signal(frame: pd.DataFrame, strategy: FixedStrategy) -> pd.Series:
    signal = pd.Series(True, index=frame.index)
    for condition in strategy.conditions:
        signal &= condition.matches(frame).fillna(False)
    return signal


def signal_overlap(
    frame: pd.DataFrame,
    left: FixedStrategy,
    right: FixedStrategy,
) -> dict[str, Any]:
    left_signal = strategy_signal(frame, left)
    right_signal = strategy_signal(frame, right)
    both = left_signal & right_signal
    union = left_signal | right_signal
    return {
        "left_signal_bars": int(left_signal.sum()),
        "right_signal_bars": int(right_signal.sum()),
        "overlap_signal_bars": int(both.sum()),
        "overlap_vs_left": float(both.sum() / left_signal.sum()) if left_signal.sum() else 0.0,
        "overlap_vs_right": float(both.sum() / right_signal.sum()) if right_signal.sum() else 0.0,
        "jaccard": float(both.sum() / union.sum()) if union.sum() else 0.0,
    }


def write_fixed_validation_report(
    payload: dict[str, Any],
    *,
    output_dir: Path,
    stem: str,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{stem}.json"
    markdown_path = output_dir / f"{stem}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_validation_markdown(payload), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(markdown_path)}


def _run(
    frame: pd.DataFrame,
    signal: pd.Series,
    strategy: FixedStrategy,
    execution: dict[str, Any],
) -> dict[str, Any]:
    return backtest_signal(
        frame,
        signal,
        direction=strategy.direction,
        target_return=execution["target_return"],
        stop_return=execution["stop_return"],
        max_hold_bars=execution["max_hold_bars"],
        round_trip_cost=execution["round_trip_cost"],
        cooldown_bars=execution["cooldown_bars"],
        max_trades_per_day=execution["max_trades_per_day"],
    )


def _summary_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in metrics.items()
        if key not in {"daily_returns", "trade_returns"}
    }


def _validation_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload.get('title', 'Fixed Strategy Validation')}",
        "",
        f"- Generated: {payload.get('generated_at', '-')}",
        "- Entry thresholds and execution parameters are frozen from the MRVL discovery run.",
        "- Earlier-than-discovery history is a backward robustness check, not true forward out-of-sample evidence.",
        "",
    ]
    if payload.get("interpretation"):
        lines.extend(
            [
                "## Test Scope",
                "",
                payload["interpretation"],
                "",
            ]
        )
    if payload.get("overlap"):
        overlap = payload["overlap"]
        lines.extend(
            [
                "## Signal Overlap",
                "",
                f"- Raw signal overlap: {overlap.get('overlap_signal_bars', 0)} bars.",
                f"- Overlap versus primary: {overlap.get('overlap_vs_left', 0):.1%}.",
                f"- Overlap versus secondary: {overlap.get('overlap_vs_right', 0):.1%}.",
                "",
            ]
        )
    if payload.get("ticker_overlaps"):
        lines.extend(["## Signal Overlap by Ticker", ""])
        for ticker, overlap in payload["ticker_overlaps"].items():
            lines.append(
                f"- {ticker}: {overlap.get('overlap_signal_bars', 0)} overlapping bars; "
                f"{overlap.get('overlap_vs_left', 0):.1%} of primary and "
                f"{overlap.get('overlap_vs_right', 0):.1%} of secondary signals."
            )
        lines.append("")
    for result in payload.get("strategies") or []:
        metrics = result["full"]
        lines.extend(
            [
                f"## {result['label']}",
                "",
                f"- Ticker: {result.get('ticker', payload.get('ticker', '-'))}",
                f"- Rule: `{result['rule']}`",
                f"- Mechanism: {result['mechanism']}",
                f"- Range: {result['date_start']} to {result['date_end']} ({result['sessions']} sessions).",
                f"- Full: {metrics['trades']} trades, {metrics['win_rate']:.1%} win, "
                f"{metrics['total_net_return']:.2%} net, PF {metrics['profit_factor']:.2f}, "
                f"{metrics['profitable_day_rate']:.1%} profitable days, "
                f"{metrics['trades_per_active_day']:.2f} trades/active day.",
                f"- Rolling blocks: {result['positive_blocks']}/{len(result['blocks'])} positive.",
                "",
            ]
        )
        for segment in result.get("segments") or []:
            segment_metrics = segment["metrics"]
            lines.append(
                f"- **{segment['name']}** ({segment['sessions']} sessions): "
                f"{segment_metrics['trades']} trades, {segment_metrics['win_rate']:.1%} win, "
                f"{segment_metrics['total_net_return']:.2%} net, PF {segment_metrics['profit_factor']:.2f}."
            )
        lines.append("")
    lines.extend(
        [
            "## Guardrail",
            "",
            "Returns are signal-ticker OHLC simulations with a 10 bps round-trip cost. "
            "They are not broker-fill results. Promotion still requires actual bid/ask, slippage, "
            "and live paper validation.",
            "",
        ]
    )
    return "\n".join(lines)
