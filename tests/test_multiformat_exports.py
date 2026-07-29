from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from PIL import Image

from visual.approved_assets import ApprovedAssetError, select_latest_approved_assets
from visual.multiformat import export_platform_assets
from visual.queue import build_visual_queue, load_json
from visual.request_queue import build_visual_request_queue
from visual.result_import import import_visual_results
from visual.review import apply_review_batch, build_review_batch

ROOT = Path(__file__).resolve().parents[1]
DAILY_RUN = ROOT / "data/daily/2026-07-29"
THEME = load_json(ROOT / "config/visual-theme.json")
PROVIDERS = load_json(ROOT / "config/visual-providers.json")
PRESETS = load_json(ROOT / "config/export-presets.json")
TEST_LOGO = ROOT / "tests/fixtures/hxp-test-logo.svg"


class MultiFormatExportTests(unittest.TestCase):
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
        requests = build_visual_request_queue(
            visual_queue=self.visual_queue,
            provider_config=PROVIDERS,
            provider_id="fixture",
        )
        result_dir = self.root / "results"
        result_dir.mkdir()
        for index, request in enumerate(requests["requests"], start=1):
            image = Image.new("RGB", (1792, 1024), (232, 244, 255 - index))
            image.save(result_dir / f"{request['item_id']}.png", format="PNG")
        imported = import_visual_results(
            request_queue=requests,
            result_dir=result_dir,
            generator_reference="fixture-multiformat-20260729",
            imported_at="2026-07-29T15:00:00+08:00",
        )
        decisions = []
        checks = {
            "fact_consistent": True,
            "brief_consistent": True,
            "no_text_or_gibberish": True,
            "no_fabricated_ui_or_data": True,
            "brand_style_consistent": True,
            "subject_clear": True,
            "crop_safe": True,
            "not_recent_visual_duplicate": True,
        }
        for request in imported["requests"]:
            decisions.append(
                {
                    "request_id": request["request_id"],
                    "decision": "approved",
                    "checks": checks,
                    "rejection_reasons": [],
                    "change_instruction": None,
                    "notes": "offline fixture approval",
                }
            )
        self.review = build_review_batch(
            request_queue=imported,
            decisions=decisions,
            reviewer_type="fixture",
            reviewer_identifier="multiformat-ci",
            reviewed_at="2026-07-29T15:10:00+08:00",
        )
        self.approved_requests = apply_review_batch(
            request_queue=imported,
            review_batch=self.review,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def validate_schema(self, name: str, payload: object) -> None:
        schema = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        errors = [error.message for error in validator.iter_errors(payload)]
        self.assertEqual([], errors)

    def test_selects_one_latest_approved_visual_per_detail_item(self) -> None:
        selected = select_latest_approved_assets(
            visual_queue=self.visual_queue,
            request_queue=self.approved_requests,
            review_batch=self.review,
        )
        self.assertEqual(5, len(selected))
        self.assertEqual({1}, {value["attempt"] for value in selected.values()})
        self.assertTrue(all(value["path"].is_file() for value in selected.values()))

    def test_missing_approval_blocks_formal_export(self) -> None:
        incomplete = dict(self.review)
        incomplete["reviews"] = incomplete["reviews"][:-1]
        with self.assertRaisesRegex(ApprovedAssetError, "缺少人工审核通过"):
            select_latest_approved_assets(
                visual_queue=self.visual_queue,
                request_queue=self.approved_requests,
                review_batch=incomplete,
            )

    def test_exports_six_jobs_in_four_independent_presets(self) -> None:
        manifest = export_platform_assets(
            visual_queue=self.visual_queue,
            request_queue=self.approved_requests,
            review_batch=self.review,
            presets_config=PRESETS,
            theme=THEME,
            output_dir=self.root / "exports",
        )
        self.validate_schema("export-manifest.schema.json", manifest)
        self.assertEqual(24, manifest["summary"]["total"])
        self.assertEqual(24, manifest["summary"]["passed"])
        self.assertEqual(0, manifest["summary"]["failed"])
        self.assertEqual(
            {
                "vertical_9x16": 6,
                "portrait_3x4": 6,
                "landscape_16x9": 6,
                "wechat_cover_235x1": 6,
            },
            manifest["summary"]["preset_counts"],
        )
        dimensions = {
            export["preset"]: (export["width"], export["height"])
            for export in manifest["exports"]
        }
        self.assertEqual((2160, 3840), dimensions["vertical_9x16"])
        self.assertEqual((2160, 2880), dimensions["portrait_3x4"])
        self.assertEqual((2560, 1440), dimensions["landscape_16x9"])
        self.assertEqual((2350, 1000), dimensions["wechat_cover_235x1"])
        details = [value for value in manifest["exports"] if value["item_id"]]
        summaries = [value for value in manifest["exports"] if value["item_id"] is None]
        self.assertEqual(20, len(details))
        self.assertEqual(4, len(summaries))
        self.assertTrue(all(value["review_decision"] == "approved" for value in details))
        self.assertTrue(all(value["source_request_id"] for value in details))
        self.assertTrue(all(value["review_decision"] == "not_applicable" for value in summaries))
        self.assertTrue(all(value["source_asset_sha256"] is None for value in summaries))


if __name__ == "__main__":
    unittest.main()
