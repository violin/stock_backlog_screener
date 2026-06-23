from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import median
from typing import Any


def compare_strategy_research(research_by_ticker: dict[str, dict[str, Any]]) -> dict[str, Any]:
    tickers = sorted(research_by_ticker)
    variants: dict[str, dict[str, Any]] = {}
    ticker_summaries = {}
    for ticker in tickers:
        research = research_by_ticker[ticker]
        candidates = (research.get("industry_strategies") or {}).get("candidates") or []
        ticker_summaries[ticker] = {
            "sessions": len(research.get("dates") or []),
            "rows": int(research.get("rows") or 0),
            "date_start": (research.get("dates") or [None])[0],
            "date_end": (research.get("dates") or [None])[-1],
            "stock_profile": research.get("stock_profile") or {},
            "top_candidates": [
                _ticker_candidate_summary(item)
                for item in sorted(
                    candidates,
                    key=lambda row: (
                        {"candidate": 2, "experiment": 1, "reject": 0}.get(row.get("status"), 0),
                        row.get("score") or 0.0,
                    ),
                    reverse=True,
                )[:10]
            ],
        }
        for candidate in candidates:
            variant = variants.setdefault(
                candidate["id"],
                {
                    "id": candidate["id"],
                    "family": candidate["family"],
                    "label": candidate["label"],
                    "direction": candidate["direction"],
                    "params": candidate["params"],
                    "mechanism": candidate["mechanism"],
                    "evidence": candidate["evidence"],
                    "tickers": {},
                },
            )
            variant["tickers"][ticker] = _ticker_candidate_summary(candidate)
    portable_candidates = []
    eligible_tickers = [
        ticker
        for ticker, summary in ticker_summaries.items()
        if _ticker_is_eligible(summary)
    ]
    excluded_tickers = [ticker for ticker in tickers if ticker not in eligible_tickers]
    for variant in variants.values():
        ticker_rows = [
            row
            for ticker, row in variant["tickers"].items()
            if ticker in eligible_tickers
        ]
        positive_both = [
            item
            for item in ticker_rows
            if _ticker_variant_is_robust(item)
        ]
        positive_test = [
            item
            for item in ticker_rows
            if item["test"]["trades"] >= 12 and item["test"]["total_net_return"] > 0
        ]
        test_returns = [item["test"]["total_net_return"] for item in ticker_rows]
        test_pfs = [item["test"]["profit_factor"] for item in ticker_rows]
        test_frequencies = [item["test"]["trades_per_active_day"] for item in ticker_rows]
        required_majority = math.ceil(len(ticker_rows) * 2 / 3) if ticker_rows else 0
        if len(ticker_rows) < 2:
            portability = "insufficient_cross_ticker_sample"
        elif (
            len(positive_both) == len(ticker_rows)
            and median(test_pfs) >= 1.2
            and max(test_frequencies, default=0.0) <= 4.0
        ):
            portability = "portable_candidate"
        elif len(positive_both) >= required_majority:
            portability = "portable_experiment"
        elif len(positive_both) == 1:
            portability = "ticker_specific"
        else:
            portability = "reject"
        variant.update(
            {
                "covered_tickers": len(ticker_rows),
                "positive_train_test_tickers": len(positive_both),
                "positive_test_tickers": len(positive_test),
                "positive_train_test_rate": len(positive_both) / len(ticker_rows) if ticker_rows else 0.0,
                "median_test_return": median(test_returns) if test_returns else 0.0,
                "worst_test_return": min(test_returns) if test_returns else 0.0,
                "median_test_profit_factor": median(test_pfs) if test_pfs else 0.0,
                "median_test_trades_per_active_day": median(test_frequencies) if test_frequencies else 0.0,
                "portability": portability,
            }
        )
        portable_candidates.append(variant)
    portable_candidates.sort(key=_portable_score, reverse=True)
    return {
        "tickers": tickers,
        "research_eligible_tickers": eligible_tickers,
        "excluded_tickers": excluded_tickers,
        "ticker_summaries": ticker_summaries,
        "portable_candidates": portable_candidates,
        "interpretation": {
            "portable_candidate": "Positive across all covered stocks, acceptable median PF, and no excessive frequency.",
            "portable_experiment": "Positive train/test behavior on at least two-thirds of covered stocks.",
            "ticker_specific": "Coherent on one stock only; requires ticker-specific calibration.",
            "reject": "Does not transfer reliably across the covered stocks.",
            "insufficient_cross_ticker_sample": "Fewer than two stocks have enough history for a transfer claim.",
        },
    }


def write_strategy_batch_outputs(
    comparison: dict[str, Any],
    *,
    output_dir: Path,
    stem: str,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{stem}.json"
    markdown_path = output_dir / f"{stem}.md"
    json_path.write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_comparison_markdown(comparison), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(markdown_path)}


