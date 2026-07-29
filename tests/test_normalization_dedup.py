from __future__ import annotations

import json
import sys
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.dedup import apply_decision, evaluate_candidate  # noqa: E402
from pipeline.normalization import (  # noqa: E402
    canonicalize_entities,
    event_fingerprint,
    load_alias_map,
    normalize_text,
)

CANDIDATE = ROOT / "data/examples/candidate.example.json"
INDEX = ROOT / "data/examples/dedup-index.example.json"
ALIASES = ROOT / "config/entity-aliases.json"
DECISION_SCHEMA = ROOT / "schemas/dedup-decision.schema.json"
INDEX_SCHEMA = ROOT / "schemas/dedup-index.schema.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(value: dict, schema_path: Path) -> list[str]:
    validator = Draft202012Validator(
        load(schema_path),
        format_checker=FormatChecker(),
    )
    return [error.message for error in validator.iter_errors(value)]


class NormalizationDedupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.candidate = load(CANDIDATE)
        self.index = load(INDEX)
        self.aliases = load_alias_map(ALIASES)

    def test_text_normalization_removes_width_case_and_punctuation_variance(self) -> None:
        self.assertEqual(
            normalize_text("ＧｉｔＨｕｂ：Dependabot！"),
            normalize_text("github dependabot"),
        )

    def test_entity_aliases_and_order_are_stable(self) -> None:
        left = canonicalize_entities(
            ["OPENSSF malicious packages", "git hub", "dependa bot"],
            self.aliases,
        )
        right = canonicalize_entities(
            ["Dependabot", "GitHub", "OpenSSF malicious-packages"],
            self.aliases,
        )
        self.assertEqual(left, right)
        self.assertEqual(
            ["Dependabot", "GitHub", "OpenSSF malicious-packages"],
            left,
        )

    def test_event_fingerprint_is_stable_across_aliases_and_entity_order(self) -> None:
        left_entities = canonicalize_entities(
            ["git hub", "dependa bot", "openssf malicious packages"],
            self.aliases,
        )
        right_entities = canonicalize_entities(
            ["OpenSSF malicious-packages", "GitHub", "Dependabot"],
            self.aliases,
        )
        left = event_fingerprint(
            left_entities,
            "扩大告警覆盖！",
            "跨 npm、PyPI 等生态的恶意软件包",
            "2026-07-28",
        )
        right = event_fingerprint(
            right_entities,
            "扩大告警覆盖",
            "跨 NPM / pypi 等生态的恶意软件包",
            "2026-07-28",
        )
        self.assertEqual(left, right)
        self.assertEqual(self.candidate["event_fingerprint"], left)

    def test_three_day_exact_event_without_delta_is_rejected(self) -> None:
        decision = evaluate_candidate(
            self.candidate,
            self.index,
            evaluated_at=datetime(2026, 7, 29, 4, 0, tzinfo=timezone.utc),
        )
        self.assertEqual("reject_duplicate_event", decision["decision"])
        self.assertTrue(decision["event_match"])
        self.assertEqual("none", decision["index_update"])
        self.assertEqual([], validate(decision, DECISION_SCHEMA))

    def test_three_day_exact_event_with_delta_becomes_continuation(self) -> None:
        follow_up = deepcopy(self.candidate)
        follow_up["candidate_id"] = "candidate-20260730-002"
        follow_up["observed_at"] = "2026-07-30T03:00:00Z"
        decision = evaluate_candidate(
            follow_up,
            self.index,
            evaluated_at=datetime(2026, 7, 30, 4, 0, tzinfo=timezone.utc),
            new_delta="GitHub 新增了企业级告警导出字段，并明确了现有仓库的迁移方式。",
        )
        self.assertEqual("continuation", decision["decision"])
        self.assertEqual("update", decision["index_update"])
        updated = apply_decision(self.index, follow_up, decision)
        self.assertIn("candidate-20260730-002", updated["entries"][0]["candidate_ids"])
        self.assertEqual([], validate(updated, INDEX_SCHEMA))

    def test_seven_day_same_topic_and_viewpoint_is_rejected(self) -> None:
        follow_up = deepcopy(self.candidate)
        follow_up["candidate_id"] = "candidate-20260801-003"
        follow_up["event_date"] = "2026-08-01"
        follow_up["dedup_keys"]["date_bucket"] = "2026-08-01"
        follow_up["event_action"] = "说明覆盖范围"
        follow_up["dedup_keys"]["action"] = "说明覆盖范围"
        follow_up["event_fingerprint"] = event_fingerprint(
            follow_up["canonical_entities"],
            follow_up["event_action"],
            follow_up["event_object"],
            follow_up["event_date"],
        )
        decision = evaluate_candidate(
            follow_up,
            self.index,
            evaluated_at=datetime(2026, 8, 1, 4, 0, tzinfo=timezone.utc),
        )
        self.assertFalse(decision["event_match"])
        self.assertTrue(decision["topic_match"])
        self.assertTrue(decision["viewpoint_match"])
        self.assertEqual("reject_duplicate_viewpoint", decision["decision"])

    def test_thirty_day_title_and_visual_reuse_generate_warnings(self) -> None:
        new_event = deepcopy(self.candidate)
        new_event.update(
            {
                "candidate_id": "candidate-20260820-004",
                "event_date": "2026-08-20",
                "canonical_entities": ["OpenAI"],
                "event_action": "发布",
                "event_object": "全新模型能力",
                "primary_category": "ai_technology",
                "summary_raw": "OpenAI 发布一项与依赖安全无关的新模型能力，用于验证标题与视觉资产去重。",
            }
        )
        new_event["dedup_keys"] = {
            "entities": ["OpenAI"],
            "action": "发布",
            "object": "全新模型能力",
            "date_bucket": "2026-08-20",
        }
        new_event["event_fingerprint"] = event_fingerprint(
            new_event["canonical_entities"],
            new_event["event_action"],
            new_event["event_object"],
            new_event["event_date"],
        )
        decision = evaluate_candidate(
            new_event,
            self.index,
            evaluated_at=datetime(2026, 8, 20, 4, 0, tzinfo=timezone.utc),
            proposed_title="Dependabot 扩大恶意软件包告警覆盖",
            visual_concept="蓝白安全控制台，展示 GitHub 仓库、恶意依赖告警与防护盾牌",
        )
        self.assertEqual("select_new", decision["decision"])
        self.assertTrue(decision["title_reuse_warning"])
        self.assertTrue(decision["visual_reuse_warning"])

    def test_asset_warnings_expire_after_thirty_days(self) -> None:
        new_event = deepcopy(self.candidate)
        new_event.update(
            {
                "candidate_id": "candidate-20260901-005",
                "event_date": "2026-09-01",
                "canonical_entities": ["OpenAI"],
                "event_action": "发布",
                "event_object": "全新模型能力",
                "primary_category": "ai_technology",
                "summary_raw": "一条发生在资产去重窗口之外的独立示例事件。",
            }
        )
        new_event["event_fingerprint"] = event_fingerprint(
            new_event["canonical_entities"],
            new_event["event_action"],
            new_event["event_object"],
            new_event["event_date"],
        )
        decision = evaluate_candidate(
            new_event,
            self.index,
            evaluated_at=datetime(2026, 9, 1, 4, 0, tzinfo=timezone.utc),
            proposed_title="Dependabot 扩大恶意软件包告警覆盖",
            visual_concept="蓝白安全控制台，展示 GitHub 仓库、恶意依赖告警与防护盾牌",
        )
        self.assertFalse(decision["title_reuse_warning"])
        self.assertFalse(decision["visual_reuse_warning"])


if __name__ == "__main__":
    unittest.main()
