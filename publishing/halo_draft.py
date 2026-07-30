"""Build Halo draft payloads and non-secret live authorization records.

No function in this module performs an HTTP request.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta
from typing import Any, Mapping
from urllib.parse import urlsplit


class HaloDraftError(ValueError):
    """Raised when a Halo draft payload or authorization is unsafe."""


SECRET_PATTERN = re.compile(
    r"(?i)(bearer\s+|authorization\s*[:=]|personal[_ -]?access[_ -]?token\s*[:=]|cookie\s*[:=]|session\s*[:=])"
)


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _parse_time(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HaloDraftError(f"时间格式无效：{value}") from exc


def _origin(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise HaloDraftError("Halo站点必须使用HTTPS")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise HaloDraftError("Halo站点Origin只能包含scheme与host")
    return f"https://{parsed.netloc.casefold()}"


def _assert_no_secrets(value: Any, field: str) -> None:
    serialized = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    if SECRET_PATTERN.search(serialized):
        raise HaloDraftError(f"Halo草稿数据不得包含凭据值：{field}")


def build_halo_draft_payload(
    *,
    official_request: Mapping[str, Any],
    package: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    """Convert a verified website package into a non-executable Halo draft payload."""
    if policy.get("connector_id") != "halo-official-draft":
        raise HaloDraftError("Halo策略connector_id错误")
    if policy.get("execution_mode") != "mock_only" or policy.get("live_execution_enabled") is not False:
        raise HaloDraftError("Halo适配器必须保持mock_only且关闭真实执行")
    if policy.get("external_write_performed") is not False:
        raise HaloDraftError("Halo策略必须声明external_write_performed=false")
    if official_request.get("connector_id") != "halo-official-draft":
        raise HaloDraftError("官方请求不是Halo草稿连接器")
    if official_request.get("platform") != "website" or package.get("platform") != "website":
        raise HaloDraftError("Halo草稿只接受website内容包")
    if official_request.get("action") != "draft_only":
        raise HaloDraftError("Halo适配器只接受draft_only")
    if official_request.get("execution_enabled") is not False or official_request.get("external_write_performed") is not False:
        raise HaloDraftError("官方请求必须保持不可执行且无外部写入")
    if official_request.get("package_id") != package.get("package_id"):
        raise HaloDraftError("Halo请求与内容包ID不一致")
    if official_request.get("content_hash") != package.get("content_hash"):
        raise HaloDraftError("Halo内容哈希漂移")
    asset_hashes = [str(value["sha256"]) for value in package.get("assets", [])]
    if list(official_request.get("asset_hashes", [])) != asset_hashes:
        raise HaloDraftError("Halo图片哈希或顺序漂移")
    operations = [str(value.get("operation")) for value in official_request.get("request_plan", [])]
    allowed = list(policy.get("allowed_operations", []))
    if operations[:2] != allowed[:2]:
        raise HaloDraftError("Halo创建与正文更新操作顺序错误")
    forbidden = [str(value).casefold() for value in policy.get("forbidden_operations", [])]
    if any(operation.casefold() in forbidden for operation in operations):
        raise HaloDraftError("Halo请求包含禁止操作")
    for step in official_request.get("request_plan", []):
        path = str(step.get("path", "")).casefold()
        if any(fragment.casefold() in path for fragment in policy.get("forbidden_path_fragments", [])):
            raise HaloDraftError("Halo请求路径包含publish/delete等禁止片段")

    content = package.get("content", {})
    title = str(content.get("title", "")).strip()
    raw = str(content.get("body_markdown", "")).strip()
    slug = str(content.get("slug", "")).strip()
    if not title or not raw or not slug:
        raise HaloDraftError("Halo内容包缺少标题、正文或slug")
    payload_seed = {
        "request_id": official_request["request_id"],
        "package_id": package["package_id"],
        "content_hash": package["content_hash"],
        "asset_hashes": asset_hashes,
        "title": title,
        "slug": slug,
        "raw": raw,
    }
    payload_hash = canonical_hash(payload_seed)
    name = f"hxp-draft-{payload_hash[:16]}"
    payload = {
        "schema_version": "1.0.0",
        "payload_id": f"halo-draft-payload-{payload_hash[:24]}",
        "request_id": official_request["request_id"],
        "connector_id": "halo-official-draft",
        "publication_entry_id": official_request["publication_entry_id"],
        "package_id": package["package_id"],
        "idempotency_key": official_request["idempotency_key"],
        "content_hash": package["content_hash"],
        "asset_hashes": asset_hashes,
        "payload_hash": payload_hash,
        "post": {
            "apiVersion": "content.halo.run/v1alpha1",
            "kind": "Post",
            "metadata": {"name": name},
            "spec": {
                "title": title,
                "slug": slug,
                "releaseSnapshot": None,
                "headSnapshot": None,
                "baseSnapshot": None,
                "owner": official_request.get("account_ref") or "hxp-account-ref-required",
                "template": "",
                "cover": package["assets"][0]["path"],
                "deleted": False,
                "publish": False,
                "publishTime": None,
                "pinned": False,
                "allowComment": True,
                "visible": "PUBLIC",
                "priority": 0,
                "excerpt": {
                    "autoGenerate": False,
                    "raw": str(content.get("summary", ""))[:300],
                },
                "categories": [],
                "tags": [],
                "htmlMetas": [],
            },
        },
        "content": {
            "raw": raw,
            "content": raw,
            "rawType": "markdown",
        },
        "paths": {
            "create": "/apis/api.console.halo.run/v1alpha1/posts",
            "content": f"/apis/api.console.halo.run/v1alpha1/posts/{name}/content",
            "status": f"/apis/content.halo.run/v1alpha1/posts/{name}",
        },
        "credential_environment_variable": policy["credential_environment_variable"],
        "base_url_environment_variable": policy["base_url_environment_variable"],
        "execution_enabled": False,
        "external_write_performed": False,
    }
    _assert_no_secrets(payload, "payload")
    return payload


def issue_halo_live_authorization(
    *,
    official_request: Mapping[str, Any],
    site_origin: str,
    site_fingerprint: str,
    halo_version: str,
    account_ref: str,
    issued_at: str,
    expires_at: str,
    issued_by: str,
    user_confirmed_draft_only: bool,
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    """Issue a non-secret authorization record; it does not enable execution by itself."""
    if not user_confirmed_draft_only:
        raise HaloDraftError("必须明确确认只创建草稿")
    if official_request.get("connector_id") != "halo-official-draft" or official_request.get("action") != "draft_only":
        raise HaloDraftError("授权只能绑定Halo draft_only请求")
    if official_request.get("execution_enabled") is not False:
        raise HaloDraftError("官方请求必须保持不可执行")
    origin = _origin(site_origin)
    if not re.fullmatch(r"site-[a-f0-9]{32,64}", site_fingerprint):
        raise HaloDraftError("站点指纹格式无效")
    if not re.fullmatch(r"[0-9]+\.[0-9]+(?:\.[0-9]+)?(?:[-+][a-zA-Z0-9.-]+)?", halo_version):
        raise HaloDraftError("Halo版本格式无效")
    issued = _parse_time(issued_at)
    expires = _parse_time(expires_at)
    maximum = int(policy.get("live_authorization", {}).get("maximum_lifetime_minutes", 60))
    if expires <= issued or expires - issued > timedelta(minutes=maximum):
        raise HaloDraftError("授权有效期无效或超过策略上限")
    for field, value in (("account_ref", account_ref), ("issued_by", issued_by), ("site_origin", origin)):
        _assert_no_secrets(value, field)
    identity = {
        "site_origin": origin,
        "site_fingerprint": site_fingerprint,
        "halo_version": halo_version,
        "account_ref": account_ref,
        "request_id": official_request["request_id"],
        "content_hash": official_request["content_hash"],
        "asset_hashes": official_request["asset_hashes"],
        "issued_at": issued_at,
        "expires_at": expires_at,
    }
    compact = official_request["request_id"].split("-")[2]
    return {
        "schema_version": "1.0.0",
        "authorization_id": f"halo-live-auth-{compact}-{canonical_hash(identity)[:24]}",
        "connector_id": "halo-official-draft",
        "status": "issued",
        "site_origin": origin,
        "site_fingerprint": site_fingerprint,
        "halo_version": halo_version,
        "account_ref": account_ref,
        "request_id": official_request["request_id"],
        "publication_entry_id": official_request["publication_entry_id"],
        "package_id": official_request["package_id"],
        "content_hash": official_request["content_hash"],
        "asset_hashes": list(official_request["asset_hashes"]),
        "action": "draft_only",
        "credential_environment_variable": "HXP_HALO_PAT",
        "issued_at": issued_at,
        "expires_at": expires_at,
        "issued_by": issued_by,
        "consumed_at": None,
        "revoked_at": None,
        "user_confirmed_draft_only": True,
        "publish_allowed": False,
    }
