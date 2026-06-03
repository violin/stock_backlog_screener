from __future__ import annotations

import csv
import time
from pathlib import Path
from typing import Callable, Iterable

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
from .llm import MiniMaxClient, heuristic_summary
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
            "summarize": summarize,
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
            llm_client = self._llm_client() if should_collect_source("minimax", config) else None
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
                if should_collect_source("yfinance", config, company):
                    _notify(progress_callback, {"event": "stage", "stage": f"{ticker} yFinance fallback"})
                    self._collect_yfinance(run_id, ticker)
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
        llm_client: MiniMaxClient | None,
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

    def _llm_client(self) -> MiniMaxClient | None:
        if not self.settings.minimax_api_key:
            return None
        return MiniMaxClient(
            api_key=self.settings.minimax_api_key,
            base_url=self.settings.minimax_base_url,
            model=self.settings.minimax_model,
            api=self.settings.minimax_api,
            retries=self.settings.minimax_retries,
            retry_wait_seconds=self.settings.minimax_retry_wait_seconds,
        )

    def _summarize_filing(
        self,
        *,
        ticker: str,
        title: str,
        snippets: list[str],
        backlog_mentions: int,
        rpo_mentions: int,
        llm_client: MiniMaxClient | None,
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
