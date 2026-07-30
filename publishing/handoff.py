"""Build deterministic no-extension publishing handoff bundles.

This module only copies already-verified assets, renders local text files and records
hashes. It never opens a browser, reads cookies, uses credentials or writes to an
external platform.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PLATFORMS = ["wechat", "xiaohongshu", "douyin", "x", "website", "zhihu"]


class HandoffError(ValueError):
    """Raised when a handoff bundle cannot be produced safely."""


def _sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    _write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _file_record(path: Path, root: Path) -> dict[str, Any]:
    body = path.read_bytes()
    return {
        "path": path.resolve().relative_to(root.resolve()).as_posix(),
        "sha256": _sha256_bytes(body),
        "byte_size": len(body),
    }


def _resolve_asset_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (ROOT / path).resolve()


def _safe_source_label(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return f"external-assets/{path.name}"


def _origin(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise HandoffError(f"创作入口必须使用HTTPS：{value}")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise HandoffError(f"创作入口不得包含凭据、查询参数或片段：{value}")
    return f"https://{parsed.netloc.casefold()}"


def _profile_map(config: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    if config.get("external_write_enabled") is not False:
        raise HandoffError("发布驾驶舱必须保持 external_write_enabled=false")
    if config.get("browser_automation_enabled") is not False:
        raise HandoffError("发布驾驶舱不得启用浏览器自动化")
    rules = config.get("global_rules", {})
    required_true = (
        "cookies_forbidden",
        "credentials_forbidden",
        "playwright_forbidden",
        "cdp_forbidden",
        "dom_injection_forbidden",
        "clipboard_read_forbidden",
        "official_https_links_only",
        "publication_success_must_be_user_recorded",
    )
    if rules.get("extensions_required") is not False:
        raise HandoffError("无扩展发布驾驶舱不得要求浏览器扩展")
    for key in required_true:
        if rules.get(key) is not True:
            raise HandoffError(f"发布驾驶舱安全规则缺失：{key}")
    if rules.get("external_write_performed") is not False:
        raise HandoffError("发布驾驶舱必须声明 external_write_performed=false")

    result: dict[str, Mapping[str, Any]] = {}
    for profile in config.get("platforms", []):
        platform = str(profile.get("platform", ""))
        if platform in result:
            raise HandoffError(f"驾驶舱平台配置重复：{platform}")
        creator_url = str(profile.get("creator_url", ""))
        allowed_origins = [str(value) for value in profile.get("allowed_origins", [])]
        creator_origin = _origin(creator_url)
        normalized_allowed = {_origin(value) for value in allowed_origins}
        if creator_origin not in normalized_allowed:
            raise HandoffError(f"创作入口不在白名单中：{platform}：{creator_url}")
        result[platform] = profile
    if list(result) != EXPECTED_PLATFORMS:
        raise HandoffError(f"驾驶舱平台必须按固定顺序完整覆盖：{EXPECTED_PLATFORMS}")
    return result


def _package_map(package_batch: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    if package_batch.get("write_actions_enabled") is not False:
        raise HandoffError("内容包批次必须保持 write_actions_enabled=false")
    result: dict[str, Mapping[str, Any]] = {}
    for package in package_batch.get("packages", []):
        platform = str(package.get("platform", ""))
        if platform in result:
            raise HandoffError(f"内容包平台重复：{platform}")
        if package.get("status") != "validated":
            raise HandoffError(f"内容包未通过验证：{platform}")
        validations = package.get("validations", {})
        if not validations or not all(bool(value) for value in validations.values()):
            raise HandoffError(f"内容包校验项未全部通过：{platform}")
        result[platform] = package
    if list(result) != EXPECTED_PLATFORMS:
        raise HandoffError(f"内容包必须按固定顺序完整覆盖：{EXPECTED_PLATFORMS}")
    return result


def _normalized_content(content: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "title": str(content.get("title", "")),
        "summary": str(content.get("summary", "")),
        "body_markdown": str(content.get("body_markdown", "")),
        "caption": str(content.get("caption", "")),
        "thread": [str(value) for value in content.get("thread", [])],
        "hashtags": [str(value) for value in content.get("hashtags", [])],
        "seo_title": str(content.get("seo_title", "")),
        "seo_description": str(content.get("seo_description", "")),
        "slug": str(content.get("slug", "")),
        "source_labels": [str(value) for value in content.get("source_labels", [])],
        "risk_disclaimer": content.get("risk_disclaimer"),
        "answer_question_placeholder": content.get("answer_question_placeholder"),
        "answer_markdown": str(content.get("answer_markdown", "")),
    }


def _markdown_for_platform(platform: str, content: Mapping[str, Any]) -> str:
    if platform == "zhihu":
        lines = [
            "# 知乎文章版",
            "",
            f"标题：{content['title']}",
            "",
            str(content["body_markdown"]),
            "",
            "# 知乎回答版",
            "",
            f"问题占位：{content['answer_question_placeholder']}",
            "",
            str(content["answer_markdown"]),
        ]
        return "\n".join(lines).strip() + "\n"

    lines = [f"# {content['title']}" if content.get("title") else "# 平台内容", ""]
    if content.get("summary"):
        lines.extend([str(content["summary"]), ""])
    if content.get("body_markdown"):
        lines.extend([str(content["body_markdown"]), ""])
    if content.get("caption"):
        lines.extend(["## 发布文案", "", str(content["caption"]), ""])
    if content.get("thread"):
        lines.extend(["## 线程", ""])
        lines.extend(f"{index}. {value}" for index, value in enumerate(content["thread"], start=1))
        lines.append("")
    if content.get("hashtags"):
        lines.extend(["## 话题", "", " ".join(content["hashtags"]), ""])
    if content.get("seo_title") or content.get("seo_description"):
        lines.extend(
            [
                "## SEO",
                "",
                f"SEO标题：{content.get('seo_title', '')}",
                f"SEO描述：{content.get('seo_description', '')}",
                f"Slug：{content.get('slug', '')}",
                "",
            ]
        )
    lines.extend(["## 来源", "", *[f"- {value}" for value in content.get("source_labels", [])]])
    if content.get("risk_disclaimer"):
        lines.extend(["", f"> {content['risk_disclaimer']}"])
    return "\n".join(lines).strip() + "\n"


def _text_for_platform(platform: str, content: Mapping[str, Any]) -> str:
    markdown = _markdown_for_platform(platform, content)
    replacements = ("# ", "", "## ", "", "> ", "", "**", "")
    value = markdown
    for index in range(0, len(replacements), 2):
        value = value.replace(replacements[index], replacements[index + 1])
    return value


def _copy_assets(
    assets: Sequence[Mapping[str, Any]],
    *,
    platform_dir: Path,
    output_root: Path,
) -> list[dict[str, Any]]:
    if not assets:
        raise HandoffError(f"交接包缺少视觉资产：{platform_dir.name}")
    result: list[dict[str, Any]] = []
    asset_dir = platform_dir / "assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    for asset in sorted(assets, key=lambda value: int(value["order"])):
        source = _resolve_asset_path(str(asset["path"]))
        if not source.is_file():
            raise HandoffError(f"视觉资产不存在：{source}")
        body = source.read_bytes()
        actual_hash = _sha256_bytes(body)
        expected_hash = str(asset["sha256"])
        if actual_hash != expected_hash:
            raise HandoffError(f"视觉资产哈希不一致：{source}")
        suffix = source.suffix.casefold()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise HandoffError(f"视觉资产格式不受支持：{source}")
        order = int(asset["order"])
        destination = asset_dir / f"{order:02d}{suffix}"
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_bytes(body)
        temporary.replace(destination)
        result.append(
            {
                "order": order,
                "source_path": _safe_source_label(source),
                "bundle_path": destination.resolve().relative_to(output_root.resolve()).as_posix(),
                "sha256": actual_hash,
                "width": int(asset["width"]),
                "height": int(asset["height"]),
            }
        )
    return result


def build_handoff_bundle(
    *,
    package_batch: Mapping[str, Any],
    config: Mapping[str, Any],
    output_dir: Path,
    generated_at: str,
) -> dict[str, Any]:
    """Create six platform handoff directories and return a manifest."""
    packages = _package_map(package_batch)
    profiles = _profile_map(config)
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    date = str(package_batch["date"])
    platforms: list[dict[str, Any]] = []

    for platform in EXPECTED_PLATFORMS:
        profile = profiles[platform]
        package = packages[platform]
        content = _normalized_content(package["content"])
        source_assets = list(package.get("assets", []))
        content_hash = str(package["content_hash"])

        platform_dir = output_dir / platform
        copied_assets = _copy_assets(
            source_assets,
            platform_dir=platform_dir,
            output_root=output_dir,
        )
        package_payload = {
            "schema_version": "1.0.0",
            "platform": platform,
            "display_name": profile["display_name"],
            "derived": False,
            "content_hash": content_hash,
            "asset_hashes": [value["sha256"] for value in copied_assets],
            "content": content,
            "creator_url": profile["creator_url"],
            "actions": profile["actions"],
            "checklist": profile["checklist"],
            "external_write_performed": False,
        }
        json_path = platform_dir / "content.json"
        markdown_path = platform_dir / "content.md"
        text_path = platform_dir / "content.txt"
        _write_json(json_path, package_payload)
        _write_text(markdown_path, _markdown_for_platform(platform, content))
        _write_text(text_path, _text_for_platform(platform, content))

        platforms.append(
            {
                "platform": platform,
                "display_name": str(profile["display_name"]),
                "status": "ready",
                "derived": False,
                "handoff_mode": str(profile["handoff_mode"]),
                "creator_url": str(profile["creator_url"]),
                "allowed_origins": [str(value) for value in profile["allowed_origins"]],
                "content_hash": content_hash,
                "asset_hashes": [value["sha256"] for value in copied_assets],
                "content": content,
                "assets": copied_assets,
                "actions": [str(value) for value in profile["actions"]],
                "checklist": [str(value) for value in profile["checklist"]],
                "files": {
                    "json": _file_record(json_path, output_dir),
                    "markdown": _file_record(markdown_path, output_dir),
                    "text": _file_record(text_path, output_dir),
                },
                "errors": [],
            }
        )

    return {
        "schema_version": "1.0.0",
        "handoff_id": "handoff-" + date.replace("-", ""),
        "package_batch_id": package_batch["package_batch_id"],
        "date": date,
        "generated_at": generated_at,
        "external_write_performed": False,
        "platforms": platforms,
        "summary": {
            "total": 6,
            "ready": 6,
            "blocked": 0,
            "derived": 0,
        },
    }
