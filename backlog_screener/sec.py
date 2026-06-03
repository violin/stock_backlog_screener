from __future__ import annotations

import html
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple
from xml.etree import ElementTree

import requests

from .config import BacklogScanConfig
from .models import FilingScan


COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession}/{document}"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

SEC_PERIODIC_FORMS = ("10-Q", "10-Q/A", "10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A", "6-K", "6-K/A")
SEC_ANNUAL_FORMS = ("10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A")
COMPANYFACT_FORMS = {form.upper() for form in SEC_PERIODIC_FORMS}


@dataclass
class FilingRef:
    cik: str
    accession: str
    form: str
    filing_date: str
    primary_document: str

    @property
    def url(self) -> str:
        accession_path = self.accession.replace("-", "")
        return ARCHIVES_URL.format(
            cik_int=int(self.cik),
            accession=accession_path,
            document=self.primary_document,
        )


class SecClient:
    def __init__(
        self,
        cache_dir: Path,
        user_agent: Optional[str] = None,
        timeout: int = 20,
        retries: int = 2,
        retry_wait_seconds: float = 2.0,
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.retries = max(0, int(retries))
        self.retry_wait_seconds = max(0.0, float(retry_wait_seconds))
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent
                or os.environ.get("SEC_USER_AGENT")
                or "stock_backlog_screener/0.1 research@example.com",
                "Accept-Encoding": "gzip, deflate",
            }
        )

    def cik_for_ticker(self, ticker: str) -> Optional[str]:
        mapping = self._company_tickers()
        record = mapping.get(ticker.upper())
        if not record:
            return None
        return str(record["cik_str"]).zfill(10)

    def latest_filing(self, ticker: str, forms: Tuple[str, ...] = ("10-Q", "10-K")) -> Optional[FilingRef]:
        filings = self.latest_filings(ticker, forms=forms, limit=1)
        return filings[0] if filings else None

    def latest_filings(
        self,
        ticker: str,
        forms: Tuple[str, ...] = ("10-Q", "10-K"),
        limit: int = 5,
    ) -> list[FilingRef]:
        cik = self.cik_for_ticker(ticker)
        if not cik:
            return []
        url = SUBMISSIONS_URL.format(cik=cik)
        data = self._get_json(url, self.cache_dir / f"submissions_{cik}.json", max_age_seconds=12 * 60 * 60)
        recent = data.get("filings", {}).get("recent", {})
        forms_list = recent.get("form", [])
        accession_numbers = recent.get("accessionNumber", [])
        filing_dates = recent.get("filingDate", [])
        primary_docs = recent.get("primaryDocument", [])
        wanted = {_normalize_sec_form(form) for form in forms}
        results = []
        for index, form in enumerate(forms_list):
            if _normalize_sec_form(str(form)) not in wanted:
                continue
            results.append(
                FilingRef(
                    cik=cik,
                    accession=accession_numbers[index],
                    form=forms_list[index],
                    filing_date=filing_dates[index],
                    primary_document=primary_docs[index],
                )
            )
            if len(results) >= limit:
                break
        return results

    def latest_filings_by_cik(
        self,
        cik: str,
        forms: Tuple[str, ...] = ("13F-HR",),
        limit: int = 3,
    ) -> list[FilingRef]:
        clean_cik = str(cik).strip().lstrip("0").zfill(10)
        url = SUBMISSIONS_URL.format(cik=clean_cik)
        data = self._get_json(url, self.cache_dir / f"submissions_{clean_cik}.json", max_age_seconds=24 * 60 * 60)
        recent = data.get("filings", {}).get("recent", {})
        forms_list = recent.get("form", [])
        accession_numbers = recent.get("accessionNumber", [])
        filing_dates = recent.get("filingDate", [])
        primary_docs = recent.get("primaryDocument", [])
        wanted = {_normalize_sec_form(form) for form in forms}
        results = []
        for index, form in enumerate(forms_list):
            if _normalize_sec_form(str(form)) not in wanted:
                continue
            results.append(
                FilingRef(
                    cik=clean_cik,
                    accession=accession_numbers[index],
                    form=forms_list[index],
                    filing_date=filing_dates[index],
                    primary_document=primary_docs[index],
                )
            )
            if len(results) >= limit:
                break
        return results

    def companyfacts(self, ticker: str) -> Dict:
        cik = self.cik_for_ticker(ticker)
        if not cik:
            return {}
        return self._get_json(
            COMPANYFACTS_URL.format(cik=cik),
            self.cache_dir / f"companyfacts_{cik}.json",
            max_age_seconds=12 * 60 * 60,
        )

    def filing_text(self, filing: FilingRef) -> str:
        return self.document_text(filing, filing.primary_document)

    def document_text(self, filing: FilingRef, document: str) -> str:
        document = document.strip()
        safe_document = filing.primary_document.replace("/", "_")
        if document != filing.primary_document:
            safe_document = document.replace("/", "_")
        cache_name = f"{filing.cik}_{filing.accession.replace('-', '')}_{safe_document}.txt"
        cache_path = self.cache_dir / cache_name
        if cache_path.exists():
            cached_text = cache_path.read_text(encoding="utf-8", errors="ignore")
            if not _looks_like_transformed_form4_html(cached_text):
                return cached_text
        url = filing.url if document == filing.primary_document else ARCHIVES_URL.format(
            cik_int=int(filing.cik),
            accession=filing.accession.replace("-", ""),
            document=document,
        )
        response = self._get(url)
        response.raise_for_status()
        text = response.text
        if document == filing.primary_document and _looks_like_transformed_form4_html(text) and "/" in filing.primary_document:
            raw_document = document.rsplit("/", 1)[-1]
            raw_url = ARCHIVES_URL.format(
                cik_int=int(filing.cik),
                accession=filing.accession.replace("-", ""),
                document=raw_document,
            )
            raw_response = self._get(raw_url)
            raw_response.raise_for_status()
            if not _looks_like_transformed_form4_html(raw_response.text):
                text = raw_response.text
        cache_path.write_text(text, encoding="utf-8")
        time.sleep(0.15)
        return text

    def filing_documents(self, filing: FilingRef) -> list[dict]:
        index_url = ARCHIVES_URL.format(
            cik_int=int(filing.cik),
            accession=filing.accession.replace("-", ""),
            document="index.json",
        )
        cache_path = self.cache_dir / f"{filing.cik}_{filing.accession.replace('-', '')}_index.json"
        data = self._get_json(index_url, cache_path, max_age_seconds=24 * 60 * 60)
        return data.get("directory", {}).get("item", [])

    def _company_tickers(self) -> Dict[str, Dict]:
        path = self.cache_dir / "company_tickers.json"
        raw = self._get_json(COMPANY_TICKERS_URL, path, max_age_seconds=7 * 24 * 60 * 60)
        mapping: Dict[str, Dict] = {}
        for record in raw.values():
            ticker = str(record.get("ticker", "")).upper()
            if ticker:
                mapping[ticker] = record
        return mapping

    def _get_json(self, url: str, cache_path: Path, max_age_seconds: int) -> Dict:
        if cache_path.exists() and time.time() - cache_path.stat().st_mtime < max_age_seconds:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        response = self._get(url)
        response.raise_for_status()
        data = response.json()
        cache_path.write_text(json.dumps(data), encoding="utf-8")
        time.sleep(0.15)
        return data

    def _get(self, url: str) -> requests.Response:
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                return self.session.get(url, timeout=self.timeout)
            except requests.RequestException as exc:
                last_error = exc
                if attempt >= self.retries:
                    break
                time.sleep(self.retry_wait_seconds * (attempt + 1))
        assert last_error is not None
        raise last_error


