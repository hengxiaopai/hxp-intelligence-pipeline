"""Load and enforce the disabled-by-default connector capability registry."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .base import ConnectorError


class ConnectorRegistryError(ConnectorError):
    """Raised when connector configuration violates hard safety rules."""


def validate_connector_registry(registry: Mapping[str, Any]) -> None:
    if registry.get("real_writes_enabled") is not False:
        raise ConnectorRegistryError("当前阶段必须保持real_writes_enabled=false")
    connectors = list(registry.get("connectors", []))
    if not connectors:
        raise ConnectorRegistryError("连接器注册表不能为空")
    seen: set[str] = set()
    enabled: list[Mapping[str, Any]] = []
    for connector in connectors:
        connector_id = str(connector.get("connector_id", ""))
        if not connector_id or connector_id in seen:
            raise ConnectorRegistryError(f"连接器ID无效或重复：{connector_id}")
        seen.add(connector_id)
        if connector.get("requires_explicit_authorization") is not True:
            raise ConnectorRegistryError(f"连接器必须要求显式授权：{connector_id}")
        if connector.get("supports_idempotency") is not True:
            raise ConnectorRegistryError(f"连接器必须支持幂等：{connector_id}")
        if connector.get("supports_public_publish") is not False:
            raise ConnectorRegistryError(f"当前阶段禁止公开发布：{connector_id}")
        if connector.get("mode") == "real" and connector.get("enabled"):
            raise ConnectorRegistryError(f"真实连接器必须保持关闭：{connector_id}")
        for name in connector.get("credential_environment_variables", []):
            if str(name).upper() != str(name) or not str(name).replace("_", "").isalnum():
                raise ConnectorRegistryError(f"凭据环境变量名无效：{connector_id}：{name}")
        if connector.get("enabled"):
            enabled.append(connector)
    if len(enabled) != 1 or enabled[0].get("mode") != "simulator":
        raise ConnectorRegistryError("当前阶段只能启用一个Simulator连接器")


def load_connector_registry(path: Path) -> dict[str, Any]:
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConnectorRegistryError(f"无法读取连接器注册表：{path}：{exc}") from exc
    validate_connector_registry(registry)
    return registry


def select_connector(
    registry: Mapping[str, Any],
    *,
    connector_id: str | None = None,
    platform: str | None = None,
    require_enabled: bool = True,
) -> dict[str, Any]:
    candidates = []
    for raw in registry.get("connectors", []):
        connector = dict(raw)
        if connector_id is not None and connector.get("connector_id") != connector_id:
            continue
        if platform is not None and connector.get("platform") != platform:
            continue
        if require_enabled and not connector.get("enabled"):
            continue
        candidates.append(connector)
    if len(candidates) != 1:
        raise ConnectorRegistryError(
            f"无法唯一确定连接器：connector_id={connector_id} platform={platform} enabled={require_enabled}"
        )
    return candidates[0]
