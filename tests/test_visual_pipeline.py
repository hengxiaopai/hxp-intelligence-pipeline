from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from visual.layout import wrap_text
from visual.pipeline import render_visual_queue
from visual.queue import VisualQueueError, build_visual_queue, load_json

ROOT = Path(__file__).resolve().parents[1]
DAILY_RUN = ROOT / "data/daily/2026-07-29"
THEME = load_json(ROOT / "config/visual-theme.json")
TEST_LOGO = ROOT / "tests/fixtures/hxp-test-logo.svg"
PLACEHOLDER = ROOT / "tests/fixtures/visual-placeholder.svg"


class VisualPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.run_dir = self.root / "run"
        shutil.copytree(DAILY_RUN, self.run_dir)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def approve_run(self) -> None:
        path = self.run_dir / "run.json"
        run = json.loads(path.read_text(encoding="utf-8"))
        run["review_status"] = "approved"
        run["publication_allowed"] = True
        path.write_text(
            json.dumps(run, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def validate_schema(self, name: str, payload: object) -> None:
        schema = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        errors = list(validator.iter_errors(payload))
        self.assertEqual([], [error.message for error in errors])

    def test_pending_run_cannot_create_visual_queue(self) -> None:
        with self.assertRaisesRegex(VisualQueueError, "approved"):
            build_visual_queue(
                run_dir=self.run_dir,
                logo_path=TEST_LOGO,
                theme=THEME,
                allow_placeholder=True,
            )

    def test_approved_run_builds_five_details_and_one_summary(self) -> None:
        self.approve_run()
        queue = build_visual_queue(
            run_dir=self.run_dir,
            logo_path=TEST_LOGO,
            theme=THEME,
            allow_placeholder=True,
        )
        self.validate_schema("visual-queue.schema.json", queue)
        self.assertTrue(queue["preview_only"])
        self.assertEqual(6, len(queue["jobs"]))
        self.assertEqual(
            5, sum(job["kind"] == "detail_9x16" for job in queue["jobs"])
        )
        self.assertEqual(
            1, sum(job["kind"] == "summary_9x16" for job in queue["jobs"])
        )
        self.assertIn("今日 5 大焦点", queue["jobs"][-1]["content"]["subtitle"])

    def test_preview_queue_renders_exact_svg_and_png_dimensions(self) -> None:
        self.approve_run()
        queue = build_visual_queue(
            run_dir=self.run_dir,
            logo_path=TEST_LOGO,
            theme=THEME,
            allow_placeholder=True,
        )
        manifest = render_visual_queue(
            queue=queue,
            theme=THEME,
            output_dir=self.root / "posters",
            placeholder_path=PLACEHOLDER,
            rasterize=True,
        )
        self.validate_schema("visual-manifest.schema.json", manifest)
        self.assertEqual(6, manifest["summary"]["passed"])
        self.assertEqual(0, manifest["summary"]["failed"])
        self.assertEqual(5, manifest["summary"]["placeholders"])
        self.assertEqual(6, manifest["summary"]["png_assets"])
        for asset in manifest["assets"]:
            self.assertTrue(asset["logo_embedded"])
            self.assertFalse(asset["text_overflow"])
            self.assertIsNotNone(asset["svg"])
            self.assertIsNotNone(asset["png"])

    def test_title_overflow_is_detected_deterministically(self) -> None:
        wrapped = wrap_text("超长标题" * 40, maximum_units=28, maximum_lines=2)
        self.assertTrue(wrapped.overflow)
        self.assertEqual(2, len(wrapped.lines))
        self.assertTrue(wrapped.lines[-1].endswith("…"))


if __name__ == "__main__":
    unittest.main()
