from __future__ import annotations

import csv
import time
from pathlib import Path
from typing import Callable, Iterable

from .company_official import CompanyOfficialClient
from .config import BacklogScanConfig
from .datasources import SOURCE_REGISTRY_VERSION, should_collect_source
from .db import PostgresStore
from .futu_provider import (
    FutuProvider,
    classification_from_futu_plates,
    futu_code,
    information_from_futu_attention,
    information_from_futu_plates,
    information_from_futu_snapshot,
    metrics_from_futu_snapshot,
)
from .launch_library import LaunchLibraryClient
from .llm import LlmSummary, SummaryClient, build_llm_client, heuristic_summary
from .openinsider import OpenInsiderClient
from .product_scoring import MODEL_VERSION, score_hidden_champion
from .sec import (
    SEC_ANNUAL_FORMS,
    SEC_PERIODIC_FORMS,
    SecClient,
    analyze_13f_holdings,
    analyze_beneficial_ownership,
    analyze_form4_transactions,
    analyze_proxy_ownership,
    clean_filing_text,
    extract_backlog_amounts,
    latest_financial_quality,
    latest_quarterly_revenue_yoy,
    scan_text_for_backlog,
    summarize_backlog_quality,
)
from .settings import AppSettings, PROJECT_ROOT
from .usaspending import USASpendingClient
from .yahoo import fetch_candidate_metrics


