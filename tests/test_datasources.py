import unittest

from backlog_screener.datasources import (
    source_payload,
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

    def test_datasource_payload_includes_bilingual_purpose(self):
        payload = source_payload(source_definition("usaspending"))
        metadata = payload["metadata"]

        self.assertIn("purpose_en", metadata)
        self.assertIn("purpose_zh", metadata)
        self.assertIn("政府", metadata["purpose_zh"])

    def test_rdw_priority_highlights_contract_and_official_sources(self):
        priorities = {
            key: source_payload(source_definition(key))["metadata"]["rdw_priority"]
            for key in ("company_official", "sec_edgar", "sec_companyfacts", "usaspending", "launch_library")
        }

        self.assertEqual(priorities["company_official"], 1)
        self.assertEqual(priorities["sec_edgar"], 1)
        self.assertEqual(priorities["sec_companyfacts"], 1)
        self.assertEqual(priorities["usaspending"], 1)
        self.assertEqual(priorities["launch_library"], 2)


if __name__ == "__main__":
    unittest.main()
