from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests


DEFAULT_OFFICIAL_TERMS = (
    "award",
    "backlog",
    "contract",
    "customer",
    "data center",
    "defense",
    "design win",
    "dod",
    "launch",
    "mission",
    "nasa",
    "order",
    "payload",
    "platform",
    "production",
    "qualification",
    "satellite",
    "spacecraft",
)


class CompanyOfficialClient:
    def __init__(
        self,
        cache_dir: str | Path,
        *,
        config_path: str | Path,
        cache_ttl_hours: float = 24,
        user_agent: str = "Code-Beta datasource monitor (contact: local)",
        timeout_seconds: float = 12,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.config_path = Path(config_path)
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._sources = _load_sources(self.config_path)

    def sources_for_ticker(self, ticker: str) -> list[dict[str, Any]]:
        rows = self._sources.get(ticker.upper(), [])
        return [normalize_source(row) for row in rows if normalize_source(row).get("url")]

    def fetch_ticker(self, ticker: str) -> dict[str, Any]:
        sources = self.sources_for_ticker(ticker)
        pages = [self.fetch_source(source) for source in sources]
        return {
            "ticker": ticker.upper(),
            "source_count": len(sources),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "highlight_count": sum(len(page.get("highlights") or []) for page in pages),
            "pages": pages,
        }

    def fetch_source(self, source: dict[str, Any]) -> dict[str, Any]:
        url = str(source.get("url") or "").strip()
        cache_path = self._cache_path(url)
        cached = self._read_cache(cache_path)
        if cached:
            cached["fetched_from_cache"] = True
            return cached

        try:
            response = requests.get(
                url,
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout_seconds,
            )
            page = extract_official_page(
                response.text if response.ok else "",
                url=response.url or url,
                label=str(source.get("label") or ""),
                source_type=str(source.get("type") or "official_page"),
                status_code=response.status_code,
            )
            if not response.ok:
                page["error"] = f"HTTP {response.status_code}"
        except Exception as exc:
            page = {
                "label": source.get("label") or _host_label(url),
                "url": url,
                "type": source.get("type") or "official_page",
                "status_code": None,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "fetched_from_cache": False,
                "title": "",
                "description": "",
                "text_checksum": "",
                "highlights": [],
                "error": str(exc),
            }
        page["configured_url"] = url
        page["fetched_from_cache"] = False
        self._write_cache(cache_path, page)
        return page

    def _cache_path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8", errors="ignore")).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def _read_cache(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        fetched_at = _parse_time(payload.get("fetched_at"))
        if not fetched_at or datetime.now(timezone.utc) - fetched_at > self.cache_ttl:
            return None
        return payload if isinstance(payload, dict) else None

    def _write_cache(self, path: Path, payload: dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_source(source: Any) -> dict[str, Any]:
    if isinstance(source, str):
        return {
            "label": _host_label(source),
            "url": source.strip(),
            "type": "official_page",
            "source_key": "company_official",
        }
    if not isinstance(source, dict):
        return {}
    url = str(source.get("url") or "").strip()
    return {
        "label": str(source.get("label") or _host_label(url)),
        "url": url,
        "type": str(source.get("type") or "official_page"),
        "source_key": str(source.get("source_key") or "company_official"),
    }


def extract_official_page(
    html_text: str,
    *,
    url: str,
    label: str = "",
    source_type: str = "official_page",
    status_code: int | None = 200,
    terms: tuple[str, ...] = DEFAULT_OFFICIAL_TERMS,
) -> dict[str, Any]:
    text = _html_to_text(html_text)
    return {
        "label": label or _host_label(url),
        "url": url,
        "type": source_type,
        "status_code": status_code,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "fetched_from_cache": False,
        "title": _extract_title(html_text),
        "description": _extract_description(html_text),
        "text_checksum": hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest() if text else "",
        "highlights": extract_highlights(text, terms=terms),
    }


def extract_highlights(
    text: str,
    *,
    terms: tuple[str, ...] = DEFAULT_OFFICIAL_TERMS,
    radius: int = 180,
    max_snippets: int = 10,
) -> list[dict[str, str]]:
    clean_text = " ".join(str(text or "").split())
    lower = clean_text.lower()
    highlights: list[dict[str, str]] = []
    seen_snippets: set[str] = set()
    for term in terms:
        index = lower.find(term.lower())
        if index < 0:
            continue
        start = max(0, index - radius)
        end = min(len(clean_text), index + len(term) + radius)
        snippet = clean_text[start:end].strip(" .")
        key = snippet.lower()
        if key in seen_snippets:
            continue
        seen_snippets.add(key)
        highlights.append({"term": term, "snippet": snippet})
        if len(highlights) >= max_snippets:
            break
    return highlights


def _load_sources(path: Path) -> dict[str, list[Any]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        str(ticker).upper(): sources if isinstance(sources, list) else [sources]
        for ticker, sources in payload.items()
    }


def _extract_title(html_text: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html_text or "", flags=re.IGNORECASE | re.DOTALL)
    return _clean_html_fragment(match.group(1)) if match else ""


def _extract_description(html_text: str) -> str:
    match = re.search(
        r"<meta[^>]+(?:name|property)=[\"'](?:description|og:description)[\"'][^>]+content=[\"']([^\"']+)[\"']",
        html_text or "",
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        match = re.search(
            r"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+(?:name|property)=[\"'](?:description|og:description)[\"']",
            html_text or "",
            flags=re.IGNORECASE | re.DOTALL,
        )
    return _clean_html_fragment(match.group(1)) if match else ""


def _html_to_text(html_text: str) -> str:
    text = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", html_text or "", flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(html.unescape(text).split())


def _clean_html_fragment(value: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", value or "")).split())


def _host_label(url: str) -> str:
    host = urlparse(url).netloc.replace("www.", "")
    return host or "Official source"


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