class HiddenChampionPipeline:
    def __init__(self, store: PostgresStore, settings: AppSettings):
        self.store = store
        self.settings = settings

    def run(
        self,
        tickers: Iterable[str],
        *,
        trigger: str = "manual",
        use_futu: bool = True,
        use_sec: bool = True,
        use_yfinance: bool = False,
        use_13f: bool = False,
        use_usaspending: bool = False,
        use_launch_library: bool = False,
        use_company_official: bool = False,
        use_openinsider: bool = False,
        summarize: bool = False,
        delay_seconds: float = 1.0,
        run_context: dict | None = None,
        progress_callback: Callable[[dict], None] | None = None,
    ) -> int:
        clean_tickers = _clean_tickers(tickers)
        config = {
            "use_futu": use_futu,
            "use_sec": use_sec,
            "use_yfinance": use_yfinance,
            "use_13f": use_13f,
            "use_usaspending": use_usaspending,
            "use_launch_library": use_launch_library,
            "use_company_official": use_company_official,
            "use_openinsider": use_openinsider,
            "summarize": summarize,
            "llm_provider": self.settings.llm_provider,
            "delay_seconds": delay_seconds,
            "source_registry_version": SOURCE_REGISTRY_VERSION,
        }
        if run_context:
            config.update(run_context)
        run_id = self.store.start_run(
            tickers=clean_tickers,
            trigger=trigger,
            config=config,
        )
        _notify(progress_callback, {"event": "run_started", "run_id": run_id, "tickers": clean_tickers})
        try:
            for ticker in clean_tickers:
                self.store.upsert_company(ticker, market="US", futu_code=futu_code(ticker, self.settings.futu_market))

            if should_collect_source("futu_opend", config):
                _notify(progress_callback, {"event": "stage", "stage": "Futu OpenD bulk snapshot"})
                self._collect_futu(run_id, clean_tickers)

            sec_client = SecClient(PROJECT_ROOT / ".cache" / "sec", user_agent=self.settings.sec_user_agent)
            usaspending_client = (
                USASpendingClient(PROJECT_ROOT / ".cache" / "usaspending") if use_usaspending else None
            )
            launch_library_client = (
                LaunchLibraryClient(
                    PROJECT_ROOT / ".cache" / "launch_library",
                    config_path=PROJECT_ROOT / "configs" / "launch_library_watchlist.json",
                )
                if use_launch_library
                else None
            )
            openinsider_client = (
                OpenInsiderClient(PROJECT_ROOT / ".cache" / "openinsider")
                if use_openinsider
                else None
            )
            company_official_client = (
                CompanyOfficialClient(
                    PROJECT_ROOT / ".cache" / "company_official",
                    config_path=PROJECT_ROOT / "configs" / "company_official_sources.json",
                )
                if use_company_official
                else None
            )
            llm_client = (
                self._llm_client()
                if should_collect_source("minimax", config)
                or should_collect_source("gemini", config)
                or use_company_official
                else None
            )
            for index, ticker in enumerate(clean_tickers, start=1):
                _notify(
                    progress_callback,
                    {
                        "event": "ticker_started",
                        "ticker": ticker,
                        "index": index,
                        "total": len(clean_tickers),
                    },
                )
                if company_official_client is not None:
                    official_sources = company_official_client.sources_for_ticker(ticker)
                    if official_sources:
                        self.store.upsert_company(ticker, metadata={"official_sources": official_sources})
                company = self.store.company(ticker) or {"ticker": ticker}
                if should_collect_source("sec_edgar", config, company):
                    _notify(progress_callback, {"event": "stage", "stage": f"{ticker} SEC filings"})
                    self._collect_sec_filing(run_id, ticker, sec_client, llm_client)
                    self._collect_sec_companyfacts(run_id, ticker, sec_client)
                    self._collect_sec_form4(run_id, ticker, sec_client)
                    self._collect_sec_beneficial_ownership(run_id, ticker, sec_client)
                    self._collect_sec_proxy_ownership(run_id, ticker, sec_client)
                    if should_collect_source("sec_13f", config, company):
                        self._collect_sec_13f(run_id, ticker, sec_client)
                    time.sleep(max(0, delay_seconds))
                if usaspending_client is not None and should_collect_source("usaspending", config, company):
                    _notify(progress_callback, {"event": "stage", "stage": f"{ticker} USAspending contracts"})
                    self._collect_usaspending(run_id, ticker, usaspending_client)
                    time.sleep(max(0, delay_seconds))
                if launch_library_client is not None and should_collect_source("launch_library", config, company):
                    _notify(progress_callback, {"event": "stage", "stage": f"{ticker} Launch Library events"})
                    self._collect_launch_library(run_id, ticker, launch_library_client)
                    time.sleep(max(0, delay_seconds))
                if openinsider_client is not None and should_collect_source("openinsider", config, company):
                    _notify(progress_callback, {"event": "stage", "stage": f"{ticker} OpenInsider transactions"})
                    self._collect_openinsider(run_id, ticker, openinsider_client)
                    time.sleep(max(0, delay_seconds))
                if should_collect_source("yfinance", config, company):
                    _notify(progress_callback, {"event": "stage", "stage": f"{ticker} yFinance fallback"})
                    self._collect_yfinance(run_id, ticker)
                    time.sleep(max(0, delay_seconds))
                company = self.store.company(ticker) or company
                if company_official_client is not None and should_collect_source("company_official", config, company):
                    _notify(progress_callback, {"event": "stage", "stage": f"{ticker} official sources"})
                    self._collect_company_official(run_id, ticker, company_official_client, llm_client)
                    time.sleep(max(0, delay_seconds))
                _notify(progress_callback, {"event": "stage", "stage": f"{ticker} scoring"})
                self._score_ticker(run_id, ticker)
                _notify(progress_callback, {"event": "ticker_done", "ticker": ticker})

            self.store.finish_run(run_id, status="DONE")
            _notify(progress_callback, {"event": "run_done", "run_id": run_id})
            return run_id
        except Exception as exc:
            self.store.finish_run(run_id, status="FAILED", error=str(exc))
            _notify(progress_callback, {"event": "run_failed", "run_id": run_id, "error": str(exc)})
            raise

    def _collect_futu(self, run_id: int, tickers: list[str]) -> None:
        with FutuProvider(
            host=self.settings.futu_host,
            port=self.settings.futu_port,
            market=self.settings.futu_market,
        ) as provider:
            owner_plates = provider.owner_plates(tickers)
            for ticker, plates in owner_plates.items():
                classification = classification_from_futu_plates(ticker, plates)
                self.store.upsert_company(
                    ticker,
                    market="US",
                    futu_code=futu_code(ticker, self.settings.futu_market),
                    sector=classification.get("sector") or "",
                    industry=classification.get("industry") or "",
                    metadata={
                        "futu_primary_plate": classification.get("primary_plate"),
                        "futu_plates": classification.get("plates"),
                    },
                )
                observation_id = self.store.save_observation(
                    run_id=run_id,
                    ticker=ticker,
                    source_key="futu_opend",
                    source_type="classification",
                    observation_type="owner_plate",
                    title=f"{ticker.upper()} Futu owner plates",
                    raw_json={"plates": plates, "classification": classification},
                    trust_level=82,
                )
                self.store.save_information_item(
                    run_id=run_id,
                    observation_id=observation_id,
                    source_key="futu_opend",
                    source_url="",
                    **information_from_futu_plates(classification),
                )

            for record in provider.snapshots(tickers):
                metrics = metrics_from_futu_snapshot(record)
                self.store.upsert_company(
                    metrics.ticker,
                    name=metrics.name,
                    market="US",
                    futu_code=record.get("code"),
                )
                observation_id = self.store.save_observation(
                    run_id=run_id,
                    ticker=metrics.ticker,
                    source_key="futu_opend",
                    source_type="market_data",
                    observation_type="snapshot",
                    title=f"{metrics.ticker} Futu market snapshot",
                    source_published_at=record.get("update_time"),
                    raw_json=record,
                    trust_level=85,
                )
                for item in information_from_futu_snapshot(record):
                    self.store.save_information_item(
                        run_id=run_id,
                        observation_id=observation_id,
                        source_key="futu_opend",
                        source_url="",
                        **item,
                    )

            for index, ticker in enumerate(tickers, start=1):
                try:
                    raw_attention = provider.attention_flow(ticker)
                except Exception as exc:
                    self.store.save_observation(
                        run_id=run_id,
                        ticker=ticker,
                        source_key="futu_opend",
                        source_type="market_data",
                        observation_type="attention_flow_error",
                        title=f"{ticker.upper()} Futu attention flow unavailable",
                        raw_json={"error": str(exc)},
                        trust_level=35,
                    )
                    continue
                observation_id = self.store.save_observation(
                    run_id=run_id,
                    ticker=ticker,
                    source_key="futu_opend",
                    source_type="market_data",
                    observation_type="attention_flow",
                    title=f"{ticker.upper()} Futu main-money and momentum snapshot",
                    source_published_at=(raw_attention.get("capital_distribution") or {}).get("update_time") or None,
                    raw_json=raw_attention,
                    trust_level=72,
                )
                item = information_from_futu_attention(raw_attention)
                if item:
                    self.store.save_information_item(
                        run_id=run_id,
                        observation_id=observation_id,
                        source_key="futu_opend",
                        source_url="",
                        **item,
                    )
                if index < len(tickers):
                    time.sleep(1.05)

    def _collect_sec_filing(
        self,
        run_id: int,
        ticker: str,
        sec_client: SecClient,
        llm_client: SummaryClient | None,
    ) -> None:
        filings = _unique_filings(
            [
                *sec_client.latest_filings(ticker, forms=SEC_PERIODIC_FORMS, limit=8),
                *sec_client.latest_filings(ticker, forms=SEC_ANNUAL_FORMS, limit=3),
            ]
        )
        if not filings:
            return
        selected = None
        config = BacklogScanConfig()
        for filing in filings:
            try:
                raw_text = sec_client.filing_text(filing)
            except Exception:
                continue
            cleaned = clean_filing_text(raw_text)
            backlog_count, rpo_count, snippets = scan_text_for_backlog(
                cleaned,
                terms=config.terms,
                radius=360,
                max_snippets=6,
            )
            amounts = extract_backlog_amounts(cleaned, snippets) if backlog_count + rpo_count > 0 else []
            selected = (filing, cleaned, backlog_count, rpo_count, snippets, amounts)
            if backlog_count + rpo_count > 0:
                break
        if not selected:
            return
        filing, cleaned, backlog_count, rpo_count, snippets, amounts = selected
        backlog_quality = summarize_backlog_quality(backlog_count, rpo_count, amounts)
        observation_id = self.store.save_observation(
            run_id=run_id,
            ticker=ticker,
            source_key="sec_edgar",
            source_type="filing",
            observation_type=filing.form,
            title=f"{ticker.upper()} latest {filing.form}",
            source_url=filing.url,
            source_published_at=filing.filing_date,
            raw_text=cleaned,
            raw_json={
                "form": filing.form,
                "filing_date": filing.filing_date,
                "accession": filing.accession,
                "primary_document": filing.primary_document,
                "backlog_mentions": backlog_count,
                "rpo_mentions": rpo_count,
                "backlog_amounts": amounts,
                "snippets": snippets,
            },
            trust_level=95,
        )
        summary = self._summarize_filing(
            ticker=ticker,
            title=f"{ticker.upper()} {filing.form} backlog/RPO scan",
            snippets=snippets,
            backlog_mentions=backlog_count,
            rpo_mentions=rpo_count,
            llm_client=llm_client,
        )
        self.store.save_information_item(
            run_id=run_id,
            observation_id=observation_id,
            ticker=ticker,
            dimension="backlog",
            event_date=filing.filing_date,
            title=f"{ticker.upper()} backlog/RPO signal",
            summary=summary.summary,
            raw_excerpt="\n\n".join(snippets),
            source_key="sec_edgar",
            source_url=filing.url,
            importance_score=summary.importance_score,
            quality_score=90,
            sentiment_score=summary.sentiment_score,
            confidence_score=summary.confidence_score,
            extracted_by=summary.provider,
            evidence={
                "backlog_mentions": backlog_count,
                "rpo_mentions": rpo_count,
                "backlog_largest_amount": backlog_quality.get("largest_amount"),
                "backlog_amount_mentions": backlog_quality.get("amount_mentions"),
                "form": filing.form,
                "filing_date": filing.filing_date,
            },
        )
        if amounts:
            self.store.save_information_item(
                run_id=run_id,
                observation_id=observation_id,
                ticker=ticker,
                dimension="backlog_quality",
                event_date=filing.filing_date,
                title=f"{ticker.upper()} backlog/RPO amount clues",
                summary=(
                    f"SEC 文件中抽取到 {len(amounts)} 个疑似 backlog/RPO 金额线索，"
                    f"最大值约 {_money(backlog_quality['largest_amount'])}。"
                ),
                raw_excerpt="\n\n".join(item["context"] for item in amounts[:4]),
                source_key="sec_edgar",
                source_url=filing.url,
                importance_score=82,
                quality_score=70,
                confidence_score=58,
                extracted_by="heuristic",
                evidence=backlog_quality,
            )

    def _collect_sec_companyfacts(self, run_id: int, ticker: str, sec_client: SecClient) -> None:
        facts = sec_client.companyfacts(ticker)
        if not facts:
            return
        revenue = latest_quarterly_revenue_yoy(facts)
        quality = latest_financial_quality(facts)
        observation_id = self.store.save_observation(
            run_id=run_id,
            ticker=ticker,
            source_key="sec_companyfacts",
            source_type="fundamental",
            observation_type="companyfacts",
            title=f"{ticker.upper()} SEC companyfacts",
            raw_json={
                "entityName": facts.get("entityName"),
                "cik": facts.get("cik"),
                "revenue_yoy": revenue,
                "financial_quality": quality,
            },
            trust_level=92,
        )
        if revenue:
            yoy = revenue["value"]
            latest = revenue["latest"]
            prior = revenue["prior_year_quarter"]
            period_label = "季度" if revenue.get("period_type") == "quarterly" else "年度"
            self.store.save_information_item(
                run_id=run_id,
                observation_id=observation_id,
                ticker=ticker,
                dimension="growth",
                event_date=latest.get("end"),
                title=f"{ticker.upper()} {period_label} revenue growth",
                summary=(
                    f"SEC companyfacts 显示最近{period_label}收入同比约 {yoy * 100:.1f}%，"
                    f"最新值 {latest.get('value'):,.0f} {latest.get('unit')}，"
                    f"去年同期 {prior.get('value'):,.0f}。"
                ),
                source_key="sec_companyfacts",
                importance_score=78 if yoy >= 0.25 else 50,
                quality_score=88,
                confidence_score=84,
                evidence={
                    "quarterly_revenue_yoy": yoy,
                    "revenue_growth_period_type": revenue.get("period_type", "quarterly"),
                    "latest_revenue": latest,
                    "prior_year_revenue": prior,
                },
            )
        if quality:
            self.store.save_information_item(
                run_id=run_id,
                observation_id=observation_id,
                ticker=ticker,
                dimension="quality",
                event_date=quality.get("period_end"),
                title=f"{ticker.upper()} profitability and balance sheet quality",
                summary=_quality_summary(quality),
                source_key="sec_companyfacts",
                importance_score=72,
                quality_score=86,
                confidence_score=78,
                evidence=quality,
            )

    def _collect_sec_form4(self, run_id: int, ticker: str, sec_client: SecClient) -> None:
        filings = sec_client.latest_filings(ticker, forms=("4", "4/A"), limit=12)
        if not filings:
            return
        filing_texts = []
        for filing in filings:
            try:
                filing_texts.append((filing, sec_client.filing_text(filing)))
            except Exception:
                continue
        analysis = analyze_form4_transactions(filing_texts)
        observation_id = self.store.save_observation(
            run_id=run_id,
            ticker=ticker,
            source_key="sec_form4",
            source_type="insider_transactions",
            observation_type="form4_recent",
            title=f"{ticker.upper()} recent Form 4 insider transactions",
            raw_json=analysis,
            trust_level=92,
        )
        if analysis["transaction_count"] <= 0:
            return
        self.store.save_information_item(
            run_id=run_id,
            observation_id=observation_id,
            ticker=ticker,
            dimension="insider_activity",
            event_date=analysis["transactions"][0].get("filing_date"),
            title=f"{ticker.upper()} insider transaction activity",
            summary=(
                f"最近 {analysis['transaction_count']} 笔 Form 4 非衍生品交易中，"
                f"买入 {analysis['purchase_count']} 笔、卖出 {analysis['sale_count']} 笔，"
                f"估算净买入金额 {_money(analysis['net_purchase_value'])}。"
            ),
            source_key="sec_form4",
            source_url=analysis["transactions"][0].get("url", ""),
            importance_score=74 if analysis["net_purchase_value"] > 0 else 52,
            quality_score=82,
            sentiment_score=18 if analysis["net_purchase_value"] > 0 else -8 if analysis["sale_value"] else 0,
            confidence_score=70,
            evidence={
                "insider_transaction_count": analysis["transaction_count"],
                "insider_purchase_count": analysis["purchase_count"],
                "insider_sale_count": analysis["sale_count"],
                "insider_purchase_value": analysis["purchase_value"],
                "insider_sale_value": analysis["sale_value"],
                "insider_net_purchase_value": analysis["net_purchase_value"],
                "transactions": analysis["transactions"],
            },
        )

    def _collect_sec_beneficial_ownership(self, run_id: int, ticker: str, sec_client: SecClient) -> None:
        forms = ("SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A")
        filings = sec_client.latest_filings(ticker, forms=forms, limit=8)
        if not filings:
            return
        filing_texts = []
        for filing in filings:
            try:
                filing_texts.append((filing, sec_client.filing_text(filing)))
            except Exception:
                continue
        analysis = analyze_beneficial_ownership(filing_texts)
        observation_id = self.store.save_observation(
            run_id=run_id,
            ticker=ticker,
            source_key="sec_beneficial_ownership",
            source_type="beneficial_ownership",
            observation_type="schedule_13dg_recent",
            title=f"{ticker.upper()} recent Schedule 13D/G beneficial ownership",
            raw_json=analysis,
            trust_level=88,
        )
        if analysis["filing_count"] <= 0:
            return
        max_percent = analysis.get("max_reported_percent")
        self.store.save_information_item(
            run_id=run_id,
            observation_id=observation_id,
            ticker=ticker,
            dimension="ownership",
            event_date=analysis["filings"][0].get("filing_date"),
            title=f"{ticker.upper()} beneficial ownership filings",
            summary=(
                f"最近检出 {analysis['filing_count']} 份 Schedule 13D/G 披露，"
                f"最高披露持股比例约 {_pct(max_percent)}。"
            ),
            raw_excerpt="\n\n".join(
                snippet
                for filing in analysis["filings"][:3]
                for snippet in filing.get("snippets", [])[:2]
            ),
            source_key="sec_beneficial_ownership",
            source_url=analysis["filings"][0].get("url", ""),
            importance_score=76 if max_percent and max_percent >= 0.05 else 58,
            quality_score=76,
            confidence_score=62,
            evidence={
                "large_holder_max_percent": max_percent,
                "beneficial_ownership_filings": analysis["filings"],
            },
        )

    def _collect_sec_proxy_ownership(self, run_id: int, ticker: str, sec_client: SecClient) -> None:
        filings = sec_client.latest_filings(ticker, forms=("DEF 14A", "10-K"), limit=3)
        if not filings:
            return
        filing_texts = []
        for filing in filings:
            try:
                filing_texts.append((filing, sec_client.filing_text(filing)))
            except Exception:
                continue
        analysis = analyze_proxy_ownership(filing_texts)
        observation_id = self.store.save_observation(
            run_id=run_id,
            ticker=ticker,
            source_key="sec_proxy_ownership",
            source_type="proxy_ownership",
            observation_type="proxy_ownership",
            title=f"{ticker.upper()} DEF 14A / 10-K ownership tables",
            raw_json=analysis,
            trust_level=90,
        )
        if analysis["filing_count"] <= 0:
            return
        management = analysis.get("management_group_percent")
        top_holder = analysis.get("top_holder_percent")
        if management is None and top_holder is None:
            return
        self.store.save_information_item(
            run_id=run_id,
            observation_id=observation_id,
            ticker=ticker,
            dimension="ownership",
            event_date=analysis["filings"][0].get("filing_date"),
            title=f"{ticker.upper()} proxy ownership alignment",
            summary=(
                f"DEF 14A/10-K 持股表显示管理层/董事高管合计持股约 {_pct(management)}，"
                f"最高单一披露持股约 {_pct(top_holder)}。"
            ),
            raw_excerpt="\n\n".join(row.get("name_or_context", "") for row in analysis.get("holder_rows", [])[:6]),
            source_key="sec_proxy_ownership",
            source_url=analysis["filings"][0].get("url", ""),
            importance_score=82 if management and management >= 0.05 else 66,
            quality_score=78,
            confidence_score=64,
            evidence={
                "insider_ownership": management,
                "proxy_management_ownership": management,
                "proxy_top_holder_percent": top_holder,
                "proxy_holder_rows": analysis.get("holder_rows", []),
                "proxy_filings": analysis.get("filings", []),
            },
        )

    def _collect_sec_13f(self, run_id: int, ticker: str, sec_client: SecClient) -> None:
        managers = _read_13f_managers(PROJECT_ROOT / "configs" / "13f_managers.csv")
        if not managers:
            return
        company_name = _company_name_for_ticker(self.store, ticker)
        analysis = analyze_13f_holdings(
            sec_client,
            ticker=ticker,
            company_name=company_name,
            managers=managers,
            limit_managers=len(managers),
        )
        observation_id = self.store.save_observation(
            run_id=run_id,
            ticker=ticker,
            source_key="sec_13f",
            source_type="institutional_holdings",
            observation_type="curated_manager_13f",
            title=f"{ticker.upper()} curated institutional 13F holdings",
            raw_json=analysis,
            trust_level=82,
        )
        if analysis["matched_manager_count"] <= 0:
            return
        self.store.save_information_item(
            run_id=run_id,
            observation_id=observation_id,
            ticker=ticker,
            dimension="institutional_activity",
            event_date=None,
            title=f"{ticker.upper()} 13F institutional holders",
            summary=(
                f"在 {analysis['manager_count_checked']} 个配置机构中，"
                f"13F 匹配到 {analysis['matched_manager_count']} 个持有者，"
                f"报告市值合计约 {_money(analysis['total_reported_value_usd'])}。"
            ),
            raw_excerpt="\n\n".join(
                f"{item.get('manager')}: {item.get('name_of_issuer')} {_money(item.get('value_usd'))}"
                for item in analysis.get("matches", [])[:8]
                if not item.get("error")
            ),
            source_key="sec_13f",
            source_url="",
            importance_score=72,
            quality_score=64,
            confidence_score=52,
            evidence={
                "institutional_13f_manager_count": analysis["matched_manager_count"],
                "institutional_13f_value_usd": analysis["total_reported_value_usd"],
                "institutional_13f_shares": analysis["total_reported_shares"],
                "institutional_13f_matches": analysis.get("matches", []),
            },
        )

    def _collect_usaspending(self, run_id: int, ticker: str, client: USASpendingClient) -> None:
        company = self.store.company(ticker) or {}
        company_name = str(company.get("name") or ticker)
        try:
            signal = client.search_company_contracts(company_name=company_name, ticker=ticker, years=3, limit=12)
            raw_json = signal.to_dict()
            observation_type = "recipient_awards"
            title = f"{ticker.upper()} USAspending federal contract awards"
        except Exception as exc:
            self.store.save_observation(
                run_id=run_id,
                ticker=ticker,
                source_key="usaspending",
                source_type="government_contracts",
                observation_type="recipient_awards_error",
                title=f"{ticker.upper()} USAspending contract search failed",
                raw_json={"company_name": company_name, "error": str(exc)},
                trust_level=35,
            )
            return
        observation_id = self.store.save_observation(
            run_id=run_id,
            ticker=ticker,
            source_key="usaspending",
            source_type="government_contracts",
            observation_type=observation_type,
            title=title,
            source_url="https://www.usaspending.gov/search",
            raw_json=raw_json,
            trust_level=76,
        )
        if signal.award_count <= 0:
            return
        top_agency = signal.top_agencies[0]["agency"] if signal.top_agencies else "federal agencies"
        self.store.save_information_item(
            run_id=run_id,
            observation_id=observation_id,
            ticker=ticker,
            dimension="government_contract",
            title=f"{ticker.upper()} federal contract signal",
            summary=(
                f"USAspending 近 3 年检出 {signal.award_count} 个疑似联邦合同奖项，"
                f"总义务金额约 {_money(signal.total_award_amount)}，"
                f"最大单项约 {_money(signal.largest_award_amount)}，主要来自 {top_agency}。"
            ),
            raw_excerpt="\n\n".join(
                (
                    f"{award.get('award_id')} · {award.get('recipient_name')} · "
                    f"{_money(award.get('award_amount'))} · {award.get('awarding_agency')}"
                )
                for award in signal.awards[:6]
            ),
            source_key="usaspending",
            source_url="https://www.usaspending.gov/search",
            importance_score=84 if signal.total_award_amount >= 50_000_000 else 70,
            quality_score=72,
            confidence_score=58,
            evidence={
                "government_contract_award_count": signal.award_count,
                "government_contract_total_value": signal.total_award_amount,
                "government_contract_largest_award": signal.largest_award_amount,
                "government_contract_dod_value": signal.dod_award_amount,
                "government_contract_top_agencies": signal.top_agencies,
                "government_contract_awards": signal.awards,
                "government_contract_query": signal.query,
                "government_contract_start_date": signal.start_date,
                "government_contract_end_date": signal.end_date,
            },
        )

    def _collect_launch_library(self, run_id: int, ticker: str, client: LaunchLibraryClient) -> None:
        company = self.store.company(ticker) or {}
        try:
            signal = client.search_ticker_launches(ticker, company=company, limit=100)
            raw_json = signal.to_dict()
            observation_type = "upcoming_launches"
            title = f"{ticker.upper()} Launch Library upcoming launch scan"
        except Exception as exc:
            self.store.save_observation(
                run_id=run_id,
                ticker=ticker,
                source_key="launch_library",
                source_type="future_event",
                observation_type="upcoming_launches_error",
                title=f"{ticker.upper()} Launch Library search failed",
                raw_json={"error": str(exc)},
                trust_level=35,
            )
            return

        matches = raw_json.get("matches") or []
        source_url = matches[0].get("url", "") if matches else "https://ll.thespacedevs.com/2.3.0/launches/upcoming/"
        observation_id = self.store.save_observation(
            run_id=run_id,
            ticker=ticker,
            source_key="launch_library",
            source_type="future_event",
            observation_type=observation_type,
            title=title,
            source_url=source_url,
            raw_json=raw_json,
            raw_text="\n\n".join(_launch_excerpt(match) for match in matches[:8]),
            trust_level=80,
        )
        for match in matches[:8]:
            event_date = _launch_event_date(match)
            event_title = _launch_event_title(ticker, match)
            event_summary = _launch_event_summary(match)
            confidence = _launch_confidence(match)
            importance = _launch_importance(ticker, match)
            self.store.save_information_item(
                run_id=run_id,
                observation_id=observation_id,
                ticker=ticker,
                dimension="future_events",
                event_date=match.get("net"),
                title=event_title,
                summary=event_summary,
                raw_excerpt=_launch_excerpt(match),
                source_key="launch_library",
                source_url=match.get("url", ""),
                importance_score=importance,
                quality_score=74,
                confidence_score=confidence,
                extracted_by="launch_library",
                evidence={
                    "launch_library_match": match,
                    "launch_event_count": len(matches),
                    "launch_matched_keywords": match.get("matched_keywords") or [],
                    "launch_provider": match.get("launch_service_provider"),
                    "launch_status": (match.get("status") or {}).get("abbrev"),
                    "launch_net": match.get("net"),
                },
            )
            self.store.save_future_event(
                ticker=ticker,
                title=event_title,
                summary=event_summary,
                event_date=event_date,
                window_label=_launch_window_label(match),
                catalyst_type="space_launch",
                source_key="launch_library",
                source_url=match.get("url", ""),
                importance_score=importance,
                confidence_score=confidence,
                status=(match.get("status") or {}).get("abbrev") or "WATCH",
                evidence={
                    "launch_library_match": match,
                    "launch_matched_keywords": match.get("matched_keywords") or [],
                },
            )

    def _collect_company_official(
        self,
        run_id: int,
        ticker: str,
        client: CompanyOfficialClient,
        llm_client: SummaryClient | None,
    ) -> None:
        signal = client.fetch_ticker(ticker)
        pages = signal.get("pages") or []
        source_url = _first_page_url(pages)
        observation_id = self.store.save_observation(
            run_id=run_id,
            ticker=ticker,
            source_key="company_official",
            source_type="ticker_scoped_official",
            observation_type="official_source_snapshot",
            title=f"{ticker.upper()} official source snapshot",
            source_url=source_url,
            raw_text=_official_raw_text(signal),
            raw_json=signal,
            trust_level=78,
        )
        highlights = [
            {**highlight, "page_label": page.get("label"), "url": page.get("url")}
            for page in pages
            for highlight in page.get("highlights", [])[:4]
        ]
        if not highlights:
            return
        summary = self._summarize_official_source(
            ticker=ticker,
            signal=signal,
            highlights=highlights,
            llm_client=llm_client,
        )
        self.store.save_information_item(
            run_id=run_id,
            observation_id=observation_id,
            ticker=ticker,
            dimension="future_events",
            title=f"{ticker.upper()} official source watch",
            summary=summary.summary,
            raw_excerpt="\n\n".join(item.get("snippet", "") for item in highlights[:6]),
            source_key="company_official",
            source_url=source_url,
            importance_score=summary.importance_score,
            quality_score=70,
            sentiment_score=summary.sentiment_score,
            confidence_score=summary.confidence_score,
            extracted_by=summary.provider,
            evidence={
                "official_source_count": signal.get("source_count"),
                "official_highlight_count": signal.get("highlight_count"),
                "summary_provider": summary.provider,
                "highlights": highlights[:12],
                "pages": [
                    {
                        "label": page.get("label"),
                        "url": page.get("url"),
                        "title": page.get("title"),
                        "description": page.get("description"),
                        "status_code": page.get("status_code"),
                        "fetched_from_cache": page.get("fetched_from_cache"),
                    }
                    for page in pages
                ],
            },
        )
        self.store.save_future_event(
            ticker=ticker,
            title=f"{ticker.upper()} official source watch",
            summary=summary.summary,
            window_label="Official source watch",
            catalyst_type="official_source",
            source_key="company_official",
            source_url=source_url,
            importance_score=max(0, summary.importance_score - 4),
            confidence_score=summary.confidence_score,
            status="WATCH",
            evidence={
                "highlights": highlights[:8],
                "source_count": signal.get("source_count"),
                "summary_provider": summary.provider,
            },
        )

    def _summarize_official_source(
        self,
        *,
        ticker: str,
        signal: dict,
        highlights: list[dict],
        llm_client: SummaryClient | None,
    ):
        if llm_client is not None:
            try:
                return llm_client.summarize_crawled_source(
                    ticker=ticker,
                    source_name=_official_source_name(signal),
                    source_url=_first_page_url(signal.get("pages") or []),
                    snippets=highlights,
                )
            except Exception:
                pass
        return _official_signal_summary(signal, highlights)

    def _collect_openinsider(self, run_id: int, ticker: str, client: OpenInsiderClient) -> None:
        try:
            signal = client.fetch_ticker(ticker, limit=100)
            raw_json = signal.to_dict()
        except Exception as exc:
            self.store.save_observation(
                run_id=run_id,
                ticker=ticker,
                source_key="openinsider",
                source_type="insider_transactions",
                observation_type="ticker_screener_error",
                title=f"{ticker.upper()} OpenInsider ticker screener failed",
                raw_json={"error": str(exc)},
                trust_level=32,
            )
            return
        transactions = raw_json.get("transactions") or []
        observation_id = self.store.save_observation(
            run_id=run_id,
            ticker=ticker,
            source_key="openinsider",
            source_type="insider_transactions",
            observation_type="ticker_screener",
            title=f"{ticker.upper()} OpenInsider ticker screener",
            source_url=raw_json.get("source_url", ""),
            raw_text="\n\n".join(_openinsider_excerpt(item) for item in transactions[:12]),
            raw_json=raw_json,
            trust_level=64,
        )
        if not transactions:
            return
        net_purchase_value = float(raw_json.get("net_purchase_value") or 0)
        sale_value = float(raw_json.get("sale_value") or 0)
        sentiment = 18 if net_purchase_value > 0 else -16 if sale_value else 0
        importance = 78 if net_purchase_value > 0 else 60 if sale_value else 52
        self.store.save_information_item(
            run_id=run_id,
            observation_id=observation_id,
            ticker=ticker,
            dimension="insider_activity",
            event_date=transactions[0].get("trade_date") or transactions[0].get("filing_datetime"),
            title=f"{ticker.upper()} OpenInsider transaction classification",
            summary=(
                f"OpenInsider 最新返回 {raw_json['transaction_count']} 笔 Form 4 表格交易，"
                f"其中公开市场买入 {raw_json['purchase_count']} 笔、卖出 {raw_json['sale_count']} 笔，"
                f"估算公开市场净买入 {_money(net_purchase_value)}。"
            ),
            raw_excerpt="\n\n".join(_openinsider_excerpt(item) for item in transactions[:8]),
            source_key="openinsider",
            source_url=raw_json.get("source_url", ""),
            importance_score=importance,
            quality_score=58,
            sentiment_score=sentiment,
            confidence_score=58,
            extracted_by="openinsider_parser",
            evidence={
                "openinsider_transaction_count": raw_json["transaction_count"],
                "openinsider_open_market_count": raw_json["open_market_count"],
                "openinsider_purchase_count": raw_json["purchase_count"],
                "openinsider_sale_count": raw_json["sale_count"],
                "openinsider_purchase_value": raw_json["purchase_value"],
                "openinsider_sale_value": raw_json["sale_value"],
                "openinsider_net_purchase_value": raw_json["net_purchase_value"],
                "openinsider_fetched_from_cache": raw_json.get("fetched_from_cache"),
                "openinsider_warning": raw_json.get("warning"),
                "transactions": transactions[:24],
            },
        )

    def _collect_yfinance(self, run_id: int, ticker: str) -> None:
        metrics = fetch_candidate_metrics(
            ticker,
            cache_dir=PROJECT_ROOT / ".cache" / "yfinance",
            cache_ttl_hours=24,
            retries=1,
            retry_wait_seconds=30,
        )
        self.store.upsert_company(
            ticker,
            name=metrics.name,
            sector=metrics.sector,
            industry=metrics.industry,
            metadata={"yfinance_source": metrics.source, "warnings": metrics.warnings},
        )
        observation_id = self.store.save_observation(
            run_id=run_id,
            ticker=ticker,
            source_key="yfinance",
            source_type="fallback_fundamental",
            observation_type="ticker_metrics",
            title=f"{ticker.upper()} yFinance fallback metrics",
            raw_json=metrics.to_dict(),
            trust_level=58,
        )
        if metrics.institutional_ownership is not None or metrics.insider_ownership is not None:
            self.store.save_information_item(
                run_id=run_id,
                observation_id=observation_id,
                ticker=ticker,
                dimension="ownership",
                title=f"{ticker.upper()} ownership structure",
                summary=(
                    f"yFinance 显示机构持股约 {_pct(metrics.institutional_ownership)}，"
                    f"内部人持股约 {_pct(metrics.insider_ownership)}。"
                ),
                source_key="yfinance",
                importance_score=65,
                quality_score=55,
                confidence_score=55,
                evidence={
                    "institutional_ownership": metrics.institutional_ownership,
                    "insider_ownership": metrics.insider_ownership,
                },
            )

    def _score_ticker(self, run_id: int, ticker: str) -> None:
        items = self.store.latest_information_items(ticker, limit=200)
        score = score_hidden_champion(ticker, items)
        self.store.save_score(
            run_id=run_id,
            ticker=ticker,
            total_score=score.total_score,
            grade=score.grade,
            component_scores=score.component_scores,
            explanation=score.explanation,
            missing_dimensions=score.missing_dimensions,
            model_version=MODEL_VERSION,
        )

    def _llm_client(self) -> SummaryClient | None:
        return build_llm_client(self.settings)

    def _summarize_filing(
        self,
        *,
        ticker: str,
        title: str,
        snippets: list[str],
        backlog_mentions: int,
        rpo_mentions: int,
        llm_client: SummaryClient | None,
    ):
        if llm_client and snippets:
            try:
                return llm_client.summarize_filing_signal(
                    ticker=ticker,
                    title=title,
                    text="\n\n".join(snippets),
                )
            except Exception:
                pass
        return heuristic_summary(
            ticker=ticker,
            snippets=snippets,
            backlog_mentions=backlog_mentions,
            rpo_mentions=rpo_mentions,
        )


