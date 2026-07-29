from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from publishing.connector_gate import (
    ConnectorGateError,
    build_connector_request,
    expire_connector_authorization,
    issue_connector_authorization,
    revoke_connector_authorization,
)
from publishing.connectors.registry import (
    ConnectorRegistryError,
    load_connector_registry,
    select_connector,
)
from publishing.connectors.simulator import (
    ConnectorSimulationError,
    empty_ledger,
    execute_simulated_draft,
)

ROOT = Path(__file__).resolve().parents[1]


class ConnectorGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = load_connector_registry(ROOT / "config/connectors.json")
        self.connector = select_connector(self.registry, connector_id="simulator-draft")
        self.entry = {
            "entry_id": "publication-entry-20260729-website",
            "platform": "website",
            "package_id": "content-package-20260729-website",
            "account_ref": None,
            "action": "draft_only",
            "approval_status": "approved",
            "idempotency_key": "pub-" + "1" * 48,
            "content_hash": "2" * 64,
            "asset_hashes": ["3" * 64, "4" * 64],
            "scheduled_at": None,
            "risk_flags": ["none"],
            "write_allowed": False,
        }

    def validate_schema(self, name: str, payload: object) -> None:
        schema = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        errors = [error.message for error in validator.iter_errors(payload)]
        self.assertEqual([], errors)

    def issue(self) -> dict:
        return issue_connector_authorization(
            connector=self.connector,
            entry=self.entry,
            account_ref="hxp-website-staging",
            issued_at="2026-07-29T16:00:00+08:00",
            expires_at="2026-07-29T17:00:00+08:00",
            issued_by="hengxiaopai",
        )

    def test_registry_only_enables_simulator(self) -> None:
        enabled = [value for value in self.registry["connectors"] if value["enabled"]]
        self.assertEqual(["simulator-draft"], [value["connector_id"] for value in enabled])
        self.assertFalse(self.registry["real_writes_enabled"])
        with self.assertRaises(ConnectorRegistryError):
            select_connector(self.registry, connector_id="website-draft")

    def test_authorization_is_stable_hash_bound_and_schema_valid(self) -> None:
        first = self.issue()
        second = self.issue()
        self.assertEqual(first, second)
        self.assertFalse(first["real_write_allowed"])
        self.assertEqual(self.entry["asset_hashes"], first["asset_hashes"])
        self.validate_schema("connector-authorization.schema.json", first)

    def test_expired_or_drifted_authorization_is_blocked(self) -> None:
        authorization = self.issue()
        with self.assertRaisesRegex(ConnectorGateError, "过期"):
            build_connector_request(
                authorization=authorization,
                connector=self.connector,
                entry=self.entry,
                package_id=self.entry["package_id"],
                account_ref="hxp-website-staging",
                requested_at="2026-07-29T17:00:00+08:00",
            )
        changed = dict(self.entry)
        changed["content_hash"] = "9" * 64
        with self.assertRaisesRegex(ConnectorGateError, "漂移"):
            build_connector_request(
                authorization=authorization,
                connector=self.connector,
                entry=changed,
                package_id=self.entry["package_id"],
                account_ref="hxp-website-staging",
                requested_at="2026-07-29T16:30:00+08:00",
            )

    def test_request_consumes_authorization_and_remains_no_write(self) -> None:
        authorization = self.issue()
        request, consumed = build_connector_request(
            authorization=authorization,
            connector=self.connector,
            entry=self.entry,
            package_id=self.entry["package_id"],
            account_ref="hxp-website-staging",
            requested_at="2026-07-29T16:30:00+08:00",
        )
        self.assertEqual("consumed", consumed["status"])
        self.assertFalse(request["real_write_allowed"])
        self.validate_schema("connector-request.schema.json", request)
        with self.assertRaisesRegex(ConnectorGateError, "状态不可消费"):
            build_connector_request(
                authorization=consumed,
                connector=self.connector,
                entry=self.entry,
                package_id=self.entry["package_id"],
                account_ref="hxp-website-staging",
                requested_at="2026-07-29T16:31:00+08:00",
            )

    def test_simulator_is_idempotent_and_never_writes_externally(self) -> None:
        request, _ = build_connector_request(
            authorization=self.issue(),
            connector=self.connector,
            entry=self.entry,
            package_id=self.entry["package_id"],
            account_ref="hxp-website-staging",
            requested_at="2026-07-29T16:30:00+08:00",
        )
        first, ledger = execute_simulated_draft(
            request=request,
            ledger=empty_ledger(updated_at="2026-07-29T16:31:00+08:00"),
            executed_at="2026-07-29T16:31:00+08:00",
        )
        replay, unchanged = execute_simulated_draft(
            request=request,
            ledger=ledger,
            executed_at="2026-07-29T16:32:00+08:00",
        )
        self.assertEqual("simulated", first["status"])
        self.assertEqual("idempotent_replay", replay["status"])
        self.assertEqual(first["result_id"], replay["result_id"])
        self.assertEqual(first["simulated_draft_id"], replay["simulated_draft_id"])
        self.assertEqual(1, len(ledger["entries"]))
        self.assertEqual(ledger, unchanged)
        self.assertFalse(first["external_write_performed"])
        self.validate_schema("connector-result.schema.json", first)
        self.validate_schema("connector-result.schema.json", replay)
        self.validate_schema("connector-ledger.schema.json", ledger)

    def test_idempotency_collision_is_blocked(self) -> None:
        request, _ = build_connector_request(
            authorization=self.issue(),
            connector=self.connector,
            entry=self.entry,
            package_id=self.entry["package_id"],
            account_ref="hxp-website-staging",
            requested_at="2026-07-29T16:30:00+08:00",
        )
        _, ledger = execute_simulated_draft(
            request=request,
            ledger=None,
            executed_at="2026-07-29T16:31:00+08:00",
        )
        collided = dict(request)
        collided["content_hash"] = "8" * 64
        with self.assertRaisesRegex(ConnectorSimulationError, "碰撞"):
            execute_simulated_draft(
                request=collided,
                ledger=ledger,
                executed_at="2026-07-29T16:32:00+08:00",
            )

    def test_revoke_expire_and_credential_boundaries(self) -> None:
        authorization = self.issue()
        self.assertEqual("revoked", revoke_connector_authorization(authorization)["status"])
        self.assertEqual(
            "expired",
            expire_connector_authorization(
                authorization, now="2026-07-29T17:00:00+08:00"
            )["status"],
        )
        with self.assertRaisesRegex(ConnectorGateError, "不得携带凭据"):
            issue_connector_authorization(
                connector=self.connector,
                entry=self.entry,
                account_ref="hxp-website-staging",
                issued_at="2026-07-29T16:00:00+08:00",
                expires_at="2026-07-29T17:00:00+08:00",
                issued_by="hengxiaopai",
                credential_reference="env:HXP_FAKE_TOKEN",
            )


if __name__ == "__main__":
    unittest.main()
