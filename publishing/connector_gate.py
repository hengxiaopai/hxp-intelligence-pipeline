"""Issue, validate, consume and revoke exact hash-bound connector authorizations."""

from __future__ import annotations

from typing import Any, Mapping

from .connectors.base import (
    ConnectorError,
    canonical_hash,
    exact_binding,
    parse_timestamp,
    safe_credential_reference,
)


class ConnectorGateError(ConnectorError):
    """Raised when a connector request crosses an authorization boundary."""


def _assert_connector_entry(connector: Mapping[str, Any], entry: Mapping[str, Any]) -> None:
    if not connector.get("enabled"):
        raise ConnectorGateError(f"连接器未启用：{connector.get('connector_id')}")
    if connector.get("mode") != "simulator":
        raise ConnectorGateError("当前阶段只允许Simulator，不允许真实或人工发布连接器")
    if connector.get("platform") != entry.get("platform"):
        raise ConnectorGateError("连接器平台与发布条目不一致")
    if entry.get("approval_status") != "approved":
        raise ConnectorGateError("发布条目尚未获得人工批准")
    if entry.get("write_allowed") is not False:
        raise ConnectorGateError("Phase 5.2前置计划必须保持write_allowed=false")
    if entry.get("action") not in connector.get("allowed_actions", []):
        raise ConnectorGateError("发布动作不在连接器允许范围内")
    if entry.get("action") != "draft_only":
        raise ConnectorGateError("当前阶段只允许draft_only")


def issue_connector_authorization(
    *,
    connector: Mapping[str, Any],
    entry: Mapping[str, Any],
    account_ref: str,
    issued_at: str,
    expires_at: str,
    issued_by: str,
    credential_reference: str | None = None,
) -> dict[str, Any]:
    """Create a single-use authorization bound to exact content and asset order."""
    _assert_connector_entry(connector, entry)
    issued = parse_timestamp(issued_at, field="issued_at")
    expires = parse_timestamp(expires_at, field="expires_at")
    if expires <= issued:
        raise ConnectorGateError("授权到期时间必须晚于签发时间")
    account = str(account_ref).strip()
    if len(account) < 3:
        raise ConnectorGateError("账号引用不能为空且至少3个字符")
    issuer = str(issued_by).strip()
    if not issuer:
        raise ConnectorGateError("授权签发人不能为空")
    credential = safe_credential_reference(credential_reference)
    if connector.get("credential_environment_variables") and credential is None:
        raise ConnectorGateError("该连接器要求凭据引用")
    if not connector.get("credential_environment_variables") and credential is not None:
        raise ConnectorGateError("Simulator不得携带凭据引用")

    binding = exact_binding(entry)
    material = {
        "connector_id": connector["connector_id"],
        "platform": connector["platform"],
        "account_ref": account,
        **binding,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "issued_by": issuer,
        "credential_reference": credential,
    }
    return {
        "schema_version": "1.0.0",
        "authorization_id": "connector-auth-" + canonical_hash(material)[:48],
        "connector_id": connector["connector_id"],
        "platform": connector["platform"],
        "account_ref": account,
        "entry_id": binding["entry_id"],
        "idempotency_key": binding["idempotency_key"],
        "content_hash": binding["content_hash"],
        "asset_hashes": binding["asset_hashes"],
        "action": binding["action"],
        "issued_at": issued_at,
        "expires_at": expires_at,
        "issued_by": {"type": "human", "identifier": issuer},
        "status": "issued",
        "real_write_allowed": False,
        "credential_reference": credential,
    }


def validate_connector_authorization(
    *,
    authorization: Mapping[str, Any],
    connector: Mapping[str, Any],
    entry: Mapping[str, Any],
    account_ref: str,
    now: str,
) -> None:
    _assert_connector_entry(connector, entry)
    if authorization.get("status") != "issued":
        raise ConnectorGateError(f"授权状态不可消费：{authorization.get('status')}")
    current = parse_timestamp(now, field="now")
    expires = parse_timestamp(str(authorization.get("expires_at")), field="expires_at")
    issued = parse_timestamp(str(authorization.get("issued_at")), field="issued_at")
    if current < issued:
        raise ConnectorGateError("授权尚未生效")
    if current >= expires:
        raise ConnectorGateError("授权已过期")
    expected = exact_binding(entry)
    checks = {
        "connector_id": connector.get("connector_id"),
        "platform": connector.get("platform"),
        "account_ref": str(account_ref).strip(),
        **expected,
    }
    for field, expected_value in checks.items():
        if authorization.get(field) != expected_value:
            raise ConnectorGateError(f"授权绑定已漂移：{field}")
    if authorization.get("real_write_allowed") is not False:
        raise ConnectorGateError("当前授权不得允许真实写入")
    safe_credential_reference(authorization.get("credential_reference"))


def build_connector_request(
    *,
    authorization: Mapping[str, Any],
    connector: Mapping[str, Any],
    entry: Mapping[str, Any],
    package_id: str,
    account_ref: str,
    requested_at: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Consume one authorization and return a deterministic request plus updated auth."""
    validate_connector_authorization(
        authorization=authorization,
        connector=connector,
        entry=entry,
        account_ref=account_ref,
        now=requested_at,
    )
    package = str(package_id).strip()
    expected_suffix = f"-{entry['platform']}"
    if not package.startswith("content-package-") or not package.endswith(expected_suffix):
        raise ConnectorGateError("内容包ID与发布平台不一致")
    material = {
        "authorization_id": authorization["authorization_id"],
        "connector_id": connector["connector_id"],
        "account_ref": str(account_ref).strip(),
        "entry_id": entry["entry_id"],
        "package_id": package,
        "idempotency_key": entry["idempotency_key"],
        "content_hash": entry["content_hash"],
        "asset_hashes": list(entry["asset_hashes"]),
        "action": entry["action"],
    }
    request = {
        "schema_version": "1.0.0",
        "request_id": "connector-request-" + canonical_hash(material)[:48],
        "authorization_id": authorization["authorization_id"],
        "connector_id": connector["connector_id"],
        "connector_mode": connector["mode"],
        "platform": entry["platform"],
        "account_ref": str(account_ref).strip(),
        "entry_id": entry["entry_id"],
        "package_id": package,
        "idempotency_key": entry["idempotency_key"],
        "content_hash": entry["content_hash"],
        "asset_hashes": list(entry["asset_hashes"]),
        "action": entry["action"],
        "requested_at": requested_at,
        "status": "ready",
        "real_write_allowed": False,
        "credential_reference": authorization.get("credential_reference"),
    }
    consumed = dict(authorization)
    consumed["status"] = "consumed"
    return request, consumed


def revoke_connector_authorization(
    authorization: Mapping[str, Any],
) -> dict[str, Any]:
    if authorization.get("status") not in {"issued", "expired"}:
        raise ConnectorGateError("只有未消费授权可以撤销")
    revoked = dict(authorization)
    revoked["status"] = "revoked"
    return revoked


def expire_connector_authorization(
    authorization: Mapping[str, Any], *, now: str
) -> dict[str, Any]:
    if authorization.get("status") != "issued":
        return dict(authorization)
    current = parse_timestamp(now, field="now")
    expires = parse_timestamp(str(authorization.get("expires_at")), field="expires_at")
    if current < expires:
        raise ConnectorGateError("授权尚未到期")
    expired = dict(authorization)
    expired["status"] = "expired"
    return expired