def _clean_tickers(tickers: Iterable[str]) -> list[str]:
    result = []
    seen = set()
    for ticker in tickers:
        clean = ticker.strip().upper()
        if not clean:
            continue
        if "." in clean:
            clean = clean.split(".", 1)[1]
        if clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


def _unique_filings(filings):
    result = []
    seen = set()
    for filing in filings:
        key = (filing.cik, filing.accession, filing.primary_document)
        if key in seen:
            continue
        seen.add(key)
        result.append(filing)
    return result


def _notify(callback: Callable[[dict], None] | None, payload: dict) -> None:
    if callback is not None:
        callback(payload)


def _pct(value) -> str:
    if value is None:
        return "missing"
    return f"{value * 100:.1f}%"


def _money(value) -> str:
    if value is None:
        return "missing"
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    return f"${value:,.0f}"


def _openinsider_excerpt(transaction: dict) -> str:
    return (
        f"{transaction.get('trade_date') or transaction.get('filing_datetime') or ''} · "
        f"{transaction.get('insider_name') or 'Unknown insider'} · "
        f"{transaction.get('title') or 'n/a'} · "
        f"{transaction.get('trade_type') or 'transaction'} · "
        f"{_money(transaction.get('value') or 0)}"
    )


def _launch_event_title(ticker: str, match: dict) -> str:
    name = str(match.get("name") or "upcoming launch")
    return f"{ticker.upper()} launch catalyst: {name}"


