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

    def test_launch_library_is_active_and_space_scoped(self):
        config = {"use_launch_library": True}

        self.assertEqual(source_definition("launch_library").status, "active")
        self.assertTrue(
            should_collect_source(
                "launch_library",
                config,
                {"ticker": "RDW", "name": "Redwire", "sector": "Industrials", "industry": "Aerospace & Defense"},
            )
        )
        self.assertFalse(
            should_collect_source(
                "launch_library",
                config,
                {"ticker": "CRDO", "name": "Credo Technology", "sector": "Technology", "industry": "Semiconductors"},
            )
        )
        self.assertFalse(
            should_collect_source(
                "launch_library",
                {"use_launch_library": False},
                {"ticker": "RDW", "industry": "Aerospace & Defense"},
            )
        )

    def test_openinsider_is_active_optional_source(self):
        config = {"use_openinsider": True}

        self.assertEqual(source_definition("openinsider").status, "active")
        self.assertTrue(
            should_collect_source(
                "openinsider",
                config,
                {"ticker": "CRDO", "name": "Credo Technology", "industry": "Semiconductors"},
            )
        )
        self.assertFalse(
            should_collect_source(
                "openinsider",
                {"use_openinsider": False},
                {"ticker": "CRDO", "industry": "Semiconductors"},
            )
        )

    def test_ticker_scoped_source_requires_company_metadata(self):
        config = {"use_company_official": True}

        self.assertEqual(source_definition("company_official").status, "active")
        self.assertTrue(
            should_collect_source(
                "company_official",
                config,
                {"ticker": "TEST", "metadata": {"official_sources": ["https://example.com/news"]}},
            )
        )
        self.assertTrue(
            should_collect_source(
                "company_official",
                config,
                {"ticker": "TEST", "metadata": {"official_sources": [{"url": "https://example.com/ir"}]}},
            )
        )
        self.assertFalse(should_collect_source("company_official", config, {"ticker": "TEST", "metadata": {}}))
        self.assertFalse(
            should_collect_source(
                "company_official",
                {"use_company_official": False},
                {"ticker": "TEST", "metadata": {"official_sources": ["https://example.com/news"]}},
            )
        )

    def test_datasource_payload_includes_bilingual_purpose(self):
        payload = source_payload(source_definition("usaspending"))
        metadata = payload["metadata"]

        self.assertIn("purpose_en", metadata)
        self.assertIn("purpose_zh", metadata)
        self.assertIn("政府", metadata["purpose_zh"])

    def test_summary_source_follows_configured_llm_provider(self):
        gemini_config = {"summarize": True, "llm_provider": "gemini"}
        minimax_config = {"summarize": True, "llm_provider": "minimax"}

        self.assertTrue(should_collect_source("gemini", gemini_config))
        self.assertFalse(should_collect_source("minimax", gemini_config))
        self.assertTrue(should_collect_source("minimax", minimax_config))
        self.assertFalse(should_collect_source("gemini", minimax_config))

    def test_datasource_payload_keeps_ticker_analysis_priority_out_of_generic_registry(self):
        metadata = source_payload(source_definition("company_official"))["metadata"]

        self.assertNotIn("rdw_priority", metadata)
        self.assertNotIn("rdw_priority_reason_en", metadata)
        self.assertNotIn("rdw_priority_reason_zh", metadata)
        self.assertNotIn("source_name_zh", metadata)


if __name__ == "__main__":
    unittest.main()
