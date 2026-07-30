"""Render an offline no-extension publishing cockpit and manual status ledger."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit


PLATFORMS = ("wechat", "xiaohongshu", "douyin", "x", "website", "zhihu")
STATUSES = (
    "not_started",
    "opened",
    "pasted",
    "draft_saved",
    "published",
    "failed",
    "skipped",
)


class CockpitError(ValueError):
    """Raised when cockpit rendering or a manual status transition is unsafe."""


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def _safe_id(value: str) -> str:
    return "".join(character if character.isalnum() else "-" for character in value)


def _field_block(platform: str, name: str, label: str, value: str) -> str:
    if not value:
        return ""
    target = _safe_id(f"{platform}-{name}")
    escaped = html.escape(value)
    return f"""
      <section class="field">
        <div class="field-head"><h3>{html.escape(label)}</h3><button type="button" data-copy="{target}">复制</button></div>
        <textarea id="{target}" readonly>{escaped}</textarea>
      </section>
    """


def _platform_card(entry: Mapping[str, Any]) -> str:
    platform = str(entry["platform"])
    content = entry["content"]
    hashtags = " ".join(content.get("hashtags", []))
    thread = "\n\n".join(content.get("thread", []))
    sources = " / ".join(content.get("source_labels", []))
    assets = "".join(
        f"""
        <figure>
          <img src="{html.escape(str(asset['bundle_path']))}" alt="{html.escape(str(entry['display_name']))} 图片 {asset['order']}" loading="lazy">
          <figcaption>{asset['order']:02d} · {asset['width']}×{asset['height']} · {asset['sha256'][:12]}…</figcaption>
        </figure>
        """
        for asset in entry.get("assets", [])
    )
    checklist = "".join(
        f'<label class="check"><input type="checkbox">{html.escape(str(value))}</label>'
        for value in entry.get("checklist", [])
    )
    files = entry["files"]
    file_links = "".join(
        f'<a class="secondary" href="{html.escape(str(record["path"]))}" download>{html.escape(label)}</a>'
        for label, record in (("JSON", files["json"]), ("Markdown", files["markdown"]), ("纯文本", files["text"]))
    )
    answer_blocks = ""
    if platform == "zhihu":
        answer_blocks = _field_block(
            platform,
            "question",
            "回答前先选择真实问题",
            str(content.get("answer_question_placeholder") or ""),
        ) + _field_block(
            platform,
            "answer",
            "知乎回答版",
            str(content.get("answer_markdown") or ""),
        )

    return f"""
    <article class="platform-card" id="platform-{html.escape(platform)}">
      <header class="card-head">
        <div><p class="eyebrow">{html.escape(platform.upper())}</p><h2>{html.escape(str(entry['display_name']))}</h2></div>
        <span class="status">{html.escape(str(entry['status']))}</span>
      </header>
      <p class="meta">内容哈希 {entry['content_hash'][:16]}… · 图片 {len(entry.get('assets', []))} 张 · {'派生内容' if entry.get('derived') else '原生平台内容包'}</p>
      <div class="actions">
        <a class="primary" href="{html.escape(str(entry['creator_url']))}" target="_blank" rel="noopener noreferrer">打开官方创作入口</a>
        {file_links}
      </div>
      {_field_block(platform, 'title', '标题', str(content.get('title', '')))}
      {_field_block(platform, 'summary', '摘要', str(content.get('summary', '')))}
      {_field_block(platform, 'body', '正文 / 文章版', str(content.get('body_markdown', '')))}
      {_field_block(platform, 'caption', '发布文案', str(content.get('caption', '')))}
      {_field_block(platform, 'thread', '线程', thread)}
      {_field_block(platform, 'hashtags', '话题标签', hashtags)}
      {_field_block(platform, 'seo', 'SEO', '\n'.join(value for value in [str(content.get('seo_title', '')), str(content.get('seo_description', '')), str(content.get('slug', ''))] if value))}
      {answer_blocks}
      {_field_block(platform, 'sources', '来源', sources)}
      {_field_block(platform, 'risk', '风险声明', str(content.get('risk_disclaimer') or ''))}
      <section class="assets"><h3>图片顺序与校验</h3><div class="asset-grid">{assets}</div></section>
      <section class="checklist"><h3>人工发布前检查</h3>{checklist}</section>
      <p class="notice">打开页面、复制内容或勾选清单都不代表发布成功。最终状态必须由用户手动记录。</p>
    </article>
    """


def render_cockpit_html(manifest: Mapping[str, Any], *, output_path: Path) -> None:
    """Write a self-contained HTML cockpit with no external scripts or styles."""
    if manifest.get("external_write_performed") is not False:
        raise CockpitError("驾驶舱只能处理 external_write_performed=false 的交接清单")
    entries = list(manifest.get("platforms", []))
    if [str(value.get("platform")) for value in entries] != list(PLATFORMS):
        raise CockpitError("驾驶舱平台顺序或集合不完整")
    cards = "\n".join(_platform_card(entry) for entry in entries)
    navigation = "".join(
        f'<a href="#platform-{html.escape(str(entry["platform"]))}">{html.escape(str(entry["display_name"]))}</a>'
        for entry in entries
    )
    embedded_manifest = html.escape(json.dumps(manifest, ensure_ascii=False, sort_keys=True))
    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>珩小派发布驾驶舱 · {html.escape(str(manifest['date']))}</title>
<style>
:root{{--bg:#f5f8fb;--panel:#fff;--ink:#10233f;--muted:#667b91;--line:#dce7f1;--accent:#0c5bff;--accent2:#23b7ff;--ok:#0b7a55}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:"Noto Sans CJK SC","Microsoft YaHei",system-ui,sans-serif;line-height:1.65}}
.shell{{max-width:1420px;margin:auto;padding:36px}}.hero{{padding:42px;border:1px solid var(--line);border-radius:30px;background:linear-gradient(135deg,#fff,#eef7ff)}}
.eyebrow{{margin:0 0 8px;color:var(--accent);font-size:13px;font-weight:800;letter-spacing:.14em}}h1{{font-size:42px;line-height:1.15;margin:0 0 12px}}h2{{margin:0;font-size:30px}}h3{{margin:0;font-size:16px}}
.hero p{{max-width:850px;color:var(--muted)}}nav{{position:sticky;top:0;z-index:5;display:flex;gap:10px;overflow:auto;padding:16px 0;background:rgba(245,248,251,.94);backdrop-filter:blur(12px)}}nav a,.secondary{{white-space:nowrap;text-decoration:none;color:var(--ink);border:1px solid var(--line);background:#fff;border-radius:999px;padding:9px 14px}}
.platform-card{{margin:24px 0;padding:30px;border:1px solid var(--line);border-radius:28px;background:var(--panel);box-shadow:0 18px 60px rgba(21,56,88,.06)}}.card-head{{display:flex;justify-content:space-between;gap:20px;align-items:center}}.status{{padding:7px 12px;border-radius:999px;background:#eaf8f2;color:var(--ok);font-weight:800}}
.meta,.notice{{color:var(--muted)}}.actions{{display:flex;gap:10px;flex-wrap:wrap;margin:22px 0}}.primary,.actions a{{text-decoration:none}}.primary{{background:var(--accent);color:#fff;padding:11px 18px;border-radius:999px;font-weight:800}}
.field{{border-top:1px solid var(--line);padding:20px 0}}.field-head{{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}}button{{border:0;border-radius:999px;padding:8px 14px;background:#eaf1ff;color:var(--accent);font-weight:800;cursor:pointer}}button.copied{{background:#dff7ec;color:var(--ok)}}textarea{{width:100%;min-height:130px;resize:vertical;border:1px solid var(--line);border-radius:16px;padding:16px;background:#fbfdff;color:var(--ink);font:inherit}}
.assets,.checklist{{border-top:1px solid var(--line);padding-top:20px;margin-top:6px}}.asset-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:14px;margin-top:14px}}figure{{margin:0;border:1px solid var(--line);border-radius:18px;overflow:hidden;background:#f8fbfe}}figure img{{width:100%;aspect-ratio:3/4;object-fit:cover;display:block}}figcaption{{padding:9px;font-size:12px;color:var(--muted);overflow-wrap:anywhere}}
.check{{display:block;padding:8px 0}}.check input{{margin-right:9px}}.notice{{padding:13px 16px;background:#fff8e8;border-radius:14px}}footer{{padding:28px 0;color:var(--muted)}}@media(max-width:720px){{.shell{{padding:18px}}.hero,.platform-card{{padding:22px;border-radius:22px}}h1{{font-size:32px}}h2{{font-size:25px}}}}
</style>
</head>
<body>
<div class="shell">
<section class="hero"><p class="eyebrow">HENGXIAOPAI · NO-EXTENSION WORKFLOW</p><h1>多平台发布驾驶舱</h1><p>{html.escape(str(manifest['date']))} · 六个平台内容、图片顺序、哈希与人工检查集中在一个离线页面。无需浏览器扩展，不读取 Cookie，不自动填写网页，也不执行真实平台写入。</p></section>
<nav>{navigation}</nav>
<main>{cards}</main>
<footer>珩小派｜一人公司情报雷达 · external_write_performed=false</footer>
<script type="application/json" id="handoff-manifest">{embedded_manifest}</script>
<script>
(function(){{
  function fallbackCopy(text){{const el=document.createElement('textarea');el.value=text;el.style.position='fixed';el.style.opacity='0';document.body.appendChild(el);el.select();document.execCommand('copy');el.remove();}}
  document.querySelectorAll('[data-copy]').forEach(function(button){{button.addEventListener('click',async function(){{const target=document.getElementById(button.dataset.copy);if(!target)return;try{{await navigator.clipboard.writeText(target.value)}}catch(error){{fallbackCopy(target.value)}}button.classList.add('copied');button.textContent='已复制';setTimeout(function(){{button.classList.remove('copied');button.textContent='复制'}},1400);}})}});
}})();
</script>
</div>
</body>
</html>
"""
    _write_text(output_path, document)


