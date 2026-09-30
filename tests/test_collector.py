import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SPEC = importlib.util.spec_from_file_location("collector", Path(__file__).parents[1] / "helpers/ai_usage_tracker_collect.py")
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)


def claude_response(**rate_limits):
    return {"rate_limits_available": True, "subscription_type": "max", "rate_limits": rate_limits}


class ClaudeLimitsTests(unittest.TestCase):
    def test_maps_account_and_model_scoped_windows(self):
        limits = collector.claude_limits(claude_response(
            seven_day={"utilization": 40, "resets_at": "2026-10-05T18:00:00.194093+00:00"},
            five_hour={"utilization": 4, "resets_at": "2026-10-01T01:40:00+00:00"},
            model_scoped=[{"display_name": "Fable", "utilization": 12, "resets_at": None}],
        ))
        self.assertEqual(limits["plan"], "Max")
        self.assertEqual([item["id"] for item in limits["windows"]], ["five_hour", "seven_day", "seven_day_fable"])
        self.assertEqual(limits["windows"][0]["resetsAt"], 1790818800)
        self.assertEqual(limits["windows"][2]["label"], "Weekly (Fable)")

    def test_skips_windows_without_utilization(self):
        limits = collector.claude_limits(claude_response(five_hour={"utilization": None}, seven_day={"utilization": 10}))
        self.assertEqual([item["id"] for item in limits["windows"]], ["seven_day"])

    def test_api_key_accounts_are_unsupported(self):
        with self.assertRaises(collector.Unsupported):
            collector.claude_limits({"rate_limits_available": False, "rate_limits": None})


class CodexLimitsTests(unittest.TestCase):
    def test_prefers_main_bucket_over_legacy_snapshot(self):
        limits = collector.codex_limits({
            "rateLimits": {"limitId": "codex_spark", "primary": {"usedPercent": 99, "windowDurationMins": 300}},
            "rateLimitsByLimitId": {"codex": {"limitId": "codex", "primary": {"usedPercent": 5, "windowDurationMins": 300},
                                              "secondary": {"usedPercent": 40, "windowDurationMins": 10080}}},
        })
        self.assertEqual([(item["kind"], item["usedPercent"]) for item in limits["windows"]], [("session", 5), ("weekly", 40)])

    def test_ignores_model_specific_legacy_snapshot(self):
        with self.assertRaises(collector.ProbeFailed):
            collector.codex_limits({"rateLimits": {"limitId": "codex_spark", "primary": {"usedPercent": 99}}})

    def test_free_plan_primary_without_duration_is_monthly(self):
        limits = collector.codex_limits({"rateLimits": {"planType": "free", "primary": {"usedPercent": 30}}})
        self.assertEqual(limits["windows"][0]["kind"], "monthly")
        self.assertEqual(limits["windows"][0]["label"], "Monthly (30 days)")


class CollectTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        patches = [mock.patch.object(collector, "STATE_DIR", Path(directory.name)),
                   mock.patch.object(collector.shutil, "which", return_value="/usr/bin/fake")]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.good = {"windows": [collector.window("primary", "session", "Session", 20, 100, 300)]}

    def failing(self, error):
        def probe():
            raise error
        return probe

    def test_probe_failure_keeps_last_good_windows_as_stale(self):
        collector.collect("codex", "codex", lambda: self.good)
        result = collector.collect("codex", "codex", self.failing(collector.ProbeFailed("Codex did not answer.")))
        self.assertEqual(result["state"], "stale")
        self.assertEqual(result["windows"], self.good["windows"])
        self.assertIn("Codex did not answer.", result["message"])

    def test_unsupported_clears_last_good_windows(self):
        collector.collect("codex", "codex", lambda: self.good)
        collector.collect("codex", "codex", self.failing(collector.Unsupported("Sign in.")))
        result = collector.collect("codex", "codex", self.failing(collector.ProbeFailed("Codex did not answer.")))
        self.assertEqual((result["state"], result["windows"]), ("unavailable", []))

    def test_missing_cli_records_capability(self):
        with mock.patch.object(collector.shutil, "which", return_value=None):
            self.assertFalse(collector.collect("codex", "codex", lambda: self.good)["cliAvailable"])


class JsonLinesProcessTests(unittest.TestCase):
    def test_wait_times_out_when_the_cli_goes_quiet(self):
        with collector.JsonLinesProcess("Sleeper", ["sleep", "5"]) as cli:
            with self.assertRaisesRegex(collector.ProbeFailed, "did not answer"):
                cli.wait_for(lambda message: True, collector.time.monotonic() + 0.2)

    def test_skips_unrelated_and_unparsable_lines(self):
        script = "print('noise'); print('{\"id\": 1}'); print('{\"id\": 2, \"result\": {}}')"
        with collector.JsonLinesProcess("Echo", ["python3", "-c", script]) as cli:
            message = cli.wait_for(lambda message: message.get("id") == 2, collector.time.monotonic() + 5)
        self.assertEqual(json.dumps(message), '{"id": 2, "result": {}}')


if __name__ == "__main__":
    unittest.main()
