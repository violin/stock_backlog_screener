import unittest
from datetime import datetime, timedelta

import pandas as pd

from backlog_screener.strategy_research import (
    RuleCondition,
    backtest_conditions,
    build_feature_matrix,
    label_turning_zones,
    mine_threshold_rules,
    resample_intraday_rows,
)


class StrategyResearchTests(unittest.TestCase):
    def test_resamples_one_minute_rows_to_three_minute_bars(self):
        start = datetime.fromisoformat("2026-06-15T09:30:00")
        rows = []
        for index in range(6):
            price = 100 + index
            rows.append(
                {
                    "time_key": (start + timedelta(minutes=index)).isoformat(sep=" "),
                    "open": price - 0.2,
                    "high": price + 0.4,
                    "low": price - 0.5,
                    "close": price,
                    "volume": 100 + index,
                    "turnover": price * (100 + index),
                }
            )

        frame = resample_intraday_rows(rows, interval_minutes=3)

        self.assertEqual(len(frame), 2)
        self.assertEqual(frame.iloc[0]["open"], 99.8)
        self.assertEqual(frame.iloc[0]["close"], 102)
        self.assertEqual(frame.iloc[1]["close"], 105)
        self.assertEqual(frame.iloc[0]["source_rows"], 3)

    def test_feature_matrix_contains_causal_indicator_columns(self):
        start = datetime.fromisoformat("2026-06-15T09:30:00")
        rows = []
        for index in range(90):
            price = 100 + index * 0.05 + (0.4 if index % 9 < 4 else -0.2)
            rows.append(
                {
                    "time_key": (start + timedelta(minutes=index)).isoformat(sep=" "),
                    "open": price - 0.05,
                    "high": price + 0.15,
                    "low": price - 0.15,
                    "close": price,
                    "volume": 1000 + index * 3,
                }
            )

        frame = build_feature_matrix(rows, interval_minutes=3)

        self.assertEqual(len(frame), 30)
        for column in [
            "rsi6",
            "rsi14",
            "kdj_j",
            "macd_hist_delta_3",
            "bb_percent_b",
            "atr14_pct",
            "volume_ratio_20",
            "relative_volume_time_20",
            "opening_relative_volume_15",
            "gap_pct",
            "range_pos_10",
        ]:
            self.assertIn(column, frame.columns)
        self.assertTrue(frame["rsi6"].notna().any())

    def test_turning_zone_merges_flat_peak_and_flat_trough(self):
        close = [100, 102, 104, 106, 108, 108.05, 107.9, 105, 102, 101.95, 103, 105, 106]
        frame = pd.DataFrame(
            {
                "date": ["2026-06-15"] * len(close),
                "time": pd.date_range("2026-06-15 09:30", periods=len(close), freq="3min"),
                "open": close,
                "high": [value + 0.2 for value in close],
                "low": [value - 0.2 for value in close],
                "close": close,
                "atr14": [1.0] * len(close),
            }
        )

        labeled = label_turning_zones(
            frame,
            window_bars=2,
            prominence_atr=1.0,
            plateau_tolerance_atr=0.2,
            merge_gap_bars=1,
        )

        peak_rows = labeled[labeled["turn_zone"] == "peak"]
        trough_rows = labeled[labeled["turn_zone"] == "trough"]
        self.assertGreaterEqual(len(peak_rows), 2)
        self.assertGreaterEqual(len(trough_rows), 2)
        self.assertEqual(peak_rows["turn_zone_id"].nunique(), 1)
        self.assertEqual(trough_rows["turn_zone_id"].nunique(), 1)
        self.assertEqual((labeled["pivot_label"] == "peak").sum(), 1)
        self.assertEqual((labeled["pivot_label"] == "trough").sum(), 1)

    def test_rule_backtest_uses_next_bar_and_reports_frequency(self):
        times = pd.date_range("2026-06-15 09:30", periods=8, freq="3min")
        frame = pd.DataFrame(
            {
                "date": ["2026-06-15"] * 8,
                "time": times,
                "open": [100, 100, 100, 102, 102, 102, 102, 102],
                "high": [100, 100, 102, 102, 102, 102, 102, 102],
                "low": [100, 100, 99.8, 102, 102, 102, 102, 102],
                "close": [100, 100, 101.5, 102, 102, 102, 102, 102],
                "rsi6": [50, 10, 40, 50, 50, 50, 50, 50],
            }
        )

        metrics = backtest_conditions(
            frame,
            [RuleCondition("rsi6", "<=", 20)],
            target_return=0.015,
            stop_return=0.008,
            max_hold_bars=3,
            round_trip_cost=0.001,
            cooldown_bars=1,
        )

        self.assertEqual(metrics["trades"], 1)
        self.assertEqual(metrics["winning_trades"], 1)
        self.assertGreater(metrics["total_net_return"], 0)
        self.assertEqual(metrics["trades_per_active_day"], 1)

    def test_short_rule_backtest_uses_falling_price_as_profit(self):
        times = pd.date_range("2026-06-15 09:30", periods=6, freq="3min")
        frame = pd.DataFrame(
            {
                "date": ["2026-06-15"] * 6,
                "time": times,
                "open": [100, 100, 100, 98, 98, 98],
                "high": [100, 100, 100.1, 98, 98, 98],
                "low": [100, 100, 98, 98, 98, 98],
                "close": [100, 100, 98.2, 98, 98, 98],
                "rsi6": [50, 90, 60, 50, 50, 50],
            }
        )

        metrics = backtest_conditions(
            frame,
            [RuleCondition("rsi6", ">=", 80)],
            direction="short",
            target_return=0.015,
            stop_return=0.008,
            max_hold_bars=3,
            round_trip_cost=0.001,
            cooldown_bars=1,
        )

        self.assertEqual(metrics["trades"], 1)
        self.assertEqual(metrics["winning_trades"], 1)
        self.assertGreater(metrics["total_net_return"], 0)

    def test_rule_mining_reports_neighboring_threshold_stability(self):
        rows = []
        start = datetime.fromisoformat("2026-05-01T09:30:00")
        for day_index in range(12):
            day_start = start + timedelta(days=day_index)
            for bar_index in range(12):
                low_signal = bar_index in (1, 7)
                base = 100 + day_index * 0.1
                open_price = base if not low_signal else base - 1
                rows.append(
                    {
                        "date": day_start.date().isoformat(),
                        "time": day_start + timedelta(minutes=bar_index * 3),
                        "open": open_price,
                        "high": open_price * (1.02 if bar_index in (2, 8) else 1.001),
                        "low": open_price * 0.999,
                        "close": open_price * (1.018 if bar_index in (2, 8) else 1.0),
                        "rsi6": (
                            5 + day_index * 0.1 + bar_index * 0.01
                            if low_signal
                            else 45 + day_index * 0.2 + bar_index * 0.1
                        ),
                    }
                )
        result = mine_threshold_rules(
            pd.DataFrame(rows),
            feature_columns=["rsi6"],
            min_train_trades=4,
            min_test_trades=2,
            target_return=0.01,
            stop_return=0.01,
            max_hold_bars=2,
            round_trip_cost=0.0,
            cooldown_bars=0,
        )

        self.assertTrue(result["candidates"])
        self.assertIn("threshold_stability", result["candidates"][0])
        self.assertEqual(result["candidates"][0]["threshold_stability"]["evaluated_neighbors"], 3)


if __name__ == "__main__":
    unittest.main()