def _ticker_candidate_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": candidate["id"],
        "family": candidate["family"],
        "label": candidate["label"],
        "direction": candidate["direction"],
        "params": candidate["params"],
        "status": candidate["status"],
        "score": candidate["score"],
        "family_parameter_stability": candidate.get("family_parameter_stability", 0.0),
        "train": _compact_metrics(candidate["train"]),
        "test": _compact_metrics(candidate["test"]),
        "walk_forward": {
            "fold_count": candidate["walk_forward"]["fold_count"],
            "positive_folds": candidate["walk_forward"]["positive_folds"],
            "positive_fold_rate": candidate["walk_forward"]["positive_fold_rate"],
            "total_net_return": candidate["walk_forward"]["total_net_return"],
        },
    }


def _compact_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "trades",
        "winning_trades",
        "win_rate",
        "win_rate_wilson_lower",
        "total_net_return",
        "profit_factor",
        "max_drawdown",
        "active_days",
        "profitable_day_rate",
        "trades_per_active_day",
        "largest_day_abs_pnl_share",
    ]
    return {key: metrics.get(key, 0) for key in keys}


def _portable_score(candidate: dict[str, Any]) -> float:
    status_bonus = {
        "portable_candidate": 3.0,
        "portable_experiment": 2.0,
        "ticker_specific": 1.0,
        "insufficient_cross_ticker_sample": 0.5,
        "reject": 0.0,
    }[candidate["portability"]]
    return (
        status_bonus
        + candidate["positive_train_test_rate"]
        + candidate["median_test_return"] * 10
        + min(candidate["median_test_profit_factor"], 4.0) * 0.1
        - max(0.0, candidate["median_test_trades_per_active_day"] - 3.0) * 0.05
    )


def _comparison_markdown(comparison: dict[str, Any]) -> str:
    lines = [
        "# Cross-Ticker Intraday Strategy Comparison",
        "",
        f"- Tickers: {', '.join(comparison.get('tickers') or [])}",
        f"- Research eligible: {', '.join(comparison.get('research_eligible_tickers') or []) or 'none'}",
        f"- Excluded for insufficient history/coverage: {', '.join(comparison.get('excluded_tickers') or []) or 'none'}",
        "- Goal: distinguish transferable strategy families from ticker-specific historical fits.",
        "",
        "## Data Coverage",
        "",
    ]
    for ticker, summary in (comparison.get("ticker_summaries") or {}).items():
        profile = summary.get("stock_profile") or {}
        lines.append(
            f"- **{ticker}**: {summary['sessions']} sessions, {summary['rows']} bars, "
            f"{summary['date_start']} to {summary['date_end']}; "
            f"median daily value ${profile.get('median_daily_dollar_value', 0):,.0f}, "
            f"median ATR {profile.get('median_atr_pct', 0):.2%}, "
            f"eligibility {'PASS' if profile.get('eligible') else 'REVIEW'}."
        )
    lines.extend(["", "## Transferability Ranking", ""])
    for item in (comparison.get("portable_candidates") or [])[:25]:
        lines.append(
            f"- **{item['portability'].upper()}** `{item['label']}` "
            f"`{item['params']}` — positive train/test on "
            f"{item['positive_train_test_tickers']}/{item['covered_tickers']} stocks; "
            f"median test return {item['median_test_return']:.2%}, "
            f"worst {item['worst_test_return']:.2%}, "
            f"median PF {item['median_test_profit_factor']:.2f}, "
            f"median frequency {item['median_test_trades_per_active_day']:.2f}/active day."
        )
    lines.extend(["", "## Per-Ticker Research Leaders", ""])
    for ticker, summary in (comparison.get("ticker_summaries") or {}).items():
        lines.extend(["", f"### {ticker}", ""])
        for item in summary["top_candidates"][:5]:
            lines.append(
                f"- **{item['status'].upper()}** `{item['label']}` `{item['params']}` — "
                f"test {item['test']['trades']} trades, {item['test']['win_rate']:.1%} win, "
                f"{item['test']['total_net_return']:.2%} net, PF {item['test']['profit_factor']:.2f}; "
                f"walk-forward {item['walk_forward']['positive_fold_rate']:.0%} positive folds."
            )
    lines.extend(
        [
            "",
            "## Guardrail",
            "",
            "A portable label means the historical mechanism transferred across this small research set. "
            "It does not imply universal validity. A new stock must still pass data-quality, liquidity, "
            "chronological holdout, walk-forward, parameter-neighborhood, and actual execution-ticker checks.",
            "",
        ]
    )
    return "\n".join(lines)


def _ticker_is_eligible(summary: dict[str, Any]) -> bool:
    profile = summary.get("stock_profile") or {}
    if "eligible" in profile:
        return bool(profile["eligible"])
    return int(summary.get("sessions") or 0) >= 60


def _ticker_variant_is_robust(item: dict[str, Any]) -> bool:
    train = item["train"]
    test = item["test"]
    return (
        train["trades"] >= 20
        and test["trades"] >= 12
        and train["total_net_return"] > 0
        and test["total_net_return"] > 0
        and train["profit_factor"] >= 1.0
        and test["profit_factor"] >= 1.2
        and item["walk_forward"]["positive_fold_rate"] >= 0.5
    )
