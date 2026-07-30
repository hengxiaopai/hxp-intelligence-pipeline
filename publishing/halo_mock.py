"""Deterministic in-process Halo draft mock with no network listener."""

from __future__ import annotations

from typing import Any, Mapping

from .halo_draft import HaloDraftError, canonical_hash


def empty_halo_mock_ledger() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "connector_id": "halo-official-draft",
        "mode": "mock",
        "network_listener_enabled": False,
        "external_write_performed": False,
        "entries": {},
    }


def simulate_halo_draft(
    *,
    payload: Mapping[str, Any],
    ledger: Mapping[str, Any] | None,
    executed_at: str,
    policy: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Simulate create, content update and lookup with idempotent replay."""
    if policy.get("execution_mode") != "mock_only":
        raise HaloDraftError("Halo Mock策略必须为mock_only")
    mock_policy = policy.get("mock", {})
    if mock_policy.get("network_listener_enabled") is not False:
        raise HaloDraftError("Halo Mock不得启动网络监听")
    if payload.get("connector_id") != "halo-official-draft":
        raise HaloDraftError("Payload不是Halo草稿连接器")
    if payload.get("execution_enabled") is not False or payload.get("external_write_performed") is not False:
        raise HaloDraftError("Halo Payload必须保持不可执行且无外部写入")
    if payload.get("post", {}).get("spec", {}).get("publish") is not False:
        raise HaloDraftError("Halo Mock禁止publish=true")
    payload_hash = canonical_hash(
        {
            "post": payload.get("post"),
            "content": payload.get("content"),
            "content_hash": payload.get("content_hash"),
            "asset_hashes": payload.get("asset_hashes"),
            "paths": payload.get("paths"),
        }
    )
    if payload_hash != payload.get("payload_hash"):
        raise HaloDraftError("Halo Payload哈希不一致")

    state = dict(ledger or empty_halo_mock_ledger())
    if state.get("connector_id") != "halo-official-draft" or state.get("mode") != "mock":
        raise HaloDraftError("Halo Mock Ledger格式错误")
    entries = dict(state.get("entries", {}))
    idempotency_key = str(payload["idempotency_key"])
    existing = entries.get(idempotency_key)
    replayed = False
    if existing is not None:
        if existing.get("payload_hash") != payload_hash:
            raise HaloDraftError("Halo Mock幂等键发生内容碰撞")
        draft_name = str(existing["draft_name"])
        replayed = True
        operation_status = "replayed"
        result_status = "replayed"
    else:
        draft_name = "mock-post-" + payload_hash[:16]
        entries[idempotency_key] = {
            "payload_hash": payload_hash,
            "draft_name": draft_name,
            "draft_state": str(mock_policy.get("draft_status", "DRAFT")),
            "created_at": executed_at,
            "request_id": payload["request_id"],
            "content_hash": payload["content_hash"],
            "asset_hashes": list(payload["asset_hashes"]),
        }
        operation_status = "simulated"
        result_status = "simulated"

    paths = payload["paths"]
    operations = [
        {
            "sequence": 1,
            "operation": "create_draft_post",
            "status": operation_status,
            "request_path": paths["create"],
            "response_ref": draft_name,
        },
        {
            "sequence": 2,
            "operation": "update_draft_content",
            "status": operation_status,
            "request_path": paths["content"],
            "response_ref": draft_name + ":content",
        },
        {
            "sequence": 3,
            "operation": "status_lookup",
            "status": operation_status,
            "request_path": paths["status"],
            "response_ref": draft_name + ":DRAFT",
        },
    ]
    compact = str(payload["request_id"]).split("-")[2]
    execution = {
        "schema_version": "1.0.0",
        "execution_id": f"halo-mock-execution-{compact}-{payload_hash[:12]}",
        "request_id": payload["request_id"],
        "connector_id": "halo-official-draft",
        "mode": "mock",
        "executed_at": executed_at,
        "idempotency_key": idempotency_key,
        "payload_hash": payload_hash,
        "content_hash": payload["content_hash"],
        "asset_hashes": list(payload["asset_hashes"]),
        "operations": operations,
        "result": {
            "status": result_status,
            "draft_name": draft_name,
            "draft_state": "DRAFT",
            "replayed": replayed,
            "error_type": None,
            "error_message": None,
        },
        "external_write_performed": False,
    }
    state.update(
        {
            "network_listener_enabled": False,
            "external_write_performed": False,
            "entries": entries,
        }
    )
    return execution, state
