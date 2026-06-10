# Datasource Integration Log

Last updated: 2026-06-05

This log tracks each datasource from registry entry to runnable collector. It is intentionally operational: if a source cannot be integrated now, record the blocker and a practical alternative instead of leaving it as a vague idea.

## Status Legend

| Status | Meaning |
| --- | --- |
| Connected | Collector is implemented and can write into `raw_observations`, `information_items`, `future_events`, or scoring inputs. |
| Registered | Present in `backlog_screener/datasources.py`, but no collector has been implemented yet. |
| Blocked | Collector cannot be completed without API key, paid access, stable endpoint, or clearer mapping. |
| Deferred | Technically possible, but lower priority or too broad for the current ingestion pass. |

## Current Summary

| Datasource | Scope | Status | Collector / Flag | Notes |
| --- | --- | --- | --- | --- |
| Futu OpenD | Base | Connected | `use_futu` | Market snapshot, valuation, sector, attention flow, and price trend. |
| SEC EDGAR Filings | Base | Connected | `use_sec` | 10-K/10-Q/8-K backlog/RPO text scan. |
| SEC Companyfacts | Base | Connected | `use_sec` | Audited revenue growth and financial quality. |
| SEC Form 4 | Base | Connected | `use_sec` | Insider transactions parsed from SEC filings/XML where available. |
| SEC Schedule 13D/G | Base | Connected | `use_sec` | Beneficial ownership filings. |
| SEC DEF 14A / 10-K Ownership Tables | Base | Connected | `use_sec` | Management/director ownership alignment. |
| SEC 13F Institutional Holdings | Optional | Connected | `use_13f` | Slow curated-manager scan from `configs/13f_managers.csv`. |
| USAspending.gov | Sector | Connected | `use_usaspending` | Public federal contract search for sector-scoped tickers. |
| Yahoo Finance via yFinance | Optional | Connected | `use_yfinance` | Unofficial fallback for missing ownership/valuation and price trend fallback. |
| MiniMax M2.7 | Optional | Connected | `summarize` | Configured locally; used for company and crawled-source summaries. |
| Gemini | Optional | Connected | `summarize` + `LLM_PROVIDER=gemini` | Alternative LLM provider for company, filing, and official-source summaries. |
| Company Official Sources | Ticker | Connected | `use_company_official` | Ticker-specific pages from `configs/company_official_sources.json`. |
| The Space Devs Launch Library 2 | Sector | Connected | `use_launch_library` | Added 2026-06-05; public JSON upcoming launch scan with ticker keyword mapping. |
| OpenInsider | Optional | Connected | `use_openinsider` | Added 2026-06-05; slow ticker-only HTTP screener parser for Form 4 transaction classification. Endpoint is intermittent. |
| Financial Modeling Prep | Optional | Blocked | `use_fmp` | API key not configured locally. |
| SEC-API.io | Optional | Blocked | `use_sec_api_io` | API key not configured locally. |
| Fintel | Optional | Blocked | `use_fintel` | API key/commercial access not configured locally. |
| Ortex | Optional | Blocked | `use_ortex` | Commercial access not configured locally. |
| Finnhub | Optional | Blocked | `use_finnhub` | API key not configured locally. |
| FCC ECFS / OET | Sector | Registered | `use_fcc` | Public search/RSS route still needs endpoint proof and ticker keyword mapping. |
| Industry Conference Agendas | Sector | Deferred | `use_industry_agenda` | Non-standard web pages; needs per-conference URL config and LLM extraction pass. |

## 2026-06-05 Exploration Notes

### The Space Devs Launch Library 2

