from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.validate_daily_run import validate_daily  # noqa: E402

RUN_DIR = ROOT / "data/daily/2026-07-29"


class DailyRunTests(unittest.TestCase):
    def validate_schema(self, schema_name: str, value: dict) -> None:
        schema = json.loads(
            (ROOT / "schemas" / schema_name).read_text(encoding="utf-8")
        )
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        errors = sorted(
            validator.iter_errors(value),
            key=lambda error: [str(part) for part in error.absolute_path],
        )
        self.assertEqual([], [error.message for error in errors])

    def test_daily_run_replays_deterministically(self) -> None:
        validate_daily(
            RUN_DIR,
            ROOT / "config/editorial-weights.json",
            ROOT / "config/daily-run.json",
        )

    def test_run_manifest_is_valid_and_not_publishable_yet(self) -> None:
        run = json.loads((RUN_DIR / "run.json").read_text(encoding="utf-8"))
        self.validate_schema("daily-run.schema.json", run)
        self.assertEqual("validated", run["status"])
        self.assertEqual("pending", run["review_status"])
        self.assertFalse(run["publication_allowed"])
        self.assertEqual(6, run["source_count"])
        self.assertEqual(5, run["selected_counts"]["new_items"])
        self.assertEqual(0, run["selected_counts"]["continuation_items"])
        self.assertEqual(2, run["selected_counts"]["rejected_candidates"])
        self.assertTrue(all(run["validations"].values()))

    def test_briefing_contains_five_distinct_official_signals(self) -> None:
        briefing = json.loads(
            (RUN_DIR / "briefing.json").read_text(encoding="utf-8")
        )
        titles = [item["title"] for item in briefing["new_items"]]
        self.assertEqual(5, len(titles))
        self.assertEqual(5, len(set(titles)))
        self.assertIn("AI正在重组岗位边界", titles)
        self.assertIn("GitHub拦截恶意工作流", titles)
        self.assertIn("Dependabot扩大恶意包告警", titles)
        self.assertIn("AI IDE进入治理阶段", titles)
        self.assertIn("Copilot统一企业治理", titles)
        rejected = {
            item["candidate_id"]: item["rejection_reason"]
            for item in briefing["rejected_candidates"]
        }
        self.assertEqual(
            "duplicate_event", rejected["candidate-20260729-006"]
        )
        self.assertEqual(
            "low_confidence", rejected["candidate-20260729-007"]
        )

    def test_all_sources_are_tier_one_and_archived(self) -> None:
        source_files = sorted((RUN_DIR / "sources").glob("*.json"))
        self.assertEqual(6, len(source_files))
        for path in source_files:
            source = json.loads(path.read_text(encoding="utf-8"))
            self.validate_schema("source.schema.json", source)
            self.assertEqual("tier_1_official", source["authority_level"])
            self.assertEqual("verified", source["verification_status"])
            self.assertTrue(source["url"].startswith("https://"))

    def test_public_markdown_excludes_internal_candidates(self) -> None:
        markdown = (RUN_DIR / "briefing.md").read_text(encoding="utf-8")
        self.assertNotIn("内部淘汰池", markdown)
        self.assertNotIn("rejected_candidates", markdown)
        self.assertNotIn("candidate-20260729", markdown)
        self.assertIn("任务跨界不等于职业已经被替代", markdown)


if __name__ == "__main__":
    unittest.main()
