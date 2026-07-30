from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from publishing.halo_draft import (
    HaloDraftError,
    build_halo_draft_payload,
    canonical_hash,
    issue_halo_live_authorization,
)
from publishing.halo_mock import empty_halo_mock_ledger, simulate_halo_draft
from visual.queue import load_json


ROOT = Path(__file__).resolve().parents[1]
POLICY = load_json(ROOT / "config/halo-draft-policy.json")


class HaloDraftAdapterTests(unittest.TestCase):
    def request(self) -> dict[str, object]:
        return {
            "schema_version": "1.0.0",
            "request_id": "official-request-20260730-halo-official-draft",
            "connector_id": "halo-official-draft",
            "platform": "website",
            "action": "draft_only",
            "qualification_status": "simulated",
            "publication_entry_id": "publication-entry-20260730-website",
            "package_id": "content-package-20260730-website",
            "account_ref": "hxp-halo-account",
            "application_ref": None,
            "content_hash": "a" * 64,
            "asset_hashes": ["1" * 64, "2" * 64],
            "material_mapping": {
                "status": "simulated",
                "cover_reference": "fixture-cover",
                "asset_references": ["fixture-01", "fixture-02"],
            },
            "credential_environment_variables": ["HXP_HALO_BASE_URL", "HXP_HALO_PAT"],
            "official_origin": "https://api.halo.run",
            "generated_at": "2026-07-30T15:10:00+08:00",
            "expires_at": "2026-07-30T16:10:00+08:00",
            "idempotency_key": "official-" + "b" * 48,
            "request_plan": [
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
            ],
            "execution_enabled": False,
            "external_write_performed": False,
        }

    def package(self) -> dict[str, object]:
        return {
            "package_id": "content-package-20260730-website",
            "platform": "website",
            "content_hash": "a" * 64,
            "content": {
                "title": "珩小派多元情报测试草稿",
                "summary": "只验证草稿载荷与本地Mock，不调用真实Halo站点。",
                "body_markdown": "# 测试草稿\n\n正文只用于离线Fixture。\n",
                "slug": "hxp-offline-halo-draft",
            },
            "assets": [
                {"order": 1, "path": "fixture/cover.png", "sha256": "1" * 64},
                {"order": 2, "path": "fixture/detail.png", "sha256": "2" * 64},
            ],
        }

    def validate_schema(self, name: str, payload: object) -> None:
        validator = Draft202012Validator(
            load_json(ROOT / "schemas" / name),
            format_checker=FormatChecker(),
        )
        self.assertEqual([], [error.message for error in validator.iter_errors(payload)])

    def test_builds_non_executable_draft_payload(self) -> None:
        payload = build_halo_draft_payload(
            official_request=self.request(),
            package=self.package(),
            policy=POLICY,
        )
        self.assertFalse(payload["execution_enabled"])
        self.assertFalse(payload["external_write_performed"])
        self.assertFalse(payload["post"]["spec"]["publish"])
        self.assertNotIn("Authorization", json.dumps(payload, ensure_ascii=False))
        self.assertEqual("markdown", payload["content"]["rawType"])
        self.assertNotIn("/publish", " ".join(payload["paths"].values()).casefold())

    def test_mock_create_then_idempotent_replay(self) -> None:
        payload = build_halo_draft_payload(
            official_request=self.request(),
            package=self.package(),
            policy=POLICY,
        )
        first, ledger = simulate_halo_draft(
            payload=payload,
            ledger=empty_halo_mock_ledger(),
            executed_at="2026-07-30T15:20:00+08:00",
            policy=POLICY,
        )
        replay, ledger2 = simulate_halo_draft(
            payload=payload,
            ledger=ledger,
            executed_at="2026-07-30T15:21:00+08:00",
            policy=POLICY,
        )
        self.validate_schema("halo-draft-execution.schema.json", first)
        self.validate_schema("halo-draft-execution.schema.json", replay)
        self.assertEqual("simulated", first["result"]["status"])
        self.assertEqual("replayed", replay["result"]["status"])
        self.assertEqual(first["result"]["draft_name"], replay["result"]["draft_name"])
        self.assertEqual(1, len(ledger2["entries"]))
        self.assertFalse(first["external_write_performed"])
        self.assertFalse(ledger2["network_listener_enabled"])

    def test_idempotency_collision_is_blocked(self) -> None:
        payload = build_halo_draft_payload(
            official_request=self.request(),
            package=self.package(),
            policy=POLICY,
        )
        _, ledger = simulate_halo_draft(
            payload=payload,
            ledger=None,
            executed_at="2026-07-30T15:20:00+08:00",
            policy=POLICY,
        )
        changed = json.loads(json.dumps(payload))
        changed["content"]["raw"] += "\nchanged"
        changed["content"]["content"] = changed["content"]["raw"]
        changed["payload_hash"] = canonical_hash(
            {
                "request_id": changed["request_id"],
                "package_id": changed["package_id"],
                "content_hash": changed["content_hash"],
                "asset_hashes": changed["asset_hashes"],
                "title": changed["post"]["spec"]["title"],
                "slug": changed["post"]["spec"]["slug"],
                "raw": changed["content"]["raw"],
            }
        )
        with self.assertRaisesRegex(HaloDraftError, "幂等键发生内容碰撞"):
            simulate_halo_draft(
                payload=changed,
                ledger=ledger,
                executed_at="2026-07-30T15:22:00+08:00",
                policy=POLICY,
            )

    def test_publish_and_hash_drift_are_blocked(self) -> None:
        request = self.request()
        request["content_hash"] = "c" * 64
        with self.assertRaisesRegex(HaloDraftError, "内容哈希漂移"):
            build_halo_draft_payload(
                official_request=request,
                package=self.package(),
                policy=POLICY,
            )
        payload = build_halo_draft_payload(
            official_request=self.request(),
            package=self.package(),
            policy=POLICY,
        )
        payload["post"]["spec"]["publish"] = True
        with self.assertRaisesRegex(HaloDraftError, "publish=true"):
            simulate_halo_draft(
                payload=payload,
                ledger=None,
                executed_at="2026-07-30T15:20:00+08:00",
                policy=POLICY,
            )

    def test_issues_schema_valid_one_hour_draft_only_authorization(self) -> None:
        authorization = issue_halo_live_authorization(
            official_request=self.request(),
            site_origin="https://blog.example.com",
            site_fingerprint="site-" + "d" * 48,
            halo_version="2.21.0",
            account_ref="hxp-halo-owner",
            issued_at="2026-07-30T15:30:00+08:00",
            expires_at="2026-07-30T16:30:00+08:00",
            issued_by="hengxiaopai",
            user_confirmed_draft_only=True,
            policy=POLICY,
        )
        self.validate_schema("halo-live-authorization.schema.json", authorization)
        self.assertEqual("issued", authorization["status"])
        self.assertFalse(authorization["publish_allowed"])
        self.assertEqual("HXP_HALO_PAT", authorization["credential_environment_variable"])
        self.assertNotIn("Bearer", json.dumps(authorization))

    def test_long_or_unconfirmed_authorization_is_blocked(self) -> None:
        kwargs = {
            "official_request": self.request(),
            "site_origin": "https://blog.example.com",
            "site_fingerprint": "site-" + "d" * 48,
            "halo_version": "2.21.0",
            "account_ref": "hxp-halo-owner",
            "issued_at": "2026-07-30T15:30:00+08:00",
            "expires_at": "2026-07-30T17:00:00+08:00",
            "issued_by": "hengxiaopai",
            "user_confirmed_draft_only": True,
            "policy": POLICY,
        }
        with self.assertRaisesRegex(HaloDraftError, "超过策略上限"):
            issue_halo_live_authorization(**kwargs)
        kwargs["expires_at"] = "2026-07-30T16:00:00+08:00"
        kwargs["user_confirmed_draft_only"] = False
        with self.assertRaisesRegex(HaloDraftError, "明确确认"):
            issue_halo_live_authorization(**kwargs)


if __name__ == "__main__":
    unittest.main()
