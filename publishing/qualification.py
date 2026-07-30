"""Evaluate official connector prerequisites without contacting any platform."""

from __future__ import annotations

import re
from typing import Any, Mapping
from urllib.parse import urlsplit


CONNECTOR_ORDER = (
    "halo-official-draft",
    "wechat-official-draft",
    "douyin-official-image-text",
    "xiaohongshu-official-share",
)
SECRET_PATTERN = re.compile(
    r"(?i)(bearer\s+|authorization\s*[:=]|access[_-]?token\s*[:=]|app[_-]?secret\s*[:=]|cookie\s*[:=]|session\s*[:=])"
)


class QualificationError(ValueError):
    """Raised when qualification inputs contain unsafe or inconsistent data."""


def _official_origin(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise QualificationError(f"官方Origin必须使用HTTPS：{value}")
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise QualificationError(f"官方Origin只能包含scheme与host：{value}")
    return f"https://{parsed.netloc.casefold()}"


def _assert_safe_value(value: Any, *, field: str) -> None:
    text = str(value)
    if SECRET_PATTERN.search(text):
        raise QualificationError(f"资格事实不得包含密钥值：{field}")


def _connector_map(config: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    if config.get("execution_enabled") is not False:
        raise QualificationError("官方连接器配置必须保持 execution_enabled=false")
    if config.get("external_write_performed") is not False:
        raise QualificationError("官方连接器配置必须保持 external_write_performed=false")
    rules = config.get("global_rules", {})
    for key in (
        "credentials_in_repository_forbidden",
        "credential_values_in_reports_forbidden",
        "authorization_headers_forbidden",
        "cookies_forbidden",
        "http_origins_forbidden",
        "non_official_fallback_forbidden",
        "execution_requires_separate_authorization",
        "public_publish_forbidden",
    ):
        if rules.get(key) is not True:
            raise QualificationError(f"官方连接器全局安全规则缺失：{key}")
    if rules.get("external_write_performed") is not False:
        raise QualificationError("全局规则必须声明 external_write_performed=false")

    result: dict[str, Mapping[str, Any]] = {}
    for connector in config.get("connectors", []):
        connector_id = str(connector.get("connector_id", ""))
        if connector_id in result:
            raise QualificationError(f"官方连接器重复：{connector_id}")
        if connector.get("enabled") is not False:
            raise QualificationError(f"Phase 5.4A禁止启用真实连接器：{connector_id}")
        origins = [_official_origin(str(value)) for value in connector.get("official_base_origins", [])]
        if not origins:
            raise QualificationError(f"官方连接器缺少Origin：{connector_id}")
        result[connector_id] = connector
    if tuple(result) != CONNECTOR_ORDER:
        raise QualificationError(f"官方连接器必须按固定顺序完整覆盖：{CONNECTOR_ORDER}")
    return result


def _check(
    *,
    check_id: str,
    kind: str,
    input_value: Any,
    simulated: bool,
) -> dict[str, Any]:
    evidence_ref = None
    if isinstance(input_value, Mapping):
        status_value = input_value.get("status")
        evidence_ref = input_value.get("evidence_ref")
        if evidence_ref is not None:
            _assert_safe_value(evidence_ref, field=check_id)
    else:
        status_value = input_value

    if simulated and status_value in {None, "simulated"}:
        status = "simulated"
        reason = "离线Fixture已覆盖该前置条件"
    elif status_value is True or status_value == "present":
        status = "present"
        reason = "已提供不含敏感值的资格事实"
    elif status_value is False or status_value == "confirmed_false":
        status = "confirmed_false"
        reason = "已确认不满足官方前置条件"
    else:
        status = "missing"
        reason = "尚未提供可核验事实"
    return {
        "check_id": check_id.replace("_", "-"),
        "kind": kind,
        "status": status,
        "evidence_ref": evidence_ref,
        "reason": reason,
    }


def evaluate_qualifications(
    *,
    config: Mapping[str, Any],
    facts: Mapping[str, Any],
    generated_at: str,
    report_slug: str = "audit",
) -> dict[str, Any]:
    """Return four deterministic qualification records without external calls."""
    connectors = _connector_map(config)
    fact_connectors = facts.get("connectors", {})
    qualifications: list[dict[str, Any]] = []

    for connector_id in CONNECTOR_ORDER:
        connector = connectors[connector_id]
        provided = fact_connectors.get(connector_id, {})
        if not isinstance(provided, Mapping):
            raise QualificationError(f"连接器资格事实格式错误：{connector_id}")
        simulated = bool(provided.get("simulated", False))
        account_ref = provided.get("account_ref")
        application_ref = provided.get("application_ref")
        for field, value in (("account_ref", account_ref), ("application_ref", application_ref)):
            if value is not None:
                _assert_safe_value(value, field=f"{connector_id}.{field}")

        checks: list[dict[str, Any]] = []
        for requirement in connector.get("required_facts", []):
            checks.append(
                _check(
                    check_id=str(requirement),
                    kind="fact",
                    input_value=provided.get("facts", {}).get(requirement),
                    simulated=simulated,
                )
            )
        for requirement in connector.get("required_capabilities", []):
            checks.append(
                _check(
                    check_id=str(requirement),
                    kind="capability",
                    input_value=provided.get("capabilities", {}).get(requirement),
                    simulated=simulated,
                )
            )
        for requirement in connector.get("asset_requirements", []):
            checks.append(
                _check(
                    check_id=str(requirement),
                    kind="asset",
                    input_value=provided.get("assets", {}).get(requirement),
                    simulated=simulated,
                )
            )
        for variable in connector.get("credential_environment_variables", []):
            checks.append(
                _check(
                    check_id=f"env_{str(variable).casefold()}",
                    kind="credential_reference",
                    input_value=provided.get("credential_references", {}).get(variable),
                    simulated=simulated,
                )
            )
        for origin in connector.get("official_base_origins", []):
            checks.append(
                {
                    "check_id": "origin-" + str(connector["platform"]),
                    "kind": "origin",
                    "status": "simulated" if simulated else "present",
                    "evidence_ref": _official_origin(str(origin)),
                    "reason": "配置中的HTTPS官方Origin已通过结构校验",
                }
            )

        confirmed_false = [value for value in checks if value["status"] == "confirmed_false"]
        missing = [value for value in checks if value["status"] == "missing"]
        if confirmed_false:
            status = "blocked"
        elif simulated and all(value["status"] in {"simulated", "present"} for value in checks):
            status = "simulated"
        elif not missing and all(value["status"] == "present" for value in checks):
            status = "eligible"
        else:
            status = "unknown"

        qualifications.append(
            {
                "connector_id": connector_id,
                "platform": connector["platform"],
                "integration_type": connector["integration_type"],
                "status": status,
                "enabled": False,
                "action": connector["action"],
                "account_ref": account_ref,
                "application_ref": application_ref,
                "official_origins": [
                    _official_origin(str(value))
                    for value in connector["official_base_origins"]
                ],
                "credential_environment_variables": list(
                    connector.get("credential_environment_variables", [])
                ),
                "checks": checks,
                "missing_requirements": [value["check_id"] for value in missing],
                "blocking_reasons": [value["reason"] for value in confirmed_false],
                "execution_allowed": False,
            }
        )

    counts = {value: 0 for value in ("unknown", "eligible", "blocked", "simulated")}
    for qualification in qualifications:
        counts[qualification["status"]] += 1
    date_token = generated_at[:10].replace("-", "")
    slug = re.sub(r"[^a-z0-9-]+", "-", report_slug.casefold()).strip("-") or "audit"
    if len(slug) < 3:
        slug += "-audit"
    return {
        "schema_version": "1.0.0",
        "report_id": f"connector-qualification-{date_token}-{slug[:40]}",
        "generated_at": generated_at,
        "execution_enabled": False,
        "external_write_performed": False,
        "qualifications": qualifications,
        "summary": {"total": 4, **counts},
    }
