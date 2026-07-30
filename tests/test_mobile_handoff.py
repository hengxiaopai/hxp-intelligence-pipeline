from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from PIL import Image

from publishing.handoff import build_handoff_bundle
from publishing.mobile_handoff import MobileHandoffError, build_mobile_handoff
from publishing.package_builder import build_content_package_batch, load_sources
from visual.queue import load_json


ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = ROOT / "data/daily/2026-07-29"
PRESETS = {
    "vertical_9x16": (2160, 3840, "9:16", ["douyin", "wechat_channels"]),
    "portrait_3x4": (2160, 2880, "3:4", ["xiaohongshu"]),
    "landscape_16x9": (2560, 1440, "16:9", ["x", "youtube", "website"]),
    "wechat_cover_235x1": (2350, 1000, "2.35:1", ["wechat_article"]),
}


class MobileHandoffTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        exports = []
        for preset, (width, height, ratio, platforms) in PRESETS.items():
            for order in range(1, 7):
                path = self.root / "source" / preset / f"poster-{order:02d}.png"
                path.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (64, 64), (180 + order, 220, 240)).save(path, "PNG")
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
        export_manifest = {
            "schema_version": "1.0.0",
            "export_manifest_id": "export-manifest-20260729",
            "visual_manifest_id": "visual-manifest-20260729",
            "review_batch_id": "visual-review-20260729-mobile-ci",
            "date": "2026-07-29",
            "generated_at": "2026-07-29T12:00:00+08:00",
            "template_version": "1.0.0",
            "exports": exports,
            "summary": {"total": 24, "passed": 24, "failed": 0, "preset_counts": {key: 6 for key in PRESETS}},
        }
        packages = build_content_package_batch(
            briefing=load_json(RUN_DIR / "briefing.json"),
            export_manifest=export_manifest,
            sources=load_sources(RUN_DIR / "sources"),
            profiles=load_json(ROOT / "config/platform-profiles.json"),
        )
        self.handoff_root = self.root / "handoff"
        self.handoff = build_handoff_bundle(
            package_batch=packages,
            config=load_json(ROOT / "config/cockpit-platforms.json"),
            output_dir=self.handoff_root,
            generated_at="2026-07-30T13:00:00+08:00",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def validate_schema(self, payload: object) -> None:
        schema = load_json(ROOT / "schemas/mobile-handoff.schema.json")
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        self.assertEqual([], [error.message for error in validator.iter_errors(payload)])

    def test_builds_three_verified_phone_transfer_directories(self) -> None:
        output = self.root / "mobile"
        manifest = build_mobile_handoff(
            handoff_manifest=self.handoff,
            handoff_root=self.handoff_root,
            output_dir=output,
            generated_at="2026-07-30T13:20:00+08:00",
        )
        self.validate_schema(manifest)
        self.assertEqual(["xiaohongshu", "douyin", "zhihu"], [value["platform"] for value in manifest["packages"]])
        self.assertEqual(3, manifest["summary"]["ready"])
        self.assertFalse(manifest["external_write_performed"])
        for package in manifest["packages"]:
            readme = output / package["instructions"]["path"]
            self.assertTrue(readme.is_file())
            self.assertIn("最终发布按钮必须由用户本人点击", readme.read_text(encoding="utf-8"))
            for asset in package["assets"]:
                path = output / asset["path"]
                self.assertTrue(path.is_file())
                self.assertEqual(asset["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        zhihu_readme = output / manifest["packages"][-1]["instructions"]["path"]
        self.assertIn("不能发布占位文本", zhihu_readme.read_text(encoding="utf-8"))

    def test_tampered_handoff_asset_is_blocked(self) -> None:
        source = self.handoff_root / self.handoff["platforms"][1]["assets"][0]["bundle_path"]
        source.write_bytes(source.read_bytes() + b"tampered")
        with self.assertRaisesRegex(MobileHandoffError, "哈希不一致"):
            build_mobile_handoff(
                handoff_manifest=self.handoff,
                handoff_root=self.handoff_root,
                output_dir=self.root / "blocked-mobile",
                generated_at="2026-07-30T13:20:00+08:00",
            )


if __name__ == "__main__":
    unittest.main()
