import unittest

from backlog_screener.intraday import intraday_payload, normalize_intraday_rows


class IntradayIndicatorTests(unittest.TestCase):
    def test_intraday_payload_computes_hot_volume_signal(self):
        rows = []
        for minute in range(30):
            close = 10 + minute * 0.1
            rows.append(
                {
                    "time_key": f"2026-06-10 09:{minute:02d}:00",
                    "open": close - 0.03,
                    "high": close + 0.05,
                    "low": close - 0.05,
                    "close": close,
                    "volume": 20_000 if minute < 29 else 80_000,
                }
            )

        payload = intraday_payload(ticker="TEST", code="US.TEST", rows=rows, tracking=True)
        indicators = payload["indicators"]

        self.assertEqual(payload["interval"], "1m")
        self.assertEqual(payload["point_count"], 30)
        self.assertGreater(indicators["rsi14"], 70)
        self.assertGreater(indicators["kdj"]["k"], 80)
        self.assertGreater(indicators["vwap"], 0)
        self.assertEqual(indicators["ema"]["state"], "bullish")
        self.assertEqual(indicators["opening_range"]["state"], "above")
        self.assertIn(indicators["atr"]["state"], {"compressed", "tradable", "wide"})
        self.assertEqual(indicators["signal"]["bias"], "strong_long_bias")
        self.assertEqual(indicators["volume"]["state"], "spike")
        self.assertIn("overbought", indicators["signal"]["tags"])
        self.assertTrue(any(rule["id"] == "vwap_hold" and rule["status"] == "pass" for rule in indicators["signal"]["rules"]))

    def test_normalize_intraday_rows_sorts_and_drops_missing_close(self):
        points = normalize_intraday_rows(
            [
                {"time_key": "2026-06-10 09:31:00", "close": 11, "high": 12, "low": 10},
                {"time_key": "2026-06-10 09:30:00", "close": None},
                {"time_key": "2026-06-10 09:29:00", "close": 10},
            ]
        )

        self.assertEqual([point["time"] for point in points], ["2026-06-10 09:29:00", "2026-06-10 09:31:00"])
        self.assertEqual(points[0]["high"], 10)
        self.assertEqual(points[0]["low"], 10)


if __name__ == "__main__":
    unittest.main()
