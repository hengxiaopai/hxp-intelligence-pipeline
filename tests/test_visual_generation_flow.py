from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from PIL import Image

from visual.queue import build_visual_queue, load_json
from visual.request_queue import build_visual_request_queue
from visual.result_import import VisualImportError, import_visual_results
from visual.review import apply_review_batch, build_review_batch
from visual.retry_policy import apply_retry_plan, build_retry_plan

ROOT = Path(__file__).resolve().parents[1]
DAILY_RUN = ROOT / "data/daily/2026-07-29"
THEME = load_json(ROOT / "config/visual-theme.json")
PROVIDERS = load_json(ROOT / "config/visual-providers.json")
TEST_LOGO = ROOT / "tests/fixtures/hxp-test-logo.svg"


def passing_checks() -> dict[str, bool]:
    return {
        "fact_consistent": True,
        "brief_consistent": True,
        "no_text_or_gibberish": True,
        "no_fabricated_ui_or_data": True,
        "brand_style_consistent": True,
        "subject_clear": True,
        "crop_safe": True,
        "not_recent_visual_duplicate": True,
    }


class VisualGenerationFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.run_dir = self.root / "run"
        shutil.copytree(DAILY_RUN, self.run_dir)
        run_path = self.run_dir / "run.json"
        run = json.loads(run_path.read_text(encoding="utf-8"))
        run["review_status"] = "approved"
        run["publication_allowed"] = True
        run_path.write_text(
            json.dumps(run, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self.visual_queue = build_visual_queue(
            run_dir=self.run_dir,
            logo_path=TEST_LOGO,
            theme=THEME,
            allow_placeholder=True,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def validate_schema(self, name: str, payload: object) -> None:
        schema = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        errors = [error.message for error in validator.iter_errors(payload)]
        self.assertEqual([], errors)

    def request_queue(self) -> dict[str, object]:
        return build_visual_request_queue(
            visual_queue=self.visual_queue,
            provider_config=PROVIDERS,
            provider_id="fixture",
        )

    def imported_queue(self) -> dict[str, object]:
        request_queue = self.request_queue()
        result_dir = self.root / "results"
        result_dir.mkdir(exist_ok=True)
        for index, request in enumerate(request_queue["requests"], start=1):
            image = Image.new("RGB", (1792, 1024), (235, 245, 255 - index))
            image.save(result_dir / f"{request['request_id']}.png", format="PNG")
        return import_visual_results(
            request_queue=request_queue,
            result_dir=result_dir,
            generator_reference="fixture-run-20260729",
            imported_at="2026-07-29T13:30:00+08:00",
        )

    def test_builds_five_stable_no_text_requests(self) -> None:
        first = self.request_queue()
        second = self.request_queue()
        self.assertEqual(first, second)
        self.validate_schema("visual-request.schema.json", first)
        self.assertEqual(5, len(first["requests"]))
        self.assertEqual(5, len({r["request_fingerprint"] for r in first["requests"]}))
        for request in first["requests"]:
            self.assertFalse(request["target"]["text_allowed"])
            self.assertIn("不得包含任何文字", request["prompt"])
            self.assertIn("禁止任何中文", request["negative_constraints"][0])
            self.assertIsNone(request["result"])

    def test_imports_exact_fixture_results_with_hashes(self) -> None:
        imported = self.imported_queue()
        self.validate_schema("visual-request.schema.json", imported)
        self.assertEqual(
            {"imported"},
            {request["status"] for request in imported["requests"]},
        )
        for request in imported["requests"]:
            result = request["result"]
            self.assertIsNotNone(result)
            self.assertEqual(64, len(result["sha256"]))
            self.assertEqual(1792, result["width"])
            self.assertEqual(1024, result["height"])
            self.assertEqual("image/png", result["mime_type"])

    def test_human_review_approves_four_and_targets_one_retry(self) -> None:
        imported = self.imported_queue()
        decisions = []
        for index, request in enumerate(imported["requests"]):
            checks = passing_checks()
            if index == 1:
                checks["subject_clear"] = False
                checks["crop_safe"] = False
                decisions.append(
                    {
                        "request_id": request["request_id"],
                        "decision": "needs_changes",
                        "checks": checks,
                        "rejection_reasons": ["composition_problem", "unsafe_crop"],
                        "change_instruction": "主体收回中央并扩大左右留白，不改动主题隐喻。",
                        "notes": "其余材质和品牌方向保留。",
                    }
                )
            else:
                decisions.append(
                    {
                        "request_id": request["request_id"],
                        "decision": "approved",
                        "checks": checks,
                        "rejection_reasons": [],
                        "change_instruction": None,
                        "notes": None,
                    }
                )

        review = build_review_batch(
            request_queue=imported,
            decisions=decisions,
            reviewer_type="fixture",
            reviewer_identifier="fixture-review",
            reviewed_at="2026-07-29T13:40:00+08:00",
        )
        self.validate_schema("visual-review.schema.json", review)
        self.assertEqual(4, review["summary"]["approved"])
        self.assertEqual(1, review["summary"]["needs_changes"])

        reviewed_queue = apply_review_batch(
            request_queue=imported,
            review_batch=review,
        )
        self.validate_schema("visual-request.schema.json", reviewed_queue)
        self.assertEqual(
            1,
            sum(request["status"] == "needs_review" for request in reviewed_queue["requests"]),
        )

        plan, scheduled = build_retry_plan(
            request_queue=reviewed_queue,
            review_batch=review,
            generated_at="2026-07-29T13:41:00+08:00",
        )
        self.validate_schema("visual-retry.schema.json", plan)
        self.assertEqual(1, plan["summary"]["eligible"])
        self.assertEqual(1, plan["summary"]["scheduled"])
        self.assertEqual(1, len(scheduled))

        retried_queue = apply_retry_plan(
            request_queue=reviewed_queue,
            retry_plan=plan,
            scheduled_requests=scheduled,
        )
        self.validate_schema("visual-request.schema.json", retried_queue)
        self.assertEqual(6, len(retried_queue["requests"]))
        retry_request = retried_queue["requests"][-1]
        self.assertEqual(2, retry_request["attempt"])
        self.assertIsNotNone(retry_request["parent_request_id"])
        self.assertIn("重试修正", retry_request["prompt"])
        self.assertNotEqual(
            retry_request["request_fingerprint"],
            reviewed_queue["requests"][1]["request_fingerprint"],
        )

    def test_fact_mismatch_returns_to_editorial_instead_of_regeneration(self) -> None:
        imported = self.imported_queue()
        request = imported["requests"][0]
        checks = passing_checks()
        checks["fact_consistent"] = False
        review = build_review_batch(
            request_queue=imported,
            decisions=[
                {
                    "request_id": request["request_id"],
                    "decision": "rejected",
                    "checks": checks,
                    "rejection_reasons": ["fact_mismatch"],
                    "change_instruction": None,
                    "notes": "标题和来源事实不一致。",
                }
            ],
            reviewer_type="fixture",
            reviewer_identifier="fixture-editorial",
            reviewed_at="2026-07-29T13:42:00+08:00",
        )
        plan, scheduled = build_retry_plan(
            request_queue=imported,
            review_batch=review,
        )
        self.validate_schema("visual-retry.schema.json", plan)
        self.assertEqual(1, plan["summary"]["editorial_blocked"])
        self.assertEqual(0, plan["summary"]["scheduled"])
        self.assertEqual({}, scheduled)

    def test_rejects_sensitive_generator_reference(self) -> None:
        request_queue = self.request_queue()
        result_dir = self.root / "sensitive-results"
        result_dir.mkdir()
        with self.assertRaisesRegex(VisualImportError, "私密信息"):
            import_visual_results(
                request_queue=request_queue,
                result_dir=result_dir,
                generator_reference="Authorization: Bearer secret",
                require_all=False,
            )

    def test_rejects_wrong_dimensions(self) -> None:
        request_queue = self.request_queue()
        result_dir = self.root / "wrong-results"
        result_dir.mkdir()
        first = request_queue["requests"][0]
        Image.new("RGB", (1024, 1024), (240, 248, 255)).save(
            result_dir / f"{first['request_id']}.png",
            format="PNG",
        )
        with self.assertRaisesRegex(VisualImportError, "尺寸不一致"):
            import_visual_results(
                request_queue=request_queue,
                result_dir=result_dir,
                generator_reference="fixture-wrong-size",
                require_all=False,
            )


if __name__ == "__main__":
    unittest.main()
