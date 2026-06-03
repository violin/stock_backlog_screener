import unittest

from backlog_screener.usaspending import (
    filter_company_awards,
    parse_awards,
    recipient_match_score,
    search_query_for_company,
    summarize_government_contracts,
)


class USASpendingTransformTests(unittest.TestCase):
    def test_search_query_removes_common_company_suffixes(self):
        self.assertEqual(search_query_for_company("Powell Industries, Inc.", "POWL"), "POWELL INDUSTRIES")

    def test_recipient_match_score_uses_company_token_overlap(self):
        self.assertGreaterEqual(
            recipient_match_score("Rocket Lab USA, Inc.", "ROCKET LAB USA, INC."),
            1.0,
        )
        self.assertLess(
            recipient_match_score("Rocket Lab USA, Inc.", "General Dynamics Mission Systems"),
            0.45,
        )

    def test_parse_filter_and_summarize_awards(self):
        payload = {
            "results": [
                {
                    "Award ID": "N001",
                    "Recipient Name": "POWELL INDUSTRIES INC",
                    "Start Date": "2025-01-01",
                    "End Date": "2026-01-01",
                    "Award Amount": "12000000",
                    "Awarding Agency": "Department of Defense",
                    "Awarding Sub Agency": "Department of the Navy",
                    "Award Type": "Definitive Contract",
                    "Funding Agency": "Department of Defense",
                    "Funding Sub Agency": "Department of the Navy",
                },
                {
                    "Award ID": "N002",
                    "Recipient Name": "UNRELATED POWER SYSTEMS",
                    "Award Amount": "5000000",
                    "Awarding Agency": "Department of Energy",
                },
            ]
        }

        awards = parse_awards(payload)
        filtered = filter_company_awards(awards, company_name="Powell Industries, Inc.", ticker="POWL")
        signal = summarize_government_contracts(
            filtered,
            query="POWELL INDUSTRIES",
            start_date="2024-01-01",
            end_date="2026-01-01",
        )

        self.assertEqual(signal.award_count, 1)
        self.assertEqual(signal.total_award_amount, 12_000_000)
        self.assertEqual(signal.dod_award_amount, 12_000_000)
        self.assertEqual(signal.top_agencies[0]["agency"], "Department of Defense")


if __name__ == "__main__":
    unittest.main()
