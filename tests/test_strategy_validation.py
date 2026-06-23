import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from backlog_screener.strategy_research import RuleCondition
from backlog_screener.strategy_validation import (
    FixedStrategy,
    signal_overlap,
    write_fixed_validation_report,
)


class StrategyValidationTests(unittest.TestCase):
    def test_signal_overlap_reports_intersection(self):
        frame = pd.DataFrame({"x": [1, 2, 3], "y": [1, 0, 1]})
        left = FixedStrategy(
            "left", "Left", "long", (RuleCondition("x", ">=", 2),),
            0.02, 0.01, 5, 2, 2, "left",
        )
        right = FixedStrategy(
            "right", "Right", "long", (RuleCondition("y", ">=", 1),),
            0.02, 0.01, 5, 2, 2, "right",
        )

        overlap = signal_overlap(frame, left, right)

        self.assertEqual(overlap["overlap_signal_bars"], 1)
        self.assertAlmostEqual(overlap["jaccard"], 1 / 3)

    def test_report_includes_transfer_scope_and_ticker_overlap(self):
        payload = {
            "title": "Transfer",
            "generated_at": "2026-06-23",
            "interpretation": "Ticker-specific diagnostic only.",
            "ticker_overlaps": {
                "TEST": {
                    "overlap_signal_bars": 3,
                    "overlap_vs_left": 0.5,
                    "overlap_vs_right": 0.75,
                }
            },
            "strategies": [],
        }
        with TemporaryDirectory() as directory:
            paths = write_fixed_validation_report(
                payload,
                output_dir=Path(directory),
                stem="transfer",
            )
            markdown = Path(paths["markdown"]).read_text(encoding="utf-8")

        self.assertIn("## Test Scope", markdown)
        self.assertIn("Ticker-specific diagnostic only.", markdown)
        self.assertIn("TEST: 3 overlapping bars", markdown)
