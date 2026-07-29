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

ROOT = Path(__file__).resolve().parents[1]
DAILY_RUN = ROOT / "data/daily/2026-07-29"
THEME = load_json(ROOT / "config/visual-theme.json")
PROVIDERS = load_json(ROOT / "config/visual-providers.json")
TEST_LOGO = ROOT / "tests/fixtures/hxp-test-logo.svg"


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

    def test_builds_five_stable_no_text_requests(self) -> None:
        first = build_visual_request_queue(
            visual_queue=self.visual_queue,
            provider_config=PROVIDERS,
            provider_id="fixture",
        )
        second = build_visual_request_queue(
            visual_queue=self.visual_queue,
            provider_config=PROVIDERS,
            provider_id="fixture",
        )
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
        request_queue = build_visual_request_queue(
            visual_queue=self.visual_queue,
            provider_config=PROVIDERS,
            provider_id="fixture",
        )
        result_dir = self.root / "results"
        result_dir.mkdir()
        for index, request in enumerate(request_queue["requests"], start=1):
            image = Image.new("RGB", (1792, 1024), (235, 245, 255 - index))
            image.save(result_dir / f"{request['item_id']}.png", format="PNG")

        imported = import_visual_results(
            request_queue=request_queue,
            result_dir=result_dir,
            generator_reference="fixture-run-20260729",
            imported_at="2026-07-29T13:30:00+08:00",
        )
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

    def test_rejects_sensitive_generator_reference(self) -> None:
        request_queue = build_visual_request_queue(
            visual_queue=self.visual_queue,
            provider_config=PROVIDERS,
            provider_id="fixture",
        )
        result_dir = self.root / "results"
        result_dir.mkdir()
        with self.assertRaisesRegex(VisualImportError, "私密信息"):
            import_visual_results(
                request_queue=request_queue,
                result_dir=result_dir,
                generator_reference="Authorization: Bearer secret",
                require_all=False,
            )

    def test_rejects_wrong_dimensions(self) -> None:
        request_queue = build_visual_request_queue(
            visual_queue=self.visual_queue,
            provider_config=PROVIDERS,
            provider_id="fixture",
        )
        result_dir = self.root / "results"
        result_dir.mkdir()
        first = request_queue["requests"][0]
        Image.new("RGB", (1024, 1024), (240, 248, 255)).save(
            result_dir / f"{first['item_id']}.png",
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