- Registry key: `launch_library`
- Source: [The Space Devs API](https://ll.thespacedevs.com/2.3.0/launches/upcoming/)
- Status: Connected
- Implemented files:
  - `backlog_screener/launch_library.py`
  - `configs/launch_library_watchlist.json`
  - `HiddenChampionPipeline._collect_launch_library`
  - CLI flag `--launch-library`
  - Web run flag `use_launch_library`
- Live check:
  - `GET https://ll.thespacedevs.com/2.3.0/launches/upcoming/?limit=2` returned HTTP 200 JSON.
  - Response includes launch window fields (`net`, `window_start`, `window_end`), status, provider, rocket, mission, pad/location, and media fields.
- DB verification:
  - Run 54 used `--no-futu --no-sec --launch-library` for `ASTS`.
  - It wrote one `launch_library/upcoming_launches` raw observation and two `future_events` rows for BlueBird launches dated 2026-06-30 and 2026-07-31.
- Matching strategy:
  - Run only when `use_launch_library` is enabled and the company is space/defense/satellite scoped or explicitly listed.
  - Match ticker-specific keywords across launch name, provider, rocket, mission, mission agencies, orbit, pad, and location.
  - Initial ticker config covers `RKLB`, `ASTS`, and `RDW`.
- Data written:
  - `raw_observations`: complete Launch Library match JSON.
  - `information_items`: `future_events` timeline rows.
  - `future_events`: timetable catalyst rows with launch date/window/status.
- Current limitation:
  - Payload ownership is inferred from mission text and keyword matching; this is useful for alerts but still needs manual review for weak keyword matches.
  - Launch Library `upcoming` can include very recent completed launches, so the collector filters successful/old launches and keeps only future-ish events.
  - Short keywords are risky. `RDW` originally included standalone `ROSA`, but live probing produced weak matches, so the config was tightened to longer phrases.
- Alternative / supplement:
  - Company official mission pages can validate whether a matched launch is actually material to the ticker.
  - FCC/OET filings may lead launch or spectrum catalysts earlier than Launch Library.

### API-Key Sources

Local key availability was checked without printing secret values.

| Source | Local key status | Current decision | Alternative while blocked |
| --- | --- | --- | --- |
| MiniMax | Configured | Continue using for summaries/translations. | Heuristic fallback only if request fails. |
| Gemini | Missing | Provider is implemented, but local default remains MiniMax until `LLM_PROVIDER=gemini` and `GEMINI_API_KEY` are configured. | MiniMax is currently configured. |
| Finnhub | Missing | Keep registered; do not mark active until key and endpoint response are verified. | FMP calendar if FMP key arrives; SEC 8-K/press releases for announced dates. |
| Financial Modeling Prep | Missing | Keep registered; useful next paid source because it covers calendars, holders, insider trades, and valuation series. | SEC Form 4 + SEC 13F + yFinance fallback. |
| Fintel | Missing | Keep registered; needs paid/API access. | FINRA short-interest files or Nasdaq short-interest pages if acceptable. |
| Ortex | Missing | Keep registered; needs commercial access. | Fintel or FINRA/Nasdaq short-interest alternatives. |
| SEC-API.io | Missing | Keep registered; useful for text search and XBRL tag extraction when key exists. | Native SEC EDGAR + local text scan, already implemented. |
| FCC ECFS public API | Missing | API route is proven, but collector should wait for `FCC_API_KEY`. | SEC 8-K/company official sources for later confirmation. |

### FCC ECFS / OET

- Status: Registered, not connected.
- Reason:
  - `https://www.fcc.gov/ecfs` and ECFS search pages returned HTTP 403 from the current environment, so broad web scraping is not a good path.
  - `https://publicapi.fcc.gov/ecfs/filings` is the better route, but it requires an `api_key`; requests without one return `API_KEY_MISSING`.
  - A probe with the FCC public demo key proved the response shape for `q=AST SpaceMobile`, including filing id, submission dates, proceedings, filers, documents, and text snippets. A real local `FCC_API_KEY` is still needed before marking this source active.
- Proposed next attempt:
  - Add `FCC_API_KEY` setting and a shortlist-only client for `publicapi.fcc.gov/ecfs/filings`.
  - Configure ticker keywords for `ASTS`, `RKLB`, `RDW`, plus company/legal names.
  - Cache by FCC filing/action id and only feed changed snippets to MiniMax for summary.
- Alternative:
  - Company official IR/news + SEC 8-K often announce major license approvals after the fact; FCC should remain a left-side source once stable.

### OpenInsider

- Status: Connected.
- Implemented files:
  - `backlog_screener/openinsider.py`
  - `HiddenChampionPipeline._collect_openinsider`
  - CLI flag `--openinsider`
  - Web run flag `use_openinsider`
  - Tests in `tests/test_openinsider.py`
- Live check:
  - `https://openinsider.com/screener?s=CRDO` and `https://www.openinsider.com/screener?s=CRDO` failed TLS handshake in the current environment.
  - `http://openinsider.com/screener?s=CRDO` returned HTTP 200 HTML with a ticker Form 4 table.
  - Later repeated probes returned intermittent `502 Bad Gateway` or empty HTTP replies, so this source should be treated as opportunistic enrichment rather than a required run stage.
- DB verification:
  - Run 55 used `--no-futu --no-sec --openinsider` for `CRDO` while the endpoint was returning empty replies; it completed and wrote an `openinsider/ticker_screener_error` raw observation instead of failing the whole run.
  - Run 56 repeated the same CRDO-only ingest after adding proxy/direct fallback; it wrote one `openinsider/ticker_screener` raw observation with 100 parsed rows and one `insider_activity` information item. Parsed values showed 0 purchases, 100 sales, and about `-$496.0M` net open-market purchase value from the returned OpenInsider table.
- Matching / parsing strategy:
  - Fetch ticker-specific screener pages only; no broad all-market scraping.
  - Try the normal environment/proxy path first, then direct HTTP as a fallback.
  - Cache HTML by ticker screener URL for 24 hours.
  - Parse returned table rows for Filing Date, Trade Date, Insider Name, Title, Trade Type, Price, Qty, Owned, delta ownership, Value, SEC Form 4 URL, and insider profile URL.
  - Treat non-derivative `P - Purchase` and `S - Sale` rows as open-market buy/sell signals; keep awards/options/grants in raw evidence but exclude them from net open-market purchase totals.
- Data written:
  - `raw_observations`: complete parsed screener signal.
  - `information_items`: one `insider_activity` item with purchase count, sale count, purchase value, sale value, and net purchase value.
- Current limitation:
  - OpenInsider has no official API, so this source is lower trust than direct SEC Form 4 parsing.
  - The current environment requires HTTP, not HTTPS, for OpenInsider.
  - The endpoint can become temporarily unavailable during repeated probes; the collector records an error observation instead of failing the whole run.
  - Page structure changes can break parsing; the collector writes a warning when no table rows are parseable.
- Alternative:
  - Native SEC Form 4 parser is already connected and more official, but less user-friendly for classifying transaction intent.

### Industry Conference Agendas

- Status: Deferred.
- Reason:
  - This is many small scrapers rather than one datasource. Needs a URL config, checksum cache, and LLM extraction prompt.
- Proposed next attempt:
  - Add `configs/industry_agendas.json` with agenda URL, sector, date, and watched company keywords.
  - Fetch slowly, detect changes by checksum, then call MiniMax only on changed agenda text.
- Alternative:
  - Company official news and SEC 8-K are cleaner but later than conference agenda changes.
