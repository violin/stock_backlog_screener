from __future__ import annotations

import threading
from datetime import date, datetime
from decimal import Decimal
import re
from typing import Any

from flask import Flask, jsonify, render_template, request

from .datasources import DATA_SOURCE_DEFINITIONS, source_is_requested
from .db import PostgresStore
from .futu_provider import FutuProvider
from .llm import MiniMaxClient
from .pipeline import HiddenChampionPipeline
from .settings import AppSettings


def create_app(*, store: PostgresStore, settings: AppSettings) -> Flask:
    app = Flask(__name__)
    state = {
        "running": False,
        "last_run_id": None,
        "last_error": None,
        "queue": _empty_queue(),
    }
    lock = threading.Lock()

    @app.get("/")
    def index():
        return render_template("dashboard.html")

    @app.get("/api/candidates")
    def candidates():
        min_score = float(request.args.get("min_score", 0))
        limit = max(1, min(500, int(request.args.get("limit", 100))))
        query = (request.args.get("query") or "").strip()
        sector = (request.args.get("sector") or "").strip()
        rows = store.ranked_scores(min_score=min_score, limit=limit, query=query, sector=sector)
        return jsonify(_clean_json(rows))

    @app.get("/api/candidates/grouped")
    def grouped_candidates():
        min_score = float(request.args.get("min_score", 0))
        per_sector = max(1, min(10, int(request.args.get("per_sector", 5))))
        query = (request.args.get("query") or "").strip()
        sector = (request.args.get("sector") or "").strip()
        effective_min_score = 0 if query else min_score
        rows = store.ranked_scores_by_sector(
            min_score=effective_min_score,
            per_sector=per_sector,
            query=query,
            sector=sector,
        )
        return jsonify(
            _clean_json(
                {
                    "group_by": "sector",
                    "per_sector": per_sector,
                    "query": query,
                    "sector": sector,
                    "total": len(rows),
                    "groups": _group_by_sector(rows),
                }
            )
        )

    @app.get("/api/sectors")
    def sectors():
        return jsonify(_clean_json({"sectors": store.ranked_sectors()}))

    @app.get("/api/datasources")
    def datasources():
        rows = [_datasource_payload(row) for row in store.data_sources()]
        summary: dict[str, int] = {}
        for row in rows:
            scope = row.get("collection_scope") or "optional"
            summary[scope] = summary.get(scope, 0) + 1
        return jsonify(_clean_json({"sources": rows, "summary": summary}))

    @app.get("/api/candidates/search")
    def search_candidates():
        query = (request.args.get("q") or "").strip()
        limit = max(1, min(100, int(request.args.get("limit", 50))))
        rows = store.search_ranked_scores(query=query, limit=limit) if query else []
        return jsonify(
            _clean_json(
                {
                    "query": query,
                    "total": len(rows),
                    "groups": _group_by_sector(rows),
                }
            )
        )

    @app.get("/api/watchlist")
    def watchlist():
        rows = store.watched_tickers()
        return jsonify(_clean_json({"total": len(rows), "tickers": rows}))

    @app.post("/api/watchlist")
    def add_watchlist():
        payload = request.get_json(force=True, silent=True) or {}
        ticker = str(payload.get("ticker") or "").strip().upper()
        if not ticker:
            return jsonify({"error": "No ticker provided."}), 400
        if "." in ticker:
            ticker = ticker.split(".", 1)[1]
        row = store.watch_ticker(ticker, note=str(payload.get("note") or ""))
        return jsonify(_clean_json({"ticker": ticker, "watched": True, "item": row}))

    @app.delete("/api/watchlist/<ticker>")
    def remove_watchlist(ticker: str):
        clean_ticker = ticker.upper()
        if "." in clean_ticker:
            clean_ticker = clean_ticker.split(".", 1)[1]
        store.unwatch_ticker(clean_ticker)
        return jsonify({"ticker": clean_ticker, "watched": False})

    @app.get("/api/ticker/<ticker>")
    def ticker_detail(ticker: str):
        clean_ticker = ticker.upper()
        dimension = request.args.get("dimension") or None
        min_importance = float(request.args.get("min_importance", 0))
        timeline = store.timeline(
            clean_ticker,
            dimension=dimension,
            min_importance=min_importance,
            limit=120,
        )
        score = store.latest_score(clean_ticker)
        last_run = store.latest_ticker_run(clean_ticker)
        return jsonify(
            _clean_json(
                {
                    "ticker": clean_ticker,
                    "score": score,
                    "last_run": last_run,
                    "timeline": timeline,
                }
            )
        )

    @app.get("/api/ticker/<ticker>/future")
    def ticker_future(ticker: str):
        clean_ticker = ticker.upper()
        watched = store.watched_ticker(clean_ticker) is not None
        events = store.future_events(clean_ticker)
        return jsonify(
            _clean_json(
                {
                    "ticker": clean_ticker,
                    "watched": watched,
                    "events": events,
                    "horizon_months": 6,
                }
            )
        )

    @app.get("/api/ticker/<ticker>/trend")
    def ticker_trend(ticker: str):
        clean_ticker = ticker.upper()
        max_points = max(50, min(800, int(request.args.get("max_points", 420))))
        try:
            with FutuProvider(host=settings.futu_host, port=settings.futu_port, market=settings.futu_market) as provider:
                trend = provider.price_trend(clean_ticker, max_points=max_points)
        except Exception as exc:
            trend = {
                "ticker": clean_ticker,
                "source": "futu_opend",
                "source_label": "Futu weekly close",
                "period": "max",
                "points": [],
                "error": _short_trend_error(str(exc)),
            }
        return jsonify(_clean_json(trend))

    @app.get("/api/ticker/<ticker>/summary")
    def ticker_summary(ticker: str):
        item = store.latest_company_summary(ticker)
        return jsonify(
            _clean_json(
                {
                    "ticker": ticker.upper(),
                    "summary": _company_summary_payload(item) if item else None,
                }
            )
        )

    @app.post("/api/ticker/<ticker>/summary")
    def generate_ticker_summary(ticker: str):
        clean_ticker = ticker.upper()
        if not settings.minimax_api_key:
            return jsonify({"error": "MiniMax API key is not configured."}), 400
        company = store.company(clean_ticker)
        if not company:
            store.upsert_company(clean_ticker)
            company = store.company(clean_ticker) or {"ticker": clean_ticker}
        score = store.latest_score(clean_ticker)
        items = [
            item
            for item in store.latest_information_items(clean_ticker, limit=120)
            if item.get("dimension") != "company_summary"
        ]
        if not items and not score:
            return jsonify({"error": f"No evidence has been collected for {clean_ticker}."}), 404

        client = MiniMaxClient(
            api_key=settings.minimax_api_key,
            base_url=settings.minimax_base_url,
            model=settings.minimax_model,
            api=settings.minimax_api,
            retries=settings.minimax_retries,
            retry_wait_seconds=settings.minimax_retry_wait_seconds,
        )
        try:
            summary = client.summarize_company_profile(
                ticker=clean_ticker,
                company=company,
                score=score,
                items=items,
            )
        except Exception as exc:
            response = getattr(exc, "response", None)
            if response is not None:
                detail = _llm_error_detail(response)
                if response.status_code == 429:
                    status_code = 429
                elif "insufficient balance" in detail.lower():
                    status_code = 402
                else:
                    status_code = 502
            else:
                detail = "MiniMax summary failed."
                status_code = 502
            return jsonify({"error": detail}), status_code

        observation_id = store.save_observation(
            run_id=None,
            ticker=clean_ticker,
            source_key="minimax",
            source_type="llm_summary",
            observation_type="company_summary",
            title=f"{clean_ticker} MiniMax company summary",
            raw_json={
                "summary": summary.to_dict(),
                "input_item_count": len(items),
                "score_id": score.get("id") if score else None,
            },
            raw_text=summary.raw_response,
            trust_level=70,
        )
        store.save_information_item(
            run_id=None,
            observation_id=observation_id,
            ticker=clean_ticker,
            dimension="company_summary",
            title=f"{clean_ticker} AI company summary",
            summary=_company_summary_text(summary.to_dict()),
            source_key="minimax",
            importance_score=78,
            quality_score=72,
            confidence_score=summary.confidence_score,
            extracted_by=summary.provider,
            evidence=summary.to_dict(),
        )
        item = store.latest_company_summary(clean_ticker)
        return jsonify(_clean_json({"ticker": clean_ticker, "summary": _company_summary_payload(item)}))

    @app.get("/api/runs")
    def runs():
        payload = {
            "worker": state.copy(),
            "runs": store.runs(limit=20),
            "monitor": _run_monitor(store),
        }
        return jsonify(_clean_json(payload))

    @app.post("/api/run")
    def run_collection():
        payload = request.get_json(force=True, silent=True) or {}
        tickers = _parse_tickers(payload.get("tickers", ""))
        screen_context = _screen_context(payload)
        if not tickers and screen_context["screen_mode"] == "condition":
            try:
                tickers = _screen_condition_tickers(payload, settings)
            except Exception as exc:
                return jsonify({"error": f"Screening failed: {exc}"}), 502
        if not tickers:
            return jsonify({"error": "No tickers provided."}), 400
        with lock:
            if state["running"]:
                return jsonify({"error": "A collection run is already active."}), 409
            state["running"] = True
            state["last_error"] = None
            state["queue"] = _new_queue(tickers)

        def progress(event: dict[str, Any]) -> None:
            with lock:
                _apply_progress(state, event)

        def worker():
            try:
                pipeline = HiddenChampionPipeline(store, settings)
                run_id = pipeline.run(
                    tickers,
                    trigger="web",
                    use_futu=bool(payload.get("use_futu", True)),
                    use_sec=bool(payload.get("use_sec", True)),
                    use_yfinance=bool(payload.get("use_yfinance", False)),
                    use_13f=bool(payload.get("use_13f", False)),
                    use_usaspending=bool(payload.get("use_usaspending", False)),
                    summarize=bool(payload.get("summarize", False)),
                    delay_seconds=float(payload.get("delay_seconds", 1.0)),
                    run_context=screen_context,
                    progress_callback=progress,
                )
                with lock:
                    state["last_run_id"] = run_id
            except Exception as exc:
                with lock:
                    state["last_error"] = str(exc)
                    _mark_queue_failed(state, str(exc))
            finally:
                with lock:
                    state["running"] = False
                    if state["queue"].get("status") == "running":
                        state["queue"]["status"] = "idle"
                        state["queue"]["stage"] = "Idle"
                        state["queue"]["current"] = None
                    state["queue"]["finished_at"] = datetime.now()

        threading.Thread(target=worker, daemon=True).start()
        return jsonify({"status": "started", "tickers": tickers})

    return app


