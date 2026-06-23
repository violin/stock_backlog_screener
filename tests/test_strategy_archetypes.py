import unittest

import pandas as pd

from backlog_screener.strategy_archetypes import StrategyVariant, build_archetype_signal


def _variant(family, direction, params):
    return StrategyVariant(
        id="test",
        family=family,
        label="Test",
        direction=direction,
        params=params,
        target_return=0.01,
        stop_return=0.01,
        max_hold_bars=5,
        cooldown_bars=1,
        max_trades_per_day=2,
        mechanism="test",
        evidence="test",
    )


class StrategyArchetypeTests(unittest.TestCase):
    def test_opening_range_breakout_only_signals_after_range_is_complete(self):
        close = [100, 101, 102, 101, 102, 103.5, 104]
        frame = pd.DataFrame(
            {
                "date": ["2026-06-15"] * len(close),
                "time": pd.date_range("2026-06-15 09:32", periods=len(close), freq="3min"),
                "session_minute": [2, 5, 8, 11, 14, 17, 20],
                "open": close,
                "high": [value + 0.2 for value in close],
                "low": [value - 0.2 for value in close],
                "close": close,
                "volume_ratio_20": [2.0] * len(close),
                "opening_relative_volume_15": [2.0] * len(close),
                "gap_pct": [0.02] * len(close),
                "ema9": [100, 100.5, 101, 101.2, 101.5, 102, 103],
                "ema21": [99] * len(close),
            }
        )
        variant = _variant(
            "opening_range_breakout",
            "long",
            {
                "opening_minutes": 15,
                "opening_relative_volume_min": 1.0,
                "gap_min": 0.0,
                "trend_filter": True,
            },
        )

        signal = build_archetype_signal(frame, variant)

        self.assertFalse(signal.iloc[:5].any())
        self.assertTrue(signal.iloc[5])

    def test_late_day_momentum_has_one_causal_trigger_bar(self):
        rows = 121
        close = [100 + index * 0.01 for index in range(rows)]
        frame = pd.DataFrame(
            {
                "date": ["2026-06-15"] * rows,
                "time": pd.date_range("2026-06-15 09:32", periods=rows, freq="3min"),
                "session_minute": [2 + index * 3 for index in range(rows)],
                "open": [100] * rows,
                "high": [value + 0.02 for value in close],
                "low": [value - 0.02 for value in close],
                "close": close,
                "realized_vol_20": [0.01] * rows,
            }
        )
        variant = _variant(
            "late_day_intraday_momentum",
            "long",
            {"opening_return_min": 0.0005},
        )

        signal = build_archetype_signal(frame, variant)

        self.assertEqual(signal.sum(), 1)
        self.assertEqual(frame.loc[signal, "session_minute"].iloc[0], 362)
