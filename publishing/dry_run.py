"""Generate local Markdown/HTML previews without contacting any platform."""

from __future__ import annotations

import hashlib
import html
import shutil
from pathlib import Path
from typing import Any, Mapping


class PublicationDryRunError(ValueError):
    """Raised when a local preview cannot preserve package integrity."""


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_assets(package: Mapping[str, Any], output_dir: Path) -> list[str]:
    target_dir = output_dir / "assets" / str(package["platform"])
    target_dir.mkdir(parents=True, exist_ok=True)
    relative_paths: list[str] = []
    for asset in sorted(package["assets"], key=lambda value: int(value["order"])):
        source = Path(str(asset["path"]))
        if not source.is_file():
            raise PublicationDryRunError(f"预览资产不存在：{source}")
        if _file_hash(source) != asset["sha256"]:
            raise PublicationDryRunError(f"预览资产哈希不一致：{source}")
        suffix = source.suffix.lower() or ".png"
        target = target_dir / f"{int(asset['order']):02d}-{asset['export_id']}{suffix}"
        shutil.copyfile(source, target)
        relative_paths.append(target.relative_to(output_dir).as_posix())
    return relative_paths


def _markdown(package: Mapping[str, Any], asset_paths: list[str]) -> str:
    content = package["content"]
    lines = [
        "---",
        f"package_id: {package['package_id']}",
        f"platform: {package['platform']}",
        f"content_hash: {package['content_hash']}",
        "external_write_performed: false",
        "---",
        "",
        f"# {content['title'] or package['platform']}",
        "",
    ]
    if content.get("summary"):
        lines.extend([content["summary"], ""])
    for path in asset_paths:
        lines.extend([f"![{package['platform']} preview]({path})", ""])
    if content.get("body_markdown"):
        lines.extend([content["body_markdown"].strip(), ""])
    if content.get("answer_question_placeholder"):
        lines.extend(
            [
                "## 回答前先选择真实问题",
                "",
                str(content["answer_question_placeholder"]),
                "",
            ]
        )
    if content.get("answer_markdown"):
        lines.extend(["## 知乎回答版", "", content["answer_markdown"].strip(), ""])
    if content.get("caption"):
        lines.extend(["## 发布文案", "", content["caption"].strip(), ""])
    if content.get("thread"):
        lines.extend(["## 线程", ""])
        for index, value in enumerate(content["thread"], start=1):
            lines.extend([f"### {index}", "", str(value), ""])
    if content.get("hashtags"):
        lines.extend([" ".join(content["hashtags"]), ""])
    if content.get("source_labels"):
        lines.extend(["来源：" + " / ".join(content["source_labels"]), ""])
    if content.get("risk_disclaimer"):
        lines.extend([f"> {content['risk_disclaimer']}", ""])
    return "\n".join(lines).rstrip() + "\n"


def _html(package: Mapping[str, Any], asset_paths: list[str]) -> str:
    content = package["content"]
    images = "".join(
        f'<figure><img src="{html.escape(path, quote=True)}" alt="{html.escape(str(package["platform"]))} preview"></figure>'
        for path in asset_paths
    )
    thread = "".join(
        f"<li>{html.escape(str(value))}</li>" for value in content.get("thread", [])
    )
    hashtags = " ".join(content.get("hashtags", []))
    body = html.escape(str(content.get("body_markdown", ""))).replace("\n", "<br>")
    caption = html.escape(str(content.get("caption", ""))).replace("\n", "<br>")
    question = html.escape(str(content.get("answer_question_placeholder", ""))).replace("\n", "<br>")
    answer = html.escape(str(content.get("answer_markdown", ""))).replace("\n", "<br>")
    zhihu_sections = ""
    if question:
        zhihu_sections += f'<section><h2>回答前先选择真实问题</h2><p class="notice">{question}</p></section>'
    if answer:
        zhihu_sections += f'<section><h2>知乎回答版</h2><p>{answer}</p></section>'
    return f'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(str(content.get("title") or package["platform"]))}</title>
