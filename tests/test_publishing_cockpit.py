from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from PIL import Image

from publishing.cockpit import (
    CockpitError,
    build_initial_session,
    render_cockpit_html,
    update_manual_record,
)
from publishing.handoff import HandoffError, build_handoff_bundle
from publishing.package_builder import build_content_package_batch, load_sources
from visual.queue import load_json


ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = ROOT / "data/daily/2026-07-29"
PROFILES = load_json(ROOT / "config/platform-profiles.json")
COCKPIT_CONFIG = load_json(ROOT / "config/cockpit-platforms.json")
PRESETS = {
    "vertical_9x16": (2160, 3840, "9:16", ["douyin", "wechat_channels"]),
    "portrait_3x4": (2160, 2880, "3:4", ["xiaohongshu"]),
    "landscape_16x9": (2560, 1440, "16:9", ["x", "youtube", "website"]),
    "wechat_cover_235x1": (2350, 1000, "2.35:1", ["wechat_article"]),
}


class PublishingCockpitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.briefing = load_json(RUN_DIR / "briefing.json")
        self.sources = load_sources(RUN_DIR / "sources")
        self.package_batch = build_content_package_batch(
            briefing=self.briefing,
            export_manifest=self.make_export_manifest(),
            sources=self.sources,
            profiles=PROFILES,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def validate_schema(self, name: str, payload: object) -> None:
        schema = load_json(ROOT / "schemas" / name)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        errors = [error.message for error in validator.iter_errors(payload)]
        self.assertEqual([], errors)

    def make_export_manifest(self) -> dict[str, object]:
        exports = []
        for preset, (width, height, ratio, platforms) in PRESETS.items():
            for order in range(1, 7):
                path = self.root / "source-assets" / preset / f"poster-{order:02d}.png"
                path.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (64, 64), (190 + order, 220 + order, 240)).save(path, "PNG")
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
                        "svg": {"path": str(path.with_suffix(".svg")), "sha256": "a" * 64, "byte_size": 1},
                        "png": {"path": str(path), "sha256": hashlib.sha256(body).hexdigest(), "byte_size": len(body)},
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
            "review_batch_id": "visual-review-20260729-cockpit-ci",
            "date": "2026-07-29",
            "generated_at": "2026-07-29T12:00:00+08:00",
            "template_version": "1.0.0",
            "exports": exports,
            "summary": {"total": 24, "passed": 24, "failed": 0, "preset_counts": {value: 6 for value in PRESETS}},
        }

    def build_manifest(self) -> dict[str, object]:
        return build_handoff_bundle(
            package_batch=self.package_batch,
            config=COCKPIT_CONFIG,
            output_dir=self.root / "handoff",
            generated_at="2026-07-30T13:00:00+08:00",
        )

    def test_builds_six_platform_handoffs_without_extensions(self) -> None:
        manifest = self.build_manifest()
        self.validate_schema("handoff-manifest.schema.json", manifest)
        self.assertEqual(6, manifest["summary"]["ready"])
        self.assertEqual(1, manifest["summary"]["derived"])
        self.assertFalse(manifest["external_write_performed"])
        platforms = [value["platform"] for value in manifest["platforms"]]
        self.assertEqual(["wechat", "xiaohongshu", "douyin", "x", "website", "zhihu"], platforms)
        zhihu = manifest["platforms"][-1]
        self.assertTrue(zhihu["derived"])
        self.assertIn("请先在知乎选择", zhihu["content"]["answer_question_placeholder"])
        self.assertIn("AI 辅助", zhihu["content"]["answer_markdown"])
        for entry in manifest["platforms"]:
            self.assertTrue(entry["creator_url"].startswith("https://"))
            self.assertGreaterEqual(len(entry["assets"]), 1)
            for asset in entry["assets"]:
                copied = self.root / "handoff" / asset["bundle_path"]
                self.assertTrue(copied.is_file())
                self.assertEqual(asset["sha256"], hashlib.sha256(copied.read_bytes()).hexdigest())

    def test_renders_single_file_offline_cockpit(self) -> None:
        manifest = self.build_manifest()
        output = self.root / "handoff" / "cockpit.html"
        render_cockpit_html(manifest, output_path=output)
        body = output.read_text(encoding="utf-8")
        self.assertIn("多平台发布驾驶舱", body)
        self.assertIn("无需浏览器扩展", body)
        self.assertIn("小红书", body)
        self.assertIn("知乎回答版", body)
        self.assertIn("navigator.clipboard.writeText", body)
        self.assertNotIn("<script src=", body)
        self.assertNotIn("playwright", body.casefold())
        self.assertNotIn("document.cookie", body.casefold())

    def test_manual_session_requires_user_confirmation_and_content_identity(self) -> None:
        manifest = self.build_manifest()
        session = build_initial_session(
            manifest,
            created_at="2026-07-30T13:10:00+08:00",
            session_slug="owner",
        )
        self.validate_schema("cockpit-session.schema.json", session)
        with self.assertRaisesRegex(CockpitError, "用户明确确认"):
            update_manual_record(
                session=session,
                manifest=manifest,
                platform="zhihu",
                status="opened",
                updated_at="2026-07-30T13:11:00+08:00",
                confirmed_by_user=False,
            )
        with self.assertRaisesRegex(CockpitError, "内容ID或HTTPS链接"):
            update_manual_record(
                session=session,
                manifest=manifest,
                platform="zhihu",
                status="published",
                updated_at="2026-07-30T13:12:00+08:00",
                confirmed_by_user=True,
            )
        updated = update_manual_record(
            session=session,
            manifest=manifest,
            platform="zhihu",
            status="draft_saved",
            updated_at="2026-07-30T13:13:00+08:00",
            confirmed_by_user=True,
            notes="人工保存草稿",
        )
        self.validate_schema("cockpit-session.schema.json", updated)
        self.assertEqual(1, updated["summary"]["draft_saved"])
        self.assertFalse(updated["external_write_performed"])

        drifted = json.loads(json.dumps(manifest))
        drifted["platforms"][-1]["content_hash"] = "f" * 64
        with self.assertRaisesRegex(CockpitError, "哈希已经漂移"):
            update_manual_record(
                session=updated,
                manifest=drifted,
                platform="zhihu",
                status="published",
                updated_at="2026-07-30T13:14:00+08:00",
                confirmed_by_user=True,
                external_url="https://www.zhihu.com/p/123",
            )

    def test_creator_link_with_query_parameters_is_blocked(self) -> None:
        config = json.loads(json.dumps(COCKPIT_CONFIG))
        config["platforms"][0]["creator_url"] = "https://mp.weixin.qq.com/?token=secret"
        with self.assertRaisesRegex(HandoffError, "查询参数"):
            build_handoff_bundle(
                package_batch=self.package_batch,
                config=config,
                output_dir=self.root / "blocked",
                generated_at="2026-07-30T13:00:00+08:00",
            )


if __name__ == "__main__":
    unittest.main()
