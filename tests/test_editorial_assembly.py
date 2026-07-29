from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.briefing_assembler import (  # noqa: E402
    BriefingAssemblyError,
    build_briefing,
    render_markdown,
)
from pipeline.editorial_scoring import load_weights, score_pool  # noqa: E402


class EditorialAssemblyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pool = json.loads(
            (ROOT / "data/examples/candidate-pool.example.json").read_text(
                encoding="utf-8"
            )
        )
        cls.weights = load_weights(ROOT / "config/editorial-weights.json")

    def validate(self, schema_name: str, value: dict) -> None:
        schema = json.loads(
            (ROOT / "schemas" / schema_name).read_text(encoding="utf-8")
        )
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        errors = sorted(
            validator.iter_errors(value),
            key=lambda error: [str(part) for part in error.absolute_path],
        )
        self.assertEqual([], [error.message for error in errors])

    def test_score_report_is_deterministic_and_valid(self) -> None:
        first = score_pool(self.pool, self.weights)
        second = score_pool(self.pool, self.weights)
        self.assertEqual(first, second)
        self.validate("editorial-score.schema.json", first)
        self.assertEqual("candidate-20260729-001", first["scores"][0]["candidate_id"])
        actions = {item["candidate_id"]: item["recommended_action"] for item in first["scores"]}
        self.assertEqual("reject_duplicate", actions["candidate-20260729-007"])
        self.assertEqual("reject_low_confidence", actions["candidate-20260729-008"])

    def test_assembled_briefing_passes_schema_and_policy(self) -> None:
        scores = score_pool(self.pool, self.weights)
        briefing = build_briefing(self.pool, scores, self.weights)
        self.validate("briefing.schema.json", briefing)
        self.assertEqual(5, len(briefing["new_items"]))
        self.assertEqual(1, len(briefing["continuation_items"]))
        self.assertEqual(1.0, briefing["editorial_policy"]["new_or_new_angle_ratio"])
        self.assertIsNone(briefing["editorial_policy"]["shortfall_reason"])
        self.assertTrue(briefing["editorial_policy"]["source_requirements_met"])
        self.assertEqual("build", briefing["product_opportunity"]["verdict"])
        self.assertEqual(2, len(briefing["rejected_candidates"]))

    def test_low_quality_pool_does_not_get_padded(self) -> None:
        pool = copy.deepcopy(self.pool)
        pool["entries"] = pool["entries"][:4]
        pool["content_opportunities"] = [
            {
                **item,
                "related_candidate_ids": [pool["entries"][0]["candidate"]["candidate_id"]],
            }
            for item in pool["content_opportunities"]
        ]
        pool["product_opportunity"] = None
        scores = score_pool(pool, self.weights)
        briefing = build_briefing(pool, scores, self.weights)
        self.assertEqual(4, len(briefing["new_items"]))
        self.assertIsNotNone(briefing["editorial_policy"]["shortfall_reason"])
        self.assertIn("未为满足数量目标", briefing["editorial_policy"]["shortfall_reason"])

    def test_content_opportunity_cannot_reference_rejected_candidate(self) -> None:
        pool = copy.deepcopy(self.pool)
        pool["content_opportunities"][0]["related_candidate_ids"] = [
            "candidate-20260729-008"
        ]
        scores = score_pool(pool, self.weights)
        with self.assertRaisesRegex(BriefingAssemblyError, "未入选候选"):
            build_briefing(pool, scores, self.weights)

    def test_markdown_keeps_internal_rejection_pool_private(self) -> None:
        scores = score_pool(self.pool, self.weights)
        briefing = build_briefing(self.pool, scores, self.weights)
        markdown = render_markdown(briefing)
        self.assertIn("不构成投资建议", markdown)
        self.assertNotIn("内部淘汰池", markdown)
        self.assertNotIn("candidate-20260729-008", markdown)


if __name__ == "__main__":
    unittest.main()
