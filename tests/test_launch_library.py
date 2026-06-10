import unittest
from datetime import datetime, timezone

from backlog_screener.launch_library import match_launches


class LaunchLibraryTests(unittest.TestCase):
    def test_matches_future_launch_by_provider_and_mission_text(self):
        launches = [
            {
                "id": "launch-1",
                "name": "Electron | Customer Mission",
                "url": "https://ll.thespacedevs.com/2.3.0/launches/launch-1/",
                "net": "2026-07-01T12:00:00Z",
                "window_start": "2026-07-01T11:00:00Z",
                "window_end": "2026-07-01T13:00:00Z",
                "status": {"abbrev": "TBC", "name": "To Be Confirmed"},
                "launch_service_provider": {"name": "Rocket Lab", "abbrev": "RKLB"},
                "rocket": {"configuration": {"full_name": "Electron"}},
                "mission": {
                    "name": "Customer Mission",
                    "type": "Dedicated Rideshare",
                    "description": "Payload integration by Rocket Lab.",
                    "orbit": {"name": "Low Earth Orbit"},
                    "agencies": [],
                },
            }
        ]

        matches = match_launches(
            launches,
            keywords=["Rocket Lab", "Neutron"],
            now=datetime(2026, 6, 5, tzinfo=timezone.utc),
        )

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["launch_service_provider"], "Rocket Lab")
        self.assertIn("Rocket Lab", matches[0]["matched_keywords"])

    def test_skips_completed_old_launches(self):
        launches = [
            {
                "id": "launch-2",
                "name": "Electron | Completed Mission",
                "net": "2026-06-01T12:00:00Z",
                "status": {"abbrev": "Success", "name": "Launch Successful"},
                "launch_service_provider": {"name": "Rocket Lab"},
                "mission": {"name": "Completed Mission", "description": ""},
            }
        ]

        matches = match_launches(
            launches,
            keywords=["Rocket Lab"],
            now=datetime(2026, 6, 5, tzinfo=timezone.utc),
        )

        self.assertEqual(matches, [])


if __name__ == "__main__":
    unittest.main()
