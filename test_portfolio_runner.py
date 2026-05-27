import tempfile
import unittest
from pathlib import Path

from portfolio_runner import Profile, build_env, parse_profile, parse_run_summary


class PortfolioRunnerTests(unittest.TestCase):
    def test_parse_run_summary_extracts_score_and_speed(self):
        output = """
[done] t01: 1.00 (8s)

==== SUMMARY ====
t01: 1.00 (8s)

FINAL: 97.92%  (47/48 perfect, 48 scored)
SPEED: wall 1130s | avg/task 142s | slowest 301s | parallel 6
per-task logs: /tmp/example/<task>.log
"""

        summary = parse_run_summary(output)

        self.assertEqual(summary.pct, 97.92)
        self.assertEqual(summary.perfect, 47)
        self.assertEqual(summary.total, 48)
        self.assertEqual(summary.scored, 48)
        self.assertEqual(summary.wall_seconds, 1130)
        self.assertEqual(summary.avg_task_seconds, 142)
        self.assertEqual(summary.slowest_seconds, 301)
        self.assertEqual(summary.parallel, 6)

    def test_build_env_isolates_logs_and_disables_results_append(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = Profile(name="codex53", model_id="codex:gpt-5.3-codex", parallel=6)
            env = build_env(profile, Path(tmp), {"BASE": "1"})

        self.assertEqual(env["MODEL_ID"], "codex:gpt-5.3-codex")
        self.assertEqual(env["PARALLEL"], "6")
        self.assertEqual(env["NO_RESULTS_APPEND"], "1")
        self.assertTrue(env["SWEEP_LOG_DIR"].endswith("codex53/tasks"))
        self.assertEqual(env["BASE"], "1")

    def test_parse_profile_allows_colon_in_model_id(self):
        profile = parse_profile("codex53:codex:gpt-5.3-codex:6")

        self.assertEqual(profile.name, "codex53")
        self.assertEqual(profile.model_id, "codex:gpt-5.3-codex")
        self.assertEqual(profile.parallel, 6)


if __name__ == "__main__":
    unittest.main()
