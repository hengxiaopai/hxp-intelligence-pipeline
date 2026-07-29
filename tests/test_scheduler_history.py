from __future__ import annotations

import copy
import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.failure_reporting import build_failure_report, sanitize_message  # noqa: E402
from pipeline.history_commit import (  # noqa: E402
    HistoryCommitError,
    prepare_history_commit,
)
from pipeline.scheduler import build_daily_plan, update_source_state  # noqa: E402
from scripts.run_daily_pipeline import run_daily  # noqa: E402


FIXED_NOW = datetime(2026, 7, 29, 1, 0, 0, tzinfo=timezone.utc)


def source(
    registry_id: str,
    *,
    priority: int = 1,
    method: str = "rss",
    policy: str = "public_standard",
    active: bool = True,
    requires_auth: bool = False,
    minimum: int = 60,
    maximum_age: int = 24,
) -> dict:
    return {
        "registry_id": registry_id,
        "name": registry_id,
        "publisher": "Example",
        "homepage_url": "https://example.com/",
        "url": "https://example.com/feed.xml",
        "source_type": "official",
        "authority_level": "tier_1_official",
        "collection_method": method,
        "access_policy": policy,
        "parser_hint": "test",
        "active": active,
        "requires_auth": requires_auth,
        "priority": priority,
        "min_interval_minutes": minimum,
        "max_age_hours": maximum_age,
        "categories": ["ai_technology"],
        "languages": ["en"],
        "risk_notes": [],
    }


class SchedulerHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads(
            (ROOT / "config/schedule.json").read_text(encoding="utf-8")
        )
        cls.registry = {
            "schema_version": "1.0.0",
            "updated_at": "2026-07-29T00:00:00Z",
            "sources": [
                source("registry-live-rss", priority=1),
                source(
                    "registry-manual-source",
                    priority=2,
                    method="manual_review",
                    policy="manual_only",
                    minimum=1440,
                ),
                source("registry-auth-source", requires_auth=True),
                source("registry-inactive-source", active=False),
            ],
        }
        cls.empty_state = {
            "schema_version": "1.0.0",
            "updated_at": "2026-07-29T00:00:00Z",
            "sources": [],
        }
        cls.empty_index = {
            "schema_version": "1.0.0",
            "updated_at": "2026-07-29T00:00:00Z",
            "entries": [],
        }

    def validate(self, schema_name: str, value: dict) -> None:
        schema = json.loads(
            (ROOT / "schemas" / schema_name).read_text(encoding="utf-8")
        )
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        errors = sorted(
            validator.iter_errors(value),
            key=lambda error: [str(part) for part in error.absolute_path],
        )
        self.assertEqual([], [error.message for error in errors])

    def test_plan_is_deterministic_and_live_is_opt_in(self) -> None:
        first = build_daily_plan(
            registry=self.registry,
            state=self.empty_state,
            config=self.config,
            now=FIXED_NOW,
            mode="plan_only",
            live_enabled=False,
        )
        second = build_daily_plan(
            registry=self.registry,
            state=self.empty_state,
            config=self.config,
            now=FIXED_NOW,
            mode="plan_only",
            live_enabled=False,
        )
        self.assertEqual(first, second)
        self.validate("daily-plan.schema.json", first)
        actions = {item["registry_id"]: item["action"] for item in first["due_sources"]}
        self.assertEqual("plan_only", actions["registry-live-rss"])
        self.assertEqual("manual_review", actions["registry-manual-source"])
        self.assertEqual(0, first["summary"]["live_collectable"])
        blocked = {item["registry_id"]: item["reason"] for item in first["blocked_sources"]}
        self.assertEqual("requires_auth", blocked["registry-auth-source"])
        self.assertEqual("inactive", blocked["registry-inactive-source"])

        live = build_daily_plan(
            registry=self.registry,
            state=self.empty_state,
            config=self.config,
            now=FIXED_NOW,
            mode="live",
            live_enabled=True,
        )
        actions = {item["registry_id"]: item["action"] for item in live["due_sources"]}
        self.assertEqual("collect_live", actions["registry-live-rss"])
        self.assertEqual("manual_review", actions["registry-manual-source"])
        self.assertEqual(1, live["summary"]["live_collectable"])

    def test_success_watermark_defers_until_interval_or_freshness(self) -> None:
        recent = update_source_state(
            self.empty_state,
            registry_id="registry-live-rss",
            observed_at=FIXED_NOW - timedelta(minutes=30),
            status="success",
            content_hash="sha256:" + "a" * 64,
        )
        plan = build_daily_plan(
            registry={"sources": [source("registry-live-rss")]},
            state=recent,
            config=self.config,
            now=FIXED_NOW,
        )
        self.assertEqual([], plan["due_sources"])
        self.assertEqual(1, plan["summary"]["deferred_sources"])

        old = update_source_state(
            self.empty_state,
            registry_id="registry-live-rss",
            observed_at=FIXED_NOW - timedelta(hours=25),
            status="success",
            content_hash="sha256:" + "b" * 64,
        )
        plan = build_daily_plan(
            registry={"sources": [source("registry-live-rss")]},
            state=old,
            config=self.config,
            now=FIXED_NOW,
        )
        self.assertEqual(
            "freshness_deadline_exceeded", plan["due_sources"][0]["due_reason"]
        )

    def test_failure_retry_window_prevents_hammering(self) -> None:
        failed = update_source_state(
            self.empty_state,
            registry_id="registry-live-rss",
            observed_at=FIXED_NOW - timedelta(minutes=30),
            status="failure",
            failure_fp="failure-" + "c" * 32,
        )
        plan = build_daily_plan(
            registry={"sources": [source("registry-live-rss")]},
            state=failed,
            config=self.config,
            now=FIXED_NOW,
        )
        self.assertEqual([], plan["due_sources"])

        later = FIXED_NOW + timedelta(hours=4)
        plan = build_daily_plan(
            registry={"sources": [source("registry-live-rss")]},
            state=failed,
            config=self.config,
            now=later,
        )
        self.assertEqual("retry_after_failure", plan["due_sources"][0]["due_reason"])

    def test_pending_run_cannot_advance_history(self) -> None:
        run_dir = ROOT / "data/daily/2026-07-29"
        state_before = copy.deepcopy(self.empty_state)
        index_before = copy.deepcopy(self.empty_index)
        with self.assertRaisesRegex(HistoryCommitError, "approved"):
            prepare_history_commit(
                run_dir=run_dir,
                source_state=state_before,
                dedup_index=index_before,
            )
        self.assertEqual(self.empty_state, state_before)
        self.assertEqual(self.empty_index, index_before)

    def test_approved_run_commits_atomically_and_idempotently(self) -> None:
        source_run = ROOT / "data/daily/2026-07-29"
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "2026-07-29"
            shutil.copytree(source_run, run_dir)
            run_daily(
                run_dir=run_dir,
                weights_path=ROOT / "config/editorial-weights.json",
                config_path=ROOT / "config/daily-run.json",
                mode="archived_real_sources",
                review_status="approved",
            )
            state, index, summary = prepare_history_commit(
                run_dir=run_dir,
                source_state=self.empty_state,
                dedup_index=self.empty_index,
            )
            self.validate("schedule-state.schema.json", state)
            self.validate("dedup-index.schema.json", index)
            self.assertEqual(5, len(index["entries"]))
            self.assertEqual(5, len(summary["committed_item_ids"]))
            self.assertEqual(
                ["registry-github-changelog", "registry-openai-news"],
                summary["updated_registry_ids"],
            )
            self.assertEqual(5, sum(len(item["item_ids"]) for item in index["entries"]))

            replay_state, replay_index, replay = prepare_history_commit(
                run_dir=run_dir,
                source_state=state,
                dedup_index=index,
            )
            self.assertEqual(state, replay_state)
            self.assertEqual(index, replay_index)
            self.assertTrue(replay["idempotent"])
            self.assertEqual(0, len(replay["committed_item_ids"]))
            self.assertEqual(5, len(replay["already_committed_item_ids"]))

    def test_failure_reports_redact_secrets_and_respect_cooldown(self) -> None:
        raw = (
            "Authorization: Bearer abc.def.ghi token=supersecret "
            "password=hunter2 Cookie=session123"
        )
        sanitized = sanitize_message(raw)
        for secret in ("abc.def.ghi", "supersecret", "hunter2", "session123"):
            self.assertNotIn(secret, sanitized)
        self.assertIn("[REDACTED]", sanitized)

        first = build_failure_report(
            occurred_at=FIXED_NOW,
            stage="collection",
            error_type="CollectionError",
            message=raw,
            config=self.config,
            issue_enabled=True,
            source_registry_id="registry-live-rss",
        )
        self.validate("failure-report.schema.json", first)
        self.assertTrue(first["issue_eligible"])

        repeated = build_failure_report(
            occurred_at=FIXED_NOW + timedelta(hours=1),
            stage="collection",
            error_type="CollectionError",
            message=raw,
            config=self.config,
            prior_reports=[first],
            issue_enabled=True,
            source_registry_id="registry-live-rss",
        )
        self.assertFalse(repeated["issue_eligible"])
        self.assertEqual(2, repeated["occurrence_count"])

        after_cooldown = build_failure_report(
            occurred_at=FIXED_NOW + timedelta(hours=25),
            stage="collection",
            error_type="CollectionError",
            message=raw,
            config=self.config,
            prior_reports=[first],
            issue_enabled=True,
            source_registry_id="registry-live-rss",
        )
        self.assertTrue(after_cooldown["issue_eligible"])


if __name__ == "__main__":
    unittest.main()
