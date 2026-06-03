import unittest

from backlog_screener.datasources import (
    selected_source_keys,
    should_collect_source,
    source_definition,
)


class DatasourceRegistryTests(unittest.TestCase):
    def test_base_sources_are_selected_by_default(self):
        keys = selected_source_keys({"use_futu": True, "use_sec": True}, {"ticker": "TEST"})

        self.assertIn("futu_opend", keys)
        self.assertIn("sec_edgar", keys)
        self.assertIn("sec_companyfacts", keys)

    def test_sector_source_requires_request_and_applicability(self):
        config = {"use_usaspending": True}

        self.assertTrue(
            should_collect_source(
                "usaspending",
                config,
                {"ticker": "RKLB", "name": "Rocket Lab USA", "sector": "Industrials", "industry": "Aerospace & Defense"},
            )
        )
        self.assertFalse(
            should_collect_source(
                "usaspending",
                config,
                {"ticker": "CRWD", "name": "CrowdStrike", "sector": "Technology", "industry": "Software - Infrastructure"},
            )
        )
        self.assertFalse(
            should_collect_source(
                "usaspending",
                {"use_usaspending": False},
                {"ticker": "RKLB", "industry": "Aerospace & Defense"},
            )
        )

    def test_ticker_scoped_source_requires_company_metadata(self):
        config = {"use_company_official": True}

        self.assertEqual(source_definition("company_official").status, "planned")
        self.assertFalse(
            should_collect_source(
                "company_official",
                config,
                {"ticker": "TEST", "metadata": {"official_sources": ["https://example.com/news"]}},
            )
        )


if __name__ == "__main__":
    unittest.main()
