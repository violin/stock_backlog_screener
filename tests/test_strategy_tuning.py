import unittest

import pandas as pd

from backlog_screener.strategy_research import RuleCondition
from backlog_screener.strategy_tuning import RuleStrategySpec, tune_individual_strategy


class StrategyTuningTests(unittest.TestCase):
    def test_rejects_when_training_has_too_few_trades(self):
        frame = pd.DataFrame(
            {
                "date": ["2026-06-15"] * 8 + ["2026-06-16"] * 8,
                "time": pd.date_range("2026-06-15 09:30", periods=16, freq="3min"),
                "open": [100] * 16,
                "high": [101] * 16,
                "low": [99] * 16,
                "close": [100] * 16,
                "rsi6": [10] + [50] * 15,
            }
        )
        spec = RuleStrategySpec(
            id="small",
            label="Small",
            direction="long",
            conditions=(RuleCondition("rsi6", "<=", 20),),
            mechanism="test",
            entry_neighbor_rate=1.0,
        )

        result = tune_individual_strategy(frame, spec)

        self.assertEqual(result["status"], "reject")
