from __future__ import annotations

import copy
import json
import math
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .futu_provider import FutuProvider
from .intraday import normalize_intraday_rows
from .settings import AppSettings, PROJECT_ROOT


DEFAULT_STORAGE_PATH = PROJECT_ROOT / "outputs" / "trading_simulator.json"
MAX_POINTS = 420
MAX_EVENTS = 220
MAX_TRADES = 220
MAX_BACKTEST_RANGE_DAYS = 62
EXECUTION_MODEL = "long_bear_rotation_v3_opend_rsi1"
DEFAULT_PROFIT_TAKE_PCT = 0.04


def trading_pair_presets() -> list[dict[str, Any]]:
    return [
        {
            "id": "qqq_3x",
            "label": "QQQ 3x Pair",
            "signal_ticker": "QQQ",
            "long_ticker": "TQQQ",
            "short_ticker": "SQQQ",
            "note": "Use QQQ as the RSI signal, trade the 3x long/inverse pair.",
        },
        {
            "id": "qqq_2x",
            "label": "QQQ 2x Pair",
            "signal_ticker": "QQQ",
            "long_ticker": "QLD",
            "short_ticker": "QID",
            "note": "Use QQQ as the RSI signal, trade the 2x long/inverse pair.",
        },
        {
            "id": "rklb_2x",
            "label": "RKLB 2x Pair",
            "signal_ticker": "RKLB",
            "long_ticker": "RKLX",
            "short_ticker": "RKLZ",
            "note": "Use RKLB as the RSI signal, trade the 2x long/inverse pair.",
        },
    ]


def pair_by_id(pair_id: str) -> dict[str, Any] | None:
    for pair in trading_pair_presets():
        if pair["id"] == pair_id:
            return pair
    return None


def trading_strategy_definitions() -> list[dict[str, Any]]:
    return [
        {
            "id": "rsi_extreme",
            "label": "RSI Extreme",
            "description": "Rotate at RSI extremes and take profit when the configured return is reached.",
            "research_status": "baseline",
            "option_summary": "Long RSI<=20 · Bear RSI>=80 · take profit",
            "buy_conditions": [
                "Buy long ticker at ask when RSI1(6) <= 20.",
                "Buy bear ticker at ask when RSI1(6) >= 80.",
            ],
            "sell_conditions": [
                "Rotate long to bear when RSI1(6) >= 80.",
                "Rotate bear to long when RSI1(6) <= 20.",
                "Close a profitable long when return reaches the configured take-profit threshold.",
            ],
            "risk_conditions": [
                "No decision until a causal RSI value is available.",
                "Execution uses estimated or actual ask for entry and bid for exit.",
            ],
            "params": {
                "buy_threshold": 20,
                "sell_threshold": 80,
                "profit_take_enabled": True,
                "profit_take_pct": DEFAULT_PROFIT_TAKE_PCT,
                "profit_take_bars": 0,
                "rsi_period": 6,
                "rsi_interval": "3m",
                "backtest_rsi_interval": "3m",
                "rsi_profile": "futu_chart_rsi1",
                "rsi_source": "opend_stock_screen",
            },
        },
        {
            "id": "rsi_rotation",
            "label": "RSI Rotation",
            "description": "Rotate only when RSI crosses the oversold or overbought thresholds; no standalone take profit.",
            "research_status": "baseline",
            "option_summary": "Long RSI<=20 · Bear RSI>=80 · threshold rotation",
            "buy_conditions": [
                "Buy long ticker at ask when RSI1(6) <= 20.",
                "Buy bear ticker at ask when RSI1(6) >= 80.",
            ],
            "sell_conditions": [
                "Rotate long to bear when RSI1(6) >= 80.",
                "Rotate bear to long when RSI1(6) <= 20.",
                "No independent take-profit exit.",
            ],
            "risk_conditions": [
                "No decision until a causal RSI value is available.",
                "Can hold through a profitable move until the opposite RSI threshold appears.",
            ],
            "params": {
                "buy_threshold": 20,
                "sell_threshold": 80,
                "profit_take_enabled": False,
                "profit_take_pct": DEFAULT_PROFIT_TAKE_PCT,
                "profit_take_bars": 0,
                "rsi_period": 6,
                "rsi_interval": "3m",
                "backtest_rsi_interval": "3m",
                "rsi_profile": "futu_chart_rsi1",
                "rsi_source": "opend_stock_screen",
            },
        },
    ]


def strategy_by_id(strategy_id: str) -> dict[str, Any] | None:
    for strategy in trading_strategy_definitions():
        if strategy["id"] == strategy_id:
            return strategy
    return None


