from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .settings import PROJECT_ROOT


DEFAULT_TIMETABLE_CONFIG = PROJECT_ROOT / "configs" / "timetable_seed_events.json"


def configured_timetable_events(
    ticker: str,
    *,
    config_path: str | Path = DEFAULT_TIMETABLE_CONFIG,
    today: date | None = None,
) -> list[dict[str, Any]]:
    clean_ticker = str(ticker or "").strip().upper()
    if not clean_ticker:
        return []
    events = _load_config(Path(config_path)).get(clean_ticker, [])
    current_date = today or date.today()
    normalized = [_normalize_event(clean_ticker, event) for event in events if isinstance(event, dict)]
    return [event for event in normalized if _event_is_upcoming(event, current_date)]


def merge_timetable_events(*event_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for group in event_groups:
        for event in group:
            key = (
                str(event.get("ticker") or "").upper(),
                str(event.get("event_date") or ""),
                str(event.get("title") or ""),
                str(event.get("source_key") or ""),
            )
            existing = merged.get(key)
            if not existing or _event_rank(event) > _event_rank(existing):
                merged[key] = dict(event)
    return sorted(merged.values(), key=_sort_key)


def _load_config(path: Path) -> dict[str, list[dict[str, Any]]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    result: dict[str, list[dict[str, Any]]] = {}
    for ticker, events in payload.items():
        result[str(ticker).upper()] = events if isinstance(events, list) else []
    return result


def _normalize_event(ticker: str, event: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "ticker": ticker,
        "event_date": _date_string(event.get("event_date")),
        "window_label": str(event.get("window_label") or ""),
        "catalyst_type": str(event.get("catalyst_type") or "event"),
        "title": str(event.get("title") or "Untitled event"),
        "summary": str(event.get("summary") or ""),
        "source_key": str(event.get("source_key") or "manual_timetable"),
        "source_url": str(event.get("source_url") or ""),
        "importance_score": float(event.get("importance_score") or 0),
        "confidence_score": float(event.get("confidence_score") or 0),
        "status": str(event.get("status") or "WATCH"),
        "evidence": event.get("evidence") if isinstance(event.get("evidence"), dict) else {},
        "configured": True,
    }
    return normalized


def _event_is_upcoming(event: dict[str, Any], today: date) -> bool:
    event_date = _parse_date(event.get("event_date"))
    return event_date is None or event_date >= today


def _event_rank(event: dict[str, Any]) -> tuple[float, float]:
    return (float(event.get("confidence_score") or 0), float(event.get("importance_score") or 0))


def _sort_key(event: dict[str, Any]) -> tuple[date, float, str]:
    event_date = _parse_date(event.get("event_date")) or date.max
    return (event_date, -float(event.get("importance_score") or 0), str(event.get("title") or ""))


def _date_string(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    parsed = _parse_date(value)
    return parsed.isoformat() if parsed else ""


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        return None
