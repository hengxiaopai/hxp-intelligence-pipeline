#!/usr/bin/env python3
"""Generate deterministic offline content packages for cockpit CI and previews."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from publishing.package_builder import build_content_package_batch, load_sources  # noqa: E402
from visual.pipeline import write_json  # noqa: E402
from visual.queue import load_json  # noqa: E402

PRESETS = {
    "vertical_9x16": (2160, 3840, "9:16", ["douyin", "wechat_channels"]),
    "portrait_3x4": (2160, 2880, "3:4", ["xiaohongshu"]),
    "landscape_16x9": (2560, 1440, "16:9", ["x", "youtube", "website"]),
    "wechat_cover_235x1": (2350, 1000, "2.35:1", ["wechat_article"]),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output_root.resolve()
    source_assets = output / "source-assets"
    output.mkdir(parents=True, exist_ok=True)
    exports = []
    for preset_index, (preset, (width, height, ratio, platforms)) in enumerate(PRESETS.items(), start=1):
        for order in range(1, 7):
            path = source_assets / preset / f"poster-{order:02d}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new(
                "RGB",
                (320, 320),
                (175 + preset_index * 8 + order, 218 + order, 238 - preset_index * 3),
            ).save(path, "PNG")
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
        "review_batch_id": "visual-review-20260729-cockpit-fixture",
        "date": "2026-07-29",
        "generated_at": "2026-07-29T12:00:00+08:00",
        "template_version": "1.0.0",
        "exports": exports,
        "summary": {"total": 24, "passed": 24, "failed": 0, "preset_counts": {value: 6 for value in PRESETS}},
    }
    package_batch = build_content_package_batch(
        briefing=load_json(ROOT / "data/daily/2026-07-29/briefing.json"),
        export_manifest=export_manifest,
        sources=load_sources(ROOT / "data/daily/2026-07-29/sources"),
        profiles=load_json(ROOT / "config/platform-profiles.json"),
    )
    write_json(output / "export-manifest.json", export_manifest)
    write_json(output / "content-packages.json", package_batch)
    print(f"PASS cockpit fixture: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
