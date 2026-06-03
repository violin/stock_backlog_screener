from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


SOURCE_REGISTRY_VERSION = 1


@dataclass(frozen=True)
class DataSourceDefinition:
    source_key: str
    source_name: str
    source_type: str
    provider: str
    website_url: str
    docs_url: str = ""
    trust_level: int = 50
    collection_scope: str = "optional"
    run_flag: str = ""
    collector_group: str = ""
    default_enabled: bool = False
    status: str = "active"
    auth: str = "none"
    dimensions: tuple[str, ...] = ()
    applies_to_keywords: tuple[str, ...] = ()
    applies_to_tickers: tuple[str, ...] = ()
    rate_limit_summary: str = ""
    cache_policy: str = ""
    notes: tuple[str, ...] = ()

    def metadata(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("source_key", "source_name", "source_type", "trust_level"):
            data.pop(key, None)
        data["registry_version"] = SOURCE_REGISTRY_VERSION
        return data


DATA_SOURCE_DEFINITIONS: tuple[DataSourceDefinition, ...] = (
    DataSourceDefinition(
        source_key="futu_opend",
        source_name="Futu OpenD",
        source_type="market_data",
        provider="Futu",
        website_url="https://openapi.futunn.com/",
        docs_url="https://openapi.futunn.com/futu-api-doc/",
        trust_level=85,
        collection_scope="base",
        run_flag="use_futu",
        collector_group="futu_market",
        default_enabled=True,
        dimensions=("market", "valuation", "sector", "attention_flow"),
        rate_limit_summary="Stock filter is observed at 10 calls per 30 seconds; capital flow is observed at 30 calls per 30 seconds.",
        cache_policy="Local OpenD gateway; no persisted HTTP cache.",
        notes=("Primary low-cost market, valuation, sector, and attention-flow source.",),
    ),
    DataSourceDefinition(
        source_key="sec_edgar",
        source_name="SEC EDGAR Filings",
        source_type="filing",
        provider="U.S. SEC",
        website_url="https://www.sec.gov/edgar",
        docs_url="https://www.sec.gov/search-filings/edgar-application-programming-interfaces",
        trust_level=95,
        collection_scope="base",
        run_flag="use_sec",
        collector_group="sec_bundle",
        default_enabled=True,
        auth="User-Agent required",
        dimensions=("backlog", "backlog_quality"),
        rate_limit_summary="Polite single-threaded HTTP with local accession/document cache and short per-request delay.",
        cache_policy="12-hour filing text cache by CIK/accession/document.",
        notes=("Truth source for Backlog/RPO text and amount extraction.",),
    ),
    DataSourceDefinition(
        source_key="sec_companyfacts",
        source_name="SEC Companyfacts",
        source_type="fundamental",
        provider="U.S. SEC",
        website_url="https://data.sec.gov/api/xbrl/companyfacts/",
        docs_url="https://www.sec.gov/search-filings/edgar-application-programming-interfaces",
        trust_level=92,
        collection_scope="base",
        run_flag="use_sec",
        collector_group="sec_bundle",
        default_enabled=True,
        auth="User-Agent required",
        dimensions=("growth", "quality"),
        rate_limit_summary="Polite single-threaded HTTP; reuse companyfacts cache.",
        cache_policy="12-hour companyfacts cache by CIK.",
        notes=("Truth source for revenue growth, margins, balance sheet, and working-capital metrics.",),
    ),
    DataSourceDefinition(
        source_key="sec_form4",
        source_name="SEC Form 4",
        source_type="insider_transactions",
        provider="U.S. SEC",
        website_url="https://www.sec.gov/edgar/search/",
        docs_url="https://www.sec.gov/search-filings/edgar-application-programming-interfaces",
        trust_level=92,
        collection_scope="base",
        run_flag="use_sec",
        collector_group="sec_bundle",
        default_enabled=True,
        auth="User-Agent required",
        dimensions=("insider_activity",),
        rate_limit_summary="Polite single-threaded SEC filing fetches with local document cache.",
        cache_policy="12-hour filing document cache.",
        notes=("Recent insider transaction signal; parsed directly from SEC XML where available.",),
    ),
    DataSourceDefinition(
        source_key="sec_beneficial_ownership",
        source_name="SEC Schedule 13D/G",
        source_type="beneficial_ownership",
        provider="U.S. SEC",
        website_url="https://www.sec.gov/edgar/search/",
        docs_url="https://www.sec.gov/search-filings/edgar-application-programming-interfaces",
        trust_level=88,
        collection_scope="base",
        run_flag="use_sec",
        collector_group="sec_bundle",
        default_enabled=True,
        auth="User-Agent required",
        dimensions=("ownership",),
        rate_limit_summary="Polite single-threaded SEC filing fetches with local document cache.",
        cache_policy="12-hour filing document cache.",
        notes=("Large-holder and beneficial ownership signal.",),
    ),
    DataSourceDefinition(
        source_key="sec_proxy_ownership",
        source_name="SEC DEF 14A / 10-K Ownership Tables",
        source_type="proxy_ownership",
        provider="U.S. SEC",
        website_url="https://www.sec.gov/edgar/search/",
        docs_url="https://www.sec.gov/search-filings/edgar-application-programming-interfaces",
        trust_level=90,
        collection_scope="base",
        run_flag="use_sec",
        collector_group="sec_bundle",
        default_enabled=True,
        auth="User-Agent required",
        dimensions=("ownership",),
        rate_limit_summary="Polite single-threaded SEC filing fetches with local document cache.",
        cache_policy="24-hour proxy/10-K ownership cache.",
        notes=("Management and board ownership alignment signal.",),
    ),
    DataSourceDefinition(
        source_key="sec_13f",
        source_name="SEC 13F Institutional Holdings",
        source_type="institutional_holdings",
        provider="U.S. SEC",
        website_url="https://www.sec.gov/edgar/search/",
        docs_url="https://www.sec.gov/search-filings/edgar-application-programming-interfaces",
        trust_level=82,
        collection_scope="optional",
        run_flag="use_13f",
        collector_group="sec_13f",
        default_enabled=False,
        auth="User-Agent required",
        dimensions=("institutional_activity",),
        rate_limit_summary="Slow optional scan over curated manager CIKs; run only on shortlists.",
        cache_policy="24-hour manager filing and information-table cache.",
        notes=("Currently configured by configs/13f_managers.csv.",),
    ),
    DataSourceDefinition(
        source_key="usaspending",
        source_name="USAspending.gov",
        source_type="government_contracts",
        provider="U.S. Treasury / USAspending",
        website_url="https://www.usaspending.gov/",
        docs_url="https://api.usaspending.gov/docs/",
        trust_level=76,
        collection_scope="sector",
        run_flag="use_usaspending",
        collector_group="usaspending",
        default_enabled=False,
        dimensions=("government_contract",),
        applies_to_keywords=(
            "aerospace",
            "defense",
            "space",
            "satellite",
            "semiconductor",
            "electrical equipment",
            "engineering",
            "construction",
            "communications",
            "industrial",
            "advanced manufacturing",
        ),
        applies_to_tickers=("RKLB", "ASTS", "RDW", "POWL", "PLPC", "STRL", "LMB", "MTZ", "TPC", "DY"),
        rate_limit_summary="Free public API; keep single-threaded with 24-hour cache and about 1 second between symbols.",
        cache_policy="24-hour recipient award cache by query/window.",
        notes=("Sector-scoped source for government order evidence; skipped for unrelated sectors.",),
    ),
    DataSourceDefinition(
        source_key="yfinance",
        source_name="Yahoo Finance via yFinance",
        source_type="fallback_fundamental",
        provider="Yahoo Finance / yFinance",
        website_url="https://finance.yahoo.com/",
        docs_url="https://github.com/ranaroussi/yfinance",
        trust_level=58,
        collection_scope="optional",
        run_flag="use_yfinance",
        collector_group="yfinance",
        default_enabled=False,
        dimensions=("ownership", "valuation"),
        rate_limit_summary="Unofficial provider; avoid broad live fetches and back off on 429/Too Many Requests.",
        cache_policy="24-hour ticker metric cache.",
        notes=("Fallback only for fields missing from Futu/SEC.",),
    ),
    DataSourceDefinition(
        source_key="minimax",
        source_name="MiniMax M2.7",
        source_type="llm_summary",
        provider="MiniMax",
        website_url="https://www.minimaxi.com/",
        docs_url="https://www.minimaxi.com/document",
        trust_level=70,
        collection_scope="optional",
        run_flag="summarize",
        collector_group="summary",
        default_enabled=False,
        auth="API key required",
        dimensions=("company_summary",),
        rate_limit_summary="Optional LLM call; single-threaded, retry once, and fall back to heuristic summaries where possible.",
        cache_policy="Summary is persisted as information_items; no broad automatic refresh.",
        notes=("Summary source only; never treated as raw truth.",),
    ),
    DataSourceDefinition(
        source_key="fmp",
        source_name="Financial Modeling Prep",
        source_type="structured_financial_api",
        provider="Financial Modeling Prep",
        website_url="https://site.financialmodelingprep.com/",
        docs_url="https://site.financialmodelingprep.com/developer/docs",
        trust_level=72,
        collection_scope="optional",
        run_flag="use_fmp",
        collector_group="financial_api",
        default_enabled=False,
        status="planned",
        auth="API key required",
        dimensions=("institutional_activity", "insider_activity", "valuation", "future_events"),
        rate_limit_summary="Plan-dependent JSON API limits; should be cached and run after broad Futu/SEC filtering.",
        cache_policy="Planned daily cache for valuation history, 13F holders, insider trades, and earnings calendars.",
        notes=("Candidate structured API for 13F, Form 4, historical valuation percentiles, and event calendars.",),
    ),
    DataSourceDefinition(
        source_key="openinsider",
        source_name="OpenInsider",
        source_type="insider_transactions",
        provider="OpenInsider",
        website_url="http://openinsider.com/",
        docs_url="",
        trust_level=64,
        collection_scope="optional",
        run_flag="use_openinsider",
        collector_group="insider_activity",
        default_enabled=False,
        status="planned",
        dimensions=("insider_activity",),
        rate_limit_summary="No official API; any scraper should be slow, cached, and limited to shortlists.",
        cache_policy="Planned daily cache by ticker and query window.",
        notes=("Candidate source for distinguishing open-market insider buys from grants and option exercises.",),
    ),
    DataSourceDefinition(
        source_key="sec_api_io",
        source_name="SEC-API.io",
        source_type="sec_structured_api",
        provider="SEC-API.io",
        website_url="https://sec-api.io/",
        docs_url="https://sec-api.io/docs",
        trust_level=78,
        collection_scope="optional",
        run_flag="use_sec_api_io",
        collector_group="sec_enrichment",
        default_enabled=False,
        status="planned",
        auth="API key required",
        dimensions=("backlog", "backlog_quality", "insider_activity", "future_events"),
        rate_limit_summary="Plan-dependent API limits; reserve for shortlist XBRL/text-search/Form 4 enrichment.",
        cache_policy="Planned filing-query cache by ticker, accession, keyword, and XBRL tag.",
        notes=("Candidate helper for structured XBRL tags, backlog/RPO paragraph search, and Form 4 webhooks.",),
    ),
    DataSourceDefinition(
        source_key="fintel",
        source_name="Fintel",
        source_type="short_interest",
        provider="Fintel",
        website_url="https://fintel.io/",
        docs_url="https://fintel.io/api",
        trust_level=66,
        collection_scope="optional",
        run_flag="use_fintel",
        collector_group="short_interest",
        default_enabled=False,
        status="planned",
        auth="API key required",
        dimensions=("short_interest",),
        rate_limit_summary="Commercial API; cache daily short-interest, borrow-fee, and availability signals.",
        cache_policy="Planned daily cache by ticker, with shorter TTL during squeeze-watch windows.",
        notes=("Candidate source for short squeeze score, borrow fee, shares available, and days-to-cover.",),
    ),
    DataSourceDefinition(
        source_key="ortex",
        source_name="Ortex",
        source_type="short_interest",
        provider="Ortex",
        website_url="https://public.ortex.com/",
        docs_url="",
        trust_level=68,
        collection_scope="optional",
        run_flag="use_ortex",
        collector_group="short_interest",
        default_enabled=False,
        status="planned",
        auth="Commercial access required",
        dimensions=("short_interest",),
        rate_limit_summary="Commercial data access; should only run on shortlist tickers if integrated.",
        cache_policy="Planned daily cache by ticker; no broad polling unless a licensed feed supports it.",
        notes=("Candidate alternative for higher-frequency short-interest, borrow, and utilization data.",),
    ),
    DataSourceDefinition(
        source_key="finnhub",
        source_name="Finnhub",
        source_type="future_event_calendar",
        provider="Finnhub",
        website_url="https://finnhub.io/",
        docs_url="https://finnhub.io/docs/api",
        trust_level=70,
        collection_scope="optional",
        run_flag="use_finnhub",
        collector_group="future_events",
        default_enabled=False,
        status="planned",
        auth="API key required",
        dimensions=("future_events",),
        rate_limit_summary="Plan-dependent API/webhook limits; use for earnings/event calendar deltas.",
        cache_policy="Planned calendar-window cache and webhook dedupe by ticker/date/event type.",
        notes=("Candidate source for earnings calendars, estimates, and low-latency event notifications.",),
    ),
    DataSourceDefinition(
        source_key="launch_library",
        source_name="The Space Devs Launch Library 2",
        source_type="future_event",
        provider="The Space Devs",
        website_url="https://thespacedevs.com/",
        docs_url="https://ll.thespacedevs.com/docs/",
        trust_level=80,
        collection_scope="sector",
        run_flag="use_launch_library",
        collector_group="future_events",
        default_enabled=False,
        status="planned",
        dimensions=("future_events",),
        applies_to_keywords=("aerospace", "space", "satellite", "defense"),
        applies_to_tickers=("RKLB", "ASTS", "RDW"),
        rate_limit_summary="Planned JSON API source for upcoming launches; should be cached and run only for space-exposed tickers.",
        cache_policy="Planned short TTL around upcoming launch windows.",
        notes=("Future catalyst source for launch windows, payloads, provider, status, and webcast links.",),
    ),
    DataSourceDefinition(
        source_key="fcc_ecfs_oet",
        source_name="FCC ECFS / OET",
        source_type="regulatory_event",
        provider="U.S. FCC",
        website_url="https://www.fcc.gov/ecfs",
        docs_url="https://www.fcc.gov/ecfs/help/ecfs",
        trust_level=82,
        collection_scope="sector",
        run_flag="use_fcc",
        collector_group="future_events",
        default_enabled=False,
        status="planned",
        dimensions=("future_events", "regulatory"),
        applies_to_keywords=("space", "satellite", "communications", "telecom", "aerospace"),
        applies_to_tickers=("ASTS", "RKLB", "RDW"),
        rate_limit_summary="Public pages/RSS; run slow keyword checks for space and satellite exposed tickers only.",
        cache_policy="Planned daily docket/action cache by keyword, ticker mapping, and filing id.",
        notes=("Candidate left-side catalyst source for satellite, spectrum, and launch-related approvals.",),
    ),
    DataSourceDefinition(
        source_key="industry_agenda",
        source_name="Industry Conference Agendas",
        source_type="conference_scraper",
        provider="Conference websites",
        website_url="",
        docs_url="",
        trust_level=55,
        collection_scope="sector",
        run_flag="use_industry_agenda",
        collector_group="future_events",
        default_enabled=False,
        status="planned",
        dimensions=("future_events",),
        applies_to_keywords=("semiconductor", "advanced packaging", "space", "satellite", "artificial intelligence"),
        applies_to_tickers=("RKLB", "ASTS", "NVDA"),
        rate_limit_summary="Non-standard websites; scrape slowly, cache aggressively, and pass only changed agendas to an LLM parser.",
        cache_policy="Planned checksum cache by conference agenda URL and event date.",
        notes=("Candidate source for GTC, Computex, ISSCC, Space Symposium, and Satellite Business Week appearances.",),
    ),
    DataSourceDefinition(
        source_key="company_official",
        source_name="Company Official Sources",
        source_type="ticker_scoped_official",
        provider="Company website / investor relations",
        website_url="",
        docs_url="",
        trust_level=78,
        collection_scope="ticker",
        run_flag="use_company_official",
        collector_group="official_site",
        default_enabled=False,
        status="planned",
        dimensions=("future_events", "company_summary"),
        rate_limit_summary="Ticker-scoped source; only runs when a watched company has official source URLs configured in metadata.",
        cache_policy="Planned per-company cache and checksum-based change detection.",
        notes=("Designed for IR pages, product pages, launch calendars, and company blog/news feeds.",),
    ),
)

DATA_SOURCE_BY_KEY = {source.source_key: source for source in DATA_SOURCE_DEFINITIONS}


def active_source_definitions() -> list[DataSourceDefinition]:
    return [source for source in DATA_SOURCE_DEFINITIONS if source.status == "active"]


def source_definition(source_key: str) -> DataSourceDefinition | None:
    return DATA_SOURCE_BY_KEY.get(source_key)


def source_is_requested(source: DataSourceDefinition, run_config: dict[str, Any]) -> bool:
    if not source.run_flag:
        return source.default_enabled
    return bool(run_config.get(source.run_flag, source.default_enabled))


def source_applies_to_company(source: DataSourceDefinition, company: dict[str, Any] | None) -> bool:
    if source.collection_scope in {"base", "optional"}:
        return True
    company = company or {}
    ticker = str(company.get("ticker") or "").upper()
    if ticker and ticker in {item.upper() for item in source.applies_to_tickers}:
        return True
    if source.collection_scope == "ticker":
        return _has_ticker_source_config(source, company)
    haystack = " ".join(
        str(company.get(key) or "")
        for key in ("name", "sector", "industry")
    )
    metadata = company.get("metadata") or {}
    if isinstance(metadata, dict):
        haystack += " " + " ".join(str(value) for value in metadata.values())
    normalized = haystack.lower()
    return any(keyword.lower() in normalized for keyword in source.applies_to_keywords)


def should_collect_source(source_key: str, run_config: dict[str, Any], company: dict[str, Any] | None = None) -> bool:
    source = source_definition(source_key)
    if not source or source.status != "active":
        return False
    return source_is_requested(source, run_config) and source_applies_to_company(source, company)


def selected_source_keys(run_config: dict[str, Any], company: dict[str, Any] | None = None) -> list[str]:
    return [
        source.source_key
        for source in DATA_SOURCE_DEFINITIONS
        if source.status == "active"
        and source_is_requested(source, run_config)
        and source_applies_to_company(source, company)
    ]


def source_payload(source: DataSourceDefinition, rate_limit_policy: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "source_key": source.source_key,
        "source_name": source.source_name,
        "source_type": source.source_type,
        "trust_level": source.trust_level,
        "enabled": source.status == "active",
        "rate_limit_policy": rate_limit_policy or {},
        "metadata": source.metadata(),
    }


def _has_ticker_source_config(source: DataSourceDefinition, company: dict[str, Any]) -> bool:
    metadata = company.get("metadata") or {}
    if not isinstance(metadata, dict):
        return False
    official_sources = metadata.get("official_sources") or metadata.get("ticker_sources") or []
    if isinstance(official_sources, dict):
        official_sources = [official_sources]
    for item in official_sources:
        if isinstance(item, str) and item.strip():
            return True
        if isinstance(item, dict) and item.get("source_key") == source.source_key:
            return True
    return False