def _summary(records: list[Mapping[str, Any]]) -> dict[str, int]:
    counts = {value: 0 for value in STATUSES}
    for record in records:
        counts[str(record["status"])] += 1
    return {"total": 6, **counts}


def build_initial_session(
    manifest: Mapping[str, Any],
    *,
    created_at: str,
    session_slug: str = "manual",
) -> dict[str, Any]:
    entries = list(manifest.get("platforms", []))
    if len(entries) != 6:
        raise CockpitError("交接清单必须包含六个平台")
    records = [
        {
            "platform": entry["platform"],
            "status": "not_started",
            "content_hash": entry["content_hash"],
            "asset_hashes": list(entry["asset_hashes"]),
            "updated_at": created_at,
            "external_content_id": None,
            "external_url": None,
            "notes": None,
            "confirmed_by_user": False,
        }
        for entry in entries
    ]
    date_token = str(manifest["date"]).replace("-", "")
    safe_slug = _safe_id(session_slug).strip("-").casefold() or "manual"
    return {
        "schema_version": "1.0.0",
        "session_id": f"cockpit-session-{date_token}-{safe_slug}",
        "handoff_id": manifest["handoff_id"],
        "created_at": created_at,
        "updated_at": created_at,
        "external_write_performed": False,
        "records": records,
        "summary": _summary(records),
    }