class BacklogScanner:
    def __init__(self, sec_client: SecClient, config: BacklogScanConfig = BacklogScanConfig()):
        self.sec_client = sec_client
        self.config = config

    def scan_ticker(self, ticker: str) -> FilingScan:
        filing = self.sec_client.latest_filing(ticker, forms=self.config.forms)
        if not filing:
            return FilingScan(warning=f"No SEC filing found for {ticker}.")
        try:
            raw_text = self.sec_client.filing_text(filing)
        except Exception as exc:
            return FilingScan(
                form=filing.form,
                filing_date=filing.filing_date,
                url=filing.url,
                warning=f"SEC filing fetch failed for {ticker}: {exc}",
            )

        cleaned = clean_filing_text(raw_text)
        backlog_count, rpo_count, snippets = scan_text_for_backlog(
            cleaned,
            terms=self.config.terms,
            radius=self.config.snippet_radius,
            max_snippets=self.config.max_snippets,
        )
        return FilingScan(
            form=filing.form,
            filing_date=filing.filing_date,
            url=filing.url,
            backlog_mentions=backlog_count,
            rpo_mentions=rpo_count,
            snippets=snippets,
        )


def scan_text_for_backlog(
    text: str,
    terms: Iterable[str],
    radius: int = 220,
    max_snippets: int = 4,
) -> Tuple[int, int, list]:
    backlog_count = 0
    rpo_count = 0
    snippets = []
    seen_spans = []
    for term in terms:
        pattern = _term_pattern(term)
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            if "backlog" in term.lower():
                backlog_count += 1
            else:
                rpo_count += 1
            if len(snippets) >= max_snippets:
                continue
            span = (max(0, match.start() - radius), min(len(text), match.end() + radius))
            if any(abs(span[0] - existing[0]) < 80 for existing in seen_spans):
                continue
            seen_spans.append(span)
            snippets.append(text[span[0] : span[1]].strip())
    return backlog_count, rpo_count, snippets


