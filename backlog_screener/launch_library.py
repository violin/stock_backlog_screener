from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests


LAUNCH_LIBRARY_BASE_URL = "https://ll.thespacedevs.com/2.3.0"
UPCOMING_LAUNCHES_PATH = "/launches/upcoming/"
DEFAULT_LOOKBACK_HOURS = 24


@dataclass(frozen=True)
class LaunchLibrarySignal:
    ticker: str
    match_count: int
    launches_checked: int
    matches: list[dict[str, Any]]
    keywords: list[str]
    warning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "match_count": self.match_count,
            "launches_checked": self.launches_checked,
            "matches": self.matches,
            "keywords": self.keywords,
            "warning": self.warning,
        }


class LaunchLibraryClient:
    def __init__(
        self,
        cache_dir: str | Path,
        *,
        config_path: str | Path,
        base_url: str = LAUNCH_LIBRARY_BASE_URL,
        timeout_seconds: float = 20,
        cache_ttl_hours: float = 6,
        user_agent: str = "Code-Beta datasource monitor (contact: local)",
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.config_path = Path(config_path)
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = float(timeout_seconds)
        self.cache_ttl_seconds = max(0.0, float(cache_ttl_hours)) * 60 * 60
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        self._watchlist = _load_watchlist(self.config_path)

    def search_ticker_launches(
        self,
        ticker: str,
        *,
        company: dict[str, Any] | None = None,
        limit: int = 80,
        lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
    ) -> LaunchLibrarySignal:
        clean_ticker = str(ticker or "").strip().upper()
        keywords = self.keywords_for_ticker(clean_ticker, company=company)
        if not keywords:
            return LaunchLibrarySignal(
                ticker=clean_ticker,
                match_count=0,
                launches_checked=0,
                matches=[],
                keywords=[],
                warning="No Launch Library keywords configured for ticker.",
            )

        payload = self.upcoming_launches(limit=limit)
        launches = payload.get("results") or []
        now = datetime.now(timezone.utc)
        matches = match_launches(
            launches,
            keywords=keywords,
            now=now,
            lookback_hours=lookback_hours,
        )
        return LaunchLibrarySignal(
            ticker=clean_ticker,
            match_count=len(matches),
            launches_checked=len(launches),
            matches=matches,
            keywords=keywords,
        )

    def keywords_for_ticker(self, ticker: str, *, company: dict[str, Any] | None = None) -> list[str]:
        config = self._watchlist.get(str(ticker or "").upper()) or {}
        keywords = _string_list(config.get("keywords"))
        provider_keywords = _string_list(config.get("provider_keywords"))
        payload_keywords = _string_list(config.get("payload_keywords"))
        mission_keywords = _string_list(config.get("mission_keywords"))
        result = [*keywords, *provider_keywords, *payload_keywords, *mission_keywords]
        company_name = str((company or {}).get("name") or "").strip()
        if company_name and len(company_name) >= 4:
            result.append(company_name)
        return _dedupe(result)

    def upcoming_launches(self, *, limit: int = 80) -> dict[str, Any]:
        clean_limit = max(1, min(200, int(limit)))
        path = f"{UPCOMING_LAUNCHES_PATH}?limit={clean_limit}"
        cache_path = self.cache_dir / f"upcoming_{_cache_key(path)}.json"
        return self._get_json(path, cache_path=cache_path)

    def _get_json(self, path: str, *, cache_path: Path) -> dict[str, Any]:
        if cache_path.exists() and time.time() - cache_path.stat().st_mtime < self.cache_ttl_seconds:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        url = f"{self.base_url}{path}"
        response = self.session.get(url, timeout=self.timeout_seconds)
        response.raise_for_status()
        data = response.json()
        cache_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data


def match_launches(
    launches: list[dict[str, Any]],
    *,
    keywords: list[str],
    now: datetime | None = None,
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
) -> list[dict[str, Any]]:
    now = now or datetime.now(timezone.utc)
    lower_keywords = [keyword.lower() for keyword in keywords if keyword.strip()]
    matches: list[dict[str, Any]] = []
    for launch in launches:
        if not _is_futureish_launch(launch, now=now, lookback_hours=lookback_hours):
            continue
        text = launch_match_text(launch)
        lower_text = text.lower()
        matched_keywords = [keyword for keyword, lower in zip(keywords, lower_keywords) if lower in lower_text]
        if not matched_keywords:
            continue
        matches.append(normalize_launch(launch, matched_keywords=matched_keywords))
    return matches


def normalize_launch(launch: dict[str, Any], *, matched_keywords: list[str]) -> dict[str, Any]:
    mission = launch.get("mission") or {}
    provider = launch.get("launch_service_provider") or {}
    rocket = (launch.get("rocket") or {}).get("configuration") or {}
    pad = launch.get("pad") or {}
    location = pad.get("location") or {}
    status = launch.get("status") or {}
    vids = launch.get("vidURLs") or []
    webcast = ""
    if vids:
        first = vids[0] if isinstance(vids[0], dict) else {}
        webcast = str(first.get("url") or "")
    return {
        "id": launch.get("id"),
        "name": launch.get("name") or "",
        "url": launch.get("url") or "",
        "net": launch.get("net"),
        "window_start": launch.get("window_start"),
        "window_end": launch.get("window_end"),
        "status": {
            "name": status.get("name") or "",
            "abbrev": status.get("abbrev") or "",
            "description": status.get("description") or "",
        },
        "probability": launch.get("probability"),
        "launch_service_provider": provider.get("name") or "",
        "rocket": rocket.get("full_name") or rocket.get("name") or "",
        "mission": {
            "name": mission.get("name") or "",
            "type": mission.get("type") or "",
            "description": mission.get("description") or "",
            "orbit": ((mission.get("orbit") or {}).get("name") or ""),
        },
        "pad": {
            "name": pad.get("name") or "",
            "location": location.get("name") or "",
        },
        "webcast_url": webcast,
        "matched_keywords": matched_keywords,
        "match_text": launch_match_text(launch),
    }


def launch_match_text(launch: dict[str, Any]) -> str:
    mission = launch.get("mission") or {}
    provider = launch.get("launch_service_provider") or {}
    rocket = (launch.get("rocket") or {}).get("configuration") or {}
    pad = launch.get("pad") or {}
    location = pad.get("location") or {}
    agency_names = []
    for agency in mission.get("agencies") or []:
        if isinstance(agency, dict):
            agency_names.append(str(agency.get("name") or ""))
            agency_names.append(str(agency.get("abbrev") or ""))
    return " ".join(
        str(value or "")
        for value in (
            launch.get("name"),
            provider.get("name"),
            provider.get("abbrev"),
            rocket.get("full_name"),
            rocket.get("name"),
            mission.get("name"),
            mission.get("type"),
            mission.get("description"),
            (mission.get("orbit") or {}).get("name"),
            pad.get("name"),
            location.get("name"),
            " ".join(agency_names),
        )
    )


def _is_futureish_launch(launch: dict[str, Any], *, now: datetime, lookback_hours: int) -> bool:
    status = launch.get("status") or {}
    status_abbrev = str(status.get("abbrev") or "").lower()
    net = _parse_datetime(launch.get("net"))
    if net and net < now - timedelta(hours=max(0, int(lookback_hours))):
        return False
    if status_abbrev in {"success", "failure", "partial failure"} and net and net < now:
        return False
    return True


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _load_watchlist(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    result = {}
    for ticker, config in payload.items():
        result[str(ticker).upper()] = config if isinstance(config, dict) else {"keywords": config}
    return result


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        key = value.lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _cache_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:24]
