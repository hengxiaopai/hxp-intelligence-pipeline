from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collectors.base import (  # noqa: E402
    CollectionError,
    assert_supported_source,
    load_registry_source,
    validate_public_https_url,
)
from collectors.snapshot import collect_from_bytes, write_snapshot  # noqa: E402

REGISTRY = ROOT / "config/sources.json"
SNAPSHOT_SCHEMA = ROOT / "schemas/raw-snapshot.schema.json"
FIXTURES = ROOT / "tests/fixtures"
FIXED_TIME = datetime(2026, 7, 29, 3, 30, 0, tzinfo=timezone.utc)


class CollectorTests(unittest.TestCase):
    def validate_snapshot(self, snapshot: dict) -> None:
        schema = json.loads(SNAPSHOT_SCHEMA.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        errors = sorted(
            validator.iter_errors(snapshot),
            key=lambda error: [str(part) for part in error.absolute_path],
        )
        self.assertEqual([], [error.message for error in errors])

    def test_rss_fixture_creates_two_items(self) -> None:
        source = load_registry_source(REGISTRY, "registry-arxiv-cs-ai")
        body = (FIXTURES / "arxiv-cs-ai.xml").read_bytes()
        snapshot, raw = collect_from_bytes(
            source,
            body,
            retrieved_at=FIXED_TIME,
        )
        self.assertEqual(body, raw)
        self.assertEqual("fixture", snapshot["fetch_mode"])
        self.assertEqual("rss", snapshot["collection_method"])
        self.assertEqual(2, len(snapshot["items"]))
        first = snapshot["items"][0]
        self.assertEqual("Auditable Agents for Long-Horizon Workflows", first["title"])
        self.assertEqual("2026-07-28T12:00:00Z", first["published_at"])
        self.assertEqual(["Example Research Group"], first["authors"])
        self.assertIn("offline fixture", first["summary"].lower())

    def test_html_fixture_resolves_relative_links(self) -> None:
        source = load_registry_source(REGISTRY, "registry-github-changelog")
        body = (FIXTURES / "github-changelog.html").read_bytes()
        snapshot, _ = collect_from_bytes(
            source,
            body,
            retrieved_at=FIXED_TIME,
        )
        self.assertEqual("html_index", snapshot["collection_method"])
        self.assertEqual(2, len(snapshot["items"]))
        first = snapshot["items"][0]
        self.assertEqual(
            "https://github.blog/changelog/2026-07-28-example-security-update/",
            first["url"],
        )
        self.assertEqual("2026-07-28T09:00:00Z", first["published_at"])
        self.assertEqual(["GitHub Example Team"], first["authors"])
        self.assertEqual(["security"], first["tags"])

    def test_written_snapshot_passes_schema(self) -> None:
        source = load_registry_source(REGISTRY, "registry-arxiv-cs-ai")
        body = (FIXTURES / "arxiv-cs-ai.xml").read_bytes()
        snapshot, raw = collect_from_bytes(
            source,
            body,
            retrieved_at=FIXED_TIME,
        )
        with tempfile.TemporaryDirectory() as directory:
            metadata_path, body_path, materialized = write_snapshot(
                snapshot,
                raw,
                output_dir=Path(directory),
            )
            self.assertTrue(metadata_path.exists())
            self.assertTrue(body_path.exists())
            self.assertEqual(raw, body_path.read_bytes())
            self.validate_snapshot(materialized)
            persisted = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(materialized, persisted)

    def test_manual_only_source_is_blocked_for_live_collection(self) -> None:
        source = load_registry_source(REGISTRY, "registry-producthunt-daily")
        with self.assertRaises(CollectionError):
            assert_supported_source(source, live=True)

    def test_private_and_local_urls_are_rejected(self) -> None:
        for url in (
            "https://127.0.0.1/test",
            "https://10.0.0.8/test",
            "https://169.254.169.254/latest/meta-data/",
            "https://localhost/test",
        ):
            with self.subTest(url=url):
                with self.assertRaises(CollectionError):
                    validate_public_https_url(url, resolve_dns=False)

    def test_unknown_registry_id_is_rejected(self) -> None:
        with self.assertRaisesRegex(CollectionError, "未注册"):
            load_registry_source(REGISTRY, "registry-does-not-exist")


if __name__ == "__main__":
    unittest.main()
