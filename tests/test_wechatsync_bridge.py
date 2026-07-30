from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from publishing.bridges import (
    BrowserBridgeError,
    build_bridge_request,
    classify_upstream_error,
    load_bridge_registry,
    normalize_bridge_result,
    normalize_health_snapshot,
    sanitize_url,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/bridge"


class WechatsyncBridgeTests(unittest.TestCase):
    def load_json(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def validate_schema(self, name: str, value: object) -> None:
        schema = self.load_json(ROOT / "schemas" / name)
        errors = list(
            Draft202012Validator(
                schema, format_checker=FormatChecker()
            ).iter_errors(value)
        )
        self.assertEqual([], [error.message for error in errors])

    def article(self) -> dict:
        value = self.load_json(FIXTURES / "article.json")
        actual = hashlib.sha256(
            (FIXTURES / "article.md").read_bytes()
        ).hexdigest()
        self.assertEqual(value["content_hash"], actual)
        return value

    def request(self, *, transport: str = "fixture") -> dict:
        return build_bridge_request(
            operation="create_draft",
            platforms=["zhihu", "juejin", "csdn"],
            created_at="2026-07-30T09:00:00+08:00",
            article=self.article(),
            account_ref="hxp-browser-fixture",
            transport=transport,
        )

    def test_registry_is_disabled_loopback_only_and_schema_valid(self) -> None:
        registry = load_bridge_registry(ROOT / "config/local-browser-bridges.json")
        self.validate_schema("browser-bridge-capability.schema.json", registry)
        self.assertFalse(registry["real_bridge_calls_enabled"])
        self.assertTrue(registry["loopback_only"])
        self.assertFalse(registry["remote_bridge_allowed"])
        for bridge in registry["bridges"]:
            self.assertFalse(bridge["enabled"])
            self.assertFalse(bridge["execution_enabled"])
            self.assertIn(bridge["host"], {"127.0.0.1", "localhost", "::1"})
            self.assertFalse(bridge["cli_exit_code_authoritative"])

    def test_request_is_stable_and_platform_order_independent(self) -> None:
        first = self.request()
        second = build_bridge_request(
            operation="create_draft",
            platforms=["csdn", "zhihu", "juejin", "zhihu"],
            created_at="2026-07-30T09:05:00+08:00",
            article=self.article(),
            account_ref="hxp-browser-fixture",
            transport="fixture",
        )
        self.validate_schema("browser-bridge-request.schema.json", first)
        self.assertEqual(first["request_fingerprint"], second["request_fingerprint"])
        self.assertEqual(first["bridge_request_id"], second["bridge_request_id"])
        self.assertFalse(first["execution_allowed"])
        self.assertFalse(first["external_write_expected"])
        self.assertFalse(first["safety"]["public_publish_allowed"])

    def test_cli_preview_always_includes_dry_run(self) -> None:
        request = build_bridge_request(
            operation="preview_draft",
            platforms=["zhihu"],
            created_at="2026-07-30T09:00:00+08:00",
            article=self.article(),
            transport="cli_dry_run",
        )
        self.validate_schema("browser-bridge-request.schema.json", request)
        command = request["upstream_call"]["command_preview"]
        self.assertIn("--dry-run", command)
        self.assertEqual("wechatsync", command[0])
        self.assertFalse(request["safety"]["cli_exit_code_authoritative"])

    def test_health_fixture_maps_only_allowed_platforms(self) -> None:
        raw = self.load_json(FIXTURES / "wechatsync-platforms.json")
        health = normalize_health_snapshot(
            raw_platforms=raw["platforms"],
            checked_at="2026-07-30T09:01:00+08:00",
            extension_connected=True,
            credential_present=True,
        )
        self.validate_schema("browser-bridge-health.schema.json", health)
        self.assertEqual("ready", health["status"])
        self.assertFalse(health["remote_endpoint_detected"])
        values = {value["platform"]: value for value in health["platforms"]}
        self.assertEqual({"zhihu", "juejin", "csdn"}, set(values))
        self.assertEqual("authenticated", values["zhihu"]["auth_status"])
        self.assertEqual("unauthenticated", values["csdn"]["auth_status"])

    def test_structured_result_is_partial_and_urls_are_sanitized(self) -> None:
        request = self.request()
        raw = self.load_json(FIXTURES / "wechatsync-sync-result.json")
        result = normalize_bridge_result(
            request=request,
            raw_result=raw,
            completed_at="2026-07-30T09:02:00+08:00",
        )
        self.validate_schema("browser-bridge-result.schema.json", result)
        self.assertEqual("partial_success", result["status"])
        self.assertFalse(result["external_write_performed"])
        self.assertTrue(result["structured_result_used"])
        self.assertFalse(result["cli_exit_code_used_as_authority"])
        values = {value["platform"]: value for value in result["platform_results"]}
        self.assertEqual("draft_created", values["zhihu"]["outcome"])
        self.assertNotIn("token", values["zhihu"]["sanitized_url"])
        self.assertNotIn("session", values["juejin"]["sanitized_url"])
        self.assertEqual("failed", values["csdn"]["outcome"])
        self.assertEqual("BRIDGE_AUTH_REQUIRED", values["csdn"]["error_code"])

    def test_non_draft_success_is_hard_blocked(self) -> None:
        request = build_bridge_request(
            operation="create_draft",
            platforms=["zhihu"],
            created_at="2026-07-30T09:00:00+08:00",
            article=self.article(),
        )
        result = normalize_bridge_result(
            request=request,
            raw_result={
                "results": [
                    {
                        "platform": "zhihu",
                        "success": True,
                        "draftOnly": False,
                        "postId": "published-1",
                        "postUrl": "https://zhuanlan.zhihu.com/p/1",
                    }
                ]
            },
            completed_at="2026-07-30T09:02:00+08:00",
        )
        self.assertEqual("blocked", result["status"])
        self.assertEqual("blocked", result["platform_results"][0]["outcome"])
        self.assertEqual(
            "BRIDGE_PUBLIC_WRITE_BLOCKED",
            result["platform_results"][0]["error_code"],
        )

    def test_risk_control_and_identity_errors_fail_closed(self) -> None:
        risk = classify_upstream_error("需要验证码，触发风控 token=secret")
        identity = classify_upstream_error("账号不匹配 Authorization: Bearer abc")
        self.assertEqual("risk_control", risk["classification"])
        self.assertFalse(risk["recoverable"])
        self.assertNotIn("secret", risk["message"])
        self.assertEqual("identity", identity["classification"])
        self.assertFalse(identity["recoverable"])
        self.assertNotIn("Bearer abc", identity["message"])

    def test_sensitive_or_credentialed_urls_are_removed(self) -> None:
        self.assertEqual(
            "https://example.com/edit?id=42&from=hxp",
            sanitize_url(
                "https://example.com/edit?id=42&token=secret&session_id=x&from=hxp#draft"
            ),
        )
        self.assertIsNone(sanitize_url("https://user:password@example.com/edit"))
        self.assertIsNone(sanitize_url("javascript:alert(1)"))

    def test_invalid_platform_and_missing_article_are_rejected(self) -> None:
        with self.assertRaises(BrowserBridgeError):
            build_bridge_request(
                operation="create_draft",
                platforms=["xiaohongshu"],
                created_at="2026-07-30T09:00:00+08:00",
                article=self.article(),
            )
        with self.assertRaises(BrowserBridgeError):
            build_bridge_request(
                operation="create_draft",
                platforms=["zhihu"],
                created_at="2026-07-30T09:00:00+08:00",
                article=None,
            )


if __name__ == "__main__":
    unittest.main()