def _launch_event_summary(match: dict) -> str:
    provider = str(match.get("launch_service_provider") or "unknown provider")
    rocket = str(match.get("rocket") or "unknown rocket")
    mission = match.get("mission") or {}
    status = match.get("status") or {}
    status_label = status.get("abbrev") or status.get("name") or "WATCH"
    net = match.get("net") or "TBD"
    keywords = ", ".join(match.get("matched_keywords") or [])
    mission_name = mission.get("name") or match.get("name") or "mission"
    return (
        f"Launch Library 匹配到 {mission_name}，窗口 {net}，"
        f"发射商 {provider}，火箭 {rocket}，状态 {status_label}。"
        f"匹配关键词：{keywords or 'n/a'}。"
    )


def _launch_excerpt(match: dict) -> str:
    mission = match.get("mission") or {}
    pad = match.get("pad") or {}
    return " ".join(
        str(value or "")
        for value in (
            match.get("name"),
            match.get("net"),
            match.get("launch_service_provider"),
            match.get("rocket"),
            mission.get("name"),
            mission.get("type"),
            mission.get("orbit"),
            mission.get("description"),
            pad.get("name"),
            pad.get("location"),
        )
    ).strip()


def _launch_event_date(match: dict):
    value = match.get("net")
    if not value:
        return None
    return str(value)[:10]