class TradingAutomationManager:
    def __init__(
        self,
        *,
        settings: AppSettings,
        storage_path: Path | None = None,
        data_provider: Any | None = None,
        db_store: Any | None = None,
    ):
        self.settings = settings
        self.storage_path = Path(storage_path or DEFAULT_STORAGE_PATH)
        self.data_provider = data_provider or TradingMarketDataProvider(settings=settings)
        self.db_store = db_store
        self.storage_error: str | None = None
        self.lock = threading.RLock()
        self.instances: dict[str, dict[str, Any]] = {}
        self.threads: dict[str, threading.Thread] = {}
        self.stop_events: dict[str, threading.Event] = {}
        self._load()

    def strategies(self) -> list[dict[str, Any]]:
        return trading_strategy_definitions()

    def pairs(self) -> list[dict[str, Any]]:
        return trading_pair_presets()

    def list_instances(self) -> dict[str, Any]:
        with self.lock:
            instances = [self._summary(instance) for instance in self.instances.values()]
        instances.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return {"instances": instances, "strategies": self.strategies(), "pairs": self.pairs()}

    def get_instance(self, instance_id: str) -> dict[str, Any] | None:
        with self.lock:
            instance = self.instances.get(instance_id)
            return self._payload(instance) if instance else None

    def backtest_instance(self, instance_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        start = _parse_backtest_time(payload.get("start"))
        end = _parse_backtest_time(payload.get("end"))
        if start is None or end is None:
            raise ValueError("Backtest start and end are required.")
        if end <= start:
            raise ValueError("Backtest end must be after start.")
        if end - start > timedelta(days=MAX_BACKTEST_RANGE_DAYS):
            raise ValueError(f"Backtest range is limited to {MAX_BACKTEST_RANGE_DAYS} days.")
        if start.date() != end.date() and end.time() <= start.time():
            raise ValueError("For multi-day backtests, end time must be after start time.")

        with self.lock:
            source = self.instances.get(instance_id)
            if not source:
                raise KeyError("Trading instance not found.")
            instance = copy.deepcopy(source)

        requested_strategy_id = str(payload.get("strategy_id") or instance.get("strategy_id") or "").strip()
        strategy = strategy_by_id(requested_strategy_id)
        if not strategy:
            raise ValueError("Backtest only supports known strategies.")
        instance["strategy_id"] = requested_strategy_id
        if "profit_take_percent" in payload or "profit_take_pct" in payload:
            instance["profit_take_pct"] = _profit_take_pct_from_payload(payload)
        params = strategy.get("params") or {}
        rsi_period = int(payload.get("rsi_period") or params.get("rsi_period") or 6)
        rsi_interval = str(
            payload.get("rsi_interval")
            or params.get("backtest_rsi_interval")
            or params.get("rsi_interval")
            or "3m"
        )
        history = self.data_provider.backtest_history(
            signal_ticker=instance["signal_ticker"],
            long_ticker=instance["long_ticker"],
            short_ticker=instance["short_ticker"],
            start=start,
            end=end,
            rsi_period=rsi_period,
            rsi_interval=rsi_interval,
        )
        if not history.get("points"):
            raise ValueError("No backtest market data returned for this range.")
        result = self._run_backtest_period(instance, history=history, start=start, end=end)
        performance = _strategy_performance_summary(result)
        result["performance"] = performance
        with self.lock:
            source = self.instances.get(instance_id)
            if source:
                source.setdefault("strategy_performance", {})[requested_strategy_id] = performance
                source["updated_at"] = _now_iso()
                self._save_locked()
        return result

    def create_instance(self, payload: dict[str, Any]) -> dict[str, Any]:
        strategy_id = "rsi_extreme"
        pair_id = str(payload.get("pair_id") or "custom").strip()
        pair = pair_by_id(pair_id)
        long_ticker = _clean_ticker(payload.get("long_ticker") or (pair or {}).get("long_ticker"))
        short_ticker = _clean_ticker(payload.get("short_ticker") or (pair or {}).get("short_ticker"))
        signal_ticker = _clean_ticker(payload.get("signal_ticker") or (pair or {}).get("signal_ticker") or long_ticker)
        if not long_ticker or not short_ticker:
            raise ValueError("Long and short tickers are required.")
        now = _now_iso()
        name = str(payload.get("name") or (pair or {}).get("label") or f"{long_ticker}/{short_ticker}").strip()
        instance = {
            "id": uuid.uuid4().hex[:12],
            "name": name,
            "strategy_id": strategy_id,
            "pair_id": pair_id if pair else "custom",
            "mode": "simulate",
            "long_ticker": long_ticker,
            "short_ticker": short_ticker,
            "signal_ticker": signal_ticker,
            "notional_per_leg": _bounded_float(payload.get("notional_per_leg"), 1000.0, 100.0, 1_000_000.0),
            "poll_seconds": _bounded_float(payload.get("poll_seconds"), 5.0, 1.0, 300.0),
            "profit_take_pct": _profit_take_pct_from_payload(payload),
            "status": "idle",
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "stopped_at": None,
            "last_error": None,
            "positions": {"long": None, "short": None},
            "metrics": _empty_metrics(),
            "state": {
                "execution_model": EXECUTION_MODEL,
                "sample_index": 0,
                "decision_index": 0,
                "last_decision_key": None,
                "latest_oversold_index": None,
                "latest_oversold_time": None,
                "last_signal": None,
            },
            "latest_market": None,
            "price_points": [],
            "events": [],
            "trades": [],
        }
        self._append_event(instance, "created", "Instance created", severity="info")
        with self.lock:
            self.instances[instance["id"]] = instance
            self._save_locked()
            return self._payload(instance)

    def update_instance_strategy(self, instance_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        strategy_id = str(payload.get("strategy_id") or "").strip()
        strategy = strategy_by_id(strategy_id)
        if strategy is None:
            raise ValueError(f"Unknown strategy: {strategy_id}")
        with self.lock:
            instance = self.instances.get(instance_id)
            if not instance:
                raise KeyError("Trading instance not found.")
            if instance.get("status") == "running":
                raise ValueError("Stop the simulation before changing strategy.")
            positions = instance.get("positions") or {}
            if positions.get("long") or positions.get("short"):
                raise ValueError("Close the open position before changing strategy.")
            previous_strategy_id = str(instance.get("strategy_id") or "")
            previous_profit_take = _instance_profit_take_pct(instance)
            instance["strategy_id"] = strategy_id
            if "profit_take_percent" in payload or "profit_take_pct" in payload:
                instance["profit_take_pct"] = _profit_take_pct_from_payload(payload)
            instance["updated_at"] = _now_iso()
            state = instance.setdefault("state", {})
            state["last_decision_key"] = None
            state["latest_oversold_index"] = None
            state["latest_oversold_time"] = None
            state["last_signal"] = None
            changed = (
                previous_strategy_id != strategy_id
                or previous_profit_take != _instance_profit_take_pct(instance)
            )
            if changed:
                self._append_event(
                    instance,
                    "strategy_changed",
                    f"Research strategy changed to {strategy.get('label') or strategy_id}",
                    severity="info",
                    strategy_id=strategy_id,
                )
            self._save_locked()
            return self._payload(instance)

    def delete_instance(self, instance_id: str) -> dict[str, Any]:
        self.stop_instance(instance_id)
        with self.lock:
            if instance_id not in self.instances:
                raise KeyError("Trading instance not found.")
            removed = self.instances.pop(instance_id)
            if self.db_store is not None:
                try:
                    self.db_store.trading_delete_instance(instance_id)
                except Exception as exc:
                    self.storage_error = _short_error(f"PostgreSQL delete failed: {exc}")
            self._save_locked()
        return {"deleted": True, "id": removed["id"]}

    def start_instance(self, instance_id: str) -> dict[str, Any]:
        with self.lock:
            instance = self.instances.get(instance_id)
            if not instance:
                raise KeyError("Trading instance not found.")
            if instance.get("status") == "running":
                return self._payload(instance)
            instance["status"] = "running"
            instance["started_at"] = instance.get("started_at") or _now_iso()
            instance["stopped_at"] = None
            instance["last_error"] = None
            instance["updated_at"] = _now_iso()
            self._append_event(instance, "started", "Simulation started", severity="info")
            stop_event = threading.Event()
            self.stop_events[instance_id] = stop_event
            thread = threading.Thread(target=self._run_loop, args=(instance_id, stop_event), daemon=True)
            self.threads[instance_id] = thread
            self._save_locked()
            payload = self._payload(instance)
        thread.start()
        return payload

    def stop_instance(self, instance_id: str) -> dict[str, Any]:
        with self.lock:
            stop_event = self.stop_events.get(instance_id)
            if stop_event:
                stop_event.set()
            instance = self.instances.get(instance_id)
            if not instance:
                return {"stopped": False, "id": instance_id}
            if instance.get("status") == "running":
                instance["status"] = "idle"
                instance["stopped_at"] = _now_iso()
                instance["updated_at"] = _now_iso()
                self._append_event(instance, "stopped", "Simulation stopped", severity="info")
            self._save_locked()
            return self._payload(instance)

    def poll_once(self, instance_id: str) -> dict[str, Any]:
        with self.lock:
            instance = self.instances.get(instance_id)
            if not instance:
                raise KeyError("Trading instance not found.")
            signal_ticker = instance["signal_ticker"]
            long_ticker = instance["long_ticker"]
            short_ticker = instance["short_ticker"]
        snapshot = self.data_provider.snapshot(
            signal_ticker=signal_ticker,
            long_ticker=long_ticker,
            short_ticker=short_ticker,
            window=90,
        )
        with self.lock:
            instance = self.instances.get(instance_id)
            if not instance:
                raise KeyError("Trading instance not found.")
            self._apply_snapshot(instance, snapshot)
            instance["last_error"] = snapshot.get("error")
            instance["updated_at"] = _now_iso()
            self._save_locked()
            return self._payload(instance)

    def _run_loop(self, instance_id: str, stop_event: threading.Event) -> None:
        tickers: list[str] = []
        try:
            with self.lock:
                instance = self.instances.get(instance_id)
                if not instance:
                    return
                signal_ticker = instance["signal_ticker"]
                long_ticker = instance["long_ticker"]
                short_ticker = instance["short_ticker"]
                tickers = _unique_tickers([signal_ticker, long_ticker, short_ticker])
            if hasattr(self.data_provider, "subscribe_trading"):
                self.data_provider.subscribe_trading(
                    signal_ticker=signal_ticker,
                    long_ticker=long_ticker,
                    short_ticker=short_ticker,
                )
            elif hasattr(self.data_provider, "subscribe"):
                self.data_provider.subscribe(tickers)
            while not stop_event.is_set():
                try:
                    self.poll_once(instance_id)
                except Exception as exc:
                    with self.lock:
                        instance = self.instances.get(instance_id)
                        if instance:
                            instance["last_error"] = _short_error(str(exc))
                            instance["updated_at"] = _now_iso()
                            self._append_event(instance, "error", instance["last_error"], severity="error")
                            self._save_locked()
                with self.lock:
                    instance = self.instances.get(instance_id)
                    poll_seconds = float(instance.get("poll_seconds") or 5.0) if instance else 5.0
                stop_event.wait(max(1.0, poll_seconds))
        finally:
            if hasattr(self.data_provider, "unsubscribe_trading") and tickers:
                try:
                    self.data_provider.unsubscribe_trading(
                        signal_ticker=signal_ticker,
                        long_ticker=long_ticker,
                        short_ticker=short_ticker,
                    )
                except Exception:
                    pass
            elif hasattr(self.data_provider, "unsubscribe") and tickers:
                try:
                    self.data_provider.unsubscribe(tickers)
                except Exception:
                    pass
            with self.lock:
                self.stop_events.pop(instance_id, None)
                self.threads.pop(instance_id, None)
                instance = self.instances.get(instance_id)
                if instance and instance.get("status") == "running":
                    instance["status"] = "idle"
                    instance["stopped_at"] = _now_iso()
                    instance["updated_at"] = _now_iso()
                    self._save_locked()

    def _apply_snapshot(self, instance: dict[str, Any], snapshot: dict[str, Any]) -> None:
        prices = snapshot.get("prices") or {}
        quotes = snapshot.get("quotes") or {}
        signal = snapshot.get("signal") or {}
        long_quote = quotes.get("long") or {}
        short_quote = quotes.get("short") or {}
        signal_quote = quotes.get("signal") or {}
        long_bid, long_ask, long_quote_source = _point_quote_values(prices.get("long"), long_quote)
        short_bid, short_ask, short_quote_source = _point_quote_values(prices.get("short"), short_quote)
        signal_bid, signal_ask, signal_quote_source = _point_quote_values(prices.get("signal"), signal_quote)
        point = {
            "time": snapshot.get("as_of") or _now_iso(),
            "long_price": _safe_float(prices.get("long")),
            "short_price": _safe_float(prices.get("short")),
            "signal_price": _safe_float(prices.get("signal")),
            "long_bid": long_bid,
            "long_ask": long_ask,
            "short_bid": short_bid,
            "short_ask": short_ask,
            "signal_bid": signal_bid,
            "signal_ask": signal_ask,
            "quote_source": long_quote_source or short_quote_source or signal_quote_source,
            "rsi1": _safe_float(signal.get("rsi1")),
            "rsi": _safe_float(signal.get("rsi")),
            "rsi3": _safe_float(signal.get("rsi3")),
            "rsi_label": signal.get("rsi_label"),
            "rsi_period": signal.get("rsi_period"),
            "rsi_interval": signal.get("rsi_interval"),
            "rsi_source": signal.get("rsi_source"),
            "rsi_error": signal.get("rsi_error"),
            "rsi_unavailable": bool(signal.get("rsi_unavailable")),
            "source": snapshot.get("source"),
        }
        self._apply_market_point(
            instance,
            point,
            source_label=snapshot.get("source_label"),
            error=snapshot.get("error"),
        )

    def _apply_market_point(
        self,
        instance: dict[str, Any],
        point: dict[str, Any],
        *,
        source_label: str | None = None,
        error: str | None = None,
    ) -> None:
        state = instance.setdefault("state", {})
        sample_index = int(state.get("sample_index") or 0) + 1
        state["sample_index"] = sample_index
        point = dict(point)
        point["index"] = sample_index
        point.setdefault("time", _now_iso())
        decision_key = _decision_key(point["time"])
        if decision_key != state.get("last_decision_key"):
            state["last_decision_key"] = decision_key
            state["decision_index"] = int(state.get("decision_index") or 0) + 1
            new_decision_node = True
        else:
            new_decision_node = False
        point["decision_index"] = int(state.get("decision_index") or 0)
        point["decision_key"] = decision_key
        point["new_decision_node"] = new_decision_node
        instance["latest_market"] = {
            **point,
            "source_label": source_label or point.get("source_label"),
            "error": error or point.get("error"),
        }
        instance.setdefault("price_points", []).append(point)
        del instance["price_points"][:-MAX_POINTS]
        warning = error or point.get("error")
        if warning and warning != state.get("last_data_warning"):
            state["last_data_warning"] = warning
            self._append_event(instance, "data_warning", warning, severity="warn", event_time=point.get("time"))
        if instance.get("strategy_id") in {"rsi_extreme", "rsi_rotation"}:
            self._apply_rsi_extreme(instance, point)
        self._mark_to_market(instance, point)

    def _run_backtest(
        self,
        instance: dict[str, Any],
        *,
        history: dict[str, Any],
        start: datetime,
        end: datetime,
    ) -> dict[str, Any]:
        replay = {
            "id": f"backtest-{instance.get('id')}",
            "name": instance.get("name"),
            "strategy_id": instance.get("strategy_id"),
            "pair_id": instance.get("pair_id") or "custom",
            "mode": "backtest",
            "long_ticker": instance.get("long_ticker"),
            "short_ticker": instance.get("short_ticker"),
            "signal_ticker": instance.get("signal_ticker"),
            "notional_per_leg": float(instance.get("notional_per_leg") or 1000.0),
            "profit_take_pct": _instance_profit_take_pct(instance),
            "status": "idle",
            "positions": {"long": None, "short": None},
            "metrics": _empty_metrics(),
            "state": {
                "execution_model": EXECUTION_MODEL,
                "sample_index": 0,
                "decision_index": 0,
                "last_decision_key": None,
                "latest_oversold_index": None,
                "latest_oversold_time": None,
                "last_signal": None,
            },
            "latest_market": None,
            "price_points": [],
            "events": [],
            "trades": [],
        }
        source_label = str(history.get("source_label") or "Backtest history")
        for point in history.get("points") or []:
            self._apply_market_point(replay, point, source_label=source_label)
        operations = [
            event
            for event in replay.get("events", [])
            if event.get("type") in {"signal", "open", "close", "data_warning", "error"}
        ]
        price_points = replay.get("price_points") or []
        metrics = replay.get("metrics") or _empty_metrics()
        detail_result = {
            "instance_id": instance.get("id"),
            "name": instance.get("name"),
            "strategy_id": instance.get("strategy_id"),
            "signal_ticker": instance.get("signal_ticker"),
            "long_ticker": instance.get("long_ticker"),
            "short_ticker": instance.get("short_ticker"),
            "notional_per_leg": replay.get("notional_per_leg"),
            "profit_take_pct": _instance_profit_take_pct(replay),
            "start": start.isoformat(timespec="minutes"),
            "end": end.isoformat(timespec="minutes"),
            "source": history.get("source") or "backtest",
            "source_label": source_label,
            "point_count": len(history.get("points") or []),
            "rsi_ready_count": sum(1 for point in history.get("points") or [] if _signal_rsi(point) is not None),
            "metrics": metrics,
            "final_pnl": metrics.get("total_pnl", 0.0),
            "positions": replay.get("positions") or {"long": None, "short": None},
            "latest_market": _market_point_payload(replay.get("latest_market")),
            "operations": operations,
            "trades": replay.get("trades") or [],
            "price_points": price_points,
            "markers": _backtest_markers(operations, price_points),
        }
        return detail_result

    def _run_backtest_period(
        self,
        instance: dict[str, Any],
        *,
        history: dict[str, Any],
        start: datetime,
        end: datetime,
    ) -> dict[str, Any]:
        points_by_date: dict[str, list[dict[str, Any]]] = {}
        for point in history.get("points") or []:
            point_time = _parse_backtest_time(point.get("time"))
            if point_time is None:
                continue
            points_by_date.setdefault(point_time.date().isoformat(), []).append(point)
        if not points_by_date:
            raise ValueError("No dated backtest market data returned for this range.")

        daily_results: list[dict[str, Any]] = []
        for day_key in sorted(points_by_date):
            day = datetime.fromisoformat(day_key)
            day_start = datetime.combine(day.date(), start.time())
            day_end = datetime.combine(day.date(), end.time())
            day_history = {
                **history,
                "points": sorted(
                    points_by_date[day_key],
                    key=lambda point: str(point.get("time") or ""),
                ),
            }
            daily = self._run_backtest(
                instance,
                history=day_history,
                start=day_start,
                end=day_end,
            )
            final_pnl = float(daily.get("final_pnl") or 0.0)
            daily["date"] = day_key
            daily["outcome"] = _daily_outcome(final_pnl)
            notional = float(daily.get("notional_per_leg") or 0.0)
            daily["return_pct"] = final_pnl / notional if notional else 0.0
            daily_results.append(daily)

        winning_days = sum(1 for item in daily_results if item["outcome"] == "win")
        losing_days = sum(1 for item in daily_results if item["outcome"] == "loss")
        flat_days = sum(1 for item in daily_results if item["outcome"] == "flat")
        decided_days = winning_days + losing_days
        total_pnl = sum(float(item.get("final_pnl") or 0.0) for item in daily_results)
        total_realized = sum(
            float((item.get("metrics") or {}).get("realized_pnl") or 0.0)
            for item in daily_results
        )
        total_unrealized = sum(
            float((item.get("metrics") or {}).get("unrealized_pnl") or 0.0)
            for item in daily_results
        )
        open_notional = sum(
            float((item.get("metrics") or {}).get("open_notional") or 0.0)
            for item in daily_results
        )
        trade_count = sum(
            int((item.get("metrics") or {}).get("trade_count") or 0)
            for item in daily_results
        )
        winning_trades = sum(
            int((item.get("metrics") or {}).get("winning_trades") or 0)
            for item in daily_results
        )
        expected_dates = _weekday_dates(start, end)
        data_dates = {item["date"] for item in daily_results}
        no_data_dates = [day for day in expected_dates if day not in data_dates]
        best_day = max(daily_results, key=lambda item: float(item.get("final_pnl") or 0.0))
        worst_day = min(daily_results, key=lambda item: float(item.get("final_pnl") or 0.0))
        period_metrics = {
            "day_count": len(daily_results),
            "winning_days": winning_days,
            "losing_days": losing_days,
            "flat_days": flat_days,
            "win_rate": winning_days / decided_days if decided_days else 0.0,
            "total_pnl": total_pnl,
            "average_daily_pnl": total_pnl / len(daily_results),
            "best_day": {"date": best_day["date"], "pnl": best_day["final_pnl"]},
            "worst_day": {"date": worst_day["date"], "pnl": worst_day["final_pnl"]},
            "no_data_day_count": len(no_data_dates),
        }
        aggregate_metrics = {
            "realized_pnl": total_realized,
            "unrealized_pnl": total_unrealized,
            "total_pnl": total_pnl,
            "open_notional": open_notional,
            "open_return_pct": total_unrealized / open_notional if open_notional else 0.0,
            "trade_count": trade_count,
            "winning_trades": winning_trades,
            "win_rate": winning_trades / trade_count if trade_count else 0.0,
        }
        period_result = {
            "instance_id": instance.get("id"),
            "name": instance.get("name"),
            "strategy_id": instance.get("strategy_id"),
            "signal_ticker": instance.get("signal_ticker"),
            "long_ticker": instance.get("long_ticker"),
            "short_ticker": instance.get("short_ticker"),
            "notional_per_leg": float(instance.get("notional_per_leg") or 1000.0),
            "profit_take_pct": _instance_profit_take_pct(instance),
            "start": start.isoformat(timespec="minutes"),
            "end": end.isoformat(timespec="minutes"),
            "source": history.get("source") or "backtest",
            "source_label": str(history.get("source_label") or "Backtest history"),
            "point_count": sum(int(item.get("point_count") or 0) for item in daily_results),
            "rsi_ready_count": sum(int(item.get("rsi_ready_count") or 0) for item in daily_results),
            "metrics": aggregate_metrics,
            "period_metrics": period_metrics,
            "final_pnl": total_pnl,
            "daily_results": daily_results,
            "no_data_dates": no_data_dates,
        }
        if len(daily_results) == 1:
            return {**daily_results[0], **period_result}
        return period_result

    def _apply_rsi_extreme(self, instance: dict[str, Any], point: dict[str, Any]) -> None:
        strategy = strategy_by_id(str(instance.get("strategy_id") or "rsi_extreme")) or {}
        params = strategy.get("params") or {}
        rsi = _signal_rsi(point)
        rsi_label = str(point.get("rsi_label") or "RSI").strip() or "RSI"
        if rsi is None:
            return
        buy_threshold = float(params.get("buy_threshold", 20))
        sell_threshold = float(params.get("sell_threshold", 80))
        profit_take_enabled = bool(params.get("profit_take_enabled", True))
        profit_take_pct = _instance_profit_take_pct(instance, params)
        decision_index = int(point.get("decision_index") or point["index"])
        state = instance.setdefault("state", {})
        positions = instance.setdefault("positions", {"long": None, "short": None})

        if profit_take_enabled and positions.get("long"):
            self._mark_to_market(instance, point)
            long_return = _safe_float((positions.get("long") or {}).get("return_pct"))
            if long_return is not None and long_return >= profit_take_pct:
                long_sell_price = _execution_price(point, "long", "sell")
                if long_sell_price is not None:
                    self._close_position(
                        instance,
                        "long",
                        price=long_sell_price,
                        at=point.get("time"),
                        reason="rsi_extreme_profit_take",
                        quote_side="bid",
                    )
                    state["latest_oversold_index"] = None
                    state["latest_oversold_time"] = None
                    state["last_signal"] = "profit_take"
                    self._append_event(
                        instance,
                        "signal",
                        f"Profit take {long_return * 100:.2f}% >= {profit_take_pct * 100:.2f}%",
                        severity="success",
                        event_time=point.get("time"),
                    )
                return

        if rsi <= buy_threshold:
            if (
                point.get("new_decision_node")
                or state.get("latest_oversold_index") is None
                or not instance.get("positions", {}).get("long")
            ):
                state["latest_oversold_index"] = decision_index
                state["latest_oversold_time"] = point.get("time")
            acted = False
            if positions.get("short"):
                bear_sell_price = _execution_price(point, "short", "sell")
                if bear_sell_price is not None:
                    self._close_position(
                        instance,
                        "short",
                        price=bear_sell_price,
                        at=point.get("time"),
                        reason="rsi_extreme_oversold",
                        quote_side="bid",
                    )
                    acted = True
            if not positions.get("long"):
                long_buy_price = _execution_price(point, "long", "buy")
                if long_buy_price is None:
                    return
                self._open_position(
                    instance,
                    "long",
                    price=long_buy_price,
                    at=point.get("time"),
                    reason="rsi_extreme_oversold",
                    quote_side="ask",
                )
                acted = True
            state["last_signal"] = "oversold"
            if acted:
                    self._append_event(
                        instance,
                        "signal",
                        f"{rsi_label} {rsi:.2f} <= {buy_threshold:.0f}: rotated to long",
                        severity="info",
                        event_time=point.get("time"),
                    )
            return

        if rsi >= sell_threshold:
            acted = False
            if positions.get("long"):
                long_sell_price = _execution_price(point, "long", "sell")
                if long_sell_price is not None:
                    self._close_position(
                        instance,
                        "long",
                        price=long_sell_price,
                        at=point.get("time"),
                        reason="rsi_extreme_overbought",
                        quote_side="bid",
                    )
                    acted = True
            if not positions.get("short"):
                bear_buy_price = _execution_price(point, "short", "buy")
                if bear_buy_price is None:
                    return
                self._open_position(
                    instance,
                    "short",
                    price=bear_buy_price,
                    at=point.get("time"),
                    reason="rsi_extreme_overbought",
                    quote_side="ask",
                )
                acted = True
            state["latest_oversold_index"] = None
            state["latest_oversold_time"] = None
            state["last_signal"] = "overbought"
            if acted:
                    self._append_event(
                        instance,
                        "signal",
                        f"{rsi_label} {rsi:.2f} >= {sell_threshold:.0f}: rotated to bear",
                        severity="info",
                        event_time=point.get("time"),
                    )
            return

    def _open_position(
        self,
        instance: dict[str, Any],
        leg: str,
        *,
        price: float,
        at: Any,
        reason: str,
        quote_side: str,
    ) -> None:
        positions = instance.setdefault("positions", {"long": None, "short": None})
        if positions.get(leg):
            return
        notional = float(instance.get("notional_per_leg") or 1000.0)
        qty = notional / price if price > 0 else 0.0
        ticker = instance["long_ticker"] if leg == "long" else instance["short_ticker"]
        position = {
            "leg": leg,
            "ticker": ticker,
            "side": "long",
            "direction": "bull" if leg == "long" else "bear",
            "entry_price": price,
            "qty": qty,
            "entry_notional": notional,
            "entry_time": at,
            "entry_reason": reason,
            "entry_quote_side": quote_side,
            "entry_sample_index": instance.get("state", {}).get("sample_index"),
            "entry_decision_index": instance.get("state", {}).get("decision_index"),
        }
        positions[leg] = position
        action = "BUY"
        self._append_event(
            instance,
            "open",
            f"{action} {ticker} @ {quote_side.upper()} {_price_text(price)}",
            leg=leg,
            ticker=ticker,
            price=price,
            quote_side=quote_side,
            qty=qty,
            reason=reason,
            severity="success",
            event_time=at,
        )

    def _close_open_positions(
        self,
        instance: dict[str, Any],
        *,
        point: dict[str, Any],
        at: Any,
        reason: str,
    ) -> bool:
        closed = False
        if instance.get("positions", {}).get("long"):
            price = _execution_price(point, "long", "sell")
            if price is not None:
                self._close_position(instance, "long", price=price, at=at, reason=reason, quote_side="bid")
                closed = True
        if instance.get("positions", {}).get("short"):
            price = _execution_price(point, "short", "sell")
            if price is not None:
                self._close_position(instance, "short", price=price, at=at, reason=reason, quote_side="bid")
                closed = True
        return closed

    def _close_position(
        self,
        instance: dict[str, Any],
        leg: str,
        *,
        price: float,
        at: Any,
        reason: str,
        quote_side: str,
    ) -> None:
        positions = instance.setdefault("positions", {"long": None, "short": None})
        position = positions.get(leg)
        if not position:
            return
        entry_price = float(position.get("entry_price") or 0.0)
        qty = float(position.get("qty") or 0.0)
        entry_notional = float(position.get("entry_notional") or 0.0)
        pnl = (price - entry_price) * qty
        return_pct = pnl / entry_notional if entry_notional else 0.0
        trade = {
            "id": uuid.uuid4().hex[:10],
            "leg": leg,
            "ticker": position.get("ticker"),
            "side": position.get("side"),
            "entry_time": position.get("entry_time"),
            "exit_time": at,
            "entry_price": entry_price,
            "exit_price": price,
            "qty": qty,
            "entry_notional": entry_notional,
            "pnl": pnl,
            "return_pct": return_pct,
            "reason": reason,
            "entry_quote_side": position.get("entry_quote_side"),
            "exit_quote_side": quote_side,
        }
        instance.setdefault("trades", []).append(trade)
        del instance["trades"][:-MAX_TRADES]
        metrics = instance.setdefault("metrics", _empty_metrics())
        metrics["realized_pnl"] = float(metrics.get("realized_pnl") or 0.0) + pnl
        metrics["trade_count"] = int(metrics.get("trade_count") or 0) + 1
        metrics["winning_trades"] = int(metrics.get("winning_trades") or 0) + (1 if pnl > 0 else 0)
        positions[leg] = None
        action = "SELL"
        self._append_event(
            instance,
            "close",
            f"{action} {trade['ticker']} @ {quote_side.upper()} {_price_text(price)} | PnL {_money_text(pnl)}",
            leg=leg,
            ticker=trade["ticker"],
            price=price,
            quote_side=quote_side,
            qty=qty,
            pnl=pnl,
            return_pct=return_pct,
            reason=reason,
            severity="success" if pnl >= 0 else "warn",
            event_time=at,
        )

    def _mark_to_market(self, instance: dict[str, Any], point: dict[str, Any]) -> None:
        positions = instance.setdefault("positions", {"long": None, "short": None})
        prices = {
            "long": _execution_price(point, "long", "sell"),
            "short": _execution_price(point, "short", "sell"),
        }
        unrealized = 0.0
        open_notional = 0.0
        for leg, position in positions.items():
            if not position:
                continue
            price = prices.get(leg)
            if price is None:
                continue
            entry_price = float(position.get("entry_price") or 0.0)
            qty = float(position.get("qty") or 0.0)
            entry_notional = float(position.get("entry_notional") or 0.0)
            pnl = (price - entry_price) * qty
            position["mark_price"] = price
            position["unrealized_pnl"] = pnl
            position["return_pct"] = pnl / entry_notional if entry_notional else 0.0
            unrealized += pnl
            open_notional += entry_notional
        metrics = instance.setdefault("metrics", _empty_metrics())
        metrics["unrealized_pnl"] = unrealized
        metrics["open_notional"] = open_notional
        metrics["open_return_pct"] = unrealized / open_notional if open_notional else 0.0
        metrics["total_pnl"] = float(metrics.get("realized_pnl") or 0.0) + unrealized
        trades = instance.get("trades") or []
        metrics["win_rate"] = (int(metrics.get("winning_trades") or 0) / len(trades)) if trades else 0.0

    def _append_event(
        self,
        instance: dict[str, Any],
        event_type: str,
        message: str,
        *,
        severity: str = "info",
        **extra: Any,
    ) -> None:
        event = {
            "id": uuid.uuid4().hex[:10],
            "time": str(extra.pop("event_time", None) or _now_iso()),
            "type": event_type,
            "severity": severity,
            "message": message,
            **extra,
        }
        instance.setdefault("events", []).append(event)
        del instance["events"][:-MAX_EVENTS]

    def _summary(self, instance: dict[str, Any]) -> dict[str, Any]:
        metrics = instance.get("metrics") or {}
        latest = instance.get("latest_market") or {}
        return {
            "id": instance.get("id"),
            "name": instance.get("name"),
            "mode": instance.get("mode") or "simulate",
            "strategy_id": instance.get("strategy_id"),
            "pair_id": instance.get("pair_id") or "custom",
            "status": instance.get("status") or "idle",
            "long_ticker": instance.get("long_ticker"),
            "short_ticker": instance.get("short_ticker"),
            "signal_ticker": instance.get("signal_ticker"),
            "total_pnl": metrics.get("total_pnl", 0.0),
            "realized_pnl": metrics.get("realized_pnl", 0.0),
            "unrealized_pnl": metrics.get("unrealized_pnl", 0.0),
            "trade_count": metrics.get("trade_count", 0),
            "latest_rsi": latest.get("rsi"),
            "latest_rsi3": latest.get("rsi3"),
            "latest_time": latest.get("time"),
            "profit_take_pct": _instance_profit_take_pct(instance),
            "created_at": instance.get("created_at"),
            "last_error": instance.get("last_error"),
            "strategy_performance": instance.get("strategy_performance") or {},
        }

    def _payload(self, instance: dict[str, Any]) -> dict[str, Any]:
        payload = {
            **self._summary(instance),
            "notional_per_leg": instance.get("notional_per_leg"),
            "profit_take_pct": _instance_profit_take_pct(instance),
            "poll_seconds": instance.get("poll_seconds"),
            "started_at": instance.get("started_at"),
            "stopped_at": instance.get("stopped_at"),
            "updated_at": instance.get("updated_at"),
            "strategy": strategy_by_id(str(instance.get("strategy_id") or "")),
            "strategy_performance": instance.get("strategy_performance") or {},
            "pair": pair_by_id(str(instance.get("pair_id") or "")),
            "strategy_state": _strategy_state(instance),
            "positions": instance.get("positions") or {"long": None, "short": None},
            "metrics": instance.get("metrics") or _empty_metrics(),
            "latest_market": _market_point_payload(instance.get("latest_market")),
            "price_points": instance.get("price_points") or [],
            "events": instance.get("events") or [],
            "trades": instance.get("trades") or [],
        }
        return payload

    def _load(self) -> None:
        loaded_from_db = False
        if self.db_store is not None:
            try:
                loaded_from_db = self._load_instance_records(self.db_store.trading_load_instances())
            except Exception as exc:
                self.storage_error = _short_error(f"PostgreSQL load failed: {exc}")
        if loaded_from_db:
            with self.lock:
                self._save_locked()
            return
        if not self.storage_path.exists():
            return
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except Exception:
            return
        instances = data.get("instances") if isinstance(data, dict) else []
        if not isinstance(instances, list):
            return
        loaded_from_json = self._load_instance_records(instances)
        if loaded_from_json and self.db_store is not None:
            with self.lock:
                self._save_locked()

    def _load_instance_records(self, instances: list[dict[str, Any]]) -> bool:
        loaded = False
        with self.lock:
            for raw in instances:
                if not isinstance(raw, dict) or not raw.get("id"):
                    continue
                raw = dict(raw)
                raw["status"] = "idle"
                raw.setdefault("positions", {"long": None, "short": None})
                raw["positions"].setdefault("long", None)
                raw["positions"].setdefault("short", None)
                for leg in ("long", "short"):
                    position = raw["positions"].get(leg)
                    if isinstance(position, dict):
                        position.setdefault("leg", leg)
                        position.setdefault("direction", "bull" if leg == "long" else "bear")
                        position["side"] = "long"
                raw.setdefault("pair_id", "custom")
                raw.setdefault("profit_take_pct", DEFAULT_PROFIT_TAKE_PCT)
                raw["metrics"] = {**_empty_metrics(), **(raw.get("metrics") or {})}
                raw.setdefault("state", {"sample_index": len(raw.get("price_points") or [])})
                if raw["state"].get("execution_model") != EXECUTION_MODEL:
                    raw.pop("legacy_events", None)
                    raw.pop("legacy_trades", None)
                    raw["positions"] = {"long": None, "short": None}
                    raw["metrics"] = _empty_metrics()
                    raw["events"] = [
                        {
                            "id": uuid.uuid4().hex[:10],
                            "time": _now_iso(),
                            "type": "model_migration",
                            "severity": "warn",
                            "message": "Execution model updated to OpenD RSI1; legacy simulated records cleared.",
                        }
                    ]
                    raw["trades"] = []
                    raw["price_points"] = []
                    raw["latest_market"] = None
                    raw["state"]["latest_oversold_index"] = None
                    raw["state"]["latest_oversold_time"] = None
                    raw["state"]["last_signal"] = None
                raw["state"]["execution_model"] = EXECUTION_MODEL
                raw["state"].setdefault("decision_index", 0)
                raw["state"].setdefault("last_decision_key", None)
                raw.setdefault("price_points", [])
                raw.setdefault("events", [])
                raw.setdefault("trades", [])
                raw.setdefault("strategy_performance", {})
                self.instances[str(raw["id"])] = raw
                loaded = True
        return loaded

    def _save_locked(self) -> None:
        if self.db_store is not None:
            try:
                self.db_store.trading_save_instances(list(self.instances.values()))
                self.storage_error = None
                return
            except Exception as exc:
                self.storage_error = _short_error(f"PostgreSQL save failed: {exc}")
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"saved_at": _now_iso(), "instances": list(self.instances.values())}
        tmp_path = self.storage_path.with_name(f".{self.storage_path.name}.{uuid.uuid4().hex}.tmp")
        try:
            tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            tmp_path.replace(self.storage_path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)


class TradingMarketDataProvider:
    def __init__(self, *, settings: AppSettings):
        self.settings = settings
        self.lock = threading.Lock()
        self.provider: FutuProvider | None = None
        self.synthetic = SyntheticMarketData()
        self.rsi_cache: dict[tuple[str, str, int], dict[str, Any]] = {}

    def subscribe(self, tickers: list[str]) -> None:
        try:
            provider = self._provider()
            for ticker in tickers:
                provider.subscribe_minute_kline(ticker, session="ALL")
        except Exception:
            return

    def subscribe_trading(self, *, signal_ticker: str, long_ticker: str, short_ticker: str) -> None:
        try:
            provider = self._provider()
            for ticker in _unique_tickers([long_ticker, short_ticker]):
                provider.subscribe_kline(ticker, subtype_name="K_1M", session="ALL")
        except Exception:
            return

    def unsubscribe(self, tickers: list[str]) -> None:
        with self.lock:
            provider = self.provider
        if provider is None:
            return
        for ticker in tickers:
            try:
                provider.unsubscribe_minute_kline(ticker)
            except Exception:
                pass

    def unsubscribe_trading(self, *, signal_ticker: str, long_ticker: str, short_ticker: str) -> None:
        with self.lock:
            provider = self.provider
        if provider is None:
            return
        for ticker, subtype_name in [(ticker, "K_1M") for ticker in _unique_tickers([long_ticker, short_ticker])]:
            try:
                provider.unsubscribe_kline(ticker, subtype_name=subtype_name)
            except Exception:
                pass

    def snapshot(
        self,
        *,
        signal_ticker: str,
        long_ticker: str,
        short_ticker: str,
        window: int = 90,
    ) -> dict[str, Any]:
        try:
            return self._futu_snapshot(
                signal_ticker=signal_ticker,
                long_ticker=long_ticker,
                short_ticker=short_ticker,
                window=window,
            )
        except Exception as exc:
            return self.synthetic.snapshot(
                signal_ticker=signal_ticker,
                long_ticker=long_ticker,
                short_ticker=short_ticker,
                window=window,
                fallback_error=_short_error(str(exc)),
            )

    def backtest_history(
        self,
        *,
        signal_ticker: str,
        long_ticker: str,
        short_ticker: str,
        start: datetime,
        end: datetime,
        rsi_period: int = 6,
        rsi_interval: str = "3m",
    ) -> dict[str, Any]:
        provider = self._provider()
        rows_by_ticker: dict[str, list[dict[str, Any]]] = {}
        interval_minutes = _interval_minutes(rsi_interval)
        rsi_subtype = _intraday_kline_subtype(rsi_interval)
        warmup_minutes = max(90, int(rsi_period) * interval_minutes * 3)
        history_start = start - timedelta(minutes=warmup_minutes)
        used_current_kline = False
        for ticker in _unique_tickers([signal_ticker, long_ticker, short_ticker]):
            _code, rows = provider.history_intraday_kline(
                ticker,
                start=history_start,
                end=end,
                subtype_name="K_1M",
                max_pages=20,
            )
            if not rows:
                used_current_kline = True
                try:
                    provider.subscribe_kline(ticker, subtype_name="K_1M", session="ALL")
                except Exception:
                    pass
                _code, rows = provider.current_kline(ticker, num=1000, subtype_name="K_1M")
            rows_by_ticker[ticker] = rows
        used_current_rsi = False
        try:
            _rsi_code, rsi_rows = provider.history_intraday_kline(
                signal_ticker,
                start=history_start,
                end=end,
                subtype_name=rsi_subtype,
                max_pages=20,
            )
        except Exception:
            rsi_rows = []
        if not rsi_rows:
            used_current_rsi = True
            try:
                provider.subscribe_kline(signal_ticker, subtype_name=rsi_subtype, session="ALL")
            except Exception:
                pass
            try:
                _rsi_code, rsi_rows = provider.current_kline(signal_ticker, num=1000, subtype_name=rsi_subtype)
            except Exception:
                rsi_rows = []
        rsi_input_label = f"Futu {rsi_subtype} {'current' if used_current_rsi else 'history'}"
        rsi_input_source = f"futu_{rsi_subtype.lower()}_{'current' if used_current_rsi else 'history'}"
        if not rsi_rows:
            rsi_rows = rows_by_ticker.get(signal_ticker) or []
            rsi_input_label = "Futu K_1M history resampled"
            rsi_input_source = "futu_k_1m_history_resampled"
        source = "futu_current_1m" if used_current_kline else "futu_history_1m"
        source_label = (
            "Futu current 1m cache"
            if used_current_kline
            else "Futu 1m history"
        )
        return {
            "source": source,
            "source_label": f"{source_label} · {rsi_input_label} RSI1({int(rsi_period)})",
            "points": backtest_points_from_rows(
                signal_ticker=signal_ticker,
                long_ticker=long_ticker,
                short_ticker=short_ticker,
                rows_by_ticker=rows_by_ticker,
                rsi_rows=rsi_rows,
                rsi_input_label=rsi_input_label,
                rsi_input_source=rsi_input_source,
                start=start,
                end=end,
                rsi_period=rsi_period,
                rsi_interval=rsi_interval,
            ),
        }

    def _futu_snapshot(
        self,
        *,
        signal_ticker: str,
        long_ticker: str,
        short_ticker: str,
        window: int,
    ) -> dict[str, Any]:
        provider = self._provider()
        tickers = _unique_tickers([signal_ticker, long_ticker, short_ticker])
        snapshot_rows = provider.snapshots(tickers)
        snapshots_by_ticker = {_snapshot_ticker_key(row): row for row in snapshot_rows}
        _long_code, long_rows = provider.current_kline(long_ticker, num=window, subtype_name="K_1M")
        _short_code, short_rows = provider.current_kline(short_ticker, num=window, subtype_name="K_1M")
        rsi_indicator, rsi_error = self._opend_rsi(signal_ticker, interval="3m", rsi_period=6)
        source_label = "OpenD RSI1 3m + 1m quotes" if rsi_indicator else "OpenD RSI unavailable + 1m quotes"
        return market_snapshot_from_rows(
            signal_ticker=signal_ticker,
            long_ticker=long_ticker,
            short_ticker=short_ticker,
            long_rows=long_rows,
            short_rows=short_rows,
            snapshots_by_ticker=snapshots_by_ticker,
            rsi_indicator=rsi_indicator,
            rsi_error=rsi_error,
            source="futu_opend",
            source_label=source_label,
        )

    def _opend_rsi(self, ticker: str, *, interval: str, rsi_period: int) -> tuple[dict[str, Any] | None, str | None]:
        cache_key = (_clean_ticker(ticker), interval, int(rsi_period))
        cached = self.rsi_cache.get(cache_key)
        now = time.time()
        if cached and now - float(cached.get("cached_at") or 0) < 25:
            payload = cached.get("payload")
            return (dict(payload) if payload else None), cached.get("error")
        provider = self._provider()
        try:
            payload = provider.stock_screen_rsi(
                ticker,
                interval=interval,
                rsi_period=rsi_period,
                watchlist_only=True,
                max_pages=3,
            )
            self.rsi_cache[cache_key] = {"cached_at": now, "payload": payload, "error": None}
            return payload, None
        except Exception as exc:
            if _is_watchlist_rsi_miss(str(exc)):
                try:
                    payload = provider.stock_screen_rsi(
                        ticker,
                        interval=interval,
                        rsi_period=rsi_period,
                        watchlist_only=False,
                        max_pages=3,
                    )
                    source_label = str(payload.get("source_label") or "OpenD RSI1").strip()
                    payload["source_label"] = f"{source_label} · market scan"
                    self.rsi_cache[cache_key] = {"cached_at": now, "payload": payload, "error": None}
                    return payload, None
                except Exception as fallback_exc:
                    exc = fallback_exc
            error = _short_error(str(exc))
            self.rsi_cache[cache_key] = {"cached_at": now, "payload": None, "error": error}
            return None, error

    def _provider(self) -> FutuProvider:
        with self.lock:
            if self.provider is None:
                self.provider = FutuProvider(
                    host=self.settings.futu_host,
                    port=self.settings.futu_port,
                    market=self.settings.futu_market,
                )
            return self.provider


class SyntheticMarketData:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.rows_by_ticker: dict[str, list[dict[str, Any]]] = {}
        self.step = 0

    def snapshot(
        self,
        *,
        signal_ticker: str,
        long_ticker: str,
        short_ticker: str,
        window: int,
        fallback_error: str = "",
    ) -> dict[str, Any]:
        with self.lock:
            self.step += 1
            for ticker in _unique_tickers([signal_ticker, long_ticker, short_ticker]):
                self._ensure_rows(ticker, window + 20)
                self._append_row(ticker)
            rows_by_ticker = {
                ticker: list(rows[-window:]) for ticker, rows in self.rows_by_ticker.items()
            }
        payload = market_snapshot_from_rows(
            signal_ticker=signal_ticker,
            long_ticker=long_ticker,
            short_ticker=short_ticker,
            rows_by_ticker=rows_by_ticker,
            source="simulated_market",
            source_label="Simulated quotes · OpenD RSI unavailable",
            rsi_error="Synthetic market data has no OpenD RSI indicator.",
        )
        if fallback_error:
            payload["error"] = f"Futu fallback: {fallback_error}"
        return payload

    def _ensure_rows(self, ticker: str, count: int) -> None:
        if ticker in self.rows_by_ticker and len(self.rows_by_ticker[ticker]) >= count:
            return
        self.rows_by_ticker[ticker] = []
        start = datetime.now().replace(second=0, microsecond=0) - timedelta(minutes=count)
        for index in range(count):
            self.rows_by_ticker[ticker].append(self._row(ticker, start + timedelta(minutes=index), index))

    def _append_row(self, ticker: str) -> None:
        rows = self.rows_by_ticker.setdefault(ticker, [])
        last_time = _parse_time(rows[-1].get("time_key") if rows else None) or datetime.now().replace(second=0, microsecond=0)
        next_index = len(rows)
        rows.append(self._row(ticker, last_time + timedelta(minutes=1), next_index))
        del rows[:-600]

    def _row(self, ticker: str, at: datetime, index: int) -> dict[str, Any]:
        seed = sum(ord(char) for char in ticker)
        base = 20 + (seed % 90)
        wave = math.sin((index + seed % 17) / 5.5) * 0.032
        drift = math.sin((index + seed % 11) / 19.0) * 0.014
        micro = math.sin((index + seed % 7) / 2.0) * 0.004
        close = max(0.2, base * (1 + wave + drift + micro))
        open_price = close * (1 - math.sin(index / 3.0) * 0.0018)
        high = max(open_price, close) * 1.002
        low = min(open_price, close) * 0.998
        volume = 30_000 + ((index + seed) % 30) * 1200
        return {
            "time_key": at.isoformat(sep=" "),
            "open": round(open_price, 4),
            "high": round(high, 4),
            "low": round(low, 4),
            "close": round(close, 4),
            "volume": volume,
        }


def backtest_points_from_rows(
    *,
    signal_ticker: str,
    long_ticker: str,
    short_ticker: str,
    rows_by_ticker: dict[str, list[dict[str, Any]]],
    rsi_rows: list[dict[str, Any]] | None = None,
    rsi_input_label: str | None = None,
    rsi_input_source: str | None = None,
    start: datetime,
    end: datetime,
    rsi_period: int = 6,
    rsi_interval: str = "3m",
) -> list[dict[str, Any]]:
    signal_ticker = _clean_ticker(signal_ticker)
    long_ticker = _clean_ticker(long_ticker)
    short_ticker = _clean_ticker(short_ticker)
    signal_points = _points_by_time(rows_by_ticker.get(signal_ticker) or [])
    long_points = _points_by_time(rows_by_ticker.get(long_ticker) or [])
    short_points = _points_by_time(rows_by_ticker.get(short_ticker) or [])
    if not signal_points or not long_points or not short_points:
        return []

    common_times = sorted(set(signal_points) & set(long_points) & set(short_points))
    common_times = [
        time_key
        for time_key in common_times
        if (parsed := _parse_time(time_key)) is not None and start <= parsed <= end
    ]
    if not common_times:
        return []

    rsi_period = max(1, int(rsi_period))
    interval_minutes = _interval_minutes(rsi_interval)
    rsi_points = _points_by_time(rsi_rows or []) if rsi_rows else {}
    rsi_input_label = rsi_input_label or ("Futu K_1M history resampled" if not rsi_points else "Futu K-line history")
    rsi_input_source = rsi_input_source or ("futu_k_1m_history_resampled" if not rsi_points else "futu_kline_history")
    rsi_by_bucket = _backtest_rsi_by_bucket(
        rsi_points or signal_points,
        start=start,
        end=end,
        period=rsi_period,
        interval_minutes=interval_minutes,
    )
    points: list[dict[str, Any]] = []
    for time_key in common_times:
        signal_point = signal_points[time_key]
        long_point = long_points[time_key]
        short_point = short_points[time_key]
        signal_price = _safe_float(signal_point.get("close"))
        long_price = _safe_float(long_point.get("close"))
        short_price = _safe_float(short_point.get("close"))
        if signal_price is None or long_price is None or short_price is None:
            continue
        signal_bid, signal_ask = _estimated_bid_ask(signal_price)
        long_bid, long_ask = _estimated_bid_ask(long_price)
        short_bid, short_ask = _estimated_bid_ask(short_price)
        bucket_key = _time_bucket_key(time_key, interval_minutes)
        rsi = rsi_by_bucket.get(bucket_key)
        points.append(
            {
                "time": time_key,
                "source": "backtest",
                "source_label": f"{rsi_input_label} RSI1({rsi_period})",
                "signal_price": signal_price,
                "long_price": long_price,
                "short_price": short_price,
                "signal_bid": signal_bid,
                "signal_ask": signal_ask,
                "long_bid": long_bid,
                "long_ask": long_ask,
                "short_bid": short_bid,
                "short_ask": short_ask,
                "quote_source": "estimated",
                "rsi": rsi,
                "rsi1": rsi,
                "rsi3": rsi,
                "rsi_label": f"RSI1({rsi_period})",
                "rsi_period": rsi_period,
                "rsi_interval": rsi_interval,
                "rsi_source": f"futu_style_rsi1_{rsi_interval}_from_{rsi_input_source}",
                "rsi_unavailable": rsi is None,
            }
        )
    return points


def _backtest_markers(events: list[dict[str, Any]], points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    points_by_time = {str(point.get("time") or ""): point for point in points if point.get("time")}
    markers: list[dict[str, Any]] = []
    for event in events:
        if event.get("type") not in {"open", "close"}:
            continue
        event_time = str(event.get("time") or "")
        point = points_by_time.get(event_time) or {}
        leg = str(event.get("leg") or "").lower()
        action = "buy" if event.get("type") == "open" else "sell"
        markers.append(
            {
                "time": event_time,
                "type": action,
                "event_type": event.get("type"),
                "leg": leg,
                "ticker": event.get("ticker"),
                "price": _safe_float(event.get("price")),
                "quote_side": event.get("quote_side"),
                "rsi": _signal_rsi(point),
                "label": "BUY" if action == "buy" else "SELL",
                "severity": event.get("severity"),
            }
        )
    return markers


def _points_by_time(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    points: dict[str, dict[str, Any]] = {}
    for point in normalize_intraday_rows(rows):
        time_key = str(point.get("time") or "").replace(" ", "T")
        if not time_key:
            continue
        points[time_key] = {**point, "time": time_key}
    return points


def _backtest_rsi_by_bucket(
    points_by_time: dict[str, dict[str, Any]],
    *,
    start: datetime,
    end: datetime,
    period: int,
    interval_minutes: int,
) -> dict[str, float | None]:
    bucket_closes: dict[str, tuple[str, float]] = {}
    for time_key, point in points_by_time.items():
        parsed = _parse_time(time_key)
        close = _safe_float(point.get("close"))
        if parsed is None or close is None or parsed > end:
            continue
        bucket_key = _time_bucket_key(time_key, interval_minutes)
        previous = bucket_closes.get(bucket_key)
        if previous is None or time_key > previous[0]:
            bucket_closes[bucket_key] = (time_key, close)
    closes: list[float] = []
    rsi_by_bucket: dict[str, float | None] = {}
    for bucket_key in sorted(bucket_closes):
        closes.append(bucket_closes[bucket_key][1])
        rsi_by_bucket[bucket_key] = _standard_rsi(closes, period)
    return rsi_by_bucket


def market_snapshot_from_rows(
    *,
    signal_ticker: str,
    long_ticker: str,
    short_ticker: str,
    rows_by_ticker: dict[str, list[dict[str, Any]]] | None = None,
    signal_rows: list[dict[str, Any]] | None = None,
    long_rows: list[dict[str, Any]] | None = None,
    short_rows: list[dict[str, Any]] | None = None,
    rsi_indicator: dict[str, Any] | None = None,
    rsi_error: str | None = None,
    source: str,
    source_label: str,
    snapshots_by_ticker: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    rows_by_ticker = rows_by_ticker or {}
    signal_points = normalize_intraday_rows(signal_rows if signal_rows is not None else rows_by_ticker.get(signal_ticker) or [])
    long_points = normalize_intraday_rows(long_rows if long_rows is not None else rows_by_ticker.get(long_ticker) or [])
    short_points = normalize_intraday_rows(short_rows if short_rows is not None else rows_by_ticker.get(short_ticker) or [])
    latest_signal = signal_points[-1] if signal_points else {}
    latest_reference = latest_signal or (long_points[-1] if long_points else {}) or (short_points[-1] if short_points else {})
    snapshots_by_ticker = snapshots_by_ticker or {}
    signal_quote = _quote_payload(signal_points, snapshots_by_ticker.get(signal_ticker))
    long_quote = _quote_payload(long_points, snapshots_by_ticker.get(long_ticker))
    short_quote = _quote_payload(short_points, snapshots_by_ticker.get(short_ticker))
    return {
        "as_of": latest_reference.get("time") or _now_iso(),
        "source": source,
        "source_label": source_label,
        "prices": {
            "signal": signal_quote.get("last"),
            "long": long_quote.get("last"),
            "short": short_quote.get("last"),
        },
        "quotes": {
            "signal": signal_quote,
            "long": long_quote,
            "short": short_quote,
        },
        "signal": {
            "ticker": signal_ticker,
            "points": signal_points,
            "rsi": _safe_float((rsi_indicator or {}).get("rsi")),
            "rsi1": _safe_float((rsi_indicator or {}).get("rsi")),
            "rsi3": _safe_float((rsi_indicator or {}).get("rsi")),
            "rsi_label": (rsi_indicator or {}).get("label") or "OpenD RSI1",
            "rsi_period": (rsi_indicator or {}).get("period") or 6,
            "rsi_interval": (rsi_indicator or {}).get("interval") or "3m",
            "rsi_source": (rsi_indicator or {}).get("source_label") or (rsi_indicator or {}).get("source"),
            "rsi_error": rsi_error,
            "rsi_unavailable": rsi_indicator is None,
        },
        "error": rsi_error,
    }


def rsi_points(points: list[dict[str, Any]], *, period: int = 14) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    closes: list[float] = []
    period = max(1, int(period))
    for point in points:
        close = _safe_float(point.get("close"))
        if close is None:
            continue
        closes.append(close)
        rsi = _standard_rsi(closes, period)
        result.append(
            {
                **point,
                "rsi": rsi,
                "rsi1": rsi,
                "rsi3": rsi,
                "rsi_label": "RSI",
                "rsi_period": period,
                "rsi_interval": "3m",
            }
        )
    return result


def rsi1_points(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return rsi_points(points, period=14)


def _standard_rsi(closes: list[float], period: int) -> float | None:
    if len(closes) <= period:
        return None
    deltas = [closes[index] - closes[index - 1] for index in range(1, len(closes))]
    tail = deltas[-period:]
    gains = [max(delta, 0.0) for delta in tail]
    losses = [abs(min(delta, 0.0)) for delta in tail]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def _strategy_state(instance: dict[str, Any]) -> dict[str, Any]:
    strategy = strategy_by_id(str(instance.get("strategy_id") or "")) or {}
    params = strategy.get("params") or {}
    buy_threshold = float(params.get("buy_threshold", 20))
    sell_threshold = float(params.get("sell_threshold", 80))
    profit_take_pct = _instance_profit_take_pct(instance, params)
    profit_take_enabled = bool(params.get("profit_take_enabled", True))
    latest = _market_point_payload(instance.get("latest_market")) or {}
    state = instance.get("state") or {}
    metrics = instance.get("metrics") or {}
    positions = instance.get("positions") or {}
    rsi = _signal_rsi(latest)
    rsi_label = str(latest.get("rsi_label") or "OpenD RSI1").strip() or "OpenD RSI1"
    decision_index = int(latest.get("decision_index") or state.get("decision_index") or 0)
    oversold_index = state.get("latest_oversold_index")
    nodes_since = decision_index - int(oversold_index) if oversold_index is not None and decision_index else None
    open_return = _safe_float(metrics.get("open_return_pct")) or 0.0
    long_open = bool(positions.get("long"))
    bear_open = bool(positions.get("short"))
    has_position = bool(long_open or bear_open)
    active_leg = "long" if long_open else "bear" if bear_open else ""

    base = {
        "strategy_id": instance.get("strategy_id"),
        "rsi": rsi,
        "rsi3": rsi,
        "rsi_label": rsi_label,
        "rsi_source": latest.get("rsi_source"),
        "rsi_error": latest.get("rsi_error") or latest.get("error"),
        "rsi_unavailable": bool(latest.get("rsi_unavailable")),
        "buy_threshold": buy_threshold,
        "sell_threshold": sell_threshold,
        "profit_take_pct": profit_take_pct,
        "profit_take_enabled": profit_take_enabled,
        "profit_take_bars": 0,
        "decision_index": decision_index,
        "decision_key": latest.get("decision_key"),
        "nodes_since_oversold": nodes_since,
        "nodes_remaining": None,
        "open_return_pct": open_return,
        "quote_source": latest.get("quote_source"),
        "active_leg": active_leg,
    }
    if not latest:
        return {
            **base,
            "status": "no_data",
            "severity": "idle",
            "headline": "Waiting for market data",
            "detail": "Start the simulation to collect quotes and OpenD RSI.",
            "next_action": "No trade decision until OpenD RSI1 is available.",
        }
    if instance.get("status") != "running" and not has_position:
        return {
            **base,
            "status": "idle",
            "severity": "idle",
            "headline": "Simulation idle",
            "detail": _rsi_detail(rsi, rsi_label=rsi_label),
            "next_action": "Press Start to evaluate the next OpenD RSI1 value.",
        }
    if rsi is None:
        detail = latest.get("rsi_error") or latest.get("error") or "OpenD RSI1 is not available yet."
        return {
            **base,
            "status": "waiting",
            "severity": "idle",
            "headline": "Waiting for RSI",
            "detail": detail,
            "next_action": "No trade until the OpenD RSI indicator returns a value.",
        }
    if has_position:
        if profit_take_enabled and long_open and open_return >= profit_take_pct:
            return {
                **base,
                "status": "profit_take_ready",
                "severity": "success",
                "headline": "Profit take ready",
                "detail": f"Open long return is {open_return * 100:.2f}%, above the {profit_take_pct * 100:.2f}% trigger.",
                "next_action": "Sell long ticker at bid on the next poll.",
            }
        if bear_open and rsi <= buy_threshold:
            return {
                **base,
                "status": "rotate_long_ready",
                "severity": "success",
                "headline": "Rotate to long ready",
                "detail": f"{rsi_label} {rsi:.2f} is at or below {buy_threshold:.0f}.",
                "next_action": "Sell bear ticker at bid, then buy long ticker at ask on the next poll.",
            }
        if long_open and rsi >= sell_threshold:
            return {
                **base,
                "status": "rotate_bear_ready",
                "severity": "warn",
                "headline": "Rotate to bear ready",
                "detail": f"{rsi_label} {rsi:.2f} is at or above {sell_threshold:.0f}.",
                "next_action": "Sell long ticker at bid, then buy bear ticker at ask on the next poll.",
            }
        return {
            **base,
            "status": "holding",
            "severity": "active",
            "headline": f"Holding {active_leg or 'exposure'}",
            "detail": f"Open return {open_return * 100:.2f}%. {_rsi_detail(rsi, rsi_label=rsi_label)}",
            "next_action": _holding_next_action(
                active_leg,
                buy_threshold,
                sell_threshold,
                profit_take_pct if profit_take_enabled else None,
            ),
        }
    if rsi <= buy_threshold:
        return {
            **base,
            "status": "long_entry_ready",
            "severity": "success",
            "headline": "Long entry ready",
            "detail": f"{rsi_label} {rsi:.2f} is at or below {buy_threshold:.0f}.",
            "next_action": "Buy long ticker at ask on the next poll.",
        }
    if rsi >= sell_threshold:
        return {
            **base,
            "status": "bear_entry_ready",
            "severity": "warn",
            "headline": "Bear entry ready",
            "detail": f"{rsi_label} {rsi:.2f} is at or above {sell_threshold:.0f}.",
            "next_action": "Buy bear ticker at ask on the next poll.",
        }
    return {
        **base,
        "status": "waiting",
        "severity": "idle",
        "headline": "Waiting for entry",
        "detail": _rsi_detail(rsi, rsi_label=rsi_label),
        "next_action": f"Buy long when {rsi_label} <= {buy_threshold:.0f}; buy bear when {rsi_label} >= {sell_threshold:.0f}.",
    }


def _signal_rsi(point: dict[str, Any] | None) -> float | None:
    if not isinstance(point, dict):
        return None
    rsi = _first_float(point, ["rsi", "rsi1", "rsi3"])
    if rsi is None:
        return None
    source = str(point.get("source") or "").lower()
    rsi_source = str(point.get("rsi_source") or "").lower()
    allowed_source_tokens = ("opend", "backtest", "futu_style")
    if rsi_source:
        if any(token in rsi_source for token in allowed_source_tokens):
            return rsi
        if source == "backtest":
            return rsi
        return None
    if source in {"fake", "backtest"}:
        return rsi
    return None


def _rsi_detail(rsi: float | None, *, rsi_label: str = "OpenD RSI1") -> str:
    if rsi is None:
        return f"{rsi_label} is not ready."
    if rsi <= 20:
        zone = "oversold"
    elif rsi >= 80:
        zone = "overbought"
    else:
        zone = "neutral"
    return f"{rsi_label} {rsi:.2f} is in the {zone} zone."


def _holding_next_action(
    active_leg: str,
    buy_threshold: float,
    sell_threshold: float,
    profit_take_pct: float | None,
) -> str:
    if active_leg == "bear":
        return f"Sell bear and rotate long if OpenD RSI1 <= {buy_threshold:.0f}; otherwise keep holding."
    if profit_take_pct is None:
        return f"Sell long and rotate bear if OpenD RSI1 >= {sell_threshold:.0f}; otherwise keep holding."
    return (
        f"Sell long once open return >= {profit_take_pct * 100:.2f}%; "
        f"RSI1 >= {sell_threshold:.0f} remains an overbought fallback."
    )


def _quote_payload(points: list[dict[str, Any]], snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    snapshot = snapshot or {}
    last = _first_float(
        snapshot,
        ["last_price", "last", "price", "nominal_price"],
        default=_latest_close(points),
    )
    bid = _first_float(snapshot, ["bid_price", "bid", "bid1_price", "bid_price1"])
    ask = _first_float(snapshot, ["ask_price", "ask", "ask1_price", "ask_price1"])
    source = "quote"
    if last is None:
        last = _latest_close(points)
    if last is None:
        return {"last": None, "bid": None, "ask": None, "source": "missing"}
    if bid is None or ask is None or bid <= 0 or ask <= 0 or bid > ask:
        bid, ask = _estimated_bid_ask(last)
        source = "estimated"
    return {
        "last": last,
        "bid": bid,
        "ask": ask,
        "spread": ask - bid,
        "source": source,
    }


def _point_quote_values(last_value: Any, quote: dict[str, Any]) -> tuple[float | None, float | None, str | None]:
    last = _safe_float(quote.get("last")) or _safe_float(last_value)
    bid = _safe_float(quote.get("bid"))
    ask = _safe_float(quote.get("ask"))
    source = str(quote.get("source") or "").strip() or None
    if last is None and bid is not None and ask is not None:
        last = (bid + ask) / 2
    if last is None:
        return bid, ask, source
    if bid is None or ask is None or bid <= 0 or ask <= 0 or bid > ask:
        bid, ask = _estimated_bid_ask(last)
        source = "estimated"
    return bid, ask, source or "quote"


def _market_point_payload(point: Any) -> dict[str, Any] | None:
    if not isinstance(point, dict):
        return None
    result = dict(point)
    sources = []
    for leg in ("long", "short", "signal"):
        bid_key = f"{leg}_bid"
        ask_key = f"{leg}_ask"
        bid, ask, source = _point_quote_values(
            result.get(f"{leg}_price"),
            {
                "bid": result.get(bid_key),
                "ask": result.get(ask_key),
                "source": result.get("quote_source"),
            },
        )
        result[bid_key] = bid
        result[ask_key] = ask
        if source:
            sources.append(source)
    if sources:
        result["quote_source"] = "quote" if "quote" in sources else sources[0]
    return result


def _execution_price(point: dict[str, Any], leg: str, action: str) -> float | None:
    if leg == "long":
        key = "long_ask" if action == "buy" else "long_bid"
        fallback_key = "long_price"
    else:
        key = "short_ask" if action == "buy" else "short_bid"
        fallback_key = "short_price"
    price = _safe_float(point.get(key))
    if price is not None:
        return price
    last = _safe_float(point.get(fallback_key))
    if last is None:
        return None
    bid, ask = _estimated_bid_ask(last)
    return ask if action == "buy" else bid


def _estimated_bid_ask(price: float) -> tuple[float, float]:
    spread = _estimated_spread(price)
    return max(0.0001, price - spread / 2), price + spread / 2


def _estimated_spread(price: float) -> float:
    tick = 0.0001 if price < 1 else 0.01
    return max(price * 0.0004, tick)


def _first_float(row: dict[str, Any], keys: list[str], *, default: Any = None) -> float | None:
    for key in keys:
        value = _safe_float(row.get(key))
        if value is not None:
            return value
    return _safe_float(default)


def _snapshot_ticker_key(row: dict[str, Any]) -> str:
    return _clean_ticker(row.get("ticker") or row.get("code") or row.get("stock_code") or "")


def _empty_metrics() -> dict[str, Any]:
    return {
        "realized_pnl": 0.0,
        "unrealized_pnl": 0.0,
        "total_pnl": 0.0,
        "open_notional": 0.0,
        "open_return_pct": 0.0,
        "trade_count": 0,
        "winning_trades": 0,
        "win_rate": 0.0,
    }


def _clean_ticker(value: Any) -> str:
    ticker = str(value or "").strip().upper()
    if "." in ticker:
        ticker = ticker.split(".", 1)[1]
    return "".join(char for char in ticker if char.isalnum() or char in {"-", "_", "."})[:18]


def _unique_tickers(tickers: list[str]) -> list[str]:
    result = []
    seen = set()
    for ticker in tickers:
        clean = _clean_ticker(ticker)
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


def _bounded_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    number = _safe_float(value)
    if number is None:
        number = default
    return min(max(float(number), minimum), maximum)


def _profit_take_pct_from_payload(payload: dict[str, Any]) -> float:
    for key in ("profit_take_pct", "take_profit_pct", "profit_take_percent", "take_profit_percent"):
        if key not in payload:
            continue
        value = _safe_float(payload.get(key))
        if value is None:
            continue
        if "percent" in key or value > 1:
            value = value / 100.0
        return min(max(float(value), 0.001), 1.0)
    return DEFAULT_PROFIT_TAKE_PCT


def _instance_profit_take_pct(instance: dict[str, Any] | None, params: dict[str, Any] | None = None) -> float:
    instance = instance or {}
    raw_value = instance.get("profit_take_pct")
    if raw_value is None:
        raw_value = (instance.get("strategy_params") or {}).get("profit_take_pct")
    if raw_value is None:
        raw_value = (params or {}).get("profit_take_pct")
    value = _safe_float(raw_value)
    if value is None:
        return DEFAULT_PROFIT_TAKE_PCT
    if value > 1:
        value = value / 100.0
    return min(max(float(value), 0.001), 1.0)


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _latest_close(points: list[dict[str, Any]]) -> float | None:
    if not points:
        return None
    return _safe_float(points[-1].get("close"))


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _parse_backtest_time(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _daily_outcome(final_pnl: float) -> str:
    rounded = round(float(final_pnl or 0.0), 2)
    if rounded > 0:
        return "win"
    if rounded < 0:
        return "loss"
    return "flat"


def _strategy_performance_summary(result: dict[str, Any]) -> dict[str, Any]:
    period = result.get("period_metrics") or {}
    metrics = result.get("metrics") or {}
    day_count = int(period.get("day_count") or len(result.get("daily_results") or []) or 1)
    winning_days = int(period.get("winning_days") or 0)
    losing_days = int(period.get("losing_days") or 0)
    flat_days = int(period.get("flat_days") or 0)
    if not result.get("period_metrics"):
        outcome = _daily_outcome(float(result.get("final_pnl") or 0.0))
        winning_days = 1 if outcome == "win" else 0
        losing_days = 1 if outcome == "loss" else 0
        flat_days = 1 if outcome == "flat" else 0
    trade_count = int(metrics.get("trade_count") or 0)
    winning_trades = int(metrics.get("winning_trades") or 0)
    decided_days = winning_days + losing_days
    return {
        "strategy_id": result.get("strategy_id"),
        "evaluated_at": _now_iso(),
        "start": result.get("start"),
        "end": result.get("end"),
        "day_count": day_count,
        "winning_days": winning_days,
        "losing_days": losing_days,
        "flat_days": flat_days,
        "day_win_rate": winning_days / decided_days if decided_days else 0.0,
        "trade_count": trade_count,
        "winning_trades": winning_trades,
        "trade_win_rate": winning_trades / trade_count if trade_count else 0.0,
        "total_pnl": float(result.get("final_pnl") or metrics.get("total_pnl") or 0.0),
        "average_daily_pnl": float(
            period.get("average_daily_pnl")
            if period.get("average_daily_pnl") is not None
            else (float(result.get("final_pnl") or 0.0) / day_count if day_count else 0.0)
        ),
        "trades_per_day": trade_count / day_count if day_count else 0.0,
        "source_label": result.get("source_label"),
    }


def _weekday_dates(start: datetime, end: datetime) -> list[str]:
    result = []
    day = start.date()
    while day <= end.date():
        if day.weekday() < 5:
            result.append(day.isoformat())
        day += timedelta(days=1)
    return result


def _decision_key(value: Any) -> str:
    return _time_bucket_key(value, 3)


def _time_bucket_key(value: Any, minutes: int) -> str:
    parsed = _parse_time(value)
    if parsed is None:
        return str(value or _now_iso())
    minutes = max(1, min(60, int(minutes or 3)))
    bucket_minute = (parsed.minute // minutes) * minutes
    bucket = parsed.replace(minute=bucket_minute, second=0, microsecond=0)
    return bucket.isoformat(timespec="minutes")


def _interval_minutes(value: Any) -> int:
    text = str(value or "3m").strip().lower()
    if text.endswith("m"):
        text = text[:-1]
    try:
        return max(1, min(60, int(text)))
    except ValueError:
        return 3


def _intraday_kline_subtype(value: Any) -> str:
    return f"K_{_interval_minutes(value)}M"


def _short_error(message: str) -> str:
    clean = str(message or "").strip()
    if not clean:
        return "Market data unavailable."
    lower = clean.lower()
    if "stockscreen" in lower:
        return clean[:180]
    if "connect" in lower or "network" in lower or "disconn" in lower:
        return "Futu OpenD connection unavailable."
    if "permission" in lower or "no right" in lower:
        return "No Futu quote right for this symbol."
    if "quota" in lower:
        return "Futu quote quota unavailable."
    return clean[:180]


def _is_watchlist_rsi_miss(message: str) -> bool:
    lower = str(message or "").lower()
    return "stockscreen rsi did not return" in lower and "watchlist" in lower


def _price_text(value: float) -> str:
    return f"${value:.2f}" if value >= 100 else f"${value:.3f}"


def _money_text(value: float) -> str:
    prefix = "+" if value >= 0 else "-"
    return f"{prefix}${abs(value):.2f}"
