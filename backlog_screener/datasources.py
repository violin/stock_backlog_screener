from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


SOURCE_REGISTRY_VERSION = 3


SOURCE_LOCALIZATION: dict[str, dict[str, Any]] = {
    "futu_opend": {
        "purpose_en": "Provides market snapshots, valuation fields, sector labels, price history, and capital-flow signals for broad first-pass screening.",
        "purpose_zh": "提供行情快照、估值字段、行业归属、价格历史和资金流信号，是大范围初筛的基础盘面层。",
        "rate_limit_summary_zh": "实测条件选股约 30 秒 10 次；资金流约 30 秒 30 次。需要单线程和批次控制。",
        "cache_policy_zh": "依赖本地 OpenD 网关；当前不做 HTTP 缓存。",
    },
    "sec_edgar": {
        "purpose_en": "Fetches 10-K, 10-Q, and 8-K text so the system can extract backlog, RPO, contract language, risks, and management commentary.",
        "purpose_zh": "抓取 10-K、10-Q、8-K 原文，用于提取 backlog、RPO、合同描述、风险和管理层表述。",
        "rate_limit_summary_zh": "对 SEC 做礼貌单线程请求，并配合本地 accession/document 缓存和短延迟。",
        "cache_policy_zh": "按 CIK、accession 和 document 缓存 12 小时。",
    },
    "sec_companyfacts": {
        "purpose_en": "Reads SEC XBRL company facts for revenue, margin, cash, debt, working capital, and other audited financial metrics.",
        "purpose_zh": "读取 SEC XBRL 公司事实，用于收入、利润率、现金、负债、营运资本等审计口径财务指标。",
        "rate_limit_summary_zh": "SEC 礼貌单线程请求；复用 companyfacts 缓存。",
        "cache_policy_zh": "按 CIK 缓存 12 小时。",
    },
    "sec_form4": {
        "purpose_en": "Collects recent insider transactions directly from SEC filings and XML where available.",
        "purpose_zh": "直接从 SEC Form 4 和可用 XML 中采集高管、董事等内部人交易。",
        "rate_limit_summary_zh": "SEC 礼貌单线程抓取，并使用本地文件缓存。",
        "cache_policy_zh": "披露文件缓存 12 小时。",
    },
    "sec_beneficial_ownership": {
        "purpose_en": "Tracks beneficial ownership filings from large holders and activist-style investors.",
        "purpose_zh": "跟踪大股东和潜在积极投资者的 13D/G 权益披露。",
        "rate_limit_summary_zh": "SEC 礼貌单线程抓取，并使用本地文件缓存。",
        "cache_policy_zh": "披露文件缓存 12 小时。",
    },
    "sec_proxy_ownership": {
        "purpose_en": "Extracts management, director, and board ownership alignment from proxy and annual-report ownership tables.",
        "purpose_zh": "从 proxy 和年报持股表中提取管理层、董事会和内部人持股绑定。",
        "rate_limit_summary_zh": "SEC 礼貌单线程抓取，并使用本地文件缓存。",
        "cache_policy_zh": "proxy/10-K ownership 缓存 24 小时。",
    },
    "sec_13f": {
        "purpose_en": "Scans curated manager 13F filings to find institutional accumulation or exits in shortlist names.",
        "purpose_zh": "扫描精选机构 13F，寻找短名单标的的机构建仓、加仓或退出线索。",
        "rate_limit_summary_zh": "慢速可选扫描；只适合短名单，不适合全市场广撒网。",
        "cache_policy_zh": "manager filing 和 information table 缓存 24 小时。",
    },
    "usaspending": {
        "purpose_en": "Finds federal awards, agencies, recipients, and contract amounts that can validate government demand before or alongside company filings.",
        "purpose_zh": "查询美国联邦政府 award、机构、收款方和合同金额，用于验证政府订单和补贴需求。",
        "rate_limit_summary_zh": "免费公开 API；建议单线程、24 小时缓存、每个标的约 1 秒延迟。",
        "cache_policy_zh": "按查询和时间窗口缓存 recipient award 24 小时。",
    },
    "yfinance": {
        "purpose_en": "Provides a quick unofficial fallback for valuation, ownership, and market fields missing from primary sources.",
        "purpose_zh": "作为非官方免费 fallback，补齐主数据源缺失的估值、持股和行情字段。",
        "rate_limit_summary_zh": "非官方源；避免大批量实时抓取，遇到 429 要退避。",
        "cache_policy_zh": "按 ticker 缓存 24 小时。",
    },
    "minimax": {
        "purpose_en": "Summarizes collected evidence into company profile, thesis, risks, and watch items; it is not treated as raw truth.",
        "purpose_zh": "把已采集证据总结为公司画像、投资逻辑、风险和跟踪点；不作为原始事实源。",
        "rate_limit_summary_zh": "可选 LLM 调用；单线程、重试一次，能不用就回退到启发式摘要。",
        "cache_policy_zh": "摘要保存为 information_items，不做大范围自动刷新。",
    },
    "gemini": {
        "purpose_en": "Alternative Gemini LLM provider for company profiles, filing summaries, and official-source translation.",
        "purpose_zh": "可替代的 Gemini LLM 摘要源，用于公司画像、公告摘要和官网/IR 片段译写。",
        "rate_limit_summary_zh": "可选 LLM 调用；单线程、重试一次，遇到限流或权限错误应回退或人工复核。",
        "cache_policy_zh": "摘要保存为 information_items，不做大范围自动刷新。",
    },
    "fmp": {
        "purpose_en": "Provides paid structured JSON for calendars, estimates, holders, insider trades, and historical valuation series.",
        "purpose_zh": "提供付费结构化 JSON，用于财报日历、预期值、机构持仓、内部人交易和历史估值序列。",
        "rate_limit_summary_zh": "限流取决于套餐；建议在 Futu/SEC 初筛后对短名单调用。",
        "cache_policy_zh": "计划按日缓存估值历史、13F holders、insider trades 和财报日历。",
    },
    "openinsider": {
        "purpose_en": "Classifies insider trades, especially open-market buys versus grants, options, and indirect transactions.",
        "purpose_zh": "更细地区分公开市场买入、授予、期权行权和间接交易等内部人交易类型。",
        "rate_limit_summary_zh": "无官方 API；当前只抓单 ticker HTTP screener，慢速运行并限制在短名单。",
        "cache_policy_zh": "按 ticker screener URL 缓存 24 小时。",
    },
    "sec_api_io": {
        "purpose_en": "Adds paid structured SEC search, XBRL tag extraction, filing text search, and possible Form 4 webhook support.",
        "purpose_zh": "提供付费 SEC 结构化搜索、XBRL 标签提取、披露文本检索和 Form 4 webhook 等增强能力。",
        "rate_limit_summary_zh": "限流取决于套餐；适合短名单的 XBRL/text-search/Form 4 增强。",
        "cache_policy_zh": "计划按 ticker、accession、关键词和 XBRL tag 缓存查询结果。",
    },
    "fintel": {
        "purpose_en": "Tracks short-interest pressure, borrow fee, available shares, squeeze score, and days-to-cover style signals.",
        "purpose_zh": "跟踪空头压力、借券费率、可借股数、轧空评分和回补天数等交易弹性信号。",
        "rate_limit_summary_zh": "商业 API；建议按日缓存，只有进入 squeeze watch 时缩短 TTL。",
        "cache_policy_zh": "计划按 ticker 日缓存，重点窗口缩短缓存时间。",
    },
    "ortex": {
        "purpose_en": "Alternative commercial source for short interest, borrow utilization, cost-to-borrow, and securities lending signals.",
        "purpose_zh": "商业替代源，用于空头比例、借券利用率、借券成本和证券借贷信号。",
        "rate_limit_summary_zh": "商业访问；若接入只对短名单调用。",
        "cache_policy_zh": "计划按 ticker 日缓存；除非授权 feed 支持，否则不做全市场轮询。",
    },
    "finnhub": {
        "purpose_en": "Provides earnings calendars, event calendar deltas, estimates, and optional webhook-style notifications.",
        "purpose_zh": "提供财报日历、事件变更、预期值和可选 webhook 通知。",
        "rate_limit_summary_zh": "限流取决于套餐；适合财报和事件日历增量更新。",
        "cache_policy_zh": "计划按日历窗口缓存，并按 ticker/date/event type 去重 webhook。",
    },
    "launch_library": {
        "purpose_en": "Provides structured upcoming launch windows, providers, rockets, payloads, mission status, and webcast links.",
        "purpose_zh": "提供结构化未来发射窗口、发射商、火箭、载荷、任务状态和直播链接。",
        "rate_limit_summary_zh": "免费公开 JSON API；只对航天相关 ticker 跑，并用短 TTL 缓存避免频繁轮询。",
        "cache_policy_zh": "upcoming launches 结果缓存 6 小时；按 ticker keyword mapping 提取匹配事件。",
    },
    "fcc_ecfs_oet": {
        "purpose_en": "Monitors FCC dockets, actions, and approvals that can lead satellite, spectrum, and communications catalysts.",
        "purpose_zh": "监控 FCC docket、action 和 approval，用于卫星、频谱和通信类监管催化剂。",
        "rate_limit_summary_zh": "FCC public API 需要 api_key；只对航天和卫星通信相关标的做慢速关键词检查。",
        "cache_policy_zh": "计划按关键词、ticker 映射和 filing id 做日缓存。",
    },
    "industry_agenda": {
        "purpose_en": "Scrapes selected conference agendas and lets an LLM identify company speakers, product launches, and technology themes.",
        "purpose_zh": "抓取重点会议 agenda，并让 LLM 识别上市公司演讲、新产品发布和技术主题。",
        "rate_limit_summary_zh": "非标准网页；慢速抓取、强缓存，只把变化的 agenda 丢给 LLM。",
        "cache_policy_zh": "计划按会议 agenda URL 和日期做 checksum 缓存。",
    },
    "company_official": {
        "purpose_en": "Tracks ticker-specific official news, investor relations pages, product pages, mission pages, and launch calendars.",
        "purpose_zh": "跟踪单票公司官网、IR 新闻、产品页、任务页和发射日历等官方信息。",
        "rate_limit_summary_zh": "单 ticker 来源；只有显式开启且公司配置 official_sources 后才运行。",
        "cache_policy_zh": "按 URL 做 24 小时缓存，并保存页面 checksum 方便后续检测变化。",
    },
    "company_ir_calendar": {
        "purpose_en": "Tracks ticker-specific official investor-relations event calendars, earnings releases, conference appearances, and webcast pages.",
        "purpose_zh": "跟踪单票官方 IR 事件日历、财报发布、会议露出和 webcast 页面。",
        "rate_limit_summary_zh": "单 ticker 来源；优先用公司官方 IR 页面确认日期，未确认前只作为低置信度窗口。",
        "cache_policy_zh": "配置事件作为人工 seed；官方 IR 页面采集按 URL 24 小时缓存。",
    },
}


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
        data.update(SOURCE_LOCALIZATION.get(self.source_key, {}))
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
        source_key="gemini",
        source_name="Gemini",
        source_type="llm_summary",
        provider="Google",
        website_url="https://ai.google.dev/",
        docs_url="https://ai.google.dev/api",
        trust_level=70,
        collection_scope="optional",
        run_flag="summarize",
        collector_group="summary",
        default_enabled=False,
        auth="API key required",
        dimensions=("company_summary",),
        rate_limit_summary="Optional LLM call; single-threaded, retry once, and fall back to heuristic summaries where possible.",
        cache_policy="Summary is persisted as information_items; no broad automatic refresh.",
        notes=("Set LLM_PROVIDER=gemini and GEMINI_API_KEY to use this provider.",),
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
        status="active",
        dimensions=("insider_activity",),
        rate_limit_summary="No official API; fetch ticker screener pages slowly and only for shortlist symbols.",
        cache_policy="24-hour HTML cache by ticker screener URL.",
        notes=("Classifies open-market purchases and sales from ticker-specific Form 4 tables.",),
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
        status="active",
        dimensions=("future_events",),
        applies_to_keywords=("aerospace", "space", "satellite", "defense"),
        applies_to_tickers=("RKLB", "ASTS", "RDW"),
        rate_limit_summary="Public JSON API; cached and run only for space-exposed tickers.",
        cache_policy="6-hour cache for upcoming launch windows plus ticker keyword mapping.",
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
        auth="FCC public API key required",
        dimensions=("future_events", "regulatory"),
        applies_to_keywords=("space", "satellite", "communications", "telecom", "aerospace"),
        applies_to_tickers=("ASTS", "RKLB", "RDW"),
        rate_limit_summary="FCC public API requires api_key; run slow keyword checks for space and satellite exposed tickers only.",
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
        dimensions=("future_events",),
        rate_limit_summary="Ticker-scoped source; only runs when a watched company has official source URLs configured in metadata.",
        cache_policy="24-hour per-URL cache with checksum metadata for later change detection.",
        notes=("Designed for IR pages, product pages, launch calendars, and company blog/news feeds.",),
    ),
    DataSourceDefinition(
        source_key="company_ir_calendar",
        source_name="Company IR Event Calendar",
        source_type="future_event_calendar",
        provider="Company investor relations sites",
        website_url="",
        docs_url="",
        trust_level=82,
        collection_scope="ticker",
        run_flag="use_company_official",
        collector_group="future_events",
        default_enabled=False,
        status="active",
        dimensions=("future_events",),
        applies_to_tickers=("PL",),
        rate_limit_summary="Ticker-scoped official IR calendar checks; manual seed dates remain low-confidence until confirmed.",
        cache_policy="Manual seed config plus 24-hour URL cache when official pages are collected.",
        notes=("Configured timetable seeds live in configs/timetable_seed_events.json.",),
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
    requested = bool(run_config.get(source.run_flag, source.default_enabled))
    if source.source_key in {"minimax", "gemini"}:
        provider = str(run_config.get("llm_provider") or "minimax").strip().lower()
        if provider not in {"minimax", "gemini"}:
            provider = "minimax"
        return requested and source.source_key == provider
    return requested


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
        if isinstance(item, dict):
            if item.get("source_key") == source.source_key:
                return True
            if source.source_key == "company_official" and item.get("url"):
                return True
    return False