def _launch_window_label(match: dict) -> str:
    start = match.get("window_start")
    end = match.get("window_end")
    if start and end:
        return f"{start} - {end}"
    return str(match.get("net") or "Launch window TBD")


def _launch_confidence(match: dict) -> int:
    status = match.get("status") or {}
    status_abbrev = str(status.get("abbrev") or "").lower()
    probability = match.get("probability")
    score = 66
    if probability is not None:
        try:
            score = max(score, min(90, int(float(probability))))
        except (TypeError, ValueError):
            pass
    if status_abbrev in {"go", "success"}:
        score += 4
    elif status_abbrev in {"tbc", "tbd"}:
        score -= 6
    return max(35, min(92, score))


def _launch_importance(ticker: str, match: dict) -> int:
    keywords = " ".join(match.get("matched_keywords") or []).lower()
    provider = str(match.get("launch_service_provider") or "").lower()
    if ticker.upper() == "RKLB" and "rocket lab" in provider:
        return 86
    if any(term in keywords for term in ("bluebird", "spacemobile", "redwire", "payload")):
        return 82
    return 76


def _quality_summary(quality: dict) -> str:
    parts = []
    if quality.get("gross_margin") is not None:
        parts.append(f"毛利率约 {_pct(quality['gross_margin'])}")
    if quality.get("operating_margin") is not None:
        parts.append(f"经营利润率约 {_pct(quality['operating_margin'])}")
    if quality.get("net_margin") is not None:
        parts.append(f"净利率约 {_pct(quality['net_margin'])}")
    if quality.get("liabilities_to_assets") is not None:
        parts.append(f"负债/资产约 {_pct(quality['liabilities_to_assets'])}")
    if quality.get("debt_to_assets") is not None:
        parts.append(f"债务/资产约 {_pct(quality['debt_to_assets'])}")
    if quality.get("free_cash_flow_margin") is not None:
        parts.append(f"自由现金流率约 {_pct(quality['free_cash_flow_margin'])}")
    if quality.get("receivables_yoy") is not None:
        parts.append(f"应收同比约 {_pct(quality['receivables_yoy'])}")
    if quality.get("inventory_yoy") is not None:
        parts.append(f"库存同比约 {_pct(quality['inventory_yoy'])}")
    return "，".join(parts) if parts else "SEC companyfacts 返回财务质量数据，但关键比率不足。"


