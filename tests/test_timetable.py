import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from backlog_screener.timetable import configured_timetable_events, merge_timetable_events


class TimetableTests(unittest.TestCase):
    def test_loads_only_upcoming_configured_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "events.json"
            config_path.write_text(
                json.dumps(
                    {
                        "PL": [
                            {
                                "event_date": "2026-06-01",
                                "title": "Past event",
                                "source_key": "company_ir_calendar",
                            },
                            {
                                "event_date": "2026-09-08",
                                "title": "Estimated earnings",
                                "source_key": "company_ir_calendar",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            events = configured_timetable_events("pl", config_path=config_path, today=date(2026, 6, 6))

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["ticker"], "PL")
        self.assertEqual(events[0]["title"], "Estimated earnings")
        self.assertTrue(events[0]["configured"])

    def test_merge_prefers_higher_confidence_duplicate(self):
        stored = [
            {
                "ticker": "PL",
                "event_date": "2026-09-08",
                "title": "Estimated earnings",
                "source_key": "company_ir_calendar",
                "confidence_score": 25,
                "importance_score": 90,
            }
        ]
        configured = [
            {
                "ticker": "PL",
                "event_date": "2026-09-08",
                "title": "Estimated earnings",
                "source_key": "company_ir_calendar",
                "confidence_score": 45,
                "importance_score": 80,
                "configured": True,
            }
        ]

        events = merge_timetable_events(stored, configured)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["confidence_score"], 45)
        self.assertTrue(events[0]["configured"])


if __name__ == "__main__":
    unittest.main()