def _validate_external_url(value: str | None) -> None:
    if value is None:
        return
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise CockpitError("平台内容URL必须使用HTTPS")
    if parsed.username or parsed.password:
        raise CockpitError("平台内容URL不得包含凭据")


def update_manual_record(
    *,
    session: Mapping[str, Any],
    manifest: Mapping[str, Any],
    platform: str,
    status: str,
    updated_at: str,
    confirmed_by_user: bool,
    external_content_id: str | None = None,
    external_url: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Update one user-confirmed manual record after verifying content identity."""
    if platform not in PLATFORMS or status not in STATUSES:
        raise CockpitError("未知平台或人工状态")
    if session.get("handoff_id") != manifest.get("handoff_id"):
        raise CockpitError("Session与Handoff不匹配")
    current = next((value for value in manifest["platforms"] if value["platform"] == platform), None)
    if current is None:
        raise CockpitError(f"交接清单缺少平台：{platform}")
    records = [dict(value) for value in session.get("records", [])]
    index = next((i for i, value in enumerate(records) if value["platform"] == platform), None)
    if index is None:
        raise CockpitError(f"Session缺少平台：{platform}")
    record = records[index]
    if record.get("content_hash") != current.get("content_hash") or list(record.get("asset_hashes", [])) != list(current.get("asset_hashes", [])):
        raise CockpitError("内容或图片哈希已经漂移，旧人工状态不可复用")
    if status in {"opened", "pasted", "draft_saved", "published", "failed", "skipped"} and not confirmed_by_user:
        raise CockpitError("状态变化必须由用户明确确认")
    if status == "published" and not (external_content_id or external_url):
        raise CockpitError("已发布状态必须由用户填写平台内容ID或HTTPS链接")
    _validate_external_url(external_url)
    record.update(
        {
            "status": status,
            "updated_at": updated_at,
            "external_content_id": external_content_id,
            "external_url": external_url,
            "notes": notes,
            "confirmed_by_user": confirmed_by_user,
        }
    )
    records[index] = record
    result = dict(session)
    result.update(
        {
            "updated_at": updated_at,
            "external_write_performed": False,
            "records": records,
            "summary": _summary(records),
        }
    )
    return result