def _read_13f_managers(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [row for row in csv.DictReader(handle) if row.get("cik")]


def _company_name_for_ticker(store: PostgresStore, ticker: str) -> str:
    rows = store.ranked_scores(min_score=0, limit=500)
    for row in rows:
        if row.get("ticker") == ticker.upper():
            return row.get("name") or ticker
    return ticker


def _first_page_url(pages: list[dict]) -> str:
    for page in pages:
        if page.get("url"):
            return str(page["url"])
    return ""


def _official_raw_text(signal: dict) -> str:
    chunks = []
    for page in signal.get("pages") or []:
        header = " · ".join(
            item
            for item in (str(page.get("label") or ""), str(page.get("title") or ""), str(page.get("url") or ""))
            if item
        )
        snippets = "\n".join(item.get("snippet", "") for item in page.get("highlights", [])[:5])
        if header or snippets:
            chunks.append("\n".join(item for item in (header, snippets) if item))
    return "\n\n".join(chunks)


def _official_signal_summary(signal: dict, highlights: list[dict] | None = None) -> LlmSummary:
    source_text = _official_source_name(signal)
    snippets = [
        " ".join(str(item.get("snippet") or "").split())[:360]
        for item in (highlights or [])
        if item.get("snippet")
    ]
    if snippets:
        summary = f"LLM 未生成译写，保留 {source_text} 的官网原文片段待人工翻译：" + "；".join(snippets[:2]) + "。"
    else:
        summary = f"官网/IR 来源 {source_text or 'official pages'} 未提取到足够原文片段，需要人工复核。"
    return LlmSummary(
        summary=summary,
        importance_score=58,
        sentiment_score=0,
        confidence_score=45,
        raw_response="",
        provider="heuristic",
    )


def _official_source_name(signal: dict) -> str:
    pages = signal.get("pages") or []
    return "、".join(
        str(page.get("label") or page.get("url") or "official page")
        for page in pages[:3]
    )
