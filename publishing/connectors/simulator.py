"""Offline connector simulator with exact idempotency collision detection."""

from __future__ import annotations

from typing import Any, Mapping

from .base import ConnectorError, canonical_hash, ordered_hashes


class ConnectorSimulationError(ConnectorError):
    """Raised when a simulated connector request is unsafe or inconsistent."""


def empty_ledger(*, updated_at: str) -> dict[str, Any]:
    return {"schema_version": "1.0.0", "updated_at": updated_at, "entries": []}


def _binding(request: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "connector_id": str(request["connector_id"]),
        "account_ref": str(request["account_ref"]),
        "content_hash": str(request["content_hash"]),
        "asset_hashes": ordered_hashes(request["asset_hashes"]),
    }


def execute_simulated_draft(
    *,
    request: Mapping[str, Any],
    ledger: Mapping[str, Any] | None,
    executed_at: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Execute a no-write draft simulation and update the idempotency ledger."""
    if request.get("connector_mode") != "simulator":
        raise ConnectorSimulationError("Simulator拒绝非simulator请求")
    if request.get("status") != "ready":
        raise ConnectorSimulationError(f"请求状态不可执行：{request.get('status')}")
    if request.get("real_write_allowed") is not False:
        raise ConnectorSimulationError("Simulator禁止真实写入")
    if request.get("action") != "draft_only":
        raise ConnectorSimulationError("Simulator只允许draft_only")
    if request.get("credential_reference") is not None:
        raise ConnectorSimulationError("Simulator不得接收凭据引用")

    current = dict(ledger or empty_ledger(updated_at=executed_at))
    entries = [dict(value) for value in current.get("entries", [])]
    key = str(request["idempotency_key"])
    matches = [value for value in entries if value.get("idempotency_key") == key]
    binding = _binding(request)

    if matches:
        if len(matches) != 1:
            raise ConnectorSimulationError("幂等账本存在重复键")
        existing = matches[0]
        for field, expected in binding.items():
            if existing.get(field) != expected:
                raise ConnectorSimulationError(f"幂等键碰撞且绑定不一致：{field}")
        result = {
            "schema_version": "1.0.0",
            "result_id": existing["result_id"],
            "request_id": request["request_id"],
            "authorization_id": request["authorization_id"],
            "connector_id": request["connector_id"],
            "connector_mode": "simulator",
            "platform": request["platform"],
            "account_ref": request["account_ref"],
            "entry_id": request["entry_id"],
            "idempotency_key": key,
            "content_hash": request["content_hash"],
            "asset_hashes": list(request["asset_hashes"]),
            "executed_at": executed_at,
            "status": "idempotent_replay",
            "external_write_performed": False,
            "external_id": None,
            "external_url": None,
            "simulated_draft_id": existing["simulated_draft_id"],
            "response_summary": "命中既有幂等记录，未创建新的模拟草稿。",
            "error_type": None,
            "error_message": None,
        }
        return result, current

    result_material = {
        "request_id": request["request_id"],
        "idempotency_key": key,
        **binding,
    }
    result_id = "connector-result-" + canonical_hash(result_material)[:48]
    simulated_draft_id = "sim-draft-" + canonical_hash(
        {"idempotency_key": key, "connector_id": request["connector_id"], "account_ref": request["account_ref"]}
    )[:32]
    result = {
        "schema_version": "1.0.0",
        "result_id": result_id,
        "request_id": request["request_id"],
        "authorization_id": request["authorization_id"],
        "connector_id": request["connector_id"],
        "connector_mode": "simulator",
        "platform": request["platform"],
        "account_ref": request["account_ref"],
        "entry_id": request["entry_id"],
        "idempotency_key": key,
        "content_hash": request["content_hash"],
        "asset_hashes": list(request["asset_hashes"]),
        "executed_at": executed_at,
        "status": "simulated",
        "external_write_performed": False,
        "external_id": None,
        "external_url": None,
        "simulated_draft_id": simulated_draft_id,
        "response_summary": "已离线模拟创建草稿；未访问或写入任何外部平台。",
        "error_type": None,
        "error_message": None,
    }
    entries.append(
        {
            "idempotency_key": key,
            "request_id": request["request_id"],
            "result_id": result_id,
            "connector_id": request["connector_id"],
            "account_ref": request["account_ref"],
            "content_hash": request["content_hash"],
            "asset_hashes": list(request["asset_hashes"]),
            "simulated_draft_id": simulated_draft_id,
            "first_executed_at": executed_at,
        }
    )
    entries.sort(key=lambda value: value["idempotency_key"])
    updated = {
        "schema_version": "1.0.0",
        "updated_at": executed_at,
        "entries": entries,
    }
    return result, updated
