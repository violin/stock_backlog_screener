import json
import tempfile
import unittest
from pathlib import Path

from backlog_screener.company_official import CompanyOfficialClient, extract_official_page


class CompanyOfficialTests(unittest.TestCase):
    def test_loads_configured_sources_for_ticker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "sources.json"
            config_path.write_text(
                json.dumps(
                    {
                        "TEST": [
                            {
                                "label": "Test IR",
                                "url": "https://example.com/news",
                                "type": "ir_news",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            client = CompanyOfficialClient(root / "cache", config_path=config_path)
            sources = client.sources_for_ticker("test")

        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["source_key"], "company_official")
        self.assertEqual(sources[0]["label"], "Test IR")

    def test_extracts_title_description_and_keyword_highlights(self):
        page = extract_official_page(
            """
            <html>
              <head>
                <title>Example Newsroom</title>
                <meta name="description" content="Official company news" />
              </head>
              <body>
                <article>
                  The company announced a new customer contract for a data center platform.
                  Management expects production qualification later this year.
                </article>
              </body>
            </html>
            """,
            url="https://example.com/news",
            label="Example",
            source_type="company_news",
        )

        self.assertEqual(page["title"], "Example Newsroom")
        self.assertEqual(page["description"], "Official company news")
        self.assertTrue(page["text_checksum"])
        self.assertGreaterEqual(len(page["highlights"]), 1)
        self.assertIn("contract", {item["term"] for item in page["highlights"]})


if __name__ == "__main__":
    unittest.main()
