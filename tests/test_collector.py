import importlib.util
import json
import tempfile
import time
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("collector", Path(__file__).parents[1] / "helpers/ai_usage_tracker_collect.py")
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)


class CollectorTests(unittest.TestCase):
    def test_duration_labels(self):
        self.assertEqual(collector.duration_label(300, "x"), "Session (5 hours)")
        self.assertEqual(collector.duration_label(10080, "x"), "Weekly (7 days)")
        self.assertEqual(collector.duration_label(15, "x"), "15-minute window")

    def test_window_rejects_invalid_percent(self):
        self.assertIsNone(collector.window("no", 1, 1, "x"))
        self.assertEqual(collector.window(25, 100, 300, "x")["usedPercent"], 25.0)

    def test_unavailable_records_cli_capability(self):
        self.assertFalse(collector.unavailable("missing CLI", cli_available=False)["cliAvailable"])

    def test_claude_quota_reset_timestamp(self):
        now = collector.datetime(2026, 7, 22, 16, 0, tzinfo=collector.ZoneInfo("America/Denver"))
        self.assertEqual(collector.quota_reset_timestamp("8:40pm (America/Denver)", now),
                         int(collector.datetime(2026, 7, 22, 20, 40, tzinfo=collector.ZoneInfo("America/Denver")).timestamp()))
        self.assertEqual(collector.quota_reset_timestamp("Jul 27, 12pm (America/Denver)", now),
                         int(collector.datetime(2026, 7, 27, 12, 0, tzinfo=collector.ZoneInfo("America/Denver")).timestamp()))

    def test_claude_state_fresh_and_stale(self):
        with tempfile.TemporaryDirectory() as directory:
            old_runtime = collector.RUNTIME_DIR
            collector.RUNTIME_DIR = Path(directory)
            payload = {"updatedAt": int(time.time()), "fiveHour": {"usedPercent": 20, "resetsAt": 100}, "sevenDay": {"usedPercent": 40, "resetsAt": 200}}
            (collector.RUNTIME_DIR / "claude.json").write_text(json.dumps(payload))
            self.assertEqual(collector.claude()["state"], "fresh")
            payload["updatedAt"] -= collector.STALE_AFTER_SECONDS + 1
            (collector.RUNTIME_DIR / "claude.json").write_text(json.dumps(payload))
            self.assertEqual(collector.claude()["state"], "stale")
            collector.RUNTIME_DIR = old_runtime


if __name__ == "__main__":
    unittest.main()