<style>
body{{margin:0;background:#f4f8fb;color:#10233f;font-family:system-ui,-apple-system,"Microsoft YaHei",sans-serif}}
main{{max-width:960px;margin:0 auto;padding:48px 24px 96px}}
header,.card{{background:#fff;border:1px solid #d7e6f5;border-radius:24px;padding:28px;margin-bottom:24px}}
h1{{font-size:34px;line-height:1.25;margin:0 0 16px}}h2{{font-size:23px;margin-top:30px}}p,li{{font-size:17px;line-height:1.8}}figure{{margin:0 0 20px}}img{{display:block;width:100%;height:auto;border-radius:18px;border:1px solid #d7e6f5}}.meta{{color:#56708f;font-size:14px}}.notice{{color:#8a5700;background:#fff8e8;border-radius:14px;padding:14px}}</style>
</head>
<body><main>
<header><div class="meta">{html.escape(str(package['package_id']))} · DRY RUN · no external write</div><h1>{html.escape(str(content.get('title') or package['platform']))}</h1><p>{html.escape(str(content.get('summary','')))}</p></header>
<div class="card">{images}</div>
<div class="card"><p>{body}</p>{zhihu_sections}<p>{caption}</p><ol>{thread}</ol><p>{html.escape(hashtags)}</p><p class="meta">来源：{html.escape(' / '.join(content.get('source_labels', [])))}</p>{f'<p class="notice">{html.escape(str(content.get("risk_disclaimer")))}</p>' if content.get('risk_disclaimer') else ''}</div>
</main></body></html>
'''


def build_dry_run_result(
    *,
    package_batch: Mapping[str, Any],
    plan: Mapping[str, Any],
    output_dir: Path,
    executed_at: str,
    approval: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if plan.get("package_batch_id") != package_batch.get("package_batch_id"):
        raise PublicationDryRunError("发布计划与内容包批次不一致")
    if plan.get("write_actions_enabled") is not False:
        raise PublicationDryRunError("发布准备禁止平台写入")
    if approval is not None and approval.get("plan_id") != plan.get("plan_id"):
        raise PublicationDryRunError("批准记录与发布计划不一致")

    output_dir.mkdir(parents=True, exist_ok=True)
    packages = {value["package_id"]: value for value in package_batch["packages"]}
    results: list[dict[str, Any]] = []
    for entry in plan["entries"]:
        package = packages.get(entry["package_id"])
        errors: list[str] = []
        preview_path: str | None = None
        status = "previewed"
        if package is None:
            status = "failed"
            errors.append("发布计划引用未知内容包")
        elif package["content_hash"] != entry["content_hash"]:
            status = "failed"
            errors.append("内容哈希与发布计划不一致")
        elif [value["sha256"] for value in package["assets"]] != entry["asset_hashes"]:
            status = "failed"
            errors.append("图片哈希或顺序与发布计划不一致")
        elif package["status"] != "validated" or entry["approval_status"] == "blocked":
            status = "blocked"
            errors.append("内容包或发布条目被阻断")
        else:
            try:
                asset_paths = _copy_assets(package, output_dir)
                markdown_path = output_dir / f"{entry['platform']}.md"
                html_path = output_dir / f"{entry['platform']}.html"
                markdown_path.write_text(_markdown(package, asset_paths), encoding="utf-8")
                html_path.write_text(_html(package, asset_paths), encoding="utf-8")
                preview_path = html_path.relative_to(output_dir).as_posix()
            except (OSError, PublicationDryRunError) as exc:
                status = "failed"
                errors.append(str(exc))

        results.append(
            {
                "entry_id": entry["entry_id"],
                "platform": entry["platform"],
                "idempotency_key": entry["idempotency_key"],
                "status": status,
                "preview_path": preview_path,
                "external_id": None,
                "external_url": None,
                "attempt": 1,
                "error_type": None if not errors else ("Blocked" if status == "blocked" else "PreviewError"),
                "error_message": None if not errors else "; ".join(errors),
                "content_hash": entry["content_hash"],
                "asset_hashes": entry["asset_hashes"],
            }
        )

    compact = str(package_batch["date"]).replace("-", "")
    return {
        "schema_version": "1.0.0",
        "result_batch_id": f"publication-result-{compact}",
        "plan_id": plan["plan_id"],
        "approval_id": approval["approval_id"] if approval else None,
        "executed_at": executed_at,
        "execution_mode": "dry_run",
        "external_write_performed": False,
        "results": results,
        "summary": {
            "total": len(results),
            "previewed": sum(value["status"] == "previewed" for value in results),
            "blocked": sum(value["status"] == "blocked" for value in results),
            "failed": sum(value["status"] == "failed" for value in results),
        },
    }