def _parse_tickers(value: Any) -> list[str]:
    if isinstance(value, list):
        raw = value
    else:
        raw = str(value).replace(",", " ").split()
    result = []
    seen = set()
    for ticker in raw:
        clean = str(ticker).strip().upper()
        if not clean:
            continue
        if "." in clean:
            clean = clean.split(".", 1)[1]
        if clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


def _screen_context(payload: dict[str, Any]) -> dict[str, Any]:
    sources = []
    if bool(payload.get("use_futu", True)):
        sources.append("futu_opend")
    if bool(payload.get("use_tradingview", False)):
        sources.append("tradingview")
    return {
        "screen_mode": str(payload.get("screen_mode") or "tickers"),
        "screen_condition": str(payload.get("screen_condition") or "").strip(),
        "screen_sources": sources,
    }


def _screen_condition_tickers(payload: dict[str, Any], settings: AppSettings) -> list[str]:
    if not bool(payload.get("use_futu", True)):
        raise ValueError("Futu OpenD is required for condition screening in this build.")
    condition = str(payload.get("screen_condition") or "")
    min_market_cap, max_market_cap = _parse_market_cap_range(condition)
    limit = max(1, min(80, int(payload.get("screen_limit") or 50)))
    with FutuProvider(host=settings.futu_host, port=settings.futu_port, market=settings.futu_market) as provider:
        rows, _ = provider.stock_filter(
            min_market_cap=min_market_cap,
            max_market_cap=max_market_cap,
            limit=limit,
            page_size=200,
            strict_common=True,
        )
    return _parse_tickers([row.get("ticker") or row.get("code") for row in rows if row.get("ticker") or row.get("code")])


