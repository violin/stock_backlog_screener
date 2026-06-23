import copy
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from backlog_screener.settings import AppSettings
from backlog_screener.trading import (
    TradingAutomationManager,
    TradingMarketDataProvider,
    _short_error,
    backtest_points_from_rows,
    rsi_points,
    trading_strategy_definitions,
)


def _settings() -> AppSettings:
    return AppSettings(
        database_url="postgresql://example/test",
        sec_user_agent=None,
        futu_host="127.0.0.1",
        futu_port=11111,
        futu_market="US",
        llm_provider="minimax",
        minimax_base_url="",
        minimax_model="",
        minimax_api="",
        minimax_api_key=None,
        minimax_retries=1,
        minimax_retry_wait_seconds=1.0,
        gemini_base_url="",
        gemini_model="",
        gemini_api_key=None,
        gemini_retries=1,
        gemini_retry_wait_seconds=1.0,
    )


class FakeTradingData:
    def __init__(self, snapshots):
        self.snapshots = list(snapshots)

    def snapshot(self, **kwargs):
        if not self.snapshots:
            raise AssertionError("No fake snapshots left")
        return self.snapshots.pop(0)


class FakeBacktestData:
    def __init__(self, points):
        self.points = list(points)
        self.calls = []

    def backtest_history(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "source": "fake_history",
            "source_label": "Fake backtest",
            "points": list(self.points),
        }


class FakeTradingStore:
    def __init__(self):
        self.instances = []
        self.deleted = []

    def trading_load_instances(self):
        return copy.deepcopy(self.instances)

    def trading_save_instances(self, instances):
        self.instances = copy.deepcopy(list(instances))

    def trading_delete_instance(self, instance_id):
        self.deleted.append(instance_id)
        self.instances = [instance for instance in self.instances if instance.get("id") != instance_id]


class FakeRsiProvider:
    def __init__(self):
        self.calls = []

    def stock_screen_rsi(self, ticker, *, interval, rsi_period, watchlist_only, max_pages):
        self.calls.append(watchlist_only)
        if watchlist_only:
            raise RuntimeError(f"OpenD StockScreen RSI did not return {ticker} from watchlist.")
        return {
            "ticker": ticker,
            "rsi": 87.264,
            "label": "OpenD RSI1",
            "period": rsi_period,
            "interval": interval,
            "source": "opend_stock_screen",
            "source_label": f"OpenD RSI1 {interval} p{rsi_period}",
        }


class TradingStrategyDefinitionTests(unittest.TestCase):
    def test_definitions_expose_selector_summary_and_rules(self):
        strategies = trading_strategy_definitions()

        self.assertGreaterEqual(len(strategies), 2)
        for strategy in strategies:
            self.assertTrue(strategy["option_summary"])
            self.assertTrue(strategy["buy_conditions"])
            self.assertTrue(strategy["sell_conditions"])
            self.assertTrue(strategy["risk_conditions"])


def _snapshot(
    index,
    *,
    rsi3,
    long_price,
    short_price,
    long_bid=None,
    long_ask=None,
    short_bid=None,
    short_ask=None,
):
    long_bid = long_price if long_bid is None else long_bid
    long_ask = long_price if long_ask is None else long_ask
    short_bid = short_price if short_bid is None else short_bid
    short_ask = short_price if short_ask is None else short_ask
    return {
        "as_of": f"2026-06-15T09:{index:02d}:00",
        "source": "fake",
        "source_label": "Fake 1m K-line",
        "prices": {
            "signal": long_price,
            "long": long_price,
            "short": short_price,
        },
        "quotes": {
            "signal": {"last": long_price, "bid": long_bid, "ask": long_ask, "source": "quote"},
            "long": {"last": long_price, "bid": long_bid, "ask": long_ask, "source": "quote"},
            "short": {"last": short_price, "bid": short_bid, "ask": short_ask, "source": "quote"},
        },
        "signal": {
            "ticker": "TQQQ",
            "rsi": rsi3,
            "rsi1": rsi3,
            "rsi3": rsi3,
            "rsi_label": "OpenD RSI1",
            "rsi_period": 6,
            "rsi_interval": "3m",
            "rsi_source": "opend_stock_screen",
            "points": [],
        },
    }


