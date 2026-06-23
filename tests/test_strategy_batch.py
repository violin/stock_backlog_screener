import unittest

from backlog_screener.strategy_batch import compare_strategy_research


def _candidate(ticker_return, train_return, *, candidate_id="orb-long", pf=1.4):
    metrics = {
        "trades": 20,
        "winning_trades": 12,
        "win_rate": 0.6,
        "win_rate_wilson_lower": 0.39,
        "total_net_return": ticker_return,
        "profit_factor": pf,
        "max_drawdown": -0.02,
        "active_days": 10,
        "profitable_day_rate": 0.6,
        "trades_per_active_day": 2.0,
        "largest_day_abs_pnl_share": 0.2,
    }
    train = dict(metrics, total_net_return=train_return)
    return {
        "id": candidate_id,
        "family": "opening_range_breakout",
        "label": "Opening Range Breakout (long)",
        "direction": "long",
        "params": {"opening_minutes": 15},
        "mechanism": "breakout",
        "evidence": "paper",
        "status": "candidate",
        "score": 1.0,
        "family_parameter_stability": 0.5,
        "train": train,
        "test": metrics,
        "walk_forward": {
            "fold_count": 4,
            "positive_folds": 3,
            "positive_fold_rate": 0.75,
            "total_net_return": ticker_return,
        },
    }


class StrategyBatchTests(unittest.TestCase):
    def test_marks_variant_portable_when_all_tickers_are_positive(self):
        research = {
            ticker: {
                "dates": ["2026-01-01", "2026-06-01"],
                "rows": 100,
                "stock_profile": {"eligible": True},
                "industry_strategies": {"candidates": [_candidate(0.04, 0.03)]},
            }
            for ticker in ("CRDO", "SPCX", "AAOI")
        }

        result = compare_strategy_research(research)

        self.assertEqual(result["portable_candidates"][0]["portability"], "portable_candidate")
        self.assertEqual(result["portable_candidates"][0]["positive_train_test_tickers"], 3)

    def test_marks_one_stock_fit_as_ticker_specific(self):
        research = {
            "CRDO": {
                "dates": ["2026-01-01"],
                "rows": 100,
                "stock_profile": {"eligible": True},
                "industry_strategies": {"candidates": [_candidate(0.04, 0.03)]},
            },
            "SPCX": {
                "dates": ["2026-01-01"],
                "rows": 100,
                "stock_profile": {"eligible": True},
                "industry_strategies": {"candidates": [_candidate(-0.02, 0.03)]},
            },
            "AAOI": {
                "dates": ["2026-01-01"],
                "rows": 100,
                "stock_profile": {"eligible": True},
                "industry_strategies": {"candidates": [_candidate(-0.01, -0.01)]},
            },
        }

        result = compare_strategy_research(research)

        self.assertEqual(result["portable_candidates"][0]["portability"], "ticker_specific")

    def test_excludes_insufficient_history_from_portability_denominator(self):
        research = {
            "CRDO": {
                "dates": ["2026-01-01"],
                "rows": 100,
                "stock_profile": {"eligible": True},
                "industry_strategies": {"candidates": [_candidate(0.04, 0.03)]},
            },
            "SPCX": {
                "dates": ["2026-06-01"],
                "rows": 20,
                "stock_profile": {"eligible": False, "reasons": ["fewer than 60 sessions"]},
                "industry_strategies": {"candidates": [_candidate(0.08, 0.08)]},
            },
        }

        result = compare_strategy_research(research)

        self.assertEqual(result["research_eligible_tickers"], ["CRDO"])
        self.assertEqual(result["excluded_tickers"], ["SPCX"])
        self.assertEqual(
            result["portable_candidates"][0]["portability"],
            "insufficient_cross_ticker_sample",
        )
