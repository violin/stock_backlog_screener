import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backlog_screener.sec import (
    FilingRef,
    SecClient,
    analyze_beneficial_ownership,
    analyze_proxy_ownership,
    latest_financial_quality,
    latest_quarterly_revenue_yoy,
)


class SecOwnershipParsingTests(unittest.TestCase):
    def test_latest_filings_matches_schedule_13g_alias(self):
        with TemporaryDirectory() as tmp_dir:
            client = SecClient(Path(tmp_dir))
            client.cik_for_ticker = lambda ticker: "0000000001"
            client._get_json = lambda url, cache_path, max_age_seconds: {
                "filings": {
                    "recent": {
                        "form": ["SCHEDULE 13G/A", "6-K"],
                        "accessionNumber": ["0000000001-26-000001", "0000000001-26-000002"],
                        "filingDate": ["2026-05-20", "2026-05-18"],
                        "primaryDocument": ["schedule13g.htm", "form6k.htm"],
                    }
                }
            }

            filings = client.latest_filings("TEST", forms=("SC 13G/A",), limit=2)

            self.assertEqual(len(filings), 1)
            self.assertEqual(filings[0].form, "SCHEDULE 13G/A")

    def test_schedule_13g_xml_class_percent_is_ownership_signal(self):
        filing = FilingRef(
            cik="0000000001",
            accession="0000000001-26-000001",
            form="SCHEDULE 13G/A",
            filing_date="2026-05-20",
            primary_document="primary_doc.xml",
        )
        analysis = analyze_beneficial_ownership(
            [
                (
                    filing,
                    """<?xml version=\"1.0\"?><edgarSubmission xmlns=\"http://www.sec.gov/edgar/schedule13g\">
                    <formData><coverPageHeaderReportingPersonDetails>
                    <reportingPersonBeneficiallyOwnedAggregateNumberOfShares>19047620</reportingPersonBeneficiallyOwnedAggregateNumberOfShares>
                    <classPercent>11.0</classPercent>
                    </coverPageHeaderReportingPersonDetails></formData></edgarSubmission>""",
                )
            ]
        )

        self.assertEqual(analysis["filing_count"], 1)
        self.assertAlmostEqual(analysis["max_reported_percent"], 0.11)

    def test_ifrs_annual_companyfacts_feed_growth_and_quality(self):
        facts = {
            "facts": {
                "ifrs-full": {
                    "Revenue": {
                        "units": {
                            "USD": [
                                {
                                    "form": "20-F",
                                    "fp": "FY",
                                    "fy": 2024,
                                    "frame": "CY2024",
                                    "start": "2024-01-01",
                                    "end": "2024-12-31",
                                    "filed": "2025-03-31",
                                    "val": 100,
                                },
                                {
                                    "form": "20-F",
                                    "fp": "FY",
                                    "fy": 2025,
                                    "frame": "CY2025",
                                    "start": "2025-01-01",
                                    "end": "2025-12-31",
                                    "filed": "2026-03-31",
                                    "val": 150,
                                },
                            ]
                        }
                    },
                    "ProfitLoss": {
                        "units": {
                            "USD": [
                                {
                                    "form": "20-F",
                                    "fp": "FY",
                                    "fy": 2025,
                                    "frame": "CY2025",
                                    "start": "2025-01-01",
                                    "end": "2025-12-31",
                                    "filed": "2026-03-31",
                                    "val": 30,
                                }
                            ]
                        }
                    },
                    "CashFlowsFromUsedInOperatingActivities": {
                        "units": {
                            "USD": [
                                {
                                    "form": "20-F",
                                    "fp": "FY",
                                    "fy": 2025,
                                    "frame": "CY2025",
                                    "start": "2025-01-01",
                                    "end": "2025-12-31",
                                    "filed": "2026-03-31",
                                    "val": 40,
                                }
                            ]
                        }
                    },
                    "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities": {
                        "units": {
                            "USD": [
                                {
                                    "form": "20-F",
                                    "fp": "FY",
                                    "fy": 2025,
                                    "frame": "CY2025",
                                    "start": "2025-01-01",
                                    "end": "2025-12-31",
                                    "filed": "2026-03-31",
                                    "val": 10,
                                }
                            ]
                        }
                    },
                    "Assets": {"units": {"USD": [{"form": "20-F", "fp": "FY", "fy": 2025, "frame": "CY2025Q4I", "end": "2025-12-31", "filed": "2026-03-31", "val": 400}]}},
                    "Liabilities": {"units": {"USD": [{"form": "20-F", "fp": "FY", "fy": 2025, "frame": "CY2025Q4I", "end": "2025-12-31", "filed": "2026-03-31", "val": 120}]}},
                    "Equity": {"units": {"USD": [{"form": "20-F", "fp": "FY", "fy": 2025, "frame": "CY2025Q4I", "end": "2025-12-31", "filed": "2026-03-31", "val": 280}]}},
                }
            }
        }

        revenue = latest_quarterly_revenue_yoy(facts)
        quality = latest_financial_quality(facts)

        self.assertEqual(revenue["period_type"], "annual")
        self.assertAlmostEqual(revenue["value"], 0.5)
        self.assertAlmostEqual(quality["net_margin"], 0.2)
        self.assertAlmostEqual(quality["free_cash_flow_margin"], 0.2)
        self.assertAlmostEqual(quality["liabilities_to_assets"], 0.3)

    def test_ifrs_quarterly_companyfacts_ignore_ytd_6k_values(self):
        facts = {
            "facts": {
                "ifrs-full": {
                    "Revenue": {
                        "units": {
                            "USD": [
                                {
                                    "form": "6-K",
                                    "fp": "Q3",
                                    "fy": 2024,
                                    "frame": None,
                                    "start": "2024-01-01",
                                    "end": "2024-09-30",
                                    "filed": "2024-11-01",
                                    "val": 260,
                                },
                                {
                                    "form": "6-K",
                                    "fp": "Q3",
                                    "fy": 2024,
                                    "frame": "CY2024Q3",
                                    "start": "2024-07-01",
                                    "end": "2024-09-30",
                                    "filed": "2024-11-01",
                                    "val": 100,
                                },
                                {
                                    "form": "6-K",
                                    "fp": "Q3",
                                    "fy": 2025,
                                    "frame": "CY2025Q3",
                                    "start": "2025-07-01",
                                    "end": "2025-09-30",
                                    "filed": "2025-11-01",
                                    "val": 150,
                                },
                            ]
                        }
                    }
                }
            }
        }

        revenue = latest_quarterly_revenue_yoy(facts)

        self.assertEqual(revenue["period_type"], "quarterly")
        self.assertAlmostEqual(revenue["value"], 0.5)

    def test_proxy_ownership_ignores_operating_percentages_without_ownership_section(self):
        filing = FilingRef(
            cik="0000000001",
            accession="0000000001-26-000001",
            form="10-K",
            filing_date="2026-02-01",
            primary_document="test.htm",
        )
        analysis = analyze_proxy_ownership(
            [
                (
                    filing,
                    "The top four customers accounted for 79% of revenue. "
                    "Gross margins were approximately 4% in the segment.",
                )
            ]
        )
        self.assertEqual(analysis["filing_count"], 0)
        self.assertIsNone(analysis["top_holder_percent"])

    def test_proxy_ownership_ignores_governance_percentages_inside_proxy(self):
        filing = FilingRef(
            cik="0000000001",
            accession="0000000001-26-000001",
            form="DEF 14A",
            filing_date="2026-03-01",
            primary_document="proxy.htm",
        )
        analysis = analyze_proxy_ownership(
            [
                (
                    filing,
                    "Security Ownership of Certain Beneficial Owners and Management. "
                    "Since a director departure, 75% of directors were appointed recently.",
                )
            ]
        )
        self.assertEqual(analysis["filing_count"], 1)
        self.assertIsNone(analysis["top_holder_percent"])

    def test_proxy_ownership_extracts_management_group_percent(self):
        filing = FilingRef(
            cik="0000000001",
            accession="0000000001-26-000001",
            form="DEF 14A",
            filing_date="2026-03-01",
            primary_document="proxy.htm",
        )
        analysis = analyze_proxy_ownership(
            [
                (
                    filing,
                    "Security Ownership of Certain Beneficial Owners and Management. "
                    "All directors and executive officers as a group beneficially owned 6.7% "
                    "of the outstanding shares.",
                )
            ]
        )
        self.assertEqual(analysis["filing_count"], 1)
        self.assertAlmostEqual(analysis["management_group_percent"], 0.067)


if __name__ == "__main__":
    unittest.main()