def _backtest_point(index, *, rsi, long_price, short_price, day="2026-06-15"):
    minute = 30 + index * 3
    long_bid = long_price - 0.1
    long_ask = long_price + 0.1
    short_bid = short_price - 0.1
    short_ask = short_price + 0.1
    return {
        "time": f"{day}T09:{minute:02d}:00",
        "source": "backtest",
        "source_label": "Fake backtest",
        "signal_price": long_price,
        "long_price": long_price,
        "short_price": short_price,
        "signal_bid": long_bid,
        "signal_ask": long_ask,
        "long_bid": long_bid,
        "long_ask": long_ask,
        "short_bid": short_bid,
        "short_ask": short_ask,
        "quote_source": "quote",
        "rsi": rsi,
        "rsi1": rsi,
        "rsi3": rsi,
        "rsi_label": "RSI1(6)",
        "rsi_period": 6,
        "rsi_interval": "3m",
        "rsi_source": "futu_style_rsi1_3m_from_1m_close",
        "rsi_unavailable": False,
    }


def _kline_row(at, close):
    return {
        "time_key": at.isoformat(sep=" "),
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 1000,
    }


class TradingStrategyTests(unittest.TestCase):
    def test_local_rsi_points_are_standard_preview_only(self):
        points = [
            {"time": "09:30", "close": 10},
            {"time": "09:31", "close": 9},
            {"time": "09:32", "close": 8},
            {"time": "09:33", "close": 7},
        ]

        enriched = rsi_points(points, period=3)

        self.assertEqual([point["rsi1"] for point in enriched], [None, None, None, 0.0])
        self.assertEqual(enriched[-1]["rsi3"], 0.0)

    def test_opend_rsi_falls_back_when_ticker_missing_from_watchlist(self):
        provider = TradingMarketDataProvider(settings=_settings())
        fake = FakeRsiProvider()
        provider.provider = fake

        payload, error = provider._opend_rsi("SPCX", interval="3m", rsi_period=6)

        self.assertIsNone(error)
        self.assertEqual(fake.calls, [True, False])
        self.assertEqual(payload["rsi"], 87.264)
        self.assertEqual(payload["source_label"], "OpenD RSI1 3m p6 · market scan")

    def test_stock_screen_miss_is_not_reported_as_connection_failure(self):
        error = _short_error("OpenD StockScreen RSI did not return SPCX from watchlist.")

        self.assertEqual(error, "OpenD StockScreen RSI did not return SPCX from watchlist.")

    def test_rsi_extreme_does_not_trade_without_opend_rsi_source(self):
        snapshot = _snapshot(30, rsi3=10, long_price=100, short_price=50)
        snapshot["signal"]["rsi_source"] = "local_preview"
        data = FakeTradingData([snapshot])
        with tempfile.TemporaryDirectory() as tmp:
            manager = TradingAutomationManager(
                settings=_settings(),
                storage_path=Path(tmp) / "trading.json",
                data_provider=data,
            )
            instance = manager.create_instance(
                {
                    "strategy_id": "rsi_extreme",
                    "long_ticker": "TQQQ",
                    "short_ticker": "SQQQ",
                    "notional_per_leg": 1000,
                }
            )["id"]

            result = manager.poll_once(instance)

            self.assertIsNone(result["positions"]["long"])
            self.assertIsNone(result["positions"]["short"])
            self.assertEqual(result["metrics"]["trade_count"], 0)

    def test_rsi_extreme_rotates_between_long_and_bear_tickers(self):
        data = FakeTradingData(
            [
                _snapshot(30, rsi3=10, long_price=100, short_price=50, long_bid=99.9, long_ask=100.1, short_bid=49.9, short_ask=50.1),
                _snapshot(33, rsi3=90, long_price=110, short_price=45, long_bid=109.9, long_ask=110.1, short_bid=44.9, short_ask=45.1),
                _snapshot(36, rsi3=10, long_price=112, short_price=47, long_bid=111.9, long_ask=112.1, short_bid=46.9, short_ask=47.1),
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            manager = TradingAutomationManager(
                settings=_settings(),
                storage_path=Path(tmp) / "trading.json",
                data_provider=data,
            )
            instance = manager.create_instance(
                {
                    "strategy_id": "rsi_extreme",
                    "long_ticker": "TQQQ",
                    "short_ticker": "SQQQ",
                    "notional_per_leg": 1000,
                    "profit_take_percent": 50,
                }
            )["id"]

            manager.poll_once(instance)
            after_open = manager.get_instance(instance)
            self.assertIsNotNone(after_open["positions"]["long"])
            self.assertIsNone(after_open["positions"]["short"])
            self.assertAlmostEqual(after_open["positions"]["long"]["entry_price"], 100.1)
            self.assertEqual(after_open["positions"]["long"]["entry_quote_side"], "ask")

            after_bear = manager.poll_once(instance)
            self.assertIsNone(after_bear["positions"]["long"])
            self.assertIsNotNone(after_bear["positions"]["short"])
            self.assertAlmostEqual(after_bear["positions"]["short"]["entry_price"], 45.1)
            self.assertEqual(after_bear["positions"]["short"]["entry_quote_side"], "ask")
            self.assertEqual(after_bear["metrics"]["trade_count"], 1)
            self.assertAlmostEqual(after_bear["trades"][0]["exit_price"], 109.9)
            self.assertEqual(after_bear["trades"][0]["entry_quote_side"], "ask")
            self.assertEqual(after_bear["trades"][0]["exit_quote_side"], "bid")
            self.assertGreater(after_bear["metrics"]["realized_pnl"], 95.0)

            after_long = manager.poll_once(instance)
            self.assertIsNotNone(after_long["positions"]["long"])
            self.assertIsNone(after_long["positions"]["short"])
            self.assertEqual(after_long["metrics"]["trade_count"], 2)
            self.assertAlmostEqual(after_long["trades"][1]["exit_price"], 46.9)
            self.assertEqual(after_long["trades"][1]["entry_quote_side"], "ask")
            self.assertEqual(after_long["trades"][1]["exit_quote_side"], "bid")
            self.assertGreater(after_long["metrics"]["realized_pnl"], 130.0)

    def test_rsi_extreme_estimates_bid_ask_instead_of_using_last_when_quotes_missing(self):
        snapshot = _snapshot(30, rsi3=10, long_price=100, short_price=50)
        snapshot.pop("quotes")
        data = FakeTradingData([snapshot])
        with tempfile.TemporaryDirectory() as tmp:
            manager = TradingAutomationManager(
                settings=_settings(),
                storage_path=Path(tmp) / "trading.json",
                data_provider=data,
            )
            instance = manager.create_instance(
                {
                    "strategy_id": "rsi_extreme",
                    "long_ticker": "TQQQ",
                    "short_ticker": "SQQQ",
                    "notional_per_leg": 1000,
                }
            )["id"]

            result = manager.poll_once(instance)

            self.assertGreater(result["positions"]["long"]["entry_price"], 100)
            self.assertIsNone(result["positions"]["short"])
            self.assertEqual(result["latest_market"]["quote_source"], "estimated")

    def test_rsi_extreme_opens_when_threshold_crosses_inside_same_decision_node(self):
        data = FakeTradingData(
            [
                _snapshot(30, rsi3=50, long_price=100, short_price=50),
                _snapshot(31, rsi3=10, long_price=101, short_price=49),
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            manager = TradingAutomationManager(
                settings=_settings(),
                storage_path=Path(tmp) / "trading.json",
                data_provider=data,
            )
            instance = manager.create_instance(
                {
                    "strategy_id": "rsi_extreme",
                    "long_ticker": "TQQQ",
                    "short_ticker": "SQQQ",
                    "notional_per_leg": 1000,
                }
            )["id"]

            first = manager.poll_once(instance)
            self.assertIsNone(first["positions"]["long"])

            second = manager.poll_once(instance)
            self.assertIsNotNone(second["positions"]["long"])
            self.assertIsNone(second["positions"]["short"])

    def test_pair_preset_can_populate_tickers(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = TradingAutomationManager(
                settings=_settings(),
                storage_path=Path(tmp) / "trading.json",
                data_provider=FakeTradingData([]),
            )
            instance = manager.create_instance({"strategy_id": "rsi_extreme", "pair_id": "rklb_2x"})

            self.assertEqual(instance["pair_id"], "rklb_2x")
            self.assertEqual(instance["signal_ticker"], "RKLB")
            self.assertEqual(instance["long_ticker"], "RKLX")
            self.assertEqual(instance["short_ticker"], "RKLZ")
            self.assertAlmostEqual(instance["profit_take_pct"], 0.04)

    def test_instance_creation_uses_default_strategy_until_detail_switch(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = TradingAutomationManager(
                settings=_settings(),
                storage_path=Path(tmp) / "trading.json",
                data_provider=FakeTradingData([]),
            )
            instance = manager.create_instance(
                {
                    "strategy_id": "rsi_rotation",
                    "long_ticker": "TQQQ",
                    "short_ticker": "SQQQ",
                }
            )

            self.assertEqual(instance["strategy_id"], "rsi_extreme")

    def test_strategy_can_switch_on_existing_flat_instance(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = TradingAutomationManager(
                settings=_settings(),
                storage_path=Path(tmp) / "trading.json",
                data_provider=FakeTradingData([]),
            )
            instance_id = manager.create_instance(
                {
                    "long_ticker": "TQQQ",
                    "short_ticker": "SQQQ",
                }
            )["id"]

            updated = manager.update_instance_strategy(
                instance_id,
                {"strategy_id": "rsi_rotation", "profit_take_percent": 7},
            )

            self.assertEqual(updated["strategy_id"], "rsi_rotation")
            self.assertEqual(updated["strategy"]["label"], "RSI Rotation")
            self.assertAlmostEqual(updated["profit_take_pct"], 0.07)
            self.assertEqual(updated["events"][-1]["type"], "strategy_changed")

    def test_strategy_switch_requires_stopped_flat_instance(self):
        data = FakeTradingData([_snapshot(30, rsi3=10, long_price=100, short_price=50)])
        with tempfile.TemporaryDirectory() as tmp:
            manager = TradingAutomationManager(
                settings=_settings(),
                storage_path=Path(tmp) / "trading.json",
                data_provider=data,
            )
            instance_id = manager.create_instance(
                {
                    "long_ticker": "TQQQ",
                    "short_ticker": "SQQQ",
                }
            )["id"]
            manager.poll_once(instance_id)

            with self.assertRaisesRegex(ValueError, "Close the open position"):
                manager.update_instance_strategy(instance_id, {"strategy_id": "rsi_rotation"})

    def test_rsi_rotation_does_not_take_profit_before_rsi_rotation_signal(self):
        data = FakeTradingData(
            [
                _snapshot(30, rsi3=10, long_price=100, short_price=50),
                _snapshot(33, rsi3=50, long_price=105, short_price=49),
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            manager = TradingAutomationManager(
                settings=_settings(),
                storage_path=Path(tmp) / "trading.json",
                data_provider=data,
            )
            instance_id = manager.create_instance(
                {
                    "long_ticker": "TQQQ",
                    "short_ticker": "SQQQ",
                }
            )["id"]
            manager.update_instance_strategy(instance_id, {"strategy_id": "rsi_rotation"})

            manager.poll_once(instance_id)
            result = manager.poll_once(instance_id)

            self.assertIsNotNone(result["positions"]["long"])
            self.assertEqual(result["metrics"]["trade_count"], 0)
            self.assertFalse(result["strategy_state"]["profit_take_enabled"])

    def test_profit_take_percent_is_instance_parameter(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = TradingAutomationManager(
                settings=_settings(),
                storage_path=Path(tmp) / "trading.json",
                data_provider=FakeTradingData([]),
            )
            instance = manager.create_instance(
                {
                    "strategy_id": "rsi_extreme",
                    "long_ticker": "TQQQ",
                    "short_ticker": "SQQQ",
                    "profit_take_percent": 6,
                }
            )

            self.assertAlmostEqual(instance["profit_take_pct"], 0.06)
            self.assertAlmostEqual(instance["strategy_state"]["profit_take_pct"], 0.06)

    def test_backtest_runs_against_backtest_rsi_without_mutating_live_instance(self):
        data = FakeBacktestData(
            [
                _backtest_point(0, rsi=10, long_price=100, short_price=50),
                _backtest_point(1, rsi=90, long_price=110, short_price=45),
                _backtest_point(2, rsi=50, long_price=112, short_price=47),
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            manager = TradingAutomationManager(
                settings=_settings(),
                storage_path=Path(tmp) / "trading.json",
                data_provider=data,
            )
            instance_id = manager.create_instance(
                {
                    "strategy_id": "rsi_extreme",
                    "long_ticker": "TQQQ",
                    "short_ticker": "SQQQ",
                    "notional_per_leg": 1000,
                    "profit_take_percent": 50,
                }
            )["id"]

            result = manager.backtest_instance(
                instance_id,
                {"start": "2026-06-15T09:30", "end": "2026-06-15T09:39"},
            )
            live = manager.get_instance(instance_id)

            self.assertEqual(result["point_count"], 3)
            self.assertEqual(result["metrics"]["trade_count"], 1)
            self.assertGreater(result["final_pnl"], 90)
            self.assertIsNotNone(result["positions"]["short"])
            self.assertIn("open", [event["type"] for event in result["operations"]])
            self.assertIn("close", [event["type"] for event in result["operations"]])
            self.assertEqual([marker["type"] for marker in result["markers"]], ["buy", "sell", "buy"])
            self.assertEqual(result["markers"][0]["ticker"], "TQQQ")
            self.assertEqual(result["markers"][0]["rsi"], 10)
            self.assertEqual(data.calls[0]["rsi_period"], 6)
            self.assertEqual(data.calls[0]["rsi_interval"], "3m")
            self.assertIsNone(live["positions"]["long"])
            self.assertIsNone(live["positions"]["short"])
            self.assertEqual(live["metrics"]["trade_count"], 0)

    def test_backtest_can_override_strategy_for_same_pair_without_mutating_live_selection(self):
        data = FakeBacktestData(
            [
                _backtest_point(0, rsi=10, long_price=100, short_price=50),
                _backtest_point(1, rsi=50, long_price=105, short_price=49),
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            manager = TradingAutomationManager(
                settings=_settings(),
                storage_path=Path(tmp) / "trading.json",
                data_provider=data,
            )
            instance_id = manager.create_instance(
                {
                    "long_ticker": "TQQQ",
                    "short_ticker": "SQQQ",
                    "notional_per_leg": 1000,
                }
            )["id"]

            result = manager.backtest_instance(
                instance_id,
                {
                    "start": "2026-06-15T09:30",
                    "end": "2026-06-15T09:39",
                    "strategy_id": "rsi_rotation",
                },
            )
            live = manager.get_instance(instance_id)

            self.assertEqual(result["strategy_id"], "rsi_rotation")
            self.assertEqual(result["metrics"]["trade_count"], 0)
            self.assertIsNotNone(result["positions"]["long"])
            self.assertEqual(live["strategy_id"], "rsi_extreme")

    def test_multi_day_backtest_returns_daily_results_and_period_win_rate(self):
        data = FakeBacktestData(
            [
                _backtest_point(0, rsi=10, long_price=100, short_price=50, day="2026-06-15"),
                _backtest_point(1, rsi=90, long_price=110, short_price=45, day="2026-06-15"),
                _backtest_point(0, rsi=10, long_price=100, short_price=50, day="2026-06-16"),
                _backtest_point(1, rsi=90, long_price=90, short_price=55, day="2026-06-16"),
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            manager = TradingAutomationManager(
                settings=_settings(),
                storage_path=Path(tmp) / "trading.json",
                data_provider=data,
            )
            instance_id = manager.create_instance(
                {
                    "strategy_id": "rsi_extreme",
                    "long_ticker": "TQQQ",
                    "short_ticker": "SQQQ",
                    "notional_per_leg": 1000,
                    "profit_take_percent": 50,
                }
            )["id"]

            result = manager.backtest_instance(
                instance_id,
                {"start": "2026-06-15T09:30", "end": "2026-06-17T16:00"},
            )

            self.assertEqual(len(data.calls), 1)
            self.assertEqual([item["date"] for item in result["daily_results"]], ["2026-06-15", "2026-06-16"])
            self.assertEqual([item["outcome"] for item in result["daily_results"]], ["win", "loss"])
            self.assertEqual(result["period_metrics"]["winning_days"], 1)
            self.assertEqual(result["period_metrics"]["losing_days"], 1)
            self.assertEqual(result["period_metrics"]["flat_days"], 0)
            self.assertEqual(result["period_metrics"]["win_rate"], 0.5)
            self.assertEqual(result["period_metrics"]["day_count"], 2)
            self.assertEqual(result["no_data_dates"], ["2026-06-17"])
            self.assertEqual(result["metrics"]["trade_count"], 2)
            self.assertEqual(result["point_count"], 4)
            self.assertEqual(result["daily_results"][0]["metrics"]["trade_count"], 1)
            self.assertEqual(result["daily_results"][1]["metrics"]["trade_count"], 1)
            saved = manager.get_instance(instance_id)["strategy_performance"]["rsi_extreme"]
            self.assertEqual(saved["day_count"], 2)
            self.assertEqual(saved["winning_days"], 1)
            self.assertEqual(saved["losing_days"], 1)
            self.assertEqual(saved["day_win_rate"], 0.5)
            self.assertEqual(saved["trade_count"], 2)

    def test_multi_day_backtest_rejects_ranges_over_sixty_two_days(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = TradingAutomationManager(
                settings=_settings(),
                storage_path=Path(tmp) / "trading.json",
                data_provider=FakeBacktestData([]),
            )
            instance_id = manager.create_instance(
                {
                    "strategy_id": "rsi_extreme",
                    "long_ticker": "TQQQ",
                    "short_ticker": "SQQQ",
                }
            )["id"]

            with self.assertRaisesRegex(ValueError, "limited to 62 days"):
                manager.backtest_instance(
                    instance_id,
                    {"start": "2026-01-01T09:30", "end": "2026-03-15T16:00"},
                )

    def test_backtest_rsi_uses_direct_three_minute_rows_when_available(self):
        start = datetime.fromisoformat("2026-06-15T09:30:00")
        one_minute_rows = [_kline_row(start + timedelta(minutes=index), 100 + index) for index in range(21)]
        three_minute_rows = [
            _kline_row(start + timedelta(minutes=index * 3), close)
            for index, close in enumerate([100, 100, 100, 100, 100, 100, 80])
        ]

        points = backtest_points_from_rows(
            signal_ticker="RKLB",
            long_ticker="RKLX",
            short_ticker="RKLZ",
            rows_by_ticker={
                "RKLB": one_minute_rows,
                "RKLX": one_minute_rows,
                "RKLZ": one_minute_rows,
            },
            rsi_rows=three_minute_rows,
            rsi_input_label="Futu K_3M history",
            rsi_input_source="futu_k_3m_history",
            start=start,
            end=start + timedelta(minutes=20),
            rsi_period=6,
            rsi_interval="3m",
        )

        point_by_time = {point["time"]: point for point in points}
        ready = point_by_time["2026-06-15T09:48:00"]
        self.assertEqual(ready["rsi"], 0.0)
        self.assertEqual(ready["rsi_label"], "RSI1(6)")
        self.assertEqual(ready["rsi_interval"], "3m")
        self.assertEqual(ready["rsi_source"], "futu_style_rsi1_3m_from_futu_k_3m_history")
        self.assertEqual(ready["source_label"], "Futu K_3M history RSI1(6)")

    def test_closed_trades_persist_after_manager_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage_path = Path(tmp) / "trading.json"
            manager = TradingAutomationManager(
                settings=_settings(),
                storage_path=storage_path,
                data_provider=FakeTradingData(
                    [
                        _snapshot(30, rsi3=10, long_price=100, short_price=50),
                        _snapshot(33, rsi3=90, long_price=110, short_price=45),
                    ]
                ),
            )
            instance_id = manager.create_instance(
                {
                    "strategy_id": "rsi_extreme",
                    "long_ticker": "TQQQ",
                    "short_ticker": "SQQQ",
                    "notional_per_leg": 1000,
                }
            )["id"]
            manager.poll_once(instance_id)
            closed = manager.poll_once(instance_id)
            self.assertEqual(closed["metrics"]["trade_count"], 1)
            self.assertIsNone(closed["positions"]["long"])
            self.assertIsNone(closed["positions"]["short"])
            self.assertEqual(closed["trades"][0]["reason"], "rsi_extreme_profit_take")

            reloaded = TradingAutomationManager(
                settings=_settings(),
                storage_path=storage_path,
                data_provider=FakeTradingData([]),
            ).get_instance(instance_id)

            self.assertEqual(reloaded["metrics"]["trade_count"], 1)
            self.assertEqual(len(reloaded["trades"]), 1)
            self.assertEqual(reloaded["trades"][0]["reason"], "rsi_extreme_profit_take")
            self.assertGreater(reloaded["metrics"]["realized_pnl"], 0)

    def test_instances_persist_through_db_store(self):
        store = FakeTradingStore()
        with tempfile.TemporaryDirectory() as tmp:
            storage_path = Path(tmp) / "unused.json"
            manager = TradingAutomationManager(
                settings=_settings(),
                storage_path=storage_path,
                db_store=store,
                data_provider=FakeTradingData(
                    [
                        _snapshot(30, rsi3=10, long_price=100, short_price=50),
                        _snapshot(33, rsi3=90, long_price=110, short_price=45),
                    ]
                ),
            )
            instance_id = manager.create_instance(
                {
                    "strategy_id": "rsi_extreme",
                    "long_ticker": "TQQQ",
                    "short_ticker": "SQQQ",
                    "notional_per_leg": 1000,
                }
            )["id"]
            manager.poll_once(instance_id)
            manager.poll_once(instance_id)

            reloaded = TradingAutomationManager(
                settings=_settings(),
                storage_path=storage_path,
                db_store=store,
                data_provider=FakeTradingData([]),
            ).get_instance(instance_id)

            self.assertEqual(reloaded["metrics"]["trade_count"], 1)
            self.assertEqual(len(reloaded["trades"]), 1)
            self.assertEqual(reloaded["trades"][0]["reason"], "rsi_extreme_profit_take")
            self.assertFalse(storage_path.exists())

            manager.delete_instance(instance_id)
            self.assertEqual(store.deleted, [instance_id])
            self.assertEqual(store.instances, [])

    def test_rsi_extreme_profit_takes_at_default_four_percent_without_waiting_for_rsi_80(self):
        data = FakeTradingData(
            [
                _snapshot(30, rsi3=10, long_price=100, short_price=50),
                _snapshot(33, rsi3=50, long_price=101, short_price=49.8),
                _snapshot(36, rsi3=50, long_price=104.5, short_price=49.5),
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            manager = TradingAutomationManager(
                settings=_settings(),
                storage_path=Path(tmp) / "trading.json",
                data_provider=data,
            )
            instance = manager.create_instance(
                {
                    "strategy_id": "rsi_extreme",
                    "long_ticker": "TQQQ",
                    "short_ticker": "SQQQ",
                    "notional_per_leg": 1000,
                }
            )["id"]

            result = None
            for _ in range(3):
                result = manager.poll_once(instance)

            self.assertIsNone(result["positions"]["long"])
            self.assertIsNone(result["positions"]["short"])
            self.assertEqual(result["metrics"]["trade_count"], 1)
            self.assertEqual(result["trades"][0]["reason"], "rsi_extreme_profit_take")
            self.assertGreater(result["metrics"]["realized_pnl"], 40)

    def test_rsi_extreme_profit_takes_before_overbought_rotation(self):
        data = FakeTradingData(
            [
                _snapshot(30, rsi3=10, long_price=100, short_price=50),
                _snapshot(33, rsi3=90, long_price=105, short_price=47),
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            manager = TradingAutomationManager(
                settings=_settings(),
                storage_path=Path(tmp) / "trading.json",
                data_provider=data,
            )
            instance = manager.create_instance(
                {
                    "strategy_id": "rsi_extreme",
                    "long_ticker": "TQQQ",
                    "short_ticker": "SQQQ",
                    "notional_per_leg": 1000,
                }
            )["id"]

            manager.poll_once(instance)
            result = manager.poll_once(instance)

            self.assertIsNone(result["positions"]["long"])
            self.assertIsNone(result["positions"]["short"])
            self.assertEqual(result["metrics"]["trade_count"], 1)
            self.assertEqual(result["trades"][0]["reason"], "rsi_extreme_profit_take")


if __name__ == "__main__":
    unittest.main()
