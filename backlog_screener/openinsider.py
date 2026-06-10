from __future__ import annotations

import hashlib
import html
import re
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests


OPENINSIDER_BASE_URL = "http://openinsider.com"


@dataclass(frozen=True)
class OpenInsiderSignal:
    ticker: str
    transaction_count: int
    open_market_count: int
    purchase_count: int
    sale_count: int
    purchase_value: float
    sale_value: float
    net_purchase_value: float
    transactions: list[dict[str, Any]]
    source_url: str
    fetched_from_cache: bool = False
    warning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "transaction_count": self.transaction_count,
            "open_market_count": self.open_market_count,
            "purchase_count": self.purchase_count,
            "sale_count": self.sale_count,
            "purchase_value": self.purchase_value,
            "sale_value": self.sale_value,
            "net_purchase_value": self.net_purchase_value,
            "transactions": self.transactions,
            "source_url": self.source_url,
            "fetched_from_cache": self.fetched_from_cache,
            "warning": self.warning,
        }


class OpenInsiderClient:
    def __init__(
        self,
        cache_dir: str | Path,
        *,
        base_url: str = OPENINSIDER_BASE_URL,
        cache_ttl_hours: float = 24,
        timeout_seconds: float = 20,
        user_agent: str = "Code-Beta datasource monitor (contact: local)",
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.base_url = base_url.rstrip("/")
        self.cache_ttl_seconds = max(0.0, float(cache_ttl_hours)) * 60 * 60
        self.timeout_seconds = timeout_seconds
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )
        self.direct_session = requests.Session()
        self.direct_session.trust_env = False
        self.direct_session.headers.update(self.session.headers)

    def ticker_url(self, ticker: str, *, limit: int = 100) -> str:
        clean_ticker = str(ticker or "").strip().upper()
        query = urlencode({"s": clean_ticker, "cnt": max(1, min(100, int(limit)))})
        return f"{self.base_url}/screener?{query}"

    def fetch_ticker(self, ticker: str, *, limit: int = 100) -> OpenInsiderSignal:
        clean_ticker = str(ticker or "").strip().upper()
        if not clean_ticker:
            return OpenInsiderSignal(
                ticker="",
                transaction_count=0,
                open_market_count=0,
                purchase_count=0,
                sale_count=0,
                purchase_value=0.0,
                sale_value=0.0,
                net_purchase_value=0.0,
                transactions=[],
                source_url="",
                warning="Ticker is blank.",
            )
        source_url = self.ticker_url(clean_ticker, limit=limit)
        cache_path = self._cache_path(source_url)
        cached = self._read_cache(cache_path)
        if cached is not None:
            signal = analyze_openinsider_html(cached, ticker=clean_ticker, source_url=source_url)
            return _with_cache_flag(signal, fetched_from_cache=True)

        response_url, text = self._request_html(source_url)
        self._write_cache(cache_path, text)
        return analyze_openinsider_html(text, ticker=clean_ticker, source_url=response_url or source_url)

    def _cache_path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8", errors="ignore")).hexdigest()
        return self.cache_dir / f"{digest}.html"

    def _read_cache(self, path: Path) -> str | None:
        if not path.exists():
            return None
        if time.time() - path.stat().st_mtime > self.cache_ttl_seconds:
            return None
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return None

    def _write_cache(self, path: Path, text: str) -> None:
        path.write_text(text, encoding="utf-8")

    def _request_html(self, url: str) -> tuple[str, str]:
        errors: list[str] = []
        for session in (self.session, self.direct_session):
            try:
                response = session.get(url, timeout=self.timeout_seconds)
                response.raise_for_status()
                return response.url or url, response.text
            except Exception as exc:
                errors.append(str(exc))
        raise RuntimeError("; ".join(errors))


def analyze_openinsider_html(html_text: str, *, ticker: str, source_url: str = "") -> OpenInsiderSignal:
    clean_ticker = str(ticker or "").strip().upper()
    transactions = parse_openinsider_transactions(html_text, ticker=clean_ticker)
    open_market_transactions = [
        item
        for item in transactions
        if item.get("trade_code") in {"P", "S"}
        and "D" not in str(item.get("transaction_flags") or "")
    ]
    purchases = [item for item in open_market_transactions if item.get("trade_code") == "P"]
    sales = [item for item in open_market_transactions if item.get("trade_code") == "S"]
    purchase_value = sum(abs(float(item.get("value") or 0)) for item in purchases)
    sale_value = sum(abs(float(item.get("value") or 0)) for item in sales)
    warning = ""
    if not transactions and "No results" not in html_text:
        warning = "No parseable OpenInsider rows were found; page structure may have changed."
    return OpenInsiderSignal(
        ticker=clean_ticker,
        transaction_count=len(transactions),
        open_market_count=len(open_market_transactions),
        purchase_count=len(purchases),
        sale_count=len(sales),
        purchase_value=purchase_value,
        sale_value=sale_value,
        net_purchase_value=purchase_value - sale_value,
        transactions=transactions[:100],
        source_url=source_url,
        warning=warning,
    )