def extract_backlog_amounts(text: str, snippets: list[str] | None = None, max_items: int = 8) -> list[dict]:
    search_text = " ".join(snippets or []) if snippets else text
    candidates = []
    patterns = [
        r"(?:backlog|remaining performance obligations?|RPOs?).{0,220}?\$?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(billion|million|thousand|bn|mm|m)?",
        r"\$?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(billion|million|thousand|bn|mm|m).{0,220}?(?:backlog|remaining performance obligations?|RPOs?)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, search_text, flags=re.IGNORECASE):
            raw_number = match.group(1)
            unit = (match.group(2) or "").lower()
            value = _money_to_number(raw_number, unit)
            if value is None or value < 100_000:
                continue
            start = max(0, match.start() - 160)
            end = min(len(search_text), match.end() + 160)
            candidates.append(
                {
                    "value": value,
                    "raw_number": raw_number,
                    "unit": unit,
                    "context": search_text[start:end].strip(),
                }
            )
            if len(candidates) >= max_items:
                return candidates
    return candidates


def summarize_backlog_quality(backlog_mentions: int, rpo_mentions: int, amounts: list[dict]) -> dict:
    largest = max((item["value"] for item in amounts), default=None)
    return {
        "backlog_mentions": backlog_mentions,
        "rpo_mentions": rpo_mentions,
        "amount_mentions": len(amounts),
        "largest_amount": largest,
        "amounts": amounts,
    }


def _term_pattern(term: str) -> str:
    if term.upper() == "RPO":
        return r"\bRPOs?\b"
    escaped = re.escape(term)
    return escaped.replace(r"\ ", r"\s+")


def clean_filing_text(raw_text: str) -> str:
    text = html.unescape(raw_text)
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _looks_like_transformed_form4_html(text: str) -> bool:
    prefix = text.lstrip()[:200].lower()
    return prefix.startswith("<!doctype") or prefix.startswith("<html")


def latest_quarterly_revenue_yoy(companyfacts: Dict) -> Optional[dict]:
    candidate_tags = (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
        "Revenue",
        "RevenueFromContractsWithCustomers",
    )
    for tag in candidate_tags:
        revenues = _fact_units(companyfacts, tag)
        result = _quarterly_revenue_yoy_from_units(revenues, tag) if revenues else None
        if result:
            return result
    return None


def latest_financial_quality(companyfacts: Dict) -> Optional[dict]:
    revenue = latest_quarterly_revenue_yoy(companyfacts)
    if not revenue:
        return None
    latest = revenue["latest"]
    end = latest.get("end")
    revenue_value = latest.get("value")
    revenue_prior = revenue.get("prior_year_quarter", {}).get("value")
    period_type = revenue.get("period_type", "quarterly")
    income_statement_quarterly_only = period_type == "quarterly"
    gross_profit = _latest_fact_value(companyfacts, ("GrossProfit",), end=end, quarterly_only=income_statement_quarterly_only)
    operating_income = _latest_fact_value(
        companyfacts,
        ("OperatingIncomeLoss", "ProfitLossFromOperatingActivities", "OperatingProfitLoss"),
        end=end,
        quarterly_only=income_statement_quarterly_only,
    )
    net_income = _latest_fact_value(companyfacts, ("NetIncomeLoss", "ProfitLoss"), end=end, quarterly_only=income_statement_quarterly_only)
    operating_cash_flow = _latest_fact_value(
        companyfacts,
        ("NetCashProvidedByUsedInOperatingActivities", "CashFlowsFromUsedInOperatingActivities", "CashFlowsFromUsedInOperations"),
        end=end,
        quarterly_only=income_statement_quarterly_only,
    )
    capex = _latest_fact_value(
        companyfacts,
        (
            "PaymentsToAcquirePropertyPlantAndEquipment",
            "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
            "PurchaseOfOtherLongtermAssetsClassifiedAsInvestingActivities",
        ),
        end=end,
        quarterly_only=income_statement_quarterly_only,
    )
    assets = _latest_fact_value(companyfacts, ("Assets",), quarterly_only=False)
    liabilities = _latest_fact_value(companyfacts, ("Liabilities",), quarterly_only=False)
    equity = _latest_fact_value(
        companyfacts,
        ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "Equity"),
        quarterly_only=False,
    )
    receivables = _latest_fact_value(
        companyfacts,
        ("AccountsReceivableNetCurrent", "ReceivablesNetCurrent", "CurrentTradeReceivables", "TradeAndOtherCurrentReceivables"),
        quarterly_only=False,
    )
    receivables_prior = _prior_year_fact_value(
        companyfacts,
        ("AccountsReceivableNetCurrent", "ReceivablesNetCurrent", "CurrentTradeReceivables", "TradeAndOtherCurrentReceivables"),
        latest_end=end,
        quarterly_only=False,
    )
    inventory = _latest_fact_value(companyfacts, ("InventoryNet", "InventoryFinishedGoodsNetOfReserves", "Inventories"), quarterly_only=False)
    inventory_prior = _prior_year_fact_value(
        companyfacts,
        ("InventoryNet", "InventoryFinishedGoodsNetOfReserves", "Inventories"),
        latest_end=end,
        quarterly_only=False,
    )
    cash = _latest_fact_value(
        companyfacts,
        ("CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "CashAndCashEquivalents", "Cash"),
        quarterly_only=False,
    )
    debt_current = _latest_fact_value(
        companyfacts,
        ("ShortTermBorrowings", "LongTermDebtCurrent", "CurrentDebtInstrumentsIssued", "CurrentLeaseLiabilities", "BorrowingsCurrent"),
        quarterly_only=False,
    )
    debt_noncurrent = _latest_fact_value(
        companyfacts,
        ("LongTermDebtNoncurrent", "LongTermDebtAndFinanceLeaseObligationsNoncurrent", "LongtermBorrowings", "NoncurrentLeaseLiabilities", "BorrowingsNoncurrent"),
        quarterly_only=False,
    )
    debt_current = _nonnegative_metric(debt_current)
    debt_noncurrent = _nonnegative_metric(debt_noncurrent)
    total_debt = None
    if debt_current is not None or debt_noncurrent is not None:
        total_debt = (debt_current or 0) + (debt_noncurrent or 0)
    free_cash_flow = None
    if operating_cash_flow is not None or capex is not None:
        free_cash_flow = (operating_cash_flow or 0) - abs(capex or 0)

    return {
        "period_end": end,
        "period_type": period_type,
        "revenue": revenue_value,
        "revenue_yoy": revenue["value"],
        "gross_profit": gross_profit,
        "operating_income": operating_income,
        "net_income": net_income,
        "operating_cash_flow": operating_cash_flow,
        "capital_expenditures": capex,
        "free_cash_flow": free_cash_flow,
        "gross_margin": _safe_ratio(gross_profit, revenue_value),
        "operating_margin": _safe_ratio(operating_income, revenue_value),
        "net_margin": _safe_ratio(net_income, revenue_value),
        "free_cash_flow_margin": _safe_ratio(free_cash_flow, revenue_value),
        "assets": assets,
        "liabilities": liabilities,
        "equity": equity,
        "receivables": receivables,
        "inventory": inventory,
        "liabilities_to_assets": _safe_ratio(liabilities, assets),
        "cash": cash,
        "total_debt": total_debt,
        "debt_to_assets": _safe_ratio(total_debt, assets),
        "receivables_yoy": _safe_growth(receivables, receivables_prior),
        "inventory_yoy": _safe_growth(inventory, inventory_prior),
        "revenue_prior_year_quarter": revenue_prior,
    }


def analyze_form4_transactions(filing_texts: list[tuple[FilingRef, str]]) -> dict:
    transactions = []
    for filing, raw_text in filing_texts:
        transactions.extend(_parse_form4_xml(filing, raw_text))
    purchase_value = sum(txn["value"] for txn in transactions if txn["acquired_disposed"] == "A" and txn["value"] is not None)
    sale_value = sum(txn["value"] for txn in transactions if txn["acquired_disposed"] == "D" and txn["value"] is not None)
    net_value = purchase_value - sale_value
    purchase_count = sum(1 for txn in transactions if txn["acquired_disposed"] == "A")
    sale_count = sum(1 for txn in transactions if txn["acquired_disposed"] == "D")
    return {
        "transaction_count": len(transactions),
        "purchase_count": purchase_count,
        "sale_count": sale_count,
        "purchase_value": purchase_value,
        "sale_value": sale_value,
        "net_purchase_value": net_value,
        "transactions": transactions[:25],
    }


def analyze_beneficial_ownership(filing_texts: list[tuple[FilingRef, str]]) -> dict:
    filings = []
    for filing, raw_text in filing_texts:
        text = clean_filing_text(raw_text)
        percents = sorted(set([*_ownership_percents(text), *_schedule_13_xml_percents(raw_text)]), reverse=True)
        snippets = []
        if percents:
            snippets.append(f"classPercent {percents[0] * 100:.1f}%")
        for pattern in (r"percent of class.{0,220}", r"beneficially owned.{0,220}", r"sole voting power.{0,220}"):
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                snippets.append(match.group(0).strip())
                if len(snippets) >= 3:
                    break
            if len(snippets) >= 3:
                break
        filings.append(
            {
                "form": filing.form,
                "filing_date": filing.filing_date,
                "url": filing.url,
                "max_percent": max(percents) if percents else None,
                "percents": percents[:10],
                "snippets": snippets,
            }
        )
    max_percent = max((item["max_percent"] for item in filings if item["max_percent"] is not None), default=None)
    return {
        "filing_count": len(filings),
        "max_reported_percent": max_percent,
        "filings": filings,
    }


def analyze_proxy_ownership(filing_texts: list[tuple[FilingRef, str]]) -> dict:
    filings = []
    management_percent = None
    top_holder_percent = None
    holder_rows = []
    for filing, raw_text in filing_texts:
        text = clean_filing_text(raw_text)
        ownership_section = _ownership_section(text)
        if not ownership_section:
            continue
        rows = _ownership_rows(ownership_section)
        group_percent = _management_group_percent(ownership_section)
        row_max = max((row["percent"] for row in rows if row["percent"] is not None), default=None)
        if group_percent is not None:
            management_percent = max(management_percent or 0, group_percent)
        if row_max is not None:
            top_holder_percent = max(top_holder_percent or 0, row_max)
        holder_rows.extend(rows[:12])
        filings.append(
            {
                "form": filing.form,
                "filing_date": filing.filing_date,
                "url": filing.url,
                "management_group_percent": group_percent,
                "top_holder_percent": row_max,
                "rows": rows[:12],
            }
        )
    return {
        "filing_count": len(filings),
        "management_group_percent": management_percent,
        "top_holder_percent": top_holder_percent,
        "holder_rows": holder_rows[:25],
        "filings": filings,
    }


def analyze_13f_holdings(
    sec_client: SecClient,
    *,
    ticker: str,
    company_name: str,
    managers: list[dict],
    limit_managers: int = 8,
) -> dict:
    matches = []
    clean_name = _normalize_name(company_name or ticker)
    ticker_upper = ticker.upper()
    for manager in managers[:limit_managers]:
        cik = str(manager.get("cik", "")).strip()
        if not cik:
            continue
        try:
            filings = sec_client.latest_filings_by_cik(cik, forms=("13F-HR", "13F-HR/A"), limit=1)
        except Exception as exc:
            matches.append({"manager": manager.get("name", cik), "error": str(exc)})
            continue
        if not filings:
            continue
        filing = filings[0]
        try:
            documents = sec_client.filing_documents(filing)
            info_doc = _find_13f_info_table_document(documents)
            if not info_doc:
                continue
            text = sec_client.document_text(filing, info_doc)
            holdings = parse_13f_information_table(text)
        except Exception as exc:
            matches.append({"manager": manager.get("name", cik), "filing_date": filing.filing_date, "error": str(exc)})
            continue
        for holding in holdings:
            issuer = _normalize_name(holding.get("name_of_issuer", ""))
            if not _matches_issuer(issuer, clean_name, ticker_upper):
                continue
            matches.append(
                {
                    "manager": manager.get("name", cik),
                    "manager_cik": cik,
                    "filing_date": filing.filing_date,
                    "filing_url": filing.url,
                    **holding,
                }
            )
    total_value = sum(item.get("value_usd") or 0 for item in matches if not item.get("error"))
    total_shares = sum(item.get("shares") or 0 for item in matches if not item.get("error"))
    matched_managers = len({item.get("manager") for item in matches if not item.get("error")})
    return {
        "manager_count_checked": min(len(managers), limit_managers),
        "matched_manager_count": matched_managers,
        "total_reported_value_usd": total_value,
        "total_reported_shares": total_shares,
        "matches": matches[:50],
    }


def parse_13f_information_table(raw_text: str) -> list[dict]:
    try:
        root = ElementTree.fromstring(raw_text.encode("utf-8"))
    except ElementTree.ParseError:
        return []
    holdings = []
    for node in root.iter():
        if _local_name(node.tag).lower() != "infotable":
            continue
        name = _child_text_by_local_name(node, "nameOfIssuer")
        cusip = _child_text_by_local_name(node, "cusip")
        value_thousands = _to_float(_child_text_by_local_name(node, "value"))
        shares = _to_float(_child_text_by_local_name(node, "sshPrnamt"))
        holdings.append(
            {
                "name_of_issuer": name or "",
                "cusip": cusip or "",
                "value_usd": value_thousands * 1000 if value_thousands is not None else None,
                "shares": shares,
                "share_type": _child_text_by_local_name(node, "sshPrnamtType") or "",
            }
        )
    return holdings


def _quarterly_revenue_yoy_from_units(revenues: Dict, tag: str) -> Optional[dict]:
    quarterly = _period_facts_from_units(revenues, period_type="quarterly")
    result = _revenue_growth_from_period_facts(quarterly, tag, period_type="quarterly")
    if result:
        return result
    annual = _period_facts_from_units(revenues, period_type="annual")
    return _revenue_growth_from_period_facts(annual, tag, period_type="annual")


def _period_facts_from_units(revenues: Dict, *, period_type: str) -> list[dict]:
    facts_out = []
    for unit, facts in revenues.items():
        for fact in facts:
            form = _normalize_sec_form(str(fact.get("form", "")))
            fp = str(fact.get("fp", ""))
            frame = str(fact.get("frame", ""))
            value = fact.get("val")
            fy = fact.get("fy")
            start = fact.get("start")
            end = fact.get("end")
            if form not in COMPANYFACT_FORMS:
                continue
            if unit != "USD":
                continue
            if period_type == "quarterly":
                if not _is_quarterly_fact(fact):
                    continue
            elif not _is_annual_fact(fact):
                continue
            try:
                numeric_value = float(value)
            except (TypeError, ValueError):
                continue
            facts_out.append(
                {
                    "unit": unit,
                    "fy": fy,
                    "fp": fp,
                    "frame": frame,
                    "start": start,
                    "end": end,
                    "form": form,
                    "value": numeric_value,
                    "filed": fact.get("filed"),
                }
            )
    return facts_out


def _revenue_growth_from_period_facts(facts: list[dict], tag: str, *, period_type: str) -> Optional[dict]:
    if len(facts) < 2:
        return None
    facts.sort(key=lambda item: (str(item.get("end") or ""), str(item.get("filed") or "")), reverse=True)
    latest = facts[0]
    prior = _matching_prior_year(latest, facts[1:])
    if not prior or not prior["value"]:
        return None
    yoy = (latest["value"] - prior["value"]) / abs(prior["value"])
    return {
        "metric": "quarterly_revenue_yoy",
        "tag": tag,
        "period_type": period_type,
        "value": yoy,
        "latest": latest,
        "prior_year_quarter": prior,
    }


def _fact_units(companyfacts: Dict, tag: str) -> Optional[Dict]:
    facts = companyfacts.get("facts", {})
    for namespace in ("us-gaap", "ifrs-full"):
        units = facts.get(namespace, {}).get(tag, {}).get("units")
        if units:
            return units
    for namespace_facts in facts.values():
        units = namespace_facts.get(tag, {}).get("units") if isinstance(namespace_facts, dict) else None
        if units:
            return units
    return None


def _matching_prior_year(latest: dict, candidates: list[dict]) -> Optional[dict]:
    latest_fp = latest.get("fp")
    try:
        latest_fy = int(latest.get("fy"))
    except (TypeError, ValueError):
        latest_fy = None
    if latest_fp and latest_fy:
        for candidate in candidates:
            try:
                candidate_fy = int(candidate.get("fy"))
            except (TypeError, ValueError):
                candidate_fy = None
            if candidate.get("fp") == latest_fp and candidate_fy == latest_fy - 1:
                return candidate
    return candidates[3] if len(candidates) >= 4 else candidates[0] if candidates else None


def _normalize_sec_form(form: str) -> str:
    normalized = re.sub(r"\s+", " ", str(form or "").strip().upper())
    if normalized.startswith("SCHEDULE 13"):
        normalized = normalized.replace("SCHEDULE ", "SC ", 1)
    return normalized


def _is_quarterly_fact(fact: dict) -> bool:
    days = _fact_duration_days(fact)
    if days is not None:
        return 60 <= days <= 120
    fp = str(fact.get("fp") or "").upper()
    frame = str(fact.get("frame") or "").upper()
    if fp.startswith("Q"):
        return True
    if re.search(r"Q[1-4](?!I)", frame) and not frame.endswith("I"):
        return True
    return False


def _is_annual_fact(fact: dict) -> bool:
    days = _fact_duration_days(fact)
    if days is not None:
        return 300 <= days <= 400
    fp = str(fact.get("fp") or "").upper()
    frame = str(fact.get("frame") or "").upper()
    if fp == "FY":
        return True
    if re.fullmatch(r"CY\d{4}", frame):
        return True
    return False


def _fact_duration_days(fact: dict) -> int | None:
    start = fact.get("start")
    end = fact.get("end")
    if not start or not end:
        return None
    try:
        return (date.fromisoformat(str(end)) - date.fromisoformat(str(start))).days
    except ValueError:
        return None


def _latest_fact_value(
    companyfacts: Dict,
    tags: tuple[str, ...],
    *,
    end: str | None = None,
    quarterly_only: bool,
) -> Optional[float]:
    facts = []
    for tag in tags:
        units = _fact_units(companyfacts, tag)
        if not units:
            continue
        for unit, values in units.items():
            for fact in values:
                if unit != "USD":
                    continue
                if _normalize_sec_form(str(fact.get("form", ""))) not in COMPANYFACT_FORMS:
                    continue
                if quarterly_only and not _is_quarterly_fact(fact):
                    continue
                if end and fact.get("end") != end:
                    continue
                try:
                    value = float(fact.get("val"))
                except (TypeError, ValueError):
                    continue
                facts.append((str(fact.get("end") or ""), str(fact.get("filed") or ""), value))
        if facts:
            break
    if not facts:
        return None
    facts.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return facts[0][2]


def _prior_year_fact_value(
    companyfacts: Dict,
    tags: tuple[str, ...],
    *,
    latest_end: str | None,
    quarterly_only: bool,
) -> Optional[float]:
    if not latest_end or len(str(latest_end)) < 4:
        return None
    try:
        prior_end = f"{int(str(latest_end)[:4]) - 1}{str(latest_end)[4:]}"
    except ValueError:
        return None
    return _latest_fact_value(companyfacts, tags, end=prior_end, quarterly_only=quarterly_only)


def _parse_form4_xml(filing: FilingRef, raw_text: str) -> list[dict]:
    try:
        root = ElementTree.fromstring(raw_text.encode("utf-8"))
    except ElementTree.ParseError:
        return []
    issuer = _node_text(root, ".//issuerTradingSymbol") or ""
    owner = _node_text(root, ".//reportingOwner/reportingOwnerId/rptOwnerName") or ""
    transactions = []
    for node in root.findall(".//nonDerivativeTransaction"):
        code = _node_text(node, ".//transactionCode")
        acquired_disposed = _node_text(node, ".//transactionAcquiredDisposedCode/value")
        shares = _to_float(_node_text(node, ".//transactionShares/value"))
        price = _to_float(_node_text(node, ".//transactionPricePerShare/value"))
        value = shares * price if shares is not None and price is not None else None
        transactions.append(
            {
                "issuer": issuer,
                "owner": owner,
                "form": filing.form,
                "filing_date": filing.filing_date,
                "transaction_date": _node_text(node, ".//transactionDate/value"),
                "transaction_code": code,
                "acquired_disposed": acquired_disposed,
                "shares": shares,
                "price": price,
                "value": value,
                "url": filing.url,
            }
        )
    return transactions


def _node_text(node, path: str) -> Optional[str]:
    found = node.find(path)
    if found is None or found.text is None:
        return None
    return found.text.strip()


def _ownership_section(text: str) -> str:
    lower = text.lower()
    anchors = [
        "security ownership of certain beneficial owners",
        "security ownership of beneficial owners",
        "security ownership of management",
        "beneficial owners and management",
        "beneficial ownership of common stock",
        "beneficial ownership of our common stock",
        "principal stockholders",
    ]
    starts = [lower.find(anchor) for anchor in anchors if lower.find(anchor) >= 0]
    if not starts:
        return ""
    start = min(starts)
    section = text[start : start + 18000]
    end_markers = ["executive compensation", "equity compensation plan", "certain relationships", "audit committee"]
    lower_section = section.lower()
    ends = [lower_section.find(marker) for marker in end_markers if lower_section.find(marker) > 1200]
    if ends:
        section = section[: min(ends)]
    return section


def _ownership_rows(section: str) -> list[dict]:
    rows = []
    sentences = re.split(r"(?<=[.%])\s+", section)
    for sentence in sentences:
        lowered = sentence.lower()
        if not _looks_like_ownership_context(lowered):
            continue
        percent_matches = re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*%", sentence)
        if not percent_matches:
            continue
        percent = max((_to_float(value) or 0) / 100 for value in percent_matches)
        if percent <= 0 or percent > 1:
            continue
        compact = sentence.strip()
        if len(compact) < 15 or len(compact) > 600:
            continue
        rows.append(
            {
                "name_or_context": compact[:220],
                "percent": percent,
            }
        )
        if len(rows) >= 25:
            break
    return rows


def _looks_like_ownership_context(sentence: str) -> bool:
    positive_terms = (
        "beneficial",
        "shares",
        "stockholder",
        "shareholder",
        "voting power",
        "blackrock",
        "vanguard",
    )
    negative_terms = (
        "customer",
        "revenue",
        "gross margin",
        "segment",
        "ownership interest",
        "proposal",
        "vote",
        "broker",
        "ratification",
        "compensation",
        "no effect",
    )
    return any(term in sentence for term in positive_terms) and not any(term in sentence for term in negative_terms)


def _management_group_percent(section: str) -> Optional[float]:
    patterns = [
        r"all\s+(?:directors|executive officers).{0,500}?([0-9]+(?:\.[0-9]+)?)\s*%",
        r"directors\s+and\s+executive\s+officers\s+as\s+a\s+group.{0,500}?([0-9]+(?:\.[0-9]+)?)\s*%",
        r"all\s+executive\s+officers\s+and\s+directors\s+as\s+a\s+group.{0,500}?([0-9]+(?:\.[0-9]+)?)\s*%",
    ]
    values = []
    for pattern in patterns:
        for match in re.finditer(pattern, section, flags=re.IGNORECASE):
            value = _to_float(match.group(1))
            if value is not None and 0 < value <= 100:
                values.append(value / 100)
    return max(values) if values else None


def _find_13f_info_table_document(documents: list[dict]) -> Optional[str]:
    candidates = []
    for document in documents:
        name = document.get("name", "")
        lower = name.lower()
        if lower.endswith(".xml") and ("info" in lower or "table" in lower or "infotable" in lower):
            candidates.append(name)
    if candidates:
        return candidates[0]
    for document in documents:
        name = document.get("name", "")
        if name.lower().endswith(".xml"):
            return name
    return None


def _child_text_by_local_name(node, name: str) -> Optional[str]:
    for child in node.iter():
        if _local_name(child.tag) == name and child.text:
            return child.text.strip()
    return None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _normalize_name(value: str) -> str:
    value = re.sub(r"[^a-z0-9 ]+", " ", value.lower())
    remove = {
        "inc",
        "corp",
        "corporation",
        "company",
        "co",
        "ltd",
        "plc",
        "class",
        "common",
        "stock",
        "ordinary",
    }
    tokens = [token for token in value.split() if token not in remove]
    return " ".join(tokens)


def _matches_issuer(issuer: str, company_name: str, ticker: str) -> bool:
    issuer_tokens = set(issuer.split())
    company_tokens = set(company_name.split())
    if len(company_tokens & issuer_tokens) >= min(2, max(1, len(company_tokens))):
        return True
    return ticker.lower() in issuer_tokens


def _ownership_percents(text: str) -> list[float]:
    percents = []
    for match in re.finditer(r"([0-9]+(?:\.[0-9]+)?)\s*%", text):
        value = _to_float(match.group(1))
        if value is None:
            continue
        if 0 < value <= 100:
            start = max(0, match.start() - 120)
            end = min(len(text), match.end() + 120)
            context = text[start:end].lower()
            if any(term in context for term in ("class", "beneficial", "voting", "ownership", "owned")):
                percents.append(value / 100)
    return sorted(set(percents), reverse=True)


def _schedule_13_xml_percents(raw_text: str) -> list[float]:
    try:
        root = ElementTree.fromstring(raw_text.encode("utf-8"))
    except ElementTree.ParseError:
        return []
    percents = []
    for node in root.iter():
        if _local_name(node.tag).lower() != "classpercent":
            continue
        value = _to_float(str(node.text or "").replace("%", "").strip())
        if value is None:
            continue
        if 0 < value <= 100:
            percents.append(value / 100)
    return sorted(set(percents), reverse=True)


def _money_to_number(raw_number: str, unit: str) -> Optional[float]:
    value = _to_float(raw_number.replace(",", ""))
    if value is None:
        return None
    if unit in {"billion", "bn"}:
        return value * 1_000_000_000
    if unit in {"million", "mm", "m"}:
        return value * 1_000_000
    if unit == "thousand":
        return value * 1_000
    return value


def _safe_ratio(numerator, denominator) -> Optional[float]:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _safe_growth(latest, prior) -> Optional[float]:
    if latest is None or prior in (None, 0):
        return None
    return (latest - prior) / abs(prior)


def _nonnegative_metric(value) -> Optional[float]:
    if value is None:
        return None
    return abs(value)


def _to_float(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
