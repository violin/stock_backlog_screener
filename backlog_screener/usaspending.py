from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import requests


USASPENDING_BASE_URL = "https://api.usaspending.gov/api"
SPENDING_BY_AWARD_PATH = "/v2/search/spending_by_award/"
CONTRACT_AWARD_TYPE_CODES = (
    "A",
    "B",
    "C",
    "D",
)
AWARD_FIELDS = (
    "Award ID",
    "Recipient Name",
    "Start Date",
    "End Date",
    "Award Amount",
    "Awarding Agency",
    "Awarding Sub Agency",
    "Award Type",
    "Funding Agency",
    "Funding Sub Agency",
)
COMPANY_SUFFIXES = {
    "A",
    "B",
    "CLASS",
    "CO",
    "COMPANY",
    "CORP",
    "CORPORATION",
    "GROUP",
    "HLDG",
    "HLDGS",
    "HOLDING",
    "HOLDINGS",
    "INC",
    "INCORPORATED",
    "LIMITED",
    "LLC",
    "LP",
    "LTD",
    "PLC",
    "SA",
    "THE",
}


@dataclass(frozen=True)
class GovernmentContractSignal:
    award_count: int
    total_award_amount: float
    largest_award_amount: float | None
    dod_award_amount: float
    top_agencies: list[dict[str, Any]]
    awards: list[dict[str, Any]]
    query: str
    start_date: str
    end_date: str
    warning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "award_count": self.award_count,
            "total_award_amount": self.total_award_amount,
            "largest_award_amount": self.largest_award_amount,
            "dod_award_amount": self.dod_award_amount,
            "top_agencies": self.top_agencies,
            "awards": self.awards,
            "query": self.query,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "warning": self.warning,
        }


