from __future__ import annotations

import threading
import json
import math
import socket
import time
from datetime import date, datetime
from decimal import Decimal
import re
from typing import Any

from flask import Flask, jsonify, render_template, request

from .datasources import DATA_SOURCE_DEFINITIONS, source_is_requested
from .db import PostgresStore
from .futu_provider import FutuProvider, futu_code
from .intraday import intraday_payload
from .llm import build_llm_client
from .market_prep import ai_prompt, opening_radar_snapshot
from .pipeline import HiddenChampionPipeline
from .settings import AppSettings
from .timetable import configured_timetable_events, merge_timetable_events
from .trading import TradingAutomationManager
from .yahoo import fetch_nasdaq_price_trend, fetch_price_trend


def create_app(*, store: PostgresStore, settings: AppSettings) -> Flask:
    app = Flask(__name__)
    state = {
        "running": False,
        "last_run_id": None,
        "last_error": None,
        "queue": _empty_queue(),
    }
    lock = threading.Lock()
    short_term_tracker = ShortTermTracker(settings)
    trading_manager = TradingAutomationManager(settings=settings, db_store=store)

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

    @app.get("/api/opening-radar")
    def opening_radar():
        force = _truthy(request.args.get("force"))
        report = None if force else store.latest_opening_radar_report()
        if report is not None and report.get("report_date") != date.today():
            report = None
        if report is None:
            snapshot = opening_radar_snapshot(history_fetcher=_futu_daily_history_fetcher(settings))
            report = store.save_opening_radar_snapshot(
                report_date=_snapshot_report_date(snapshot),
                snapshot=snapshot,
            )
        return jsonify(_clean_json(_opening_radar_payload(report, store)))

    @app.get("/api/opening-radar/<int:report_id>")
    def opening_radar_report(report_id: int):
        report = store.opening_radar_report(report_id)
        if not report:
            return jsonify({"error": "Opening Radar report not found."}), 404
        return jsonify(_clean_json(_opening_radar_payload(report, store)))

    @app.post("/api/opening-radar/advice")
    def opening_radar_advice():
        provider_label = _llm_provider_label(settings)
        client = build_llm_client(settings)
        if client is None:
            return jsonify({"error": f"{provider_label} API key is not configured."}), 400
        if not hasattr(client, "complete_json"):
            return jsonify({"error": f"{provider_label} does not support opening-radar JSON advice yet."}), 400
        payload = request.get_json(force=True, silent=True) or {}
        report_id = payload.get("report_id")
        report = store.opening_radar_report(int(report_id)) if report_id else store.latest_opening_radar_report()
        if report is None:
            snapshot = opening_radar_snapshot(history_fetcher=_futu_daily_history_fetcher(settings))
            report = store.save_opening_radar_snapshot(
                report_date=_snapshot_report_date(snapshot),
                snapshot=snapshot,
            )
        snapshot = report.get("snapshot") or {}
        prompt = ai_prompt(json.dumps(_clean_json(snapshot), ensure_ascii=False, indent=2))
        system = (
            "你是美股日线技术面交易顾问。你只基于输入事实，服务开盘前半小时的仓位和方向决策。"
            "先判断市场状态，再给今天的可执行预案。只输出 JSON。"
        )
        try:
            advice = client.complete_json(
                system=system,
                user=prompt,
            )
        except Exception as exc:
            response = getattr(exc, "response", None)
            if response is not None:
                detail = _llm_error_detail(response, provider_label)
                status_code = 429 if response.status_code == 429 else 502
            else:
                detail = f"{provider_label} opening-radar advice failed."
                status_code = 502
            return jsonify({"error": detail}), status_code
        raw_response = str(advice.pop("raw_response", "") or "")
        report = store.save_opening_radar_advice(
            report_id=int(report["id"]),
            advice=advice,
            provider=provider_label,
            prompt=prompt,
            raw_response=raw_response,
        )
        return jsonify(_clean_json(_opening_radar_payload(report, store)))

    @app.get("/api/opening-radar/long-term-trend")
    def opening_radar_long_term_trend():
        index_key = str(request.args.get("index") or "nasdaq").strip().lower()
        transform = str(request.args.get("transform") or "raw").strip().lower()
        max_points = max(120, min(1600, int(request.args.get("max_points") or 760)))
        config = _opening_trend_index_config(index_key)
        payload = _opening_long_term_trend_data(config, transform, max_points=max_points)
        return jsonify(_clean_json(payload))

    @app.post("/api/opening-radar/long-term-trend/analyze")
    def opening_radar_long_term_trend_analyze():
        provider_label = _llm_provider_label(settings)
        client = build_llm_client(settings)
        if client is None:
            return jsonify({"error": f"{provider_label} API key is not configured."}), 400
        if not hasattr(client, "complete_json"):
            return jsonify({"error": f"{provider_label} does not support long-term trend JSON analysis yet."}), 400
        payload = request.get_json(force=True, silent=True) or {}
        index_key = str(payload.get("index") or "nasdaq").strip().lower()
        transform = str(payload.get("transform") or "raw").strip().lower()
        config = _opening_trend_index_config(index_key)
        trend_payload = _opening_long_term_trend_data(config, transform, max_points=760)
        if trend_payload.get("error") or len(trend_payload.get("points") or []) < 2:
            return jsonify({"error": trend_payload.get("error") or "Not enough long term history."}), 400
        prompt = _opening_trend_analysis_prompt(trend_payload)
        system = (
            "你是美股指数长期趋势和仓位风险顾问。你只能基于用户输入的指数点位、趋势残差和统计字段分析，"
            "不得编造新闻、宏观数据或未提供的价格。输出必须是 JSON。"
        )
        try:
            analysis = client.complete_json(system=system, user=prompt)
        except Exception as exc:
            response = getattr(exc, "response", None)
            if response is not None:
                detail = _llm_error_detail(response, provider_label)
                status_code = 429 if response.status_code == 429 else 502
            else:
                detail = f"{provider_label} long-term trend analysis failed."
                status_code = 502
            return jsonify({"error": detail}), status_code
        raw_response = str(analysis.pop("raw_response", "") or "")
        analysis["provider"] = analysis.get("provider") or provider_label
        return jsonify(
            _clean_json(
                {
                    "provider": provider_label,
                    "analysis": analysis,
                    "prompt": prompt,
                    "raw_response": raw_response,
                }
            )
        )

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
        stored_events = store.future_events(clean_ticker)
        configured_events = configured_timetable_events(clean_ticker)
        events = merge_timetable_events(stored_events, configured_events)
        return jsonify(
            _clean_json(
                {
                    "ticker": clean_ticker,
                    "watched": watched,
                    "events": events,
                    "horizon_months": 6,
                    "configured_events": len(configured_events),
                }
            )
        )

    @app.get("/api/ticker/<ticker>/trend")
    def ticker_trend(ticker: str):
        clean_ticker = ticker.upper()
        max_points = max(50, min(800, int(request.args.get("max_points", 420))))
        futu_error = ""
        try:
            _assert_futu_opend_available(settings.futu_host, settings.futu_port)
            with FutuProvider(host=settings.futu_host, port=settings.futu_port, market=settings.futu_market) as provider:
                trend = provider.price_trend(clean_ticker, max_points=max_points)
        except Exception as exc:
            futu_error = _short_trend_error(str(exc))
            trend = {
                "ticker": clean_ticker,
                "source": "futu_opend",
                "source_label": "Futu weekly close",
                "period": "max",
                "points": [],
                "error": futu_error,
            }
        if not _trend_has_points(trend):
            trend = _fallback_price_trend(clean_ticker, max_points=max_points, base_trend=trend, base_error=futu_error)
        return jsonify(_clean_json(trend))

    @app.get("/api/ticker/<ticker>/short-term")
    def ticker_short_term(ticker: str):
        window = _short_term_window(request.args)
        return jsonify(_clean_json(short_term_tracker.snapshot(ticker, window=window)))

    @app.post("/api/ticker/<ticker>/short-term/start")
    def start_ticker_short_term(ticker: str):
        payload = request.get_json(force=True, silent=True) or {}
        window = _short_term_window(payload)
        try:
            data = short_term_tracker.start(ticker, window=window)
        except Exception as exc:
            return jsonify({"error": _short_futu_error(str(exc))}), 502
        return jsonify(_clean_json(data))

    @app.post("/api/ticker/<ticker>/short-term/stop")
    def stop_ticker_short_term(ticker: str):
        return jsonify(_clean_json(short_term_tracker.stop(ticker)))

    @app.get("/api/trading/simulate/strategies")
    def trading_simulate_strategies():
        return jsonify(_clean_json({"strategies": trading_manager.strategies(), "pairs": trading_manager.pairs()}))

    @app.get("/api/trading/simulate/instances")
    def trading_simulate_instances():
        return jsonify(_clean_json(trading_manager.list_instances()))

    @app.post("/api/trading/simulate/instances")
    def create_trading_simulate_instance():
        payload = request.get_json(force=True, silent=True) or {}
        try:
            instance = trading_manager.create_instance(payload)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(_clean_json({"instance": instance}))

    @app.get("/api/trading/simulate/instances/<instance_id>")
    def trading_simulate_instance(instance_id: str):
        instance = trading_manager.get_instance(instance_id)
        if not instance:
            return jsonify({"error": "Trading instance not found."}), 404
        return jsonify(_clean_json({"instance": instance}))

    @app.patch("/api/trading/simulate/instances/<instance_id>/strategy")
    def update_trading_simulate_instance_strategy(instance_id: str):
        payload = request.get_json(force=True, silent=True) or {}
        try:
            instance = trading_manager.update_instance_strategy(instance_id, payload)
        except KeyError as exc:
            return jsonify({"error": str(exc)}), 404
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(_clean_json({"instance": instance}))

    @app.delete("/api/trading/simulate/instances/<instance_id>")
    def delete_trading_simulate_instance(instance_id: str):
        try:
            result = trading_manager.delete_instance(instance_id)
        except KeyError as exc:
            return jsonify({"error": str(exc)}), 404
        return jsonify(_clean_json(result))

    @app.post("/api/trading/simulate/instances/<instance_id>/start")
    def start_trading_simulate_instance(instance_id: str):
        try:
            instance = trading_manager.start_instance(instance_id)
        except KeyError as exc:
            return jsonify({"error": str(exc)}), 404
        return jsonify(_clean_json({"instance": instance}))

    @app.post("/api/trading/simulate/instances/<instance_id>/stop")
    def stop_trading_simulate_instance(instance_id: str):
        try:
            instance = trading_manager.stop_instance(instance_id)
        except KeyError as exc:
            return jsonify({"error": str(exc)}), 404
        return jsonify(_clean_json({"instance": instance}))

    @app.post("/api/trading/simulate/instances/<instance_id>/backtest")
    def backtest_trading_simulate_instance(instance_id: str):
        payload = request.get_json(force=True, silent=True) or {}
        try:
            result = trading_manager.backtest_instance(instance_id, payload)
        except KeyError as exc:
            return jsonify({"error": str(exc)}), 404
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"error": _short_futu_error(str(exc))}), 502
        return jsonify(_clean_json({"backtest": result}))

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
        provider_label = _llm_provider_label(settings)
        client = build_llm_client(settings)
        if client is None:
            return jsonify({"error": f"{provider_label} API key is not configured."}), 400
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
                detail = _llm_error_detail(response, provider_label)
                if response.status_code == 429:
                    status_code = 429
                elif "insufficient balance" in detail.lower():
                    status_code = 402
                else:
                    status_code = 502
            else:
                detail = f"{provider_label} summary failed."
                status_code = 502
            return jsonify({"error": detail}), status_code

        source_key = _llm_source_key(summary.provider)
        observation_id = store.save_observation(
            run_id=None,
            ticker=clean_ticker,
            source_key=source_key,
            source_type="llm_summary",
            observation_type="company_summary",
            title=f"{clean_ticker} {summary.provider} company summary",
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
            source_key=source_key,
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
                    use_launch_library=bool(payload.get("use_launch_library", False)),
                    use_company_official=bool(payload.get("use_company_official", False)),
                    use_openinsider=bool(payload.get("use_openinsider", False)),
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


def _futu_daily_history_fetcher(settings: AppSettings):
    def fetch(symbol: str) -> list[dict[str, Any]]:
        with FutuProvider(host=settings.futu_host, port=settings.futu_port, market=settings.futu_market) as provider:
            return provider.history_kline(futu_code(symbol, settings.futu_market), days=260)

    return fetch


class ShortTermTracker:
    min_unsubscribe_seconds = 60

    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.lock = threading.Lock()
        self.provider: FutuProvider | None = None
        self.active: dict[str, dict[str, Any]] = {}
        self.unsubscribe_timers: dict[str, threading.Timer] = {}

    def start(self, ticker: str, *, window: int = 160) -> dict[str, Any]:
        clean_ticker = _clean_ticker(ticker)
        with self.lock:
            timer = self.unsubscribe_timers.pop(clean_ticker, None)
            if timer is not None:
                timer.cancel()
            provider = self._provider_locked()
            code = provider.subscribe_minute_kline(clean_ticker, session="ALL")
            now = datetime.now()
            existing = self.active.get(clean_ticker) or {}
            was_tracking = bool(existing.get("tracking"))
            self.active[clean_ticker] = {
                "tracking": True,
                "code": code,
                "active_since": existing.get("active_since") if was_tracking else now.isoformat(timespec="seconds"),
                "started_monotonic": existing.get("started_monotonic") if was_tracking else time.monotonic(),
                "last_error": None,
            }
        return self.snapshot(clean_ticker, window=window)

    def stop(self, ticker: str) -> dict[str, Any]:
        clean_ticker = _clean_ticker(ticker)
        with self.lock:
            active = self.active.get(clean_ticker) or {}
            was_tracking = bool(active.get("tracking"))
            active["tracking"] = False
            error = None
            provider = self.provider
            if was_tracking and provider is not None and active.get("code"):
                elapsed = time.monotonic() - float(active.get("started_monotonic") or 0)
                if elapsed < self.min_unsubscribe_seconds:
                    self._schedule_unsubscribe_locked(clean_ticker, delay=self.min_unsubscribe_seconds - elapsed + 1)
                else:
                    try:
                        provider.unsubscribe_minute_kline(clean_ticker)
                    except Exception as exc:
                        error = _short_futu_error(str(exc))
            active["last_error"] = error
            self.active[clean_ticker] = active
        return intraday_payload(
            ticker=clean_ticker,
            code=active.get("code"),
            rows=[],
            tracking=False,
            active_since=active.get("active_since"),
            error=error,
        )

    def snapshot(self, ticker: str, *, window: int = 160) -> dict[str, Any]:
        clean_ticker = _clean_ticker(ticker)
        with self.lock:
            active = self.active.get(clean_ticker) or {}
            if not active.get("tracking"):
                return intraday_payload(
                    ticker=clean_ticker,
                    code=active.get("code") or futu_code(clean_ticker, self.settings.futu_market),
                    rows=[],
                    tracking=False,
                    active_since=active.get("active_since"),
                    error=active.get("last_error"),
                )
            provider = self._provider_locked()
            try:
                code, rows = provider.current_minute_kline(clean_ticker, num=window)
            except Exception as exc:
                error = _short_futu_error(str(exc))
                active["last_error"] = error
                self.active[clean_ticker] = active
                return intraday_payload(
                    ticker=clean_ticker,
                    code=active.get("code") or futu_code(clean_ticker, self.settings.futu_market),
                    rows=[],
                    tracking=True,
                    active_since=active.get("active_since"),
                    error=error,
                )
            active["code"] = code
            active["last_error"] = None
            self.active[clean_ticker] = active
        return intraday_payload(
            ticker=clean_ticker,
            code=code,
            rows=rows,
            tracking=True,
            active_since=active.get("active_since"),
        )

    def _provider_locked(self) -> FutuProvider:
        if self.provider is None:
            _assert_futu_opend_available(self.settings.futu_host, self.settings.futu_port)
            self.provider = FutuProvider(
                host=self.settings.futu_host,
                port=self.settings.futu_port,
                market=self.settings.futu_market,
            )
        return self.provider

    def _schedule_unsubscribe_locked(self, ticker: str, *, delay: float) -> None:
        existing = self.unsubscribe_timers.pop(ticker, None)
        if existing is not None:
            existing.cancel()
        timer = threading.Timer(max(1.0, delay), self._delayed_unsubscribe, args=(ticker,))
        timer.daemon = True
        self.unsubscribe_timers[ticker] = timer
        timer.start()

    def _delayed_unsubscribe(self, ticker: str) -> None:
        with self.lock:
            self.unsubscribe_timers.pop(ticker, None)
            active = self.active.get(ticker) or {}
            if active.get("tracking"):
                return
            provider = self.provider
            if provider is None or not active.get("code"):
                return
            error = None
            try:
                provider.unsubscribe_minute_kline(ticker)
            except Exception as exc:
                error = _short_futu_error(str(exc))
            active["last_error"] = error
            self.active[ticker] = active


def _short_term_window(values: Any) -> int:
    raw = values.get("window", 160) if hasattr(values, "get") else 160
    try:
        value = int(raw or 160)
    except (TypeError, ValueError):
        value = 160
    return max(40, min(360, value))


def _clean_ticker(ticker: str) -> str:
    clean = str(ticker or "").strip().upper()
    if "." in clean:
        clean = clean.split(".", 1)[1]
    return clean


def _short_futu_error(message: str) -> str:
    clean = str(message or "").strip()
    if not clean:
        return "Futu OpenD unavailable."
    lower = clean.lower()
    if "no right" in lower or "permission" in lower:
        return "No Futu quote right for this symbol."
    if "connect" in lower or "connection" in lower or "opend" in lower:
        return "Futu OpenD connection unavailable."
    if "quota" in lower:
        return "Futu quote quota unavailable."
    return clean[:160]


def _assert_futu_opend_available(host: str, port: int) -> None:
    try:
        with socket.create_connection((host, int(port)), timeout=0.45):
            return
    except OSError as exc:
        raise RuntimeError("Futu OpenD connection unavailable.") from exc


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
        source_rows = conn.execute(
            """
            select run_id,
                   source_key,
                   count(*) as observation_count,
                   count(distinct ticker) as ticker_count,
                   max(fetched_at) as latest_at
            from raw_observations
            where run_id = any(%s::bigint[])
            group by run_id, source_key
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

    for row in source_rows:
        run_id = int(row["run_id"])
        bucket = counts.setdefault(run_id, {})
        sources = bucket.setdefault("sources", {})
        sources[row["source_key"]] = {
            "observation_count": int(row["observation_count"] or 0),
            "ticker_count": int(row["ticker_count"] or 0),
            "latest_at": row["latest_at"],
        }
        _max_time(bucket, row["latest_at"])

    return counts


def _enrich_run(row: dict[str, Any], counts: dict[str, Any]) -> dict[str, Any]:
    tickers = row.get("tickers") or []
    config = row.get("config") or {}
    total = len(tickers)
    expected_units = _expected_run_units(config)
    expected_sources = _expected_run_sources(config)
    dimensions = counts.get("dimensions") or {}
    collected_sources = counts.get("sources") or {}
    source_progress = []
    for source in expected_sources:
        data = collected_sources.get(source["source_key"]) or {}
        source_progress.append(
            {
                **source,
                "ticker_count": int(data.get("ticker_count") or 0),
                "observation_count": int(data.get("observation_count") or 0),
                "total": total,
            }
        )
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
        "sources": source_progress,
        "dimensions": dimension_progress,
    }


def _expected_run_sources(config: dict[str, Any]) -> list[dict[str, Any]]:
    sources = []
    for source in DATA_SOURCE_DEFINITIONS:
        if source.status != "active" or not source_is_requested(source, config):
            continue
        sources.append(
            {
                "source_key": source.source_key,
                "source_name": source.source_name,
                "collection_scope": source.collection_scope,
            }
        )
    return sources


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


def _trend_has_points(trend: dict[str, Any]) -> bool:
    points = trend.get("points") if isinstance(trend, dict) else []
    return isinstance(points, list) and len(points) >= 2


def _opening_trend_index_config(index_key: str) -> dict[str, str]:
    configs = {
        "nasdaq": {
            "key": "nasdaq",
            "symbol": "^IXIC",
            "nasdaq_symbol": "COMP",
            "label": "Nasdaq Composite",
            "short_label": "Nasdaq",
        },
        "sox": {
            "key": "sox",
            "symbol": "^SOX",
            "nasdaq_symbol": "SOX",
            "label": "PHLX Semiconductor",
            "short_label": "SOX",
        },
        "semiconductor": {
            "key": "sox",
            "symbol": "^SOX",
            "nasdaq_symbol": "SOX",
            "label": "PHLX Semiconductor",
            "short_label": "SOX",
        },
    }
    return configs.get(index_key, configs["nasdaq"])


def _opening_trend_fallback(config: dict[str, str], *, max_points: int, base_error: str = "") -> dict[str, Any]:
    try:
        fallback = fetch_nasdaq_price_trend(
            config.get("nasdaq_symbol") or config["symbol"],
            max_points=max_points,
            from_date="1970-01-01",
            asset_class="index",
        )
    except Exception as exc:
        return {
            "ticker": config["symbol"],
            "source": "nasdaq",
            "source_label": "Nasdaq daily close",
            "period": "max",
            "points": [],
            "error": "; ".join(part for part in [base_error, _short_trend_error(str(exc))] if part),
        }
    fallback["source_label"] = "Nasdaq index daily close"
    if base_error:
        fallback["fallback_from"] = "yfinance"
        fallback["fallback_error"] = base_error
    return fallback


def _opening_long_term_trend_data(config: dict[str, str], transform: str, *, max_points: int) -> dict[str, Any]:
    try:
        trend = fetch_price_trend(config["symbol"], period="max", max_points=max_points)
    except Exception as exc:
        trend = _opening_trend_fallback(config, max_points=max_points, base_error=_short_trend_error(str(exc)))
    if not _trend_has_points(trend):
        trend = _opening_trend_fallback(config, max_points=max_points, base_error=_short_trend_error(str(trend.get("error") or "")))
    return _opening_long_term_trend_payload(config, trend, transform)


def _opening_trend_transform_meta(transform: str) -> dict[str, str]:
    metas = {
        "raw": {
            "key": "raw",
            "label": "Raw Index",
            "unit": "points",
            "explanation_zh": "原始指数点位保留真实价格水平，但长期复利会让曲线越来越陡。",
        },
        "log": {
            "key": "log",
            "label": "Log Index",
            "unit": "ln(points)",
            "explanation_zh": "对指数取自然对数后，稳定复利增长会接近直线，更适合观察长期趋势斜率是否变化。",
        },
        "detrended": {
            "key": "detrended",
            "label": "Trend Gap",
            "unit": "percent",
            "explanation_zh": "先对 ln(index) 做线性回归，再显示 exp(残差)-1。高于 0 表示指数高于长期复利趋势线，低于 0 表示低于趋势线。",
        },
    }
    return metas.get(transform, metas["raw"])


def _opening_long_term_trend_payload(config: dict[str, str], trend: dict[str, Any], transform: str) -> dict[str, Any]:
    raw_points = []
    for point in trend.get("points") or []:
        close = _safe_float(point.get("close"))
        if close is None or close <= 0:
            continue
        raw_points.append({"date": point.get("date"), "close": close})
    transformed, regression = _opening_trend_transform_points(raw_points, transform)
    first = raw_points[0] if raw_points else None
    latest = raw_points[-1] if raw_points else None
    total_return = None
    cagr = None
    if first and latest and first.get("close") not in (None, 0):
        total_return = (latest["close"] - first["close"]) / abs(first["close"])
        years = _date_span_years(first.get("date"), latest.get("date"))
        if years and years > 0:
            cagr = (latest["close"] / first["close"]) ** (1 / years) - 1
    payload = {
        **config,
        "source": trend.get("source") or "yfinance",
        "source_label": trend.get("source_label") or "Yahoo/yFinance daily close",
        "period": trend.get("period") or "max",
        "transform": _opening_trend_transform_meta(transform),
        "points": transformed,
        "point_count": len(transformed),
        "first_date": first.get("date") if first else None,
        "latest_date": latest.get("date") if latest else None,
        "first_close": first.get("close") if first else None,
        "latest_close": latest.get("close") if latest else None,
        "total_return": total_return,
        "cagr": cagr,
        "regression": regression,
    }
    if trend.get("error"):
        payload["error"] = trend.get("error")
    if len(transformed) < 2:
        payload["error"] = payload.get("error") or "Not enough long term history."
    return payload


def _opening_trend_analysis_prompt(trend: dict[str, Any]) -> str:
    points = trend.get("points") or []
    compact_points = [
        {
            "date": point.get("date"),
            "close": _round_number(point.get("close"), 2),
            "value": _round_number(point.get("value"), 6),
            "trend_gap_pct": _round_number((point.get("value") or 0) * 100, 2)
            if (trend.get("transform") or {}).get("key") == "detrended"
            else None,
        }
        for point in points
    ]
    latest = points[-1] if points else {}
    payload = {
        "index": {
            "symbol": trend.get("symbol"),
            "label": trend.get("label"),
            "source": trend.get("source_label") or trend.get("source"),
        },
        "view": trend.get("transform"),
        "range": {
            "first_date": trend.get("first_date"),
            "latest_date": trend.get("latest_date"),
            "point_count": trend.get("point_count"),
        },
        "current": {
            "date": latest.get("date"),
            "close": _round_number(latest.get("close"), 2),
            "value": _round_number(latest.get("value"), 6),
            "trend_gap_pct": _round_number((latest.get("value") or 0) * 100, 2)
            if (trend.get("transform") or {}).get("key") == "detrended"
            else None,
        },
        "stats": {
            "total_return": trend.get("total_return"),
            "cagr": trend.get("cagr"),
            "regression": trend.get("regression"),
        },
        "points": compact_points,
    }
    return (
        "请分析当前指数长期趋势图的风险和机会。重点判断当前点位相对长期趋势的位置、"
        "潜在均值回归风险、顺势机会、需要观察的价格/趋势信号。不要使用输入外的新闻或宏观事实。\n\n"
        "只输出 JSON，字段如下：\n"
        "{\n"
        '  "current_read": "中文，2-4句，说明当前状态和含义",\n'
        '  "risks": ["中文，每条可执行/可观察"],\n'
        '  "opportunities": ["中文，每条可执行/可观察"],\n'
        '  "watch_levels": ["中文，结合当前点位或趋势gap给观察位"],\n'
        '  "action_notes": ["中文，仓位/节奏建议，不要给保证性结论"],\n'
        '  "confidence_score": 0-100\n'
        "}\n\n"
        f"输入数据：\n{json.dumps(_clean_json(payload), ensure_ascii=False, separators=(',', ':'))}"
    )


def _round_number(value: Any, digits: int) -> float | None:
    number = _safe_float(value)
    if number is None:
        return None
    return round(number, digits)


def _opening_trend_transform_points(points: list[dict[str, Any]], transform: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta = _opening_trend_transform_meta(transform)
    log_values = [math.log(float(point["close"])) for point in points if _safe_float(point.get("close"))]
    regression = _linear_regression(log_values)
    result = []
    for index, point in enumerate(points):
        close = float(point["close"])
        log_close = math.log(close)
        trend_log = regression["intercept"] + regression["slope"] * index if regression else log_close
        if meta["key"] == "log":
            value = log_close
        elif meta["key"] == "detrended":
            value = math.exp(log_close - trend_log) - 1
        else:
            value = close
        result.append(
            {
                "date": point.get("date"),
                "close": close,
                "value": value,
                "log_close": log_close,
                "trend_log": trend_log,
            }
        )
    return result, regression


def _linear_regression(values: list[float]) -> dict[str, float]:
    if not values:
        return {"slope": 0.0, "intercept": 0.0, "r2": 0.0}
    if len(values) == 1:
        return {"slope": 0.0, "intercept": values[0], "r2": 1.0}
    n = len(values)
    mean_x = (n - 1) / 2
    mean_y = sum(values) / n
    numerator = sum((index - mean_x) * (value - mean_y) for index, value in enumerate(values))
    denominator = sum((index - mean_x) ** 2 for index in range(n))
    slope = numerator / denominator if denominator else 0.0
    intercept = mean_y - slope * mean_x
    total = sum((value - mean_y) ** 2 for value in values)
    residual = sum((value - (intercept + slope * index)) ** 2 for index, value in enumerate(values))
    r2 = 1 - residual / total if total else 1.0
    return {"slope": slope, "intercept": intercept, "r2": r2}


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip().replace(",", "").replace("$", "").replace("%", "")
        if not value or value.lower() in {"nan", "none", "n/a", "--"}:
            return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _date_span_years(start: Any, end: Any) -> float | None:
    try:
        start_date = datetime.fromisoformat(str(start)).date()
        end_date = datetime.fromisoformat(str(end)).date()
    except Exception:
        return None
    days = (end_date - start_date).days
    return days / 365.25 if days > 0 else None


def _fallback_price_trend(
    ticker: str,
    *,
    max_points: int,
    base_trend: dict[str, Any],
    base_error: str = "",
) -> dict[str, Any]:
    errors = []
    if base_error:
        errors.append(f"Futu: {base_error}")
    for label, fetcher in (
        ("yFinance", lambda: fetch_price_trend(ticker, period="max", max_points=max_points)),
        ("Nasdaq", lambda: fetch_nasdaq_price_trend(ticker, max_points=max_points)),
    ):
        try:
            fallback = fetcher()
        except Exception as exc:
            errors.append(f"{label}: {_short_trend_error(str(exc))}")
            continue
        if label == "yFinance":
            fallback["source_label"] = "Yahoo/yFinance daily close"
        if base_error:
            fallback["fallback_from"] = "futu_opend"
            fallback["fallback_error"] = base_error
        if _trend_has_points(fallback):
            return fallback
        if fallback.get("error"):
            errors.append(f"{label}: {_short_trend_error(str(fallback['error']))}")
    if errors:
        base_trend["error"] = "; ".join(errors)
    return base_trend


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
        "purpose_en": metadata.get("purpose_en") or "",
        "purpose_zh": metadata.get("purpose_zh") or "",
        "rate_limit_summary": metadata.get("rate_limit_summary")
        or rate_limit_policy.get("observed_limit")
        or "",
        "rate_limit_summary_zh": metadata.get("rate_limit_summary_zh") or "",
        "cache_policy": metadata.get("cache_policy") or "",
        "cache_policy_zh": metadata.get("cache_policy_zh") or "",
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


def _llm_error_detail(response, provider_label: str) -> str:
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
        return f"{provider_label} summary failed ({response.status_code}): {message}"
    return f"{provider_label} summary failed ({response.status_code})."


def _llm_provider_label(settings: AppSettings) -> str:
    provider = (settings.llm_provider or "minimax").strip().lower()
    if provider == "gemini":
        return "Gemini"
    return "MiniMax"


def _llm_source_key(provider: str) -> str:
    if (provider or "").strip().lower() == "gemini":
        return "gemini"
    return "minimax"


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _snapshot_report_date(snapshot: dict[str, Any]) -> date:
    return date.today()


def _opening_radar_payload(report: dict[str, Any], store: PostgresStore) -> dict[str, Any]:
    snapshot = report.get("snapshot") or {}
    advice = report.get("advice") or {}
    return {
        **snapshot,
        "report": {
            "id": report.get("id"),
            "report_date": report.get("report_date"),
            "session_label": report.get("session_label"),
            "created_at": report.get("created_at"),
            "updated_at": report.get("updated_at"),
            "provider": report.get("provider"),
            "has_advice": bool(advice),
        },
        "advice": advice or None,
        "advice_provider": report.get("provider") or "",
        "history": store.opening_radar_reports(limit=14),
    }


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
