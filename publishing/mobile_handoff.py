"""Build phone-transfer directories from a validated no-extension handoff manifest."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any, Mapping


MOBILE_PLATFORMS = ("xiaohongshu", "douyin", "zhihu")


class MobileHandoffError(ValueError):
    """Raised when mobile handoff files cannot preserve source identity."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def _file_record(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": path.resolve().relative_to(root.resolve()).as_posix(),
        "sha256": _sha256(path),
        "byte_size": path.stat().st_size,
    }


def _instructions(platform: str, display_name: str) -> str:
    common = [
        f"# {display_name} 手机交接包",
        "",
        "该目录只用于把已审核文案和图片传输到手机。它不会登录平台、调用发布接口或自动点击发布。",
        "",
        "## 使用步骤",
        "",
        "1. 将整个目录发送到自己的手机或同步到可信的个人文件空间。",
        "2. 按 assets 目录中的两位数字顺序选择图片。",
        "3. 从 content.txt 或 content.md 复制对应文案。",
        "4. 在官方 App 中人工核对账号、标题、正文、图片顺序、话题和风险声明。",
        "5. 最终发布按钮必须由用户本人点击。",
        "",
        "## 禁止事项",
        "",
        "- 不把该目录上传到公开文件空间。",
        "- 不把打开 App、复制内容或选择图片误认为发布成功。",
        "- 不修改图片后继续沿用旧 SHA-256 或旧人工确认状态。",
    ]
    if platform == "xiaohongshu":
        common.extend(
            [
                "",
                "## 小红书检查",
                "",
                "- 优先使用 3:4 图片，确认首图和后续图顺序。",
                "- 检查标题、正文和话题标签，避免过度营销或绝对化表述。",
            ]
        )
    elif platform == "douyin":
        common.extend(
            [
                "",
                "## 抖音图文检查",
                "",
                "- 使用 9:16 图片并确认顺序。",
                "- 检查标题、描述和话题，品牌标识不要遮挡主体。",
            ]
        )
    else:
        common.extend(
            [
                "",
                "## 知乎检查",
                "",
                "- 先选择文章或回答形态。",
                "- 回答版必须先选择一个真实相关问题，不能发布占位文本。",
                "- 保留来源、AI 辅助说明和适用的风险声明。",
            ]
        )
    return "\n".join(common).strip() + "\n"


def build_mobile_handoff(
    *,
    handoff_manifest: Mapping[str, Any],
    handoff_root: Path,
    output_dir: Path,
    generated_at: str,
) -> dict[str, Any]:
    """Copy three mobile-oriented packages after verifying all hashes."""
    if handoff_manifest.get("external_write_performed") is not False:
        raise MobileHandoffError("手机交接只接受未执行外部写入的Handoff")
    entries = {value["platform"]: value for value in handoff_manifest.get("platforms", [])}
    if not all(platform in entries for platform in MOBILE_PLATFORMS):
        raise MobileHandoffError("Handoff缺少小红书、抖音或知乎")

    handoff_root = handoff_root.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    packages: list[dict[str, Any]] = []

    for platform in MOBILE_PLATFORMS:
        entry = entries[platform]
        if entry.get("status") != "ready":
            raise MobileHandoffError(f"平台交接内容未就绪：{platform}")
        platform_dir = output_dir / platform
        asset_dir = platform_dir / "assets"
        asset_dir.mkdir(parents=True, exist_ok=True)

        content_text_source = handoff_root / entry["files"]["text"]["path"]
        content_md_source = handoff_root / entry["files"]["markdown"]["path"]
        for source, record in (
            (content_text_source, entry["files"]["text"]),
            (content_md_source, entry["files"]["markdown"]),
        ):
            if not source.is_file() or _sha256(source) != record["sha256"]:
                raise MobileHandoffError(f"内容文件缺失或哈希不一致：{source}")

        content_text = platform_dir / "content.txt"
        content_markdown = platform_dir / "content.md"
        shutil.copyfile(content_text_source, content_text)
        shutil.copyfile(content_md_source, content_markdown)
        instructions = platform_dir / "README.txt"
        _write_text(instructions, _instructions(platform, str(entry["display_name"])))

        copied_assets: list[dict[str, Any]] = []
        for asset in sorted(entry["assets"], key=lambda value: int(value["order"])):
            source = handoff_root / asset["bundle_path"]
            if not source.is_file():
                raise MobileHandoffError(f"手机交接图片不存在：{source}")
            actual_hash = _sha256(source)
            if actual_hash != asset["sha256"]:
                raise MobileHandoffError(f"手机交接图片哈希不一致：{source}")
            target = asset_dir / source.name
            shutil.copyfile(source, target)
            copied_assets.append(
                {
                    "order": int(asset["order"]),
                    "path": target.resolve().relative_to(output_dir).as_posix(),
                    "sha256": actual_hash,
                    "byte_size": target.stat().st_size,
                }
            )

        packages.append(
            {
                "platform": platform,
                "display_name": str(entry["display_name"]),
                "status": "ready",
                "content_hash": str(entry["content_hash"]),
                "asset_hashes": [value["sha256"] for value in copied_assets],
                "directory": platform_dir.resolve().relative_to(output_dir).as_posix(),
                "instructions": _file_record(instructions, output_dir),
                "content_text": _file_record(content_text, output_dir),
                "content_markdown": _file_record(content_markdown, output_dir),
                "assets": copied_assets,
                "errors": [],
            }
        )

    index_lines = [
        "珩小派手机交接包",
        "",
        f"日期：{handoff_manifest['date']}",
        "",
        "目录：",
        *[f"- {value['display_name']}：{value['directory']}" for value in packages],
        "",
        "该交接包不包含账号、密码、Cookie或自动发布程序。",
    ]
    _write_text(output_dir / "README.txt", "\n".join(index_lines).strip() + "\n")

    return {
        "schema_version": "1.0.0",
        "mobile_handoff_id": "mobile-handoff-" + str(handoff_manifest["date"]).replace("-", ""),
        "handoff_id": handoff_manifest["handoff_id"],
        "date": handoff_manifest["date"],
        "generated_at": generated_at,
        "external_write_performed": False,
        "packages": packages,
        "summary": {
            "total": 3,
            "ready": 3,
            "failed": 0,
            "assets": sum(len(value["assets"]) for value in packages),
        },
    }
