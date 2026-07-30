"""Build no-credential official connector request plans without executing them."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any, Mapping
from urllib.parse import urlsplit


class OfficialRequestError(ValueError):
    """Raised when an official request plan is unsafe or incomplete."""


SECRET_PATTERN = re.compile(
    r"(?i)(bearer\s+|authorization\s*[:=]|access[_-]?token\s*[:=]|app[_-]?secret\s*[:=]|cookie\s*[:=]|session\s*[:=])"
)


def _canonical_hash(value: Any) -> str:
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _parse_time(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OfficialRequestError(f"时间格式无效：{value}") from exc


def _origin(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise OfficialRequestError("官方Origin必须使用HTTPS")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise OfficialRequestError("官方Origin只能包含scheme与host")
    return f"https://{parsed.netloc.casefold()}"


def _assert_no_secret(value: Any, field: str) -> None:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    if SECRET_PATTERN.search(text):
        raise OfficialRequestError(f"请求计划不得包含敏感值：{field}")


def _request_plan(connector_id: str) -> list[dict[str, Any]]:
    if connector_id == "halo-official-draft":
        return [
            {
                "sequence": 1,
                "operation": "create_draft_post",
                "method": "POST",
                "path": "/apis/api.console.halo.run/v1alpha1/posts",
                "body_fields": ["metadata", "spec", "content"],
                "requires_user_confirmation": False,
            },
            {
                "sequence": 2,
                "operation": "update_draft_content",
                "method": "PUT",
                "path": "/apis/api.console.halo.run/v1alpha1/posts/{name}/content",
                "body_fields": ["raw", "content", "rawType"],
                "requires_user_confirmation": False,
            },
        ]
    if connector_id == "wechat-official-draft":
        return [
            {
                "sequence": 1,
                "operation": "verify_material_mapping",
                "method": "GET",
                "path": "/offline/material-mapping",
                "body_fields": ["thumb_media_id", "body_image_urls"],
                "requires_user_confirmation": False,
            },
            {
                "sequence": 2,
                "operation": "add_draft",
                "method": "POST",
                "path": "/cgi-bin/draft/add",
                "body_fields": ["articles", "title", "author", "digest", "content", "thumb_media_id"],
                "requires_user_confirmation": False,
            },
        ]
    if connector_id == "douyin-official-image-text":
        return [
            {
                "sequence": 1,
                "operation": "verify_oauth_scope",
                "method": "GET",
                "path": "/offline/oauth/video.create",
                "body_fields": ["application_ref", "user_authorization_ref", "scope"],
                "requires_user_confirmation": True,
            },
            {
                "sequence": 2,
                "operation": "upload_images",
                "method": "POST",
                "path": "/image/upload/",
                "body_fields": ["ordered_images"],
                "requires_user_confirmation": True,
            },
            {
                "sequence": 3,
                "operation": "create_image_text",
                "method": "POST",
                "path": "/image_text/create/",
                "body_fields": ["title", "text", "image_ids", "topics"],
                "requires_user_confirmation": True,
            },
        ]
    if connector_id == "xiaohongshu-official-share":
        return [
            {
                "sequence": 1,
                "operation": "register_share_sdk",
                "method": "CLIENT_SHARE",
                "path": "xhs-share-sdk://register",
                "body_fields": ["app_key_reference", "application_platform"],
                "requires_user_confirmation": True,
            },
            {
                "sequence": 2,
                "operation": "open_xiaohongshu_publish_tool",
                "method": "CLIENT_SHARE",
                "path": "xhs-share-sdk://share-note",
                "body_fields": ["ordered_images", "title_optional", "content_optional"],
                "requires_user_confirmation": True,
            },
        ]
    raise OfficialRequestError(f"未知官方连接器：{connector_id}")


def build_official_request(
    *,
    qualification: Mapping[str, Any],
    connector_config: Mapping[str, Any],
    plan_entry: Mapping[str, Any],
    package: Mapping[str, Any],
    generated_at: str,
    expires_at: str,
    material_mapping: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a deterministic request contract that remains non-executable."""
    if qualification.get("status") not in {"eligible", "simulated"}:
        raise OfficialRequestError("连接器资格必须为eligible或simulated")
    if qualification.get("execution_allowed") is not False:
        raise OfficialRequestError("资格报告不得允许执行")
    if connector_config.get("enabled") is not False:
        raise OfficialRequestError("Phase 5.4A连接器必须保持禁用")
    connector_id = str(connector_config["connector_id"])
    platform = str(connector_config["platform"])
    if qualification.get("connector_id") != connector_id or qualification.get("platform") != platform:
        raise OfficialRequestError("资格报告与连接器配置不一致")
    if plan_entry.get("platform") != platform or package.get("platform") != platform:
        raise OfficialRequestError("平台、发布计划和内容包不一致")
    if plan_entry.get("package_id") != package.get("package_id"):
        raise OfficialRequestError("发布计划引用的内容包不一致")
    if plan_entry.get("content_hash") != package.get("content_hash"):
        raise OfficialRequestError("内容哈希漂移")
    asset_hashes = [str(value["sha256"]) for value in package.get("assets", [])]
    if list(plan_entry.get("asset_hashes", [])) != asset_hashes:
        raise OfficialRequestError("图片哈希或顺序漂移")
    if plan_entry.get("write_allowed") is not False:
        raise OfficialRequestError("发布计划必须保持write_allowed=false")
    if connector_config.get("supports_public_publish") is not False:
        raise OfficialRequestError("Phase 5.4A禁止公开发布能力")

    generated = _parse_time(generated_at)
    expires = _parse_time(expires_at)
    if expires <= generated:
        raise OfficialRequestError("请求计划到期时间必须晚于生成时间")
    official_origin = _origin(str(connector_config["official_base_origins"][0]))
    credentials = list(connector_config.get("credential_environment_variables", []))
    for field, value in (
        ("qualification", qualification),
        ("material_mapping", material_mapping),
        ("account_ref", qualification.get("account_ref")),
        ("application_ref", qualification.get("application_ref")),
    ):
        _assert_no_secret(value, field)

    mapping_status = str(material_mapping.get("status", "pending"))
    if connector_id == "wechat-official-draft" and mapping_status not in {"complete", "simulated"}:
        raise OfficialRequestError("微信草稿请求必须完成封面与正文素材映射")
    if connector_id == "douyin-official-image-text" and not 1 <= len(asset_hashes) <= 30:
        raise OfficialRequestError("抖音图文图片数量必须为1至30张")
    if connector_id == "xiaohongshu-official-share" and not 1 <= len(asset_hashes) <= 18:
        raise OfficialRequestError("小红书图文图片数量必须为1至18张")

    material = {
        "status": mapping_status,
        "cover_reference": material_mapping.get("cover_reference"),
        "asset_references": list(material_mapping.get("asset_references", [])),
    }
    identity = {
        "connector_id": connector_id,
        "platform": platform,
        "entry_id": plan_entry["entry_id"],
        "package_id": package["package_id"],
        "content_hash": package["content_hash"],
        "asset_hashes": asset_hashes,
        "material_mapping": material,
        "account_ref": qualification.get("account_ref"),
        "application_ref": qualification.get("application_ref"),
        "expires_at": expires_at,
    }
    compact = str(package["package_id"]).split("-")[2]
    return {
        "schema_version": "1.0.0",
        "request_id": f"official-request-{compact}-{connector_id}",
        "connector_id": connector_id,
        "platform": platform,
        "action": connector_config["action"],
        "qualification_status": qualification["status"],
        "publication_entry_id": plan_entry["entry_id"],
        "package_id": package["package_id"],
        "account_ref": qualification.get("account_ref"),
        "application_ref": qualification.get("application_ref"),
        "content_hash": package["content_hash"],
        "asset_hashes": asset_hashes,
        "material_mapping": material,
        "credential_environment_variables": credentials,
        "official_origin": official_origin,
        "generated_at": generated_at,
        "expires_at": expires_at,
        "idempotency_key": "official-" + _canonical_hash(identity)[:48],
        "request_plan": _request_plan(connector_id),
        "execution_enabled": False,
        "external_write_performed": False,
    }
