"""Load and enforce the disabled-by-default local browser bridge registry."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .base import BrowserBridgeError


LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def load_bridge_registry(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BrowserBridgeError(f"无法读取本地桥接注册表：{path}：{exc}") from exc
    validate_bridge_registry(value)
    return value


def validate_bridge_registry(registry: Mapping[str, Any]) -> None:
    if registry.get("real_bridge_calls_enabled") is not False:
        raise BrowserBridgeError("Phase 5.3A 必须保持 real_bridge_calls_enabled=false")
    if registry.get("loopback_only") is not True:
        raise BrowserBridgeError("本地桥接必须固定 loopback_only=true")
    if registry.get("remote_bridge_allowed") is not False:
        raise BrowserBridgeError("HXP 禁止远程明文浏览器桥接")

    bridges = registry.get("bridges")
    if not isinstance(bridges, list) or not bridges:
        raise BrowserBridgeError("本地桥接注册表没有有效连接器")

    seen: set[str] = set()
    for bridge in bridges:
        bridge_id = str(bridge.get("bridge_id", ""))
        if not bridge_id or bridge_id in seen:
            raise BrowserBridgeError(f"本地桥接ID无效或重复：{bridge_id}")
        seen.add(bridge_id)
        if bridge.get("enabled") is not False or bridge.get("execution_enabled") is not False:
            raise BrowserBridgeError(f"Phase 5.3A 连接器必须关闭：{bridge_id}")
        if bridge.get("host") not in LOOPBACK_HOSTS:
            raise BrowserBridgeError(f"连接器不是回环地址：{bridge_id}")
        if bridge.get("credential_values_persisted") is not False:
            raise BrowserBridgeError(f"连接器禁止持久化凭据值：{bridge_id}")
        if bridge.get("cli_exit_code_authoritative") is not False:
            raise BrowserBridgeError(f"不得把CLI退出码作为成功依据：{bridge_id}")
        if bridge.get("public_publish_supported") is not False:
            raise BrowserBridgeError(f"当前连接器不得支持公开发布：{bridge_id}")
        if set(bridge.get("allowed_actions", [])) != {"draft_only"}:
            raise BrowserBridgeError(f"当前连接器只允许 draft_only：{bridge_id}")


def get_bridge(registry: Mapping[str, Any], bridge_id: str) -> Mapping[str, Any]:
    for bridge in registry.get("bridges", []):
        if bridge.get("bridge_id") == bridge_id:
            return bridge
    raise BrowserBridgeError(f"未知本地桥接：{bridge_id}")