class USASpendingClient:
    def __init__(
        self,
        cache_dir: Path,
        *,
        base_url: str = USASPENDING_BASE_URL,
        timeout: int = 20,
        retries: int = 1,
        retry_wait_seconds: float = 2.0,
        cache_ttl_hours: float = 24,
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.base_url = base_url.rstrip("/")
        self.timeout = int(timeout)
        self.retries = max(0, int(retries))
        self.retry_wait_seconds = max(0.0, float(retry_wait_seconds))
        self.cache_ttl_seconds = max(0.0, float(cache_ttl_hours)) * 60 * 60
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def search_company_contracts(
        self,
        *,
        company_name: str,
        ticker: str,
        years: int = 3,
        limit: int = 12,
    ) -> GovernmentContractSignal:
        query = search_query_for_company(company_name, ticker)
        end = date.today()
        start = end - timedelta(days=max(1, int(years)) * 365)
        if not query:
            return GovernmentContractSignal(
                award_count=0,
                total_award_amount=0.0,
                largest_award_amount=None,
                dod_award_amount=0.0,
                top_agencies=[],
                awards=[],
                query="",
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                warning="No company name available for USAspending recipient search.",
            )

        payload = {
            "subawards": False,
            "page": 1,
            "limit": max(1, min(100, int(limit))),
            "sort": "Award Amount",
            "order": "desc",
            "filters": {
                "recipient_search_text": [query],
                "award_type_codes": list(CONTRACT_AWARD_TYPE_CODES),
                "time_period": [{"start_date": start.isoformat(), "end_date": end.isoformat()}],
            },
            "fields": list(AWARD_FIELDS),
        }
        cache_path = self.cache_dir / f"awards_{_cache_key(query, ticker, start.isoformat(), end.isoformat(), limit)}.json"
        data = self._post_json(SPENDING_BY_AWARD_PATH, payload, cache_path=cache_path)
        awards = filter_company_awards(
            parse_awards(data),
            company_name=company_name,
            ticker=ticker,
        )
        return summarize_government_contracts(
            awards,
            query=query,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
        )

    def _post_json(self, path: str, payload: dict[str, Any], *, cache_path: Path) -> dict[str, Any]:
        if cache_path.exists() and time.time() - cache_path.stat().st_mtime < self.cache_ttl_seconds:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        url = f"{self.base_url}{path}"
        response = None
        for attempt in range(self.retries + 1):
            response = self.session.post(url, json=payload, timeout=self.timeout)
            if response.status_code < 500:
                break
            if attempt < self.retries:
                time.sleep(self.retry_wait_seconds * (attempt + 1))
        assert response is not None
        response.raise_for_status()
        data = response.json()
        cache_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data


def search_query_for_company(company_name: str, ticker: str = "") -> str:
    raw = str(company_name or "").strip()
    if raw:
        tokens = _company_tokens(raw)
        if tokens:
            return " ".join(tokens[:4])
        return raw
    return str(ticker or "").strip().upper()


def parse_awards(payload: dict[str, Any]) -> list[dict[str, Any]]:
    awards = []
    for row in payload.get("results") or []:
        amount = _to_float(row.get("Award Amount"))
        awards.append(
            {
                "award_id": str(row.get("Award ID") or ""),
                "recipient_name": str(row.get("Recipient Name") or ""),
                "start_date": row.get("Start Date"),
                "end_date": row.get("End Date"),
                "award_amount": amount,
                "awarding_agency": str(row.get("Awarding Agency") or ""),
                "awarding_sub_agency": str(row.get("Awarding Sub Agency") or ""),
                "funding_agency": str(row.get("Funding Agency") or ""),
                "funding_sub_agency": str(row.get("Funding Sub Agency") or ""),
                "award_type": str(row.get("Award Type") or ""),
            }
        )
    return awards


def filter_company_awards(awards: list[dict[str, Any]], *, company_name: str, ticker: str) -> list[dict[str, Any]]:
    company_tokens = set(_company_tokens(company_name))
    if not company_tokens:
        return awards
    filtered = []
    for award in awards:
        recipient = str(award.get("recipient_name") or "")
        score = recipient_match_score(company_name, recipient)
        if score < 0.45:
            continue
        enriched = dict(award)
        enriched["recipient_match_score"] = round(score, 3)
        enriched["ticker"] = ticker.upper()
        filtered.append(enriched)
    return filtered


def summarize_government_contracts(
    awards: list[dict[str, Any]],
    *,
    query: str,
    start_date: str,
    end_date: str,
) -> GovernmentContractSignal:
    amounts = [_to_float(award.get("award_amount")) or 0.0 for award in awards]
    total = sum(amounts)
    largest = max(amounts) if amounts else None
    agency_totals: dict[str, float] = {}
    dod_total = 0.0
    for award, amount in zip(awards, amounts):
        agency = str(award.get("awarding_agency") or award.get("funding_agency") or "").strip()
        if agency:
            agency_totals[agency] = agency_totals.get(agency, 0.0) + amount
        agency_text = " ".join(
            str(award.get(key) or "")
            for key in ("awarding_agency", "awarding_sub_agency", "funding_agency", "funding_sub_agency")
        ).upper()
        if "DEFENSE" in agency_text or "DEPARTMENT OF THE AIR FORCE" in agency_text or "DEPARTMENT OF THE NAVY" in agency_text:
            dod_total += amount
    top_agencies = [
        {"agency": agency, "award_amount": amount}
        for agency, amount in sorted(agency_totals.items(), key=lambda item: item[1], reverse=True)[:5]
    ]
    return GovernmentContractSignal(
        award_count=len(awards),
        total_award_amount=total,
        largest_award_amount=largest,
        dod_award_amount=dod_total,
        top_agencies=top_agencies,
        awards=awards[:25],
        query=query,
        start_date=start_date,
        end_date=end_date,
    )


def recipient_match_score(company_name: str, recipient_name: str) -> float:
    company_tokens = set(_company_tokens(company_name))
    recipient_tokens = set(_company_tokens(recipient_name))
    if not company_tokens or not recipient_tokens:
        return 0.0
    if company_tokens.issubset(recipient_tokens):
        return 1.0
    overlap = len(company_tokens & recipient_tokens)
    return overlap / max(len(company_tokens), 1)


def _company_tokens(value: str) -> list[str]:
    cleaned = re.sub(r"[^A-Za-z0-9]+", " ", str(value or "").upper())
    tokens = []
    for token in cleaned.split():
        if token in COMPANY_SUFFIXES:
            continue
        if len(token) <= 1 and not token.isdigit():
            continue
        tokens.append(token)
    return tokens


def _cache_key(*parts: Any) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(str(part).encode("utf-8", errors="ignore"))
        digest.update(b"\0")
    return digest.hexdigest()[:24]


def _to_float(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
