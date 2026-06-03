from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable, List

from .models import ScreenResult


def write_outputs(results: List[ScreenResult], output_dir: Path, stem: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(results, output_dir / f"{stem}.csv")
    write_json(results, output_dir / f"{stem}.json")
    write_markdown(results, output_dir / f"{stem}.md")


def write_csv(results: Iterable[ScreenResult], path: Path) -> None:
    rows = [_row(result) for result in results]
    fieldnames = list(rows[0].keys()) if rows else _row_fields()
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(results: Iterable[ScreenResult], path: Path) -> None:
    data = [result.to_dict() for result in results]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_markdown(results: List[ScreenResult], path: Path) -> None:
    lines = [
        "# Backlog/RPO Screener Results",
        "",
        "| Rank | Ticker | Score | Pass | Market Cap | Inst | Insider | Rev YoY | P/E | Backlog/RPO |",
        "| ---: | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    sorted_results = sorted(results, key=lambda item: item.score, reverse=True)
    for rank, result in enumerate(sorted_results, start=1):
        metrics = result.metrics
        lines.append(
            "| {rank} | {ticker} | {score:.2f} | {passed} | {market_cap} | {inst} | {insider} | {rev} | {pe} | {backlog} |".format(
                rank=rank,
                ticker=metrics.ticker,
                score=result.score,
                passed="YES" if result.passed else "NO",
                market_cap=_money(metrics.market_cap),
                inst=_pct(metrics.institutional_ownership),
                insider=_pct(metrics.insider_ownership),
                rev=_pct(metrics.quarterly_revenue_yoy),
                pe=_num(metrics.trailing_pe),
                backlog=metrics.backlog_mentions + metrics.rpo_mentions,
            )
        )

    lines.append("")
    lines.append("## Notes")
    for result in sorted_results:
        metrics = result.metrics
        lines.append(f"### {metrics.ticker} {metrics.name}".rstrip())
        if metrics.filing_url:
            lines.append(f"- Filing: {metrics.filing_form} {metrics.filing_date} {metrics.filing_url}")
        if result.positives:
            lines.append(f"- Positives: {'; '.join(result.positives)}")
        if result.hard_failures:
            lines.append(f"- Gaps: {'; '.join(result.hard_failures)}")
        if result.next_steps:
            lines.append(f"- Next steps: {'; '.join(result.next_steps)}")
        if metrics.backlog_snippets:
            lines.append("- Filing snippets:")
            for snippet in metrics.backlog_snippets:
                lines.append(f"  - {snippet}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def _row(result: ScreenResult) -> dict:
    metrics = result.metrics
    return {
        "ticker": metrics.ticker,
        "score": result.score,
        "passed": result.passed,
        "financial_passed": result.financial_passed,
        "name": metrics.name,
        "sector": metrics.sector,
        "industry": metrics.industry,
        "market_cap": metrics.market_cap,
        "institutional_ownership_pct": _pct_number(metrics.institutional_ownership),
        "insider_ownership_pct": _pct_number(metrics.insider_ownership),
        "quarterly_revenue_yoy_pct": _pct_number(metrics.quarterly_revenue_yoy),
        "trailing_pe": metrics.trailing_pe,
        "forward_pe": metrics.forward_pe,
        "price": metrics.price,
        "backlog_mentions": metrics.backlog_mentions,
        "rpo_mentions": metrics.rpo_mentions,
        "filing_form": metrics.filing_form,
        "filing_date": metrics.filing_date,
        "filing_url": metrics.filing_url,
        "hard_failures": "; ".join(result.hard_failures),
        "positives": "; ".join(result.positives),
        "next_steps": "; ".join(result.next_steps),
        "warnings": "; ".join(metrics.warnings),
    }


def _row_fields() -> list:
    return [
        "ticker",
        "score",
        "passed",
        "financial_passed",
        "name",
        "sector",
        "industry",
        "market_cap",
        "institutional_ownership_pct",
        "insider_ownership_pct",
        "quarterly_revenue_yoy_pct",
        "trailing_pe",
        "forward_pe",
        "price",
        "backlog_mentions",
        "rpo_mentions",
        "filing_form",
        "filing_date",
        "filing_url",
        "hard_failures",
        "positives",
        "next_steps",
        "warnings",
    ]


def _pct(value) -> str:
    if value is None:
        return ""
    return f"{value * 100:.1f}%"


def _pct_number(value):
    if value is None:
        return None
    return round(value * 100, 4)


def _money(value) -> str:
    if value is None:
        return ""
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    return f"${value:,.0f}"


def _num(value) -> str:
    if value is None:
        return ""
    return f"{value:.2f}"
