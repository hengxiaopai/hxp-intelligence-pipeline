#!/usr/bin/env python3
"""Build a non-executable official connector request from qualified fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from publishing.official_request import OfficialRequestError, build_official_request  # noqa: E402
from visual.pipeline import write_json  # noqa: E402
from visual.queue import load_json  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qualification-report", type=Path, required=True)
    parser.add_argument("--connector-id", required=True)
    parser.add_argument("--packages", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--material-mapping", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "config/official-connectors.json")
    parser.add_argument("--generated-at", required=True)
    parser.add_argument("--expires-at", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def schema_errors(payload: Any) -> list[str]:
    validator = Draft202012Validator(
        load_json(ROOT / "schemas/official-connector-request.schema.json"),
        format_checker=FormatChecker(),
    )
    return [
        f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(
            validator.iter_errors(payload),
            key=lambda error: [str(part) for part in error.absolute_path],
        )
    ]


def main() -> int:
    args = parse_args()
    try:
        report = load_json(args.qualification_report)
        config = load_json(args.config)
        packages = load_json(args.packages)
        plan = load_json(args.plan)
        qualification = next(
            (value for value in report["qualifications"] if value["connector_id"] == args.connector_id),
            None,
        )
        connector = next(
            (value for value in config["connectors"] if value["connector_id"] == args.connector_id),
            None,
        )
        if qualification is None or connector is None:
            raise OfficialRequestError(f"未知连接器：{args.connector_id}")
        platform = connector["platform"]
        package = next((value for value in packages["packages"] if value["platform"] == platform), None)
        entry = next((value for value in plan["entries"] if value["platform"] == platform), None)
        if package is None or entry is None:
            raise OfficialRequestError(f"内容包或发布计划缺少平台：{platform}")
        request = build_official_request(
            qualification=qualification,
            connector_config=connector,
            plan_entry=entry,
            package=package,
            generated_at=args.generated_at,
            expires_at=args.expires_at,
            material_mapping=load_json(args.material_mapping),
        )
        errors = schema_errors(request)
        if errors:
            raise OfficialRequestError("官方请求Schema校验失败：\n- " + "\n- ".join(errors))
        write_json(args.output, request)
    except (OfficialRequestError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        "PASS official request: "
        f"connector={request['connector_id']} steps={len(request['request_plan'])} "
        f"execution={request['execution_enabled']} external_write={request['external_write_performed']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
