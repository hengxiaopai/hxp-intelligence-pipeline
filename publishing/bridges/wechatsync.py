"""Provider-neutral Wechatsync contracts without launching a browser or bridge."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from .base import BrowserBridgeError, canonical_hash, classify_upstream_error, sanitize_url


SUPPORTED_PLATFORMS = ("zhihu", "juejin", "csdn")
DISPLAY_NAMES = {"zhihu": "知乎", "juejin": "掘金", "csdn": "CSDN"}


def _platforms(values: Sequence[str]) -> list[str]:
    result = sorted({str(value).strip().casefold() for value in values if str(value).strip()})
    if not result:
        raise BrowserBridgeError("Wechatsync 请求至少需要一个平台")
    unsupported = [value for value in result if value not in SUPPORTED_PLATFORMS]
    if unsupported:
        raise BrowserBridgeError(f"Phase 5.3A 尚未允许平台：{unsupported}")
    return result


def build_bridge_request(
    *,
    operation: str,
    platforms: Sequence[str],
    created_at: str,
    article: Mapping[str, Any] | None = None,
    account_ref: str | None = None,
    transport: str = "fixture",
    bridge_id: str = "wechatsync-mcp",
) -> dict[str, Any]:
    normalized_platforms = _platforms(platforms)
    if operation not in {"list_platforms", "check_auth", "preview_draft", "create_draft"}:
        raise BrowserBridgeError(f"未知 Wechatsync 操作：{operation}")
    if operation == "check_auth" and len(normalized_platforms) != 1:
        raise BrowserBridgeError("check_auth 只能检查一个平台")
    if operation in {"preview_draft", "create_draft"} and article is None:
        raise BrowserBridgeError("草稿操作必须绑定文章")
    if operation in {"list_platforms", "check_auth"} and article is not None:
        raise BrowserBridgeError("只读操作不得携带文章正文")
    if transport not in {"fixture", "mcp_tool", "cli_dry_run"}:
        raise BrowserBridgeError(f"不支持的桥接传输：{transport}")

    normalized_article = None
    if article is not None:
        normalized_article = {
            "article_id": str(article["article_id"]),
            "title": str(article["title"]).strip(),
            "markdown_path": Path(str(article["markdown_path"])).as_posix(),
            "content_hash": str(article["content_hash"]),
            "asset_hashes": list(article.get("asset_hashes", [])),
            "cover_path": (
                Path(str(article["cover_path"])).as_posix()
                if article.get("cover_path")
                else None
            ),
            "source_labels": list(article.get("source_labels", [])),
        }
        if not normalized_article["title"]:
            raise BrowserBridgeError("文章标题不能为空")

    if operation == "list_platforms":
        upstream_name = "list_platforms"
        upstream_arguments: dict[str, Any] = {"forceRefresh": False}
        command_preview = None
    elif operation == "check_auth":
        upstream_name = "check_auth"
        upstream_arguments = {"platform": normalized_platforms[0]}
        command_preview = None
    elif transport == "cli_dry_run" or operation == "preview_draft":
        upstream_name = "wechatsync sync --dry-run"
        upstream_arguments = {
            "platforms": normalized_platforms,
            "article_reference": normalized_article,
        }
        command_preview = [
            "wechatsync",
            "sync",
            normalized_article["markdown_path"],
            "--platforms",
            ",".join(normalized_platforms),
            "--title",
            normalized_article["title"],
            "--dry-run",
        ]
        if normalized_article.get("cover_path"):
            command_preview.extend(["--cover", normalized_article["cover_path"]])
    else:
        upstream_name = "sync_article"
        upstream_arguments = {
            "platforms": normalized_platforms,
            "title": normalized_article["title"],
            "markdown_file": normalized_article["markdown_path"],
            "content_hash": normalized_article["content_hash"],
            "cover_file": normalized_article.get("cover_path"),
        }
        command_preview = None

    fingerprint_material = {
        "bridge_id": bridge_id,
        "provider": "wechatsync",
        "operation": operation,
        "action": "draft_only",
        "platforms": normalized_platforms,
        "account_ref": account_ref,
        "transport": transport,
        "upstream_name": upstream_name,
        "article": normalized_article,
    }
    fingerprint = canonical_hash(fingerprint_material)
    return {
        "schema_version": "1.0.0",
        "bridge_request_id": "bridge-request-" + fingerprint,
        "request_fingerprint": "bridge-" + fingerprint,
        "bridge_id": bridge_id,
        "provider": "wechatsync",
        "operation": operation,
        "action": "draft_only",
        "created_at": created_at,
        "platforms": normalized_platforms,
        "account_ref": account_ref,
        "transport": transport,
        "upstream_call": {
            "name": upstream_name,
            "arguments": upstream_arguments,
            "command_preview": command_preview,
        },
        "article": normalized_article,
        "execution_allowed": False,
        "external_write_expected": False,
        "safety": {
            "loopback_only": True,
            "remote_bridge_allowed": False,
            "credential_values_persisted": False,
            "cli_exit_code_authoritative": False,
            "public_publish_allowed": False,
            "captcha_or_risk_control_policy": "hard_block",
        },
    }


def normalize_health_snapshot(
    *,
    raw_platforms: Sequence[Mapping[str, Any]],
    checked_at: str,
    extension_connected: bool | None,
    credential_present: bool | None,
    mode: str = "fixture",
    bridge_id: str = "wechatsync-mcp",
) -> dict[str, Any]:
    normalized: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for raw in raw_platforms:
        platform = str(raw.get("id") or raw.get("platform") or "").casefold()
        if platform not in SUPPORTED_PLATFORMS:
            continue
        authenticated = raw.get("isAuthenticated")
        error_message = raw.get("error")
        if error_message:
            error = dict(classify_upstream_error(error_message))
            errors.append(error)
            auth_status = "blocked" if not error["recoverable"] else "unknown"
            reason = error["message"]
        elif authenticated is True:
            auth_status = "authenticated"
            reason = None
        elif authenticated is False:
            auth_status = "unauthenticated"
            reason = "平台未登录或登录态已失效"
        else:
            auth_status = "unknown"
            reason = "上游未返回明确登录状态"
        normalized.append(
            {
                "platform": platform,
                "display_name": str(raw.get("name") or DISPLAY_NAMES[platform]),
                "auth_status": auth_status,
                "account_ref": str(raw.get("username")).strip() if raw.get("username") else None,
                "reason": reason,
            }
        )

    normalized.sort(key=lambda value: value["platform"])
    health_material = {
        "bridge_id": bridge_id,
        "checked_at": checked_at,
        "mode": mode,
        "extension_connected": extension_connected,
        "credential_present": credential_present,
        "platforms": normalized,
        "errors": errors,
    }
    if errors and any(not error["recoverable"] for error in errors):
        status = "blocked"
    elif extension_connected is False:
        status = "unavailable"
    elif errors or any(value["auth_status"] == "unknown" for value in normalized):
        status = "degraded"
    else:
        status = "ready"
    return {
        "schema_version": "1.0.0",
        "health_id": "bridge-health-" + canonical_hash(health_material),
        "bridge_id": bridge_id,
        "provider": "wechatsync",
        "checked_at": checked_at,
        "mode": mode,
        "status": status,
        "loopback_verified": True,
        "remote_endpoint_detected": False,
        "extension_connected": extension_connected,
        "credential_present": credential_present,
        "platforms": normalized,
        "errors": errors,
    }


def normalize_bridge_result(
    *,
    request: Mapping[str, Any],
    raw_result: Mapping[str, Any],
    completed_at: str,
    mode: str = "fixture",
) -> dict[str, Any]:
    if request.get("execution_allowed") is not False:
        raise BrowserBridgeError("Phase 5.3A 只接受 execution_allowed=false 的请求")
    if request.get("provider") != "wechatsync":
        raise BrowserBridgeError("结果解析器只接受 Wechatsync 请求")

    raw_platform_results = raw_result.get("results", [])
    if not isinstance(raw_platform_results, list):
        raise BrowserBridgeError("Wechatsync 结构化结果缺少 results 数组")

    normalized: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    requested = set(request.get("platforms", []))
    seen: set[str] = set()
    for raw in raw_platform_results:
        platform = str(raw.get("platform", "")).casefold()
        if platform not in requested or platform not in SUPPORTED_PLATFORMS:
            continue
        seen.add(platform)
        success = raw.get("success") is True
        draft_only = raw.get("draftOnly") is not False
        error_message = raw.get("error") or raw.get("message")
        error_code = None
        message = str(raw.get("message")).strip() if raw.get("message") else None

        if success and draft_only:
            outcome = "draft_created"
        elif success and not draft_only:
            outcome = "blocked"
            error = {
                "code": "BRIDGE_PUBLIC_WRITE_BLOCKED",
                "classification": "configuration",
                "message": "上游结果不是草稿，HXP 已硬阻断",
                "recoverable": False,
            }
            errors.append(error)
            error_code = error["code"]
            message = error["message"]
        else:
            error = dict(classify_upstream_error(error_message))
            errors.append(error)
            error_code = error["code"]
            message = error["message"]
            if error["classification"] == "risk_control":
                outcome = "blocked"
            elif error["code"] == "BRIDGE_REVIEW_REQUIRED":
                outcome = "review_required"
            else:
                outcome = "failed"

        normalized.append(
            {
                "platform": platform,
                "outcome": outcome,
                "draft_only": True,
                "platform_post_id": str(raw.get("postId")) if raw.get("postId") else None,
                "sanitized_url": sanitize_url(raw.get("postUrl") or raw.get("url")),
                "account_ref": str(raw.get("username")).strip() if raw.get("username") else request.get("account_ref"),
                "error_code": error_code,
                "message": message,
            }
        )

    for platform in sorted(requested - seen):
        error = {
            "code": "BRIDGE_MISSING_PLATFORM_RESULT",
            "classification": "upstream",
            "message": f"上游未返回平台结果：{platform}",
            "recoverable": False,
        }
        errors.append(error)
        normalized.append(
            {
                "platform": platform,
                "outcome": "unknown",
                "draft_only": True,
                "platform_post_id": None,
                "sanitized_url": None,
                "account_ref": request.get("account_ref"),
                "error_code": error["code"],
                "message": error["message"],
            }
        )

    normalized.sort(key=lambda value: value["platform"])
    outcomes = {value["outcome"] for value in normalized}
    if outcomes and outcomes <= {"draft_created", "authenticated"}:
        status = "success"
    elif "blocked" in outcomes:
        status = "blocked"
    elif "draft_created" in outcomes:
        status = "partial_success"
    else:
        status = "failed"

    material = {
        "bridge_request_id": request["bridge_request_id"],
        "completed_at": completed_at,
        "mode": mode,
        "platform_results": normalized,
        "errors": errors,
    }
    return {
        "schema_version": "1.0.0",
        "result_id": "bridge-result-" + canonical_hash(material),
        "bridge_request_id": request["bridge_request_id"],
        "request_fingerprint": request["request_fingerprint"],
        "bridge_id": request["bridge_id"],
        "provider": "wechatsync",
        "operation": request["operation"],
        "completed_at": completed_at,
        "mode": mode,
        "status": status,
        "external_write_performed": False,
        "structured_result_used": True,
        "cli_exit_code_used_as_authority": False,
        "platform_results": normalized,
        "errors": errors,
    }