def parse_openinsider_transactions(html_text: str, *, ticker: str) -> list[dict[str, Any]]:
    parser = _OpenInsiderTableParser()
    parser.feed(html_text or "")
    clean_ticker = str(ticker or "").strip().upper()
    transactions: list[dict[str, Any]] = []
    for cells in parser.rows:
        if len(cells) < 12:
            continue
        row_ticker = cells[3]["text"].upper()
        if row_ticker != clean_ticker:
            continue
        trade_type = cells[6]["text"]
        trade_code = _trade_code(trade_type)
        sec_url = _first_matching_link(cells[1], "sec.gov")
        insider_url = _first_matching_link(cells[4], "/insider/")
        if insider_url.startswith("/"):
            insider_url = f"{OPENINSIDER_BASE_URL}{insider_url}"
        value = _parse_money(cells[11]["text"])
        transaction = {
            "transaction_flags": cells[0]["text"],
            "filing_datetime": cells[1]["text"],
            "trade_date": cells[2]["text"],
            "ticker": row_ticker,
            "insider_name": cells[4]["text"],
            "title": cells[5]["text"],
            "trade_type": trade_type,
            "trade_code": trade_code,
            "price": _parse_money(cells[7]["text"]),
            "quantity": _parse_number(cells[8]["text"]),
            "owned": _parse_number(cells[9]["text"]),
            "ownership_delta": cells[10]["text"],
            "value": value,
            "sec_form4_url": sec_url,
            "insider_url": insider_url,
            "source": "openinsider",
        }
        transactions.append(transaction)
    return transactions


class _OpenInsiderTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[dict[str, Any]]] = []
        self._in_tr = False
        self._in_td = False
        self._current_row: list[dict[str, Any]] = []
        self._current_text: list[str] = []
        self._current_links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "tr":
            self._in_tr = True
            self._current_row = []
        elif tag == "td" and self._in_tr:
            self._in_td = True
            self._current_text = []
            self._current_links = []
        elif tag == "a" and self._in_td:
            attr_map = {name.lower(): value or "" for name, value in attrs}
            href = attr_map.get("href", "")
            if href:
                self._current_links.append(html.unescape(href))

    def handle_data(self, data: str) -> None:
        if self._in_td and data:
            self._current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "td" and self._in_td:
            self._current_row.append(
                {
                    "text": _clean_text(" ".join(self._current_text)),
                    "links": list(self._current_links),
                }
            )
            self._in_td = False
        elif tag == "tr" and self._in_tr:
            if self._current_row:
                self.rows.append(self._current_row)
            self._in_tr = False


def _with_cache_flag(signal: OpenInsiderSignal, *, fetched_from_cache: bool) -> OpenInsiderSignal:
    return OpenInsiderSignal(
        ticker=signal.ticker,
        transaction_count=signal.transaction_count,
        open_market_count=signal.open_market_count,
        purchase_count=signal.purchase_count,
        sale_count=signal.sale_count,
        purchase_value=signal.purchase_value,
        sale_value=signal.sale_value,
        net_purchase_value=signal.net_purchase_value,
        transactions=signal.transactions,
        source_url=signal.source_url,
        fetched_from_cache=fetched_from_cache,
        warning=signal.warning,
    )


def _first_matching_link(cell: dict[str, Any], needle: str) -> str:
    for href in cell.get("links") or []:
        if needle.lower() in str(href).lower():
            return str(href)
    return ""


def _trade_code(value: str) -> str:
    match = re.match(r"\s*([A-Z])\b", value or "")
    return match.group(1) if match else ""


def _parse_money(value: str) -> float:
    clean = str(value or "").strip()
    if not clean:
        return 0.0
    sign = -1.0 if clean.startswith("-") or clean.startswith("(") else 1.0
    number = re.sub(r"[^0-9.]", "", clean)
    if not number:
        return 0.0
    try:
        return sign * float(number)
    except ValueError:
        return 0.0


def _parse_number(value: str) -> float:
    clean = str(value or "").strip()
    if not clean:
        return 0.0
    sign = -1.0 if clean.startswith("-") or clean.startswith("(") else 1.0
    number = re.sub(r"[^0-9.]", "", clean)
    if not number:
        return 0.0
    try:
        return sign * float(number)
    except ValueError:
        return 0.0


def _clean_text(value: str) -> str:
    return " ".join(html.unescape(value or "").split())
