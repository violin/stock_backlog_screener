from typing import List, Optional, Tuple

from .config import ScreenThresholds
from .models import CandidateMetrics, ScreenResult


def _fmt_pct(value: Optional[float]) -> str:
    if value is None:
        return "missing"
    return f"{value * 100:.1f}%"


def _fmt_money(value: Optional[float]) -> str:
    if value is None:
        return "missing"
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    return f"${value:,.0f}"


def _check(
    actual: Optional[float],
    predicate,
    success: str,
    failure: str,
) -> Tuple[bool, str]:
    if actual is None:
        return False, failure.replace("{actual}", "missing")
    if predicate(actual):
        return True, success
    return False, failure.replace("{actual}", str(actual))


def evaluate_candidate(
    metrics: CandidateMetrics,
    thresholds: ScreenThresholds = ScreenThresholds(),
) -> ScreenResult:
    positives: List[str] = []
    failures: List[str] = []
    next_steps: List[str] = []
    score = 0.0
    hard_pass_count = 0

    checks = [
        _check(
            metrics.market_cap,
            lambda value: thresholds.min_market_cap <= value <= thresholds.max_market_cap,
            f"market cap in target range ({_fmt_money(metrics.market_cap)})",
            "market cap outside target range or missing ({actual})",
        ),
        _check(
            metrics.institutional_ownership,
            lambda value: value >= thresholds.min_institutional_ownership,
            f"institutional ownership >= {_fmt_pct(thresholds.min_institutional_ownership)}",
            "institutional ownership below threshold or missing ({actual})",
        ),
        _check(
            metrics.insider_ownership,
            lambda value: value >= thresholds.min_insider_ownership,
            f"insider ownership >= {_fmt_pct(thresholds.min_insider_ownership)}",
            "insider ownership below threshold or missing ({actual})",
        ),
        _check(
            metrics.quarterly_revenue_yoy,
            lambda value: value >= thresholds.min_quarterly_revenue_yoy,
            f"quarterly revenue YoY >= {_fmt_pct(thresholds.min_quarterly_revenue_yoy)}",
            "quarterly revenue YoY below threshold or missing ({actual})",
        ),
        _check(
            metrics.trailing_pe,
            lambda value: 0 < value <= thresholds.max_trailing_pe,
            f"trailing P/E <= {thresholds.max_trailing_pe:.1f}",
            "trailing P/E above threshold, negative, or missing ({actual})",
        ),
    ]

    weights = [18, 16, 14, 24, 12]
    for (ok, message), weight in zip(checks, weights):
        if ok:
            positives.append(message)
            score += weight
            hard_pass_count += 1
        else:
            failures.append(message)

    if metrics.quarterly_revenue_yoy is not None and metrics.quarterly_revenue_yoy > thresholds.min_quarterly_revenue_yoy:
        score += min(10, (metrics.quarterly_revenue_yoy - thresholds.min_quarterly_revenue_yoy) * 30)

    if metrics.trailing_pe is not None and 0 < metrics.trailing_pe <= 20:
        score += 4

    backlog_signal = metrics.backlog_mentions + metrics.rpo_mentions
    if backlog_signal > 0:
        positives.append(
            f"filing text contains Backlog/RPO signal ({metrics.backlog_mentions} backlog, {metrics.rpo_mentions} RPO)"
        )
        score += 16
        score += min(6, backlog_signal)
    else:
        failures.append("Backlog/RPO filing text signal missing or not scanned")
        next_steps.append("Open the latest 10-Q/10-K and search Backlog / Remaining Performance Obligations manually.")

    if not metrics.filing_url:
        next_steps.append("Run with --sec-text to fetch and scan latest SEC filings.")

    for warning in metrics.warnings:
        next_steps.append(warning)

    financial_passed = hard_pass_count == len(checks)
    passed = financial_passed and backlog_signal > 0
    return ScreenResult(
        metrics=metrics,
        score=round(score, 2),
        passed=passed,
        financial_passed=financial_passed,
        hard_pass_count=hard_pass_count,
        hard_failures=failures,
        positives=positives,
        next_steps=next_steps,
    )
