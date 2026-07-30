from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from PIL import Image

from publishing.approval import (
    PublicationApprovalError,
    apply_publication_approval,
    build_publication_approval,
)
from publishing.dry_run import build_dry_run_result
from publishing.package_builder import (
    ContentPackageError,
    build_content_package_batch,
    load_sources,
)
from publishing.plan import build_publication_plan
from visual.queue import load_json


ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = ROOT / "data/daily/2026-07-29"
PROFILES = load_json(ROOT / "config/platform-profiles.json")
PRESETS = {
    "vertical_9x16": (2160, 3840, "9:16", ["douyin", "wechat_channels"]),
    "portrait_3x4": (2160, 2880, "3:4", ["xiaohongshu"]),
    "landscape_16x9": (2560, 1440, "16:9", ["x", "youtube", "website"]),
    "wechat_cover_235x1": (2350, 1000, "2.35:1", ["wechat_article"]),
}
PLATFORMS = ("wechat", "xiaohongshu", "douyin", "x", "website", "zhihu")


class PublicationPackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.briefing = load_json(RUN_DIR / "briefing.json")
        self.sources = load_sources(RUN_DIR / "sources")
        self.manifest = self.make_export_manifest()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def validate_schema(self, name: str, payload: object) -> None:
        schema = load_json(ROOT / "schemas" / name)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        errors = [error.message for error in validator.iter_errors(payload)]
        self.assertEqual([], errors)

    def make_export_manifest(self) -> dict[str, object]:
        import hashlib

        exports = []
        for preset, (width, height, ratio, platforms) in PRESETS.items():
            for order in range(1, 7):
                path = self.root / preset / f"poster-{order:02d}.png"
                path.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (64, 64), (220 + order, 235, 245)).save(path, "PNG")
                body = path.read_bytes()
                item_id = f"item-20260729-{order:02d}" if order <= 5 else None
                exports.append(
                    {
                        "export_id": f"export-20260729-{order:02d}-{preset}",
                        "job_id": f"visual-job-20260729-{order:02d}",
                        "item_id": item_id,
                        "preset": preset,
                        "width": width,
                        "height": height,
                        "ratio": ratio,
                        "platforms": platforms,
                        "source_request_id": f"visual-request-20260729-{order:02d}-a1" if item_id else None,
                        "source_asset_sha256": hashlib.sha256(body).hexdigest() if item_id else None,
                        "review_decision": "approved" if item_id else "not_applicable",
                        "svg": {
                            "path": str(path.with_suffix(".svg")),
                            "sha256": "a" * 64,
                            "byte_size": 1,
                        },
                        "png": {
                            "path": str(path),
                            "sha256": hashlib.sha256(body).hexdigest(),
                            "byte_size": len(body),
                        },
                        "text_overflow": False,
                        "crop_safe": True,
                        "status": "passed",
                        "errors": [],
                    }
                )
        return {
            "schema_version": "1.0.0",
            "export_manifest_id": "export-manifest-20260729",
            "visual_manifest_id": "visual-manifest-20260729",
            "review_batch_id": "visual-review-20260729-publication-ci",
            "date": "2026-07-29",
            "generated_at": "2026-07-29T12:00:00+08:00",
            "template_version": "1.0.0",
            "exports": exports,
            "summary": {
                "total": 24,
                "passed": 24,
                "failed": 0,
                "preset_counts": {value: 6 for value in PRESETS},
            },
        }

    def build_batch(self) -> dict[str, object]:
        return build_content_package_batch(
            briefing=self.briefing,
            export_manifest=self.manifest,
            sources=self.sources,
            profiles=PROFILES,
        )

    def test_builds_six_validated_platform_packages(self) -> None:
        batch = self.build_batch()
        self.validate_schema("content-package.schema.json", batch)
        self.assertEqual(6, batch["summary"]["validated"])
        self.assertEqual(0, batch["summary"]["blocked"])
        packages = {value["platform"]: value for value in batch["packages"]}
        self.assertEqual(set(PLATFORMS), set(packages))
        self.assertEqual(["wechat_cover_235x1"], [a["preset"] for a in packages["wechat"]["assets"]])
        self.assertEqual(6, len(packages["xiaohongshu"]["assets"]))
        self.assertEqual(6, len(packages["douyin"]["assets"]))
        self.assertEqual(1, len(packages["x"]["assets"]))
        self.assertEqual(6, len(packages["website"]["assets"]))
        self.assertEqual(6, len(packages["zhihu"]["assets"]))
        self.assertIn("请先在知乎选择", packages["zhihu"]["content"]["answer_question_placeholder"])
        self.assertIn("AI 辅助", packages["zhihu"]["content"]["answer_markdown"])
        self.assertFalse(batch["write_actions_enabled"])

    def test_non_zhihu_packages_have_explicit_empty_answer_fields(self) -> None:
        packages = {value["platform"]: value for value in self.build_batch()["packages"]}
        for platform in ("wechat", "xiaohongshu", "douyin", "x", "website"):
            self.assertIsNone(packages[platform]["content"]["answer_question_placeholder"])
            self.assertEqual("", packages[platform]["content"]["answer_markdown"])

    def test_content_hashes_are_deterministic(self) -> None:
        first = self.build_batch()
        second = self.build_batch()
        self.assertEqual(
            [value["content_hash"] for value in first["packages"]],
            [value["content_hash"] for value in second["packages"]],
        )

    def test_failed_export_blocks_package_creation(self) -> None:
        self.manifest["exports"][0]["status"] = "failed"
        with self.assertRaisesRegex(ContentPackageError, "未通过"):
            self.build_batch()

    def test_plan_and_human_approval_never_enable_writes(self) -> None:
        batch = self.build_batch()
        plan = build_publication_plan(
            package_batch=batch,
            created_at="2026-07-29T16:30:00+08:00",
        )
        self.validate_schema("publication-plan.schema.json", plan)
        self.assertEqual(6, plan["summary"]["pending"])
        self.assertTrue(all(not value["write_allowed"] for value in plan["entries"]))

        decisions = []
        for entry in plan["entries"]:
            decisions.append(
                {
                    "entry_id": entry["entry_id"],
                    "platform": entry["platform"],
                    "decision": "approved",
                    "account_ref_confirmed": True,
                    "content_hash_confirmed": True,
                    "asset_hashes_confirmed": True,
                    "asset_order_confirmed": True,
                    "risk_reviewed": True,
                    "action_confirmed": True,
                    "notes": "offline fixture approval",
                }
            )
        approval = build_publication_approval(
            plan=plan,
            decisions=decisions,
            approver_identifier="hxp-owner",
            approved_at="2026-07-29T16:35:00+08:00",
        )
        updated = apply_publication_approval(plan=plan, approval=approval)
        self.validate_schema("publication-approval.schema.json", approval)
        self.validate_schema("publication-plan.schema.json", updated)
        self.assertEqual(6, updated["summary"]["approved"])
        self.assertFalse(updated["write_actions_enabled"])
        self.assertTrue(all(not value["write_allowed"] for value in updated["entries"]))

    def test_approval_requires_every_explicit_confirmation(self) -> None:
        plan = build_publication_plan(
            package_batch=self.build_batch(),
            created_at="2026-07-29T16:30:00+08:00",
        )
        entry = plan["entries"][0]
        with self.assertRaisesRegex(PublicationApprovalError, "未完成"):
            build_publication_approval(
                plan=plan,
                decisions=[
                    {
                        "entry_id": entry["entry_id"],
                        "platform": entry["platform"],
                        "decision": "approved",
                        "account_ref_confirmed": True,
                        "content_hash_confirmed": True,
                        "asset_hashes_confirmed": False,
                        "asset_order_confirmed": True,
                        "risk_reviewed": True,
                        "action_confirmed": True,
                        "notes": None,
                    }
                ],
                approver_identifier="hxp-owner",
                approved_at="2026-07-29T16:35:00+08:00",
            )

    def test_dry_run_creates_six_html_and_markdown_previews(self) -> None:
        batch = self.build_batch()
        plan = build_publication_plan(
            package_batch=batch,
            created_at="2026-07-29T16:30:00+08:00",
        )
        result = build_dry_run_result(
            package_batch=batch,
            plan=plan,
            output_dir=self.root / "preview",
            executed_at="2026-07-29T16:40:00+08:00",
        )
        self.validate_schema("publication-result.schema.json", result)
        self.assertEqual(6, result["summary"]["previewed"])
        self.assertFalse(result["external_write_performed"])
        for platform in PLATFORMS:
            self.assertTrue((self.root / "preview" / f"{platform}.html").is_file())
            self.assertTrue((self.root / "preview" / f"{platform}.md").is_file())
        zhihu_markdown = (self.root / "preview" / "zhihu.md").read_text(encoding="utf-8")
        self.assertIn("知乎回答版", zhihu_markdown)
        self.assertIn("回答前先选择真实问题", zhihu_markdown)


if __name__ == "__main__":
    unittest.main()
