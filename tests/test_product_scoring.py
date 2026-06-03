import unittest

from backlog_screener.product_scoring import score_hidden_champion


class ProductScoringTests(unittest.TestCase):
    def test_hidden_champion_score_uses_layered_items(self):
        items = [
            {
                "source_key": "futu_opend",
                "importance_score": 70,
                "evidence": {"market_cap": 1_800_000_000, "pe_ttm": 18.0},
            },
            {
                "source_key": "sec_companyfacts",
                "importance_score": 80,
                "evidence": {
                    "quarterly_revenue_yoy": 0.34,
                    "gross_margin": 0.42,
                    "operating_margin": 0.18,
                    "net_margin": 0.12,
                    "free_cash_flow_margin": 0.10,
                    "liabilities_to_assets": 0.48,
                    "debt_to_assets": 0.18,
                    "receivables_yoy": 0.20,
                    "inventory_yoy": 0.22,
                },
            },
            {
                "source_key": "sec_edgar",
                "importance_score": 90,
                "evidence": {
                    "backlog_mentions": 12,
                    "rpo_mentions": 5,
                    "backlog_largest_amount": 3_800_000_000,
                    "revenue": 1_500_000_000,
                },
            },
            {
                "source_key": "yfinance",
                "importance_score": 60,
                "evidence": {"institutional_ownership": 0.72, "insider_ownership": 0.07},
            },
        ]
        score = score_hidden_champion("TEST", items)
        self.assertGreaterEqual(score.total_score, 80)
        self.assertEqual(score.grade, "A")
        self.assertFalse(score.missing_dimensions)

    def test_latest_null_metric_does_not_resurrect_stale_value(self):
        items = [
            {
                "source_key": "sec_edgar",
                "created_at": "2026-05-01T00:00:00",
                "importance_score": 60,
                "evidence": {"backlog_mentions": 0, "rpo_mentions": 0, "backlog_largest_amount": 120_000_000},
            },
            {
                "source_key": "sec_edgar",
                "created_at": "2026-05-02T00:00:00",
                "importance_score": 50,
                "evidence": {"backlog_mentions": 0, "rpo_mentions": 0, "backlog_largest_amount": None},
            },
        ]
        score = score_hidden_champion("TEST", items)
        self.assertIsNone(score.component_scores["raw_metrics"]["backlog_largest_amount"])

    def test_attention_flow_rewards_quiet_accumulation_over_crowded_momentum(self):
        base_items = [
            {
                "source_key": "futu_opend",
                "importance_score": 70,
                "evidence": {"market_cap": 1_800_000_000, "pe_ttm": 18.0},
            },
            {
                "source_key": "sec_companyfacts",
                "importance_score": 80,
                "evidence": {
                    "quarterly_revenue_yoy": 0.34,
                    "gross_margin": 0.42,
                    "operating_margin": 0.18,
                    "net_margin": 0.12,
                    "free_cash_flow_margin": 0.10,
                    "liabilities_to_assets": 0.48,
                    "debt_to_assets": 0.18,
                },
            },
            {
                "source_key": "sec_edgar",
                "importance_score": 90,
                "evidence": {"backlog_mentions": 12, "rpo_mentions": 5},
            },
            {
                "source_key": "sec_proxy_ownership",
                "importance_score": 80,
                "evidence": {"insider_ownership": 0.07, "large_holder_max_percent": 0.12},
            },
        ]
        quiet = base_items + [
            {
                "source_key": "futu_opend",
                "importance_score": 72,
                "evidence": {
                    "large_buy_sell_ratio": 1.6,
                    "large_net_flow_20d": 8_000_000,
                    "return_20d": 0.06,
                    "attention_flow_label": "quiet_accumulation",
                },
            }
        ]
        crowded = base_items + [
            {
                "source_key": "futu_opend",
                "importance_score": 66,
                "evidence": {
                    "large_buy_sell_ratio": 1.6,
                    "large_net_flow_20d": 8_000_000,
                    "return_20d": 0.48,
                    "attention_flow_label": "crowded_momentum",
                },
            }
        ]

        quiet_score = score_hidden_champion("TEST", quiet)
        crowded_score = score_hidden_champion("TEST", crowded)
        self.assertGreater(quiet_score.component_scores["attention_flow"], 0)
        self.assertLess(crowded_score.component_scores["attention_flow"], 0)
        self.assertGreater(quiet_score.total_score, crowded_score.total_score)

    def test_attention_flow_does_not_reward_net_inflow_when_buy_sell_ratio_is_weak(self):
        items = [
            {
                "source_key": "futu_opend",
                "importance_score": 72,
                "evidence": {
                    "large_buy_sell_ratio": 0.55,
                    "large_net_flow_20d": 8_000_000,
                    "return_20d": -0.06,
                    "attention_flow_label": "neutral",
                },
            }
        ]

        score = score_hidden_champion("TEST", items)

        self.assertLessEqual(score.component_scores["attention_flow"], 0)

    def test_government_contracts_boost_order_quality_without_missing_penalty(self):
        base_items = [
            {
                "source_key": "futu_opend",
                "importance_score": 70,
                "evidence": {"market_cap": 1_800_000_000, "pe_ttm": 18.0},
            },
            {
                "source_key": "sec_companyfacts",
                "importance_score": 80,
                "evidence": {
                    "quarterly_revenue_yoy": 0.34,
                    "gross_margin": 0.42,
                    "operating_margin": 0.18,
                },
            },
            {
                "source_key": "sec_edgar",
                "importance_score": 72,
                "evidence": {"backlog_mentions": 1, "rpo_mentions": 0},
            },
            {
                "source_key": "sec_proxy_ownership",
                "importance_score": 80,
                "evidence": {"insider_ownership": 0.07, "large_holder_max_percent": 0.12},
            },
        ]
        gov_items = base_items + [
            {
                "source_key": "usaspending",
                "importance_score": 84,
                "evidence": {
                    "government_contract_award_count": 3,
                    "government_contract_total_value": 125_000_000,
                    "government_contract_largest_award": 90_000_000,
                    "government_contract_dod_value": 80_000_000,
                },
            }
        ]

        base_score = score_hidden_champion("TEST", base_items)
        gov_score = score_hidden_champion("TEST", gov_items)

        self.assertGreater(gov_score.component_scores["order_quality"], base_score.component_scores["order_quality"])
        self.assertEqual(gov_score.component_scores["raw_metrics"]["government_contract_award_count"], 3)


if __name__ == "__main__":
    unittest.main()
