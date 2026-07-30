from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from publishing.official_request import OfficialRequestError, build_official_request
from publishing.qualification import QualificationError, evaluate_qualifications
from visual.queue import load_json


ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_json(ROOT / "config/official-connectors.json")


class OfficialConnectorQualificationTests(unittest.TestCase):
    def validate_schema(self, name: str, payload: object) -> None:
        validator = Draft202012Validator(
            load_json(ROOT / "schemas" / name),
            format_checker=FormatChecker(),
        )
        self.assertEqual([], [error.message for error in validator.iter_errors(payload)])

    def simulated_facts(self) -> dict[str, object]:
        return {
            "connectors": {
                connector["connector_id"]: {"simulated": True}
                for connector in CONFIG["connectors"]
            }
        }

    def test_all_four_connectors_can_be_simulated_offline(self) -> None:
        report = evaluate_qualifications(
            config=CONFIG,
            facts=self.simulated_facts(),
            generated_at="2026-07-30T15:00:00+08:00",
            report_slug="ci",
        )
        self.validate_schema("connector-qualification.schema.json", report)
        self.assertEqual(
            {"total": 4, "unknown": 0, "eligible": 0, "blocked": 0, "simulated": 4},
            report["summary"],
        )
        self.assertTrue(all(not value["enabled"] for value in report["qualifications"]))
        self.assertTrue(all(not value["execution_allowed"] for value in report["qualifications"]))
        self.assertFalse(report["external_write_performed"])

    def test_missing_facts_remain_unknown(self) -> None:
        report = evaluate_qualifications(
            config=CONFIG,
            facts={"connectors": {}},
            generated_at="2026-07-30T15:00:00+08:00",
        )
        self.assertEqual(4, report["summary"]["unknown"])
        self.assertTrue(all(value["missing_requirements"] for value in report["qualifications"]))

    def test_confirmed_false_fact_blocks_connector(self) -> None:
        facts = self.simulated_facts()
        facts["connectors"]["wechat-official-draft"] = {
            "facts": {"ip_allowlist_verified": False}
        }
        report = evaluate_qualifications(
            config=CONFIG,
            facts=facts,
            generated_at="2026-07-30T15:00:00+08:00",
        )
        wechat = next(
            value for value in report["qualifications"]
            if value["connector_id"] == "wechat-official-draft"
        )
        self.assertEqual("blocked", wechat["status"])
        self.assertTrue(wechat["blocking_reasons"])

    def test_sensitive_values_are_rejected(self) -> None:
        facts = self.simulated_facts()
        facts["connectors"]["halo-official-draft"] = {
            "simulated": True,
            "account_ref": "Authorization: Bearer secret-value",
        }
        with self.assertRaisesRegex(QualificationError, "密钥值"):
            evaluate_qualifications(
                config=CONFIG,
                facts=facts,
                generated_at="2026-07-30T15:00:00+08:00",
            )

    def request_fixture(self, connector_id: str) -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
        report = evaluate_qualifications(
            config=CONFIG,
            facts=self.simulated_facts(),
            generated_at="2026-07-30T15:00:00+08:00",
        )
        connector = next(value for value in CONFIG["connectors"] if value["connector_id"] == connector_id)
        qualification = next(value for value in report["qualifications"] if value["connector_id"] == connector_id)
        platform = connector["platform"]
        asset_count = 6 if platform in {"website", "wechat", "douyin", "xiaohongshu"} else 1
        assets = [
            {"order": index, "sha256": f"{index:064x}"}
            for index in range(1, asset_count + 1)
        ]
        package = {
            "package_id": f"content-package-20260730-{platform}",
            "platform": platform,
            "content_hash": "a" * 64,
            "assets": assets,
        }
        entry = {
            "entry_id": f"publication-entry-20260730-{platform}",
            "platform": platform,
            "package_id": package["package_id"],
            "content_hash": package["content_hash"],
            "asset_hashes": [value["sha256"] for value in assets],
            "write_allowed": False,
        }
        return qualification, connector, package, entry

    def test_builds_four_schema_valid_non_executable_requests(self) -> None:
        for connector_id in (
            "halo-official-draft",
            "wechat-official-draft",
            "douyin-official-image-text",
            "xiaohongshu-official-share",
        ):
            with self.subTest(connector_id=connector_id):
                qualification, connector, package, entry = self.request_fixture(connector_id)
                mapping = {
                    "status": "simulated",
                    "cover_reference": "fixture-cover",
                    "asset_references": [f"fixture-{index}" for index in range(len(package["assets"]))],
                }
                request = build_official_request(
                    qualification=qualification,
                    connector_config=connector,
                    plan_entry=entry,
                    package=package,
                    generated_at="2026-07-30T15:10:00+08:00",
                    expires_at="2026-07-30T16:10:00+08:00",
                    material_mapping=mapping,
                )
                self.validate_schema("official-connector-request.schema.json", request)
                self.assertFalse(request["execution_enabled"])
                self.assertFalse(request["external_write_performed"])
                self.assertTrue(request["idempotency_key"].startswith("official-"))

    def test_hash_drift_and_incomplete_wechat_mapping_are_blocked(self) -> None:
        qualification, connector, package, entry = self.request_fixture("wechat-official-draft")
        with self.assertRaisesRegex(OfficialRequestError, "素材映射"):
            build_official_request(
                qualification=qualification,
                connector_config=connector,
                plan_entry=entry,
                package=package,
                generated_at="2026-07-30T15:10:00+08:00",
                expires_at="2026-07-30T16:10:00+08:00",
                material_mapping={
                    "status": "pending",
                    "cover_reference": None,
                    "asset_references": [],
                },
            )
        entry = json.loads(json.dumps(entry))
        entry["content_hash"] = "b" * 64
        with self.assertRaisesRegex(OfficialRequestError, "内容哈希漂移"):
            build_official_request(
                qualification=qualification,
                connector_config=connector,
                plan_entry=entry,
                package=package,
                generated_at="2026-07-30T15:10:00+08:00",
                expires_at="2026-07-30T16:10:00+08:00",
                material_mapping={
                    "status": "simulated",
                    "cover_reference": "fixture-cover",
                    "asset_references": ["fixture"],
                },
            )


if __name__ == "__main__":
    unittest.main()
