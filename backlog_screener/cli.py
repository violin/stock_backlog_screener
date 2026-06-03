from __future__ import annotations

import argparse
import csv
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable, List

from .config import BacklogScanConfig, ScreenThresholds
from .db import PostgresStore
from .formatting import write_outputs
from .futu_provider import FutuProvider
from .models import CandidateMetrics
from .pipeline import HiddenChampionPipeline
from .sample_data import sample_metrics
from .scoring import evaluate_candidate
from .sec import BacklogScanner, SecClient
from .settings import load_settings
from .yahoo import fetch_candidate_metrics, seed_yfinance_universe


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WATCHLIST = PROJECT_ROOT / "configs" / "default_watchlist.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs"


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "sample":
        results = [evaluate_candidate(metrics, _thresholds_from_args(args)) for metrics in sample_metrics()]
        stem = args.stem or f"sample_{_timestamp()}"
        write_outputs(results, Path(args.output_dir), stem)
        _print_summary(results, Path(args.output_dir), stem)
        return 0

    if args.command == "init-db":
        settings = load_settings()
        store = PostgresStore(settings.database_url)
        store.ensure_schema()
        print(f"Initialized PostgreSQL schema: {settings.database_url}")
        return 0

    if args.command == "ingest":
        settings = load_settings()
        store = PostgresStore(settings.database_url)
        store.ensure_schema()
        tickers = _collect_ingest_symbols(args)
        if args.offset or args.limit:
            offset = max(0, args.offset)
            limit = args.limit if args.limit is None else max(0, args.limit)
            tickers = tickers[offset : offset + limit if limit else None]
        if not tickers:
            parser.error("No tickers found. Pass --tickers or --watchlist.")
        pipeline = HiddenChampionPipeline(store, settings)
        run_id = pipeline.run(
            tickers,
            trigger="cli",
            use_futu=not args.no_futu,
            use_sec=not args.no_sec,
            use_yfinance=args.yfinance,
            use_13f=args.sec_13f,
            use_usaspending=args.usaspending,
            summarize=args.summarize,
            delay_seconds=args.delay,
        )
        print(f"Completed collection run {run_id} for {', '.join(tickers)}")
        return 0

    if args.command == "serve":
        from .webapp import create_app

        settings = load_settings()
        store = PostgresStore(settings.database_url)
        store.ensure_schema()
        app = create_app(store=store, settings=settings)
        app.run(host=args.host, port=args.port, debug=args.debug)
        return 0

    if args.command == "seed":
        thresholds = _thresholds_from_args(args)
        symbols = seed_yfinance_universe(thresholds, limit=args.limit)
        if args.output:
            Path(args.output).write_text("\n".join(symbols) + "\n", encoding="utf-8")
        for symbol in symbols:
            print(symbol)
        return 0

    if args.command == "seed-futu":
        settings = load_settings()
        with FutuProvider(
            host=settings.futu_host,
            port=settings.futu_port,
            market=args.market,
        ) as provider:
            rows, all_count = provider.stock_filter(
                min_market_cap=args.min_market_cap,
                max_market_cap=args.max_market_cap,
                min_pe_ttm=args.min_pe_ttm,
                max_pe_ttm=args.max_pe_ttm,
                page_size=args.page_size,
                limit=args.limit,
                strict_common=not args.include_non_common,
                page_delay_seconds=args.page_delay,
                rate_limit_wait_seconds=args.rate_limit_wait,
            )
        if args.output:
            _write_seed_csv(Path(args.output), rows)
        for row in rows:
            print(row["ticker"])
        print(
            f"Futu OpenD seed returned {len(rows)} common-stock tickers "
            f"from {all_count} raw matches.",
            file=sys.stderr,
        )
        if args.output:
            print(f"Wrote: {args.output}", file=sys.stderr)
        return 0

    if args.command == "score":
        thresholds = _thresholds_from_args(args)
        symbols = _collect_symbols(args, thresholds)
        if not symbols:
            parser.error("No tickers found. Pass --tickers, --watchlist, or --seed-yfinance.")
        scanner = _build_scanner(args) if args.sec_text else None
        results = []
        for index, symbol in enumerate(symbols, start=1):
            print(f"[{index}/{len(symbols)}] scoring {symbol}", file=sys.stderr)
            metrics = fetch_candidate_metrics(
                symbol,
                cache_dir=Path(args.yf_cache_dir),
                cache_ttl_hours=args.yf_cache_hours,
                force_refresh=args.yf_force_refresh,
                retries=args.yf_retries,
                retry_wait_seconds=args.yf_retry_wait,
            )
            if scanner is not None:
                _attach_filing_scan(metrics, scanner.scan_ticker(symbol))
            results.append(evaluate_candidate(metrics, thresholds))
            if index < len(symbols) and args.yf_delay > 0:
                time.sleep(args.yf_delay)

        stem = args.stem or f"backlog_screener_{_timestamp()}"
        write_outputs(results, Path(args.output_dir), stem)
        _print_summary(results, Path(args.output_dir), stem)
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="backlog-screener",
        description="Find small/mid-cap stocks with ownership, growth, valuation, and Backlog/RPO signals.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    sample = subparsers.add_parser("sample", help="Run an offline sample without network access.")
    _add_threshold_args(sample)
    _add_output_args(sample)

    subparsers.add_parser("init-db", help="Create or update the PostgreSQL schema.")

    ingest = subparsers.add_parser("ingest", help="Collect layered evidence into PostgreSQL and rescore tickers.")
    ingest.add_argument("--tickers", nargs="*", default=[], help="Ticker symbols, for example PLPC STRL POWL.")
    ingest.add_argument("--watchlist", default=str(DEFAULT_WATCHLIST), help="CSV or plain text ticker list.")
    ingest.add_argument("--no-watchlist", action="store_true", help="Do not load the default watchlist.")
    ingest.add_argument("--offset", type=int, default=0, help="Skip this many symbols after loading tickers/watchlist.")
    ingest.add_argument("--limit", type=int, default=None, help="Limit number of symbols in this collection run.")
    ingest.add_argument("--no-futu", action="store_true", help="Skip Futu OpenD snapshot collection.")
    ingest.add_argument("--no-sec", action="store_true", help="Skip SEC filing and companyfacts collection.")
    ingest.add_argument("--yfinance", action="store_true", help="Use yFinance only as slow fallback for ownership fields.")
    ingest.add_argument("--sec-13f", action="store_true", help="Enable slow curated SEC 13F institutional holder scan.")
    ingest.add_argument("--usaspending", action="store_true", help="Enable USAspending federal contract award search.")
    ingest.add_argument("--summarize", action="store_true", help="Use MiniMax when MINIMAX_API_KEY is configured.")
    ingest.add_argument("--delay", type=float, default=1.0, help="Seconds to sleep between low-frequency source calls.")

    serve = subparsers.add_parser("serve", help="Start the local interactive hidden-champion dashboard.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=5055)
    serve.add_argument("--debug", action="store_true")

    seed = subparsers.add_parser("seed", help="Use yfinance's Yahoo screener to seed a ticker list.")
    _add_threshold_args(seed)
    seed.add_argument("--limit", type=int, default=100, help="Maximum Yahoo screener symbols to return, max 250.")
    seed.add_argument("--output", help="Optional path for a one-symbol-per-line output file.")

    seed_futu = subparsers.add_parser("seed-futu", help="Use Futu OpenD stock filter to seed a low-frequency ticker list.")
    seed_futu.add_argument("--market", default="US", help="Futu market enum name, default US.")
    seed_futu.add_argument("--min-market-cap", type=float, default=500_000_000)
    seed_futu.add_argument("--max-market-cap", type=float, default=4_000_000_000)
    seed_futu.add_argument("--min-pe-ttm", type=float, default=None, help="Optional minimum positive TTM P/E.")
    seed_futu.add_argument("--max-pe-ttm", type=float, default=None, help="Optional maximum TTM P/E, for example 30.")
    seed_futu.add_argument("--page-size", type=int, default=200, help="OpenD page size, capped at 200.")
    seed_futu.add_argument("--page-delay", type=float, default=3.2, help="Seconds to sleep between OpenD filter pages.")
    seed_futu.add_argument("--rate-limit-wait", type=float, default=30, help="Seconds to wait after an OpenD filter rate-limit response.")
    seed_futu.add_argument("--limit", type=int, default=None, help="Optional cap after filtering common-stock tickers.")
    seed_futu.add_argument("--include-non-common", action="store_true", help="Keep ADR/preferred/note/unit/OTC-like matches.")
    seed_futu.add_argument("--output", help="Optional CSV watchlist output with ticker/name/valuation columns.")

    score = subparsers.add_parser("score", help="Score a watchlist, explicit tickers, or yfinance-seeded universe.")
    _add_threshold_args(score)
    _add_output_args(score)
    score.add_argument("--tickers", nargs="*", default=[], help="Ticker symbols, for example PLPC STRL POWL.")
    score.add_argument("--watchlist", default=str(DEFAULT_WATCHLIST), help="CSV or plain text ticker list.")
    score.add_argument("--no-watchlist", action="store_true", help="Do not load the default watchlist.")
    score.add_argument("--seed-yfinance", action="store_true", help="Add symbols from yfinance's Yahoo screener.")
    score.add_argument("--limit", type=int, default=100, help="Maximum yfinance seed symbols, max 250.")
    score.add_argument("--sec-text", action="store_true", help="Fetch latest SEC 10-Q/10-K text and scan Backlog/RPO.")
    score.add_argument("--forms", default="10-Q,10-K", help="Comma-separated SEC forms to scan.")
    score.add_argument("--cache-dir", default=str(PROJECT_ROOT / ".cache" / "sec"), help="SEC cache directory.")
    score.add_argument("--sec-user-agent", default=None, help="SEC User-Agent header. Can also use SEC_USER_AGENT.")
    score.add_argument("--yf-cache-dir", default=str(PROJECT_ROOT / ".cache" / "yfinance"), help="yFinance metrics cache directory.")
    score.add_argument("--yf-cache-hours", type=float, default=24, help="Reuse cached yFinance metrics younger than this many hours.")
    score.add_argument("--yf-force-refresh", action="store_true", help="Ignore fresh yFinance cache and fetch live data.")
    score.add_argument("--yf-delay", type=float, default=1.5, help="Seconds to wait between ticker detail requests.")
    score.add_argument("--yf-retries", type=int, default=1, help="Number of retries after a yFinance rate-limit response.")
    score.add_argument("--yf-retry-wait", type=float, default=30, help="Base seconds to wait before retrying a rate-limited yFinance request.")
    return parser


def _add_threshold_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-market-cap", type=float, default=500_000_000)
    parser.add_argument("--max-market-cap", type=float, default=4_000_000_000)
    parser.add_argument("--min-inst", type=float, default=65.0, help="Minimum institutional ownership percent.")
    parser.add_argument("--min-insider", type=float, default=5.0, help="Minimum insider ownership percent.")
    parser.add_argument("--min-rev-growth", type=float, default=25.0, help="Minimum quarterly revenue YoY percent.")
    parser.add_argument("--max-pe", type=float, default=30.0, help="Maximum positive trailing P/E.")


def _add_output_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--stem", default=None, help="Output filename stem without extension.")


def _thresholds_from_args(args) -> ScreenThresholds:
    return ScreenThresholds(
        min_market_cap=args.min_market_cap,
        max_market_cap=args.max_market_cap,
        min_institutional_ownership=args.min_inst / 100,
        min_insider_ownership=args.min_insider / 100,
        min_quarterly_revenue_yoy=args.min_rev_growth / 100,
        max_trailing_pe=args.max_pe,
    )


def _collect_symbols(args, thresholds: ScreenThresholds) -> List[str]:
    symbols: List[str] = []
    if args.seed_yfinance:
        symbols.extend(seed_yfinance_universe(thresholds, limit=args.limit))
    if not args.no_watchlist and args.watchlist:
        symbols.extend(_read_watchlist(Path(args.watchlist)))
    symbols.extend(args.tickers or [])
    return _dedupe(symbols)


def _collect_ingest_symbols(args) -> List[str]:
    symbols: List[str] = []
    if not args.no_watchlist and args.watchlist:
        symbols.extend(_read_watchlist(Path(args.watchlist)))
    symbols.extend(args.tickers or [])
    return _dedupe(symbols)


def _read_watchlist(path: Path) -> List[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if "," not in text.splitlines()[0]:
        return [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]
    rows = csv.DictReader(text.splitlines())
    if rows.fieldnames and "ticker" in rows.fieldnames:
        return [row["ticker"].strip() for row in rows if row.get("ticker")]
    return [row[rows.fieldnames[0]].strip() for row in rows if rows.fieldnames and row.get(rows.fieldnames[0])]


def _write_seed_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["ticker", "code", "name", "market_cap", "pe_ttm", "pb", "exchange_type", "listing_date"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _build_scanner(args) -> BacklogScanner:
    forms = tuple(form.strip().upper() for form in args.forms.split(",") if form.strip())
    sec_client = SecClient(Path(args.cache_dir), user_agent=args.sec_user_agent)
    return BacklogScanner(sec_client, BacklogScanConfig(forms=forms))


def _attach_filing_scan(metrics: CandidateMetrics, scan) -> None:
    metrics.filing_form = scan.form
    metrics.filing_date = scan.filing_date
    metrics.filing_url = scan.url
    metrics.backlog_mentions = scan.backlog_mentions
    metrics.rpo_mentions = scan.rpo_mentions
    metrics.backlog_snippets = scan.snippets
    if scan.warning:
        metrics.warnings.append(scan.warning)


def _dedupe(values: Iterable[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        key = value.strip().upper()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(key)
    return result


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _print_summary(results, output_dir: Path, stem: str) -> None:
    ranked = sorted(results, key=lambda item: item.score, reverse=True)
    print("\nTop candidates:")
    for result in ranked[:10]:
        print(
            f"{result.metrics.ticker:>6} score={result.score:>6.2f} "
            f"pass={'YES' if result.passed else 'NO '} "
            f"financial={'YES' if result.financial_passed else 'NO '}"
        )
    print(f"\nWrote: {output_dir / (stem + '.csv')}")
    print(f"Wrote: {output_dir / (stem + '.json')}")
    print(f"Wrote: {output_dir / (stem + '.md')}")


if __name__ == "__main__":
    raise SystemExit(main())
