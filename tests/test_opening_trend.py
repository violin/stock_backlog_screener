import unittest

from backlog_screener.webapp import _opening_trend_transform_points


class OpeningTrendTransformTests(unittest.TestCase):
    def test_detrended_exponential_growth_is_near_zero(self):
        points = [
            {"date": f"2026-01-{day + 1:02d}", "close": 100 * (1.01**day)}
            for day in range(20)
        ]

        transformed, regression = _opening_trend_transform_points(points, "detrended")

        self.assertGreater(regression["r2"], 0.999)
        self.assertTrue(all(abs(point["value"]) < 1e-10 for point in transformed))

    def test_log_transform_uses_natural_log(self):
        transformed, _ = _opening_trend_transform_points(
            [{"date": "2026-01-01", "close": 100.0}],
            "log",
        )

        self.assertAlmostEqual(transformed[0]["value"], 4.605170185988092)


if __name__ == "__main__":
    unittest.main()
