import unittest

from backlog_screener.futu_provider import attention_metrics, information_from_futu_attention


class FutuProviderTransformTests(unittest.TestCase):
    def test_attention_metrics_identifies_quiet_accumulation(self):
        raw = {
            "ticker": "TEST",
            "capital_distribution": {
                "capital_in_super": 6_000_000,
                "capital_in_big": 4_000_000,
                "capital_out_super": 2_000_000,
                "capital_out_big": 3_000_000,
                "update_time": "2026-05-26 16:00:00",
            },
            "capital_flow": [
                {"super_in_flow": 100_000, "big_in_flow": 200_000, "main_in_flow": 300_000}
                for _ in range(20)
            ],
            "kline": [
                {"time_key": f"2026-04-{day:02d}", "close": 100 + day * 0.25}
                for day in range(1, 31)
            ],
        }

        metrics = attention_metrics(raw)
        item = information_from_futu_attention(raw)

        self.assertAlmostEqual(metrics["large_buy_sell_ratio"], 2.0)
        self.assertEqual(metrics["attention_flow_label"], "quiet_accumulation")
        self.assertIsNotNone(item)
        self.assertEqual(item["dimension"], "attention_flow")
        self.assertIn("主力吸筹", item["summary"])

    def test_attention_metrics_does_not_treat_weak_ratio_as_quiet_accumulation(self):
        raw = {
            "ticker": "WEAK",
            "capital_distribution": {
                "capital_in_super": 1_000_000,
                "capital_in_big": 1_000_000,
                "capital_out_super": 2_000_000,
                "capital_out_big": 2_000_000,
                "update_time": "2026-05-26 16:00:00",
            },
            "capital_flow": [
                {"super_in_flow": 500_000, "big_in_flow": 500_000, "main_in_flow": 1_000_000}
                for _ in range(20)
            ],
            "kline": [
                {"time_key": f"2026-04-{day:02d}", "close": 100 + day * 0.1}
                for day in range(1, 31)
            ],
        }

        metrics = attention_metrics(raw)

        self.assertLess(metrics["large_buy_sell_ratio"], 1)
        self.assertEqual(metrics["attention_flow_label"], "neutral")


if __name__ == "__main__":
    unittest.main()
