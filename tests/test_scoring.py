import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backlog_screener.config import ScreenThresholds
from backlog_screener.models import CandidateMetrics
from backlog_screener.scoring import evaluate_candidate
from backlog_screener.sec import extract_backlog_amounts, scan_text_for_backlog
from backlog_screener.yahoo import _cache_path, _read_cached_metrics, _write_cached_metrics


class ScoringTests(unittest.TestCase):
    def test_candidate_passes_when_all_signals_exist(self):
        metrics = CandidateMetrics(
            ticker="TEST",
            market_cap=1_000_000_000,
            institutional_ownership=0.7,
            insider_ownership=0.08,
            quarterly_revenue_yoy=0.35,
            trailing_pe=20,
            backlog_mentions=2,
        )
        result = evaluate_candidate(metrics, ScreenThresholds())
        self.assertTrue(result.financial_passed)
        self.assertTrue(result.passed)
        self.assertGreater(result.score, 80)

    def test_missing_backlog_blocks_final_pass(self):
        metrics = CandidateMetrics(
            ticker="TEST",
            market_cap=1_000_000_000,
            institutional_ownership=0.7,
            insider_ownership=0.08,
            quarterly_revenue_yoy=0.35,
            trailing_pe=20,
        )
        result = evaluate_candidate(metrics, ScreenThresholds())
        self.assertTrue(result.financial_passed)
        self.assertFalse(result.passed)

    def test_backlog_text_scan_counts_terms(self):
        text = "The company backlog increased. Remaining performance obligations also increased. RPO was higher."
        backlog, rpo, snippets = scan_text_for_backlog(
            text,
            ["backlog", "remaining performance obligation", "RPO"],
        )
        self.assertEqual(backlog, 1)
        self.assertEqual(rpo, 2)
        self.assertTrue(snippets)

    def test_backlog_amount_extraction(self):
        text = "Total backlog was $1.2 billion at quarter end. Remaining performance obligations were $450 million."
        amounts = extract_backlog_amounts(text)
        values = [item["value"] for item in amounts]
        self.assertIn(1_200_000_000, values)
        self.assertIn(450_000_000, values)

    def test_yfinance_metric_cache_round_trip(self):
        with TemporaryDirectory() as tmp_dir:
            metrics = CandidateMetrics(ticker="TEST", market_cap=1_000_000_000, trailing_pe=18.5)
            path = _cache_path(Path(tmp_dir), "TEST")
            _write_cached_metrics(path, metrics)
            cached = _read_cached_metrics(path, max_age_seconds=3600)
            self.assertIsNotNone(cached)
            self.assertEqual(cached.ticker, "TEST")
            self.assertEqual(cached.market_cap, 1_000_000_000)


if __name__ == "__main__":
    unittest.main()