def _parse_market_cap_range(condition: str) -> tuple[float, float]:
    text = condition.upper().replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)\s*([MB])\s*[-~至TO]+\s*(\d+(?:\.\d+)?)\s*([MB])", text)
    if not match:
        return 500_000_000, 10_000_000_000
    low = _market_cap_unit(float(match.group(1)), match.group(2))
    high = _market_cap_unit(float(match.group(3)), match.group(4))
    return (min(low, high), max(low, high))


def _market_cap_unit(value: float, unit: str) -> float:
    return value * (1_000_000_000 if unit == "B" else 1_000_000)


def _group_by_sector(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    by_name: dict[str, dict[str, Any]] = {}
    for row in rows:
        name = row.get("sector_group") or row.get("industry") or row.get("sector") or "Unclassified"
        if name not in by_name:
            by_name[name] = {"sector": name, "count": 0, "candidates": []}
            groups.append(by_name[name])
        by_name[name]["candidates"].append(row)
        by_name[name]["count"] += 1
    groups.sort(key=lambda group: (-_best_group_score(group), group["sector"]))
    return groups


def _best_group_score(group: dict[str, Any]) -> float:
    scores = [float(item.get("total_score") or 0) for item in group.get("candidates", [])]
    return max(scores) if scores else 0


def _run_monitor(store: PostgresStore, *, limit: int = 20) -> dict[str, Any]:
    runs = store.runs(limit=limit)
    run_ids = [int(row["id"]) for row in runs]
    counts = _run_monitor_counts(store, run_ids)
    enriched = [_enrich_run(row, counts.get(int(row["id"]), {})) for row in runs]
    active = [row for row in enriched if row["status"] == "RUNNING"]
    recent = [row for row in enriched if row["status"] != "RUNNING"]
    return {
        "active_count": len(active),
        "active_runs": active,
        "recent_runs": recent,
        "latest_run": enriched[0] if enriched else None,
        "latest_run_id": enriched[0]["id"] if enriched else None,
        "total_recent": len(enriched),
    }


def _run_monitor_counts(store: PostgresStore, run_ids: list[int]) -> dict[int, dict[str, Any]]:
    counts: dict[int, dict[str, Any]] = {run_id: {} for run_id in run_ids}
    if not run_ids:
        return counts

    with store.connect() as conn:
        info_rows = conn.execute(
            """
            select run_id,
                   dimension,
                   count(*) as item_count,
                   count(distinct ticker) as ticker_count,
                   max(created_at) as latest_at
            from information_items
            where run_id = any(%s::bigint[])
            group by run_id, dimension
            """,
            (run_ids,),
        ).fetchall()
        score_rows = conn.execute(
            """
            select run_id,
                   count(*) as score_count,
                   count(distinct ticker) as scored_tickers,
                   max(scored_at) as latest_at
            from security_scores
            where run_id = any(%s::bigint[])
            group by run_id
            """,
            (run_ids,),
        ).fetchall()
        observation_rows = conn.execute(
            """
            select run_id,
                   observation_type,
                   count(*) as observation_count,
                   count(distinct ticker) as ticker_count,
                   max(fetched_at) as latest_at
            from raw_observations
            where run_id = any(%s::bigint[])
            group by run_id, observation_type
            """,
            (run_ids,),
        ).fetchall()

    for row in info_rows:
        run_id = int(row["run_id"])
        bucket = counts.setdefault(run_id, {})
        dimensions = bucket.setdefault("dimensions", {})
        dimensions[row["dimension"]] = {
            "item_count": int(row["item_count"] or 0),
            "ticker_count": int(row["ticker_count"] or 0),
            "latest_at": row["latest_at"],
        }
        _max_time(bucket, row["latest_at"])

    for row in score_rows:
        run_id = int(row["run_id"])
        bucket = counts.setdefault(run_id, {})
        bucket["score_count"] = int(row["score_count"] or 0)
        bucket["scored_tickers"] = int(row["scored_tickers"] or 0)
        _max_time(bucket, row["latest_at"])

    for row in observation_rows:
        run_id = int(row["run_id"])
        bucket = counts.setdefault(run_id, {})
        observations = bucket.setdefault("observations", {})
        observations[row["observation_type"]] = {
            "observation_count": int(row["observation_count"] or 0),
            "ticker_count": int(row["ticker_count"] or 0),
            "latest_at": row["latest_at"],
        }
        if str(row["observation_type"]).endswith("_error"):
            bucket["error_observations"] = int(bucket.get("error_observations") or 0) + int(
                row["observation_count"] or 0
            )
        _max_time(bucket, row["latest_at"])

    return counts


def _enrich_run(row: dict[str, Any], counts: dict[str, Any]) -> dict[str, Any]:
    tickers = row.get("tickers") or []
    config = row.get("config") or {}
    total = len(tickers)
    expected_units = _expected_run_units(config)
    dimensions = counts.get("dimensions") or {}
    dimension_progress = []
    completed_slots = 0
    for dimension in expected_units:
        if dimension == "score":
            ticker_count = int(counts.get("scored_tickers") or 0)
            item_count = int(counts.get("score_count") or 0)
        else:
            data = dimensions.get(dimension) or {}
            ticker_count = int(data.get("ticker_count") or 0)
            item_count = int(data.get("item_count") or 0)
        completed_slots += min(ticker_count, total) if total else ticker_count
        dimension_progress.append(
            {
                "key": dimension,
                "label": _dimension_monitor_label(dimension),
                "ticker_count": ticker_count,
                "item_count": item_count,
                "total": total,
            }
        )

    expected_slots = total * len(expected_units) if total and expected_units else 0
    progress_percent = (completed_slots / expected_slots * 100) if expected_slots else 0
    status = str(row.get("status") or "UNKNOWN").upper()
    if status == "DONE":
        progress_percent = max(progress_percent, 100)
    latest_activity_at = counts.get("latest_activity_at") or row.get("finished_at") or row.get("started_at")
    return {
        "id": int(row["id"]),
        "trigger": row.get("trigger") or "manual",
        "status": status,
        "tickers": tickers[:12],
        "total": total,
        "config": config,
        "started_at": row.get("started_at"),
        "finished_at": row.get("finished_at"),
        "latest_activity_at": latest_activity_at,
        "error_message": row.get("error_message"),
        "progress": {
            "completed_slots": completed_slots,
            "expected_slots": expected_slots,
            "percent": round(min(progress_percent, 100), 1),
            "scored_tickers": int(counts.get("scored_tickers") or 0),
            "error_observations": int(counts.get("error_observations") or 0),
        },
        "dimensions": dimension_progress,
    }


def _expected_run_units(config: dict[str, Any]) -> list[str]:
    units = []
    has_requested_source = False
    for source in DATA_SOURCE_DEFINITIONS:
        if source.status != "active" or not source_is_requested(source, config):
            continue
        has_requested_source = True
        for dimension in source.dimensions:
            if dimension not in units:
                units.append(dimension)
    if has_requested_source:
        units.append("score")
    return units or ["score"]


def _dimension_monitor_label(dimension: str) -> str:
    labels = {
        "market": "Market",
        "valuation": "Valuation",
        "sector": "Sector",
        "attention_flow": "Attention",
        "backlog": "Backlog Text",
        "backlog_quality": "Backlog Amount",
        "growth": "Growth",
        "quality": "Quality",
        "ownership": "Ownership",
        "insider_activity": "Insider Activity",
        "institutional_activity": "Institutions",
        "government_contract": "Gov Contracts",
        "future_events": "Future Events",
        "company_summary": "AI Summary",
        "score": "Score",
    }
    return labels.get(dimension, dimension.replace("_", " ").title())


def _max_time(bucket: dict[str, Any], value: Any) -> None:
    if value is None:
        return
    current = bucket.get("latest_activity_at")
    if current is None or value > current:
        bucket["latest_activity_at"] = value


def _empty_queue() -> dict[str, Any]:
    return {
        "status": "idle",
        "run_id": None,
        "stage": "Idle",
        "tickers": [],
        "current": None,
        "pending": [],
        "completed": [],
        "failed": [],
        "total": 0,
        "started_at": None,
        "finished_at": None,
    }


def _new_queue(tickers: list[str]) -> dict[str, Any]:
    queue = _empty_queue()
    queue.update(
        {
            "status": "running",
            "stage": "Queued",
            "tickers": tickers,
            "pending": tickers.copy(),
            "total": len(tickers),
            "started_at": datetime.now(),
        }
    )
    return queue


def _apply_progress(state: dict[str, Any], event: dict[str, Any]) -> None:
    queue = state["queue"]
    event_name = event.get("event")
    if event_name == "run_started":
        queue["run_id"] = event.get("run_id")
        queue["stage"] = "Starting"
        state["last_run_id"] = event.get("run_id")
    elif event_name == "stage":
        queue["stage"] = event.get("stage") or queue.get("stage")
    elif event_name == "ticker_started":
        ticker = str(event.get("ticker") or "").upper()
        queue["current"] = ticker
        queue["stage"] = f"{ticker} collecting"
        queue["pending"] = [item for item in queue.get("pending", []) if item != ticker]
    elif event_name == "ticker_done":
        ticker = str(event.get("ticker") or "").upper()
        if ticker and ticker not in queue["completed"]:
            queue["completed"].append(ticker)
        if queue.get("current") == ticker:
            queue["current"] = None
        queue["stage"] = f"{ticker} done"
    elif event_name == "run_done":
        queue["status"] = "done"
        queue["stage"] = "Done"
        queue["current"] = None
        queue["pending"] = []
        queue["finished_at"] = datetime.now()
    elif event_name == "run_failed":
        _mark_queue_failed(state, str(event.get("error") or "Run failed"))


def _mark_queue_failed(state: dict[str, Any], error: str) -> None:
    queue = state["queue"]
    current = queue.get("current")
    if current and current not in queue["failed"]:
        queue["failed"].append(current)
    queue["status"] = "failed"
    queue["stage"] = "Failed"
    queue["error"] = error


def _company_summary_payload(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    evidence = item.get("evidence") or {}
    return {
        "business": evidence.get("business") or "",
        "industry_role": evidence.get("industry_role") or "",
        "recommendation_reason": evidence.get("recommendation_reason") or [],
        "risks": evidence.get("risks") or [],
        "watch_items": evidence.get("watch_items") or [],
        "confidence_score": evidence.get("confidence_score") or item.get("confidence_score"),
        "provider": evidence.get("provider") or item.get("extracted_by"),
        "created_at": item.get("created_at"),
        "source_key": item.get("source_key"),
        "summary": item.get("summary") or "",
    }


def _company_summary_text(summary: dict[str, Any]) -> str:
    parts = []
    if summary.get("business"):
        parts.append(f"公司业务：{summary['business']}")
    if summary.get("industry_role"):
        parts.append(f"行业角色：{summary['industry_role']}")
    if summary.get("recommendation_reason"):
        parts.append("推荐理由：" + "；".join(summary["recommendation_reason"]))
    if summary.get("risks"):
        parts.append("主要风险：" + "；".join(summary["risks"]))
    if summary.get("watch_items"):
        parts.append("跟踪要点：" + "；".join(summary["watch_items"]))
    return "\n".join(parts)


def _datasource_payload(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata") or {}
    rate_limit_policy = row.get("rate_limit_policy") or {}
    return {
        "source_key": row.get("source_key"),
        "source_name": row.get("source_name"),
        "source_type": row.get("source_type"),
        "trust_level": row.get("trust_level"),
        "enabled": row.get("enabled"),
        "updated_at": row.get("updated_at"),
        "provider": metadata.get("provider") or "",
        "website_url": metadata.get("website_url") or "",
        "docs_url": metadata.get("docs_url") or "",
        "collection_scope": metadata.get("collection_scope") or "optional",
        "run_flag": metadata.get("run_flag") or "",
        "collector_group": metadata.get("collector_group") or "",
        "default_enabled": metadata.get("default_enabled") or False,
        "status": metadata.get("status") or ("active" if row.get("enabled") else "planned"),
        "auth": metadata.get("auth") or "none",
        "dimensions": metadata.get("dimensions") or [],
        "applies_to_keywords": metadata.get("applies_to_keywords") or [],
        "applies_to_tickers": metadata.get("applies_to_tickers") or [],
        "rate_limit_summary": metadata.get("rate_limit_summary")
        or rate_limit_policy.get("observed_limit")
        or "",
        "cache_policy": metadata.get("cache_policy") or "",
        "notes": metadata.get("notes") or [],
        "rate_limit_policy": rate_limit_policy,
    }


def _short_trend_error(message: str) -> str:
    clean = (message or "").strip()
    if not clean:
        return "Trend unavailable"
    lower = clean.lower()
    if "too many requests" in lower or "rate limit" in lower:
        return "Rate limited"
    if "historical candlestick quota" in lower or "quota is released" in lower:
        return "Futu history quota"
    if "no yfpricedata" in lower or "possibly delisted" in lower:
        return "No price history"
    return clean[:80]


def _llm_error_detail(response) -> str:
    try:
        payload = response.json()
    except Exception:
        payload = {}
    message = ""
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = str(error.get("message") or "")
        elif error:
            message = str(error)
        elif payload.get("message"):
            message = str(payload.get("message"))
    if message:
        return f"MiniMax summary failed ({response.status_code}): {message}"
    return f"MiniMax summary failed ({response.status_code})."


def _clean_json(value):
    if isinstance(value, list):
        return [_clean_json(item) for item in value]
    if isinstance(value, dict):
        return {key: _clean_json(item) for key, item in value.items()}
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value
