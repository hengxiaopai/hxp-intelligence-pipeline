#!/usr/bin/env python3
"""Materialize the first real-source HXP daily run for 2026-07-29.

The source records below summarize official pages reviewed on 2026-07-29.
They are archived facts, not synthetic news and not live network responses.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.normalization import event_fingerprint  # noqa: E402
from scripts.run_daily_pipeline import run_daily  # noqa: E402

DATE = "2026-07-29"
OBSERVED_AT = "2026-07-29T12:00:00+08:00"
RETRIEVED_AT = "2026-07-29T04:00:00Z"
RUN_DIR = ROOT / "data/daily/2026-07-29"


def stable_hash(*values: str) -> str:
    payload = "\n".join(values).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def source(
    *,
    source_id: str,
    title: str,
    url: str,
    publisher: str,
    source_type: str,
    published_at: str,
    evidence_summary: str,
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "title": title,
        "url": url,
        "publisher": publisher,
        "source_type": source_type,
        "authority_level": "tier_1_official",
        "published_at": published_at,
        "retrieved_at": RETRIEVED_AT,
        "evidence_summary": evidence_summary,
        "verification_status": "verified",
        "conflicts": [],
    }


def candidate(
    *,
    sequence: int,
    title_raw: str,
    entities: list[str],
    action: str,
    event_object: str,
    event_date: str,
    category: str,
    information_types: list[str],
    summary_raw: str,
    source_ids: list[str],
    source_urls: list[str],
    claims: list[dict[str, str]],
    authority: int,
    freshness: int,
    relevance: int,
    confidence: str,
    risk_flags: list[str],
    registry_id: str,
    status: str = "deduped",
    rejection_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "candidate_id": f"candidate-20260729-{sequence:03d}",
        "observed_at": OBSERVED_AT,
        "title_raw": title_raw,
        "title_normalized": title_raw,
        "canonical_entities": entities,
        "event_action": action,
        "event_object": event_object,
        "event_date": event_date,
        "primary_category": category,
        "information_types": information_types,
        "summary_raw": summary_raw,
        "source_ids": source_ids,
        "source_urls": source_urls,
        "evidence_claims": claims,
        "authority_score": authority,
        "freshness_score": freshness,
        "relevance_score": relevance,
        "preliminary_confidence": confidence,
        "event_fingerprint": event_fingerprint(
            entities, action, event_object, event_date
        ),
        "dedup_keys": {
            "entities": entities,
            "action": action,
            "object": event_object,
            "date_bucket": event_date,
        },
        "risk_flags": risk_flags,
        "ingestion": {
            "source_registry_id": registry_id,
            "collection_method": "manual_review",
            "retrieved_at": RETRIEVED_AT,
            "content_hash": "sha256:"
            + stable_hash(*source_urls, summary_raw, *[claim["evidence_text"] for claim in claims]),
            "parser_version": "daily-real-v0.1.0",
            "raw_snapshot_path": f"data/daily/2026-07-29/sources/{source_ids[0]}.json",
        },
        "status": status,
        "rejection_reason": rejection_reason,
    }


def editorial(
    *,
    impact: int,
    novelty: int,
    content_value: int,
    product_value: int,
    evidence_quality: int,
    public_title: str,
    subtitle: str,
    summary: str,
    why: list[str],
    follow: list[str],
    conversions: list[str],
    audiences: list[str],
    selected_reason: str,
    visual_concept: str,
    must_not_fabricate: list[str],
) -> dict[str, Any]:
    return {
        "impact_score": impact,
        "novelty_score": novelty,
        "content_value_score": content_value,
        "product_value_score": product_value,
        "evidence_quality_score": evidence_quality,
        "public_title": public_title,
        "subtitle": subtitle,
        "summary": summary,
        "why_it_matters": why,
        "follow_up": follow,
        "conversion_directions": conversions,
        "audiences": audiences,
        "selected_reason": selected_reason,
        "visual_brief": {
            "concept": visual_concept,
            "visual_type": "self_made_infographic",
            "must_not_fabricate": must_not_fabricate,
        },
    }


def dedup(
    action: str,
    novelty_kind: str,
    *,
    matched: list[str] | None = None,
    new_delta: str | None = None,
    previous: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "action": action,
        "novelty_kind": novelty_kind,
        "matched_item_ids": matched or [],
        "new_delta": new_delta,
        "previous_item_ids": previous or [],
    }


def build_sources() -> list[dict[str, Any]]:
    return [
        source(
            source_id="src-openai-work-crossover-20260727",
            title="How AI is expanding what people do at work",
            url="https://openai.com/index/how-ai-is-expanding-what-people-do-at-work/",
            publisher="OpenAI",
            source_type="official",
            published_at="2026-07-27T00:00:00Z",
            evidence_summary=(
                "OpenAI Economic Research 分析超过80万条美国ChatGPT用户消息；"
                "16.8%的工作相关消息、43.5%的职业特定消息涉及传统上属于其他职业的任务。"
            ),
        ),
        source(
            source_id="src-github-actions-workflow-approval-20260728",
            title="GitHub Actions holds potentially malicious workflows for approval",
            url="https://github.blog/changelog/2026-07-28-github-actions-holds-unproven-workflows-for-approval/",
            publisher="GitHub",
            source_type="github",
            published_at="2026-07-28T00:00:00Z",
            evidence_summary=(
                "GitHub对被识别为潜在恶意的公共仓库Actions工作流先行暂停，"
                "需具有写权限的协作者通过已认证网页会话审核后才能运行。"
            ),
        ),
        source(
            source_id="src-github-dependabot-malware-20260728",
            title="Dependabot alerts on malicious packages across more ecosystems",
            url="https://github.blog/changelog/2026-07-28-dependabot-alerts-on-malicious-packages-across-more-ecosystems/",
            publisher="GitHub",
            source_type="github",
            published_at="2026-07-28T00:00:00Z",
            evidence_summary=(
                "GitHub Advisory Database接入OpenSSF malicious-packages数据，"
                "Dependabot恶意软件告警覆盖由npm扩展至PyPI等更多生态。"
            ),
        ),
        source(
            source_id="src-github-copilot-jetbrains-governance-20260727",
            title="GitHub Copilot for JetBrains adds improved OpenTelemetry configuration and model management",
            url="https://github.blog/changelog/2026-07-27-github-copilot-for-jetbrains-adds-improvved-opentelemetry-configuration-and-model-management/",
            publisher="GitHub",
            source_type="github",
            published_at="2026-07-27T00:00:00Z",
            evidence_summary=(
                "JetBrains插件新增Agent工作流OpenTelemetry导出、BYOK与自定义端点Token上限、"
                "内置模型开关、Claude Agent流程中的MCP与自定义Agent，以及AI credits显示。"
            ),
        ),
        source(
            source_id="src-github-copilot-app-policy-20260727",
            title="Manage GitHub Copilot app access with a dedicated policy",
            url="https://github.blog/changelog/2026-07-27-manage-github-copilot-app-access-with-a-dedicated-policy/",
            publisher="GitHub",
            source_type="github",
            published_at="2026-07-27T00:00:00Z",
            evidence_summary=(
                "GitHub Copilot App获得独立于Copilot CLI的企业与组织访问策略，"
                "管理员可统一启用、禁用或下放组织决定。"
            ),
        ),
        source(
            source_id="src-github-copilot-managed-settings-20260727",
            title="Enterprise managed settings in the GitHub Copilot app and Copilot cloud agent",
            url="https://github.blog/changelog/2026-07-27-enterprise-managed-settings-now-apply-to-the-github-copilot-app/",
            publisher="GitHub",
            source_type="github",
            published_at="2026-07-27T00:00:00Z",
            evidence_summary=(
                "managed-settings.json现可统一约束Copilot App与Cloud Agent，"
                "覆盖插件、市场、权限提示绕过和默认模型选择等企业治理项。"
            ),
        ),
    ]


def build_pool() -> dict[str, Any]:
    openai_url = "https://openai.com/index/how-ai-is-expanding-what-people-do-at-work/"
    actions_url = "https://github.blog/changelog/2026-07-28-github-actions-holds-unproven-workflows-for-approval/"
    dependabot_url = "https://github.blog/changelog/2026-07-28-dependabot-alerts-on-malicious-packages-across-more-ecosystems/"
    jetbrains_url = "https://github.blog/changelog/2026-07-27-github-copilot-for-jetbrains-adds-improvved-opentelemetry-configuration-and-model-management/"
    app_policy_url = "https://github.blog/changelog/2026-07-27-manage-github-copilot-app-access-with-a-dedicated-policy/"
    managed_url = "https://github.blog/changelog/2026-07-27-enterprise-managed-settings-now-apply-to-the-github-copilot-app/"

    entries: list[dict[str, Any]] = []

    entries.append(
        {
            "candidate": candidate(
                sequence=1,
                title_raw="AI正在推动任务跨越岗位边界",
                entities=["OpenAI", "ChatGPT"],
                action="发布工作任务跨界研究",
                event_object="AI使用中的跨职业任务迁移",
                event_date="2026-07-27",
                category="career_skills",
                information_types=["research_report"],
                summary_raw=(
                    "OpenAI对超过80万条美国ChatGPT用户消息的研究显示，"
                    "16.8%的工作相关消息和43.5%的职业特定消息涉及其他职业的任务。"
                ),
                source_ids=["src-openai-work-crossover-20260727"],
                source_urls=[openai_url],
                claims=[
                    {
                        "claim": "研究样本超过80万条美国ChatGPT用户消息",
                        "source_id": "src-openai-work-crossover-20260727",
                        "support_level": "direct",
                        "evidence_text": "OpenAI官方页面明确说明分析对象超过800,000条消息。",
                    },
                    {
                        "claim": "43.5%的职业特定消息涉及用户本职之外的职业任务",
                        "source_id": "src-openai-work-crossover-20260727",
                        "support_level": "direct",
                        "evidence_text": "官方研究将这一现象定义为task crossover，并披露43.5%的比例。",
                    },
                ],
                authority=98,
                freshness=88,
                relevance=96,
                confidence="high",
                risk_flags=["none"],
                registry_id="registry-openai-news",
            ),
            "dedup": dedup("keep_new", "new_theme"),
            "editorial": editorial(
                impact=94,
                novelty=92,
                content_value=98,
                product_value=90,
                evidence_quality=98,
                public_title="AI正在重组岗位边界",
                subtitle="一人公司获得更多跨职能执行能力",
                summary=(
                    "OpenAI的新研究显示，AI不仅提高原岗位效率，还让用户直接承担原本属于其他职业的任务。"
                    "这种任务跨界在小企业中更明显，正在改变团队分工和个人技能组合。"
                ),
                why=[
                    "AI价值从提效扩展到减少跨部门交接",
                    "小企业与一人公司更容易成为跨职能受益者",
                    "岗位变化可能先体现在任务组合而非职位消失",
                ],
                follow=[
                    "不同职业的长期任务迁移是否持续",
                    "跨界工作对质量、责任与薪酬的影响",
                    "一人公司应优先补齐哪些复合技能",
                ],
                conversions=[
                    "wechat_article",
                    "douyin_carousel",
                    "deep_report",
                    "product_prototype",
                ],
                audiences=["general_public", "founders", "creators", "students"],
                selected_reason="官方大样本研究直接支持结论，并与一人公司能力边界高度相关。",
                visual_concept="一个人连接设计、营销、分析、法务与技术五个任务模块的跨职能地图",
                must_not_fabricate=[
                    "不得把任务跨界写成岗位已被替代",
                    "不得虚构中国市场或收入数据",
                ],
            ),
        }
    )

    entries.append(
        {
            "candidate": candidate(
                sequence=2,
                title_raw="GitHub开始拦截潜在恶意Actions工作流",
                entities=["GitHub", "GitHub Actions"],
                action="暂停潜在恶意工作流等待审批",
                event_object="公共仓库CI/CD凭据供应链攻击",
                event_date="2026-07-28",
                category="risk_counter_signal",
                information_types=["github_update", "security_incident"],
                summary_raw=(
                    "GitHub Actions会自动暂停被识别为潜在恶意的公共仓库工作流，"
                    "直到具有写权限的协作者通过已认证网页会话审核。"
                ),
                source_ids=["src-github-actions-workflow-approval-20260728"],
                source_urls=[actions_url],
                claims=[
                    {
                        "claim": "潜在恶意工作流在审批前不会执行",
                        "source_id": "src-github-actions-workflow-approval-20260728",
                        "support_level": "direct",
                        "evidence_text": "GitHub官方说明工作流被hold后，需写权限协作者审核批准才会继续。",
                    },
                    {
                        "claim": "该保护当前适用于github.com公共仓库",
                        "source_id": "src-github-actions-workflow-approval-20260728",
                        "support_level": "direct",
                        "evidence_text": "官方页面明确限定当前覆盖公共仓库，GitHub Enterprise Server暂不包含。",
                    },
                ],
                authority=99,
                freshness=100,
                relevance=94,
                confidence="high",
                risk_flags=["security_sensitive"],
                registry_id="registry-github-changelog",
            ),
            "dedup": dedup("keep_new", "new_theme"),
            "editorial": editorial(
                impact=92,
                novelty=95,
                content_value=94,
                product_value=74,
                evidence_quality=99,
                public_title="GitHub拦截恶意工作流",
                subtitle="AI与自动化时代，CI审批重新成为安全闸门",
                summary=(
                    "近期供应链攻击会利用被盗GitHub凭据写入恶意Actions工作流。"
                    "GitHub现对部分可疑运行先行暂停，要求具有写权限的协作者在网页端确认后再执行。"
                ),
                why=[
                    "CI/CD已成为凭据窃取和横向攻击的重要入口",
                    "自动化越强，执行前审批和最小权限越重要",
                    "公共开源项目需要重新审视Actions写权限",
                ],
                follow=[
                    "检测规则的误报率和覆盖范围",
                    "私有仓库与Enterprise Server是否跟进",
                    "组织能否查看被拦截工作流的审计数据",
                ],
                conversions=["wechat_article", "douyin_carousel", "poster"],
                audiences=["developers", "enterprise_users", "founders"],
                selected_reason="官方安全更新具有明确行为变化和直接供应链风险，时效性高。",
                visual_concept="CI流水线在执行前经过红色风险扫描与人工批准闸门",
                must_not_fabricate=[
                    "不得展示真实攻击代码或凭据",
                    "不得声称所有恶意工作流都能被识别",
                ],
            ),
        }
    )

    entries.append(
        {
            "candidate": candidate(
                sequence=3,
                title_raw="Dependabot扩展恶意软件包告警生态",
                entities=["GitHub", "Dependabot", "OpenSSF"],
                action="接入恶意软件包通告",
                event_object="npm、PyPI等依赖生态的恶意软件告警",
                event_date="2026-07-28",
                category="developer_tools",
                information_types=["github_update", "security_incident"],
                summary_raw=(
                    "GitHub Advisory Database接入OpenSSF malicious-packages项目，"
                    "已启用恶意软件告警的Dependabot用户将自动获得npm、PyPI等更广覆盖。"
                ),
                source_ids=["src-github-dependabot-malware-20260728"],
                source_urls=[dependabot_url],
                claims=[
                    {
                        "claim": "GitHub Advisory Database已接入OpenSSF malicious-packages",
                        "source_id": "src-github-dependabot-malware-20260728",
                        "support_level": "direct",
                        "evidence_text": "GitHub官方Changelog直接说明新的恶意软件通告数据来源。",
                    },
                    {
                        "claim": "现有恶意软件告警用户无需额外配置即可获得扩展覆盖",
                        "source_id": "src-github-dependabot-malware-20260728",
                        "support_level": "direct",
                        "evidence_text": "官方说明已启用malware alerting的用户会自动受益。",
                    },
                ],
                authority=99,
                freshness=100,
                relevance=92,
                confidence="high",
                risk_flags=["security_sensitive"],
                registry_id="registry-github-changelog",
            ),
            "dedup": dedup("keep_new", "new_theme"),
            "editorial": editorial(
                impact=88,
                novelty=91,
                content_value=91,
                product_value=70,
                evidence_quality=99,
                public_title="Dependabot扩大恶意包告警",
                subtitle="软件供应链风险从npm延伸至更多生态",
                summary=(
                    "GitHub把OpenSSF恶意软件包数据接入Advisory Database，"
                    "Dependabot可在更多依赖生态中识别已知恶意版本，现有启用用户无需重新配置。"
                ),
                why=[
                    "恶意依赖已成为AI生成项目的现实风险",
                    "跨生态数据聚合提高供应链发现能力",
                    "自动生成代码仍需依赖清单与告警治理",
                ],
                follow=[
                    "PyPI等生态的覆盖完整度",
                    "私有包同名导致的误报治理",
                    "告警到自动修复之间的安全边界",
                ],
                conversions=["wechat_article", "poster", "deep_report"],
                audiences=["developers", "enterprise_users", "founders"],
                selected_reason="官方更新直接改变依赖安全覆盖，适合AI Coding安全选题。",
                visual_concept="npm与PyPI依赖节点汇入统一恶意软件数据库和Dependabot盾牌",
                must_not_fabricate=[
                    "不得虚构被感染项目数量",
                    "不得声称告警等同于自动清除风险",
                ],
            ),
        }
    )

    entries.append(
        {
            "candidate": candidate(
                sequence=4,
                title_raw="Copilot JetBrains进入可观测与模型治理",
                entities=["GitHub", "GitHub Copilot", "JetBrains"],
                action="增加可观测性与模型控制",
                event_object="Agent工作流、Token上限、MCP与AI Credits",
                event_date="2026-07-27",
                category="developer_tools",
                information_types=["github_update"],
                summary_raw=(
                    "GitHub Copilot for JetBrains新增Agent工作流OpenTelemetry导出、"
                    "自定义端点Token上限、模型开关、Claude流程中的MCP与自定义Agent，以及AI credits显示。"
                ),
                source_ids=["src-github-copilot-jetbrains-governance-20260727"],
                source_urls=[jetbrains_url],
                claims=[
                    {
                        "claim": "JetBrains插件支持Agent工作流OpenTelemetry导出",
                        "source_id": "src-github-copilot-jetbrains-governance-20260727",
                        "support_level": "direct",
                        "evidence_text": "官方更新列出可配置的OpenTelemetry export settings。",
                    },
                    {
                        "claim": "管理员可设置自定义端点Token上限并管理内置模型",
                        "source_id": "src-github-copilot-jetbrains-governance-20260727",
                        "support_level": "direct",
                        "evidence_text": "官方更新列出maxInputToken、maxOutputToken和内置模型开关。",
                    },
                    {
                        "claim": "Claude Agent流程可直接使用MCP服务器和自定义Agent",
                        "source_id": "src-github-copilot-jetbrains-governance-20260727",
                        "support_level": "direct",
                        "evidence_text": "GitHub官方页面将该能力列为本次JetBrains更新。",
                    },
                ],
                authority=99,
                freshness=90,
                relevance=98,
                confidence="high",
                risk_flags=["none"],
                registry_id="registry-github-changelog",
            ),
            "dedup": dedup("keep_new", "new_angle"),
            "editorial": editorial(
                impact=93,
                novelty=88,
                content_value=96,
                product_value=94,
                evidence_quality=99,
                public_title="AI IDE进入治理阶段",
                subtitle="可观测、模型、Token与Agent开始统一管理",
                summary=(
                    "Copilot for JetBrains把OpenTelemetry、Token上限、模型开关、MCP和自定义Agent放进同一开发环境。"
                    "AI Coding竞争正在从补全能力转向可观测、成本和执行治理。"
                ),
                why=[
                    "企业需要知道Agent调用了什么、花了多少",
                    "BYOK与自定义模型必须配套Token边界",
                    "MCP和自定义Agent扩大能力也扩大权限面",
                ],
                follow=[
                    "遥测数据能否区分模型、工具和任务",
                    "AI credits与Token预算如何统一",
                    "MCP权限和命令审批是否可集中审计",
                ],
                conversions=[
                    "wechat_article",
                    "douyin_carousel",
                    "product_prototype",
                    "deep_report",
                ],
                audiences=["developers", "enterprise_users", "founders"],
                selected_reason="官方更新同时覆盖可观测、成本、模型和Agent治理，产品机会清晰。",
                visual_concept="IDE中心连接OpenTelemetry、Token预算、模型路由、MCP与Agent权限面板",
                must_not_fabricate=[
                    "不得仿造真实Copilot界面",
                    "不得虚构企业节省比例或Token价格",
                ],
            ),
        }
    )

    entries.append(
        {
            "candidate": candidate(
                sequence=5,
                title_raw="Copilot企业治理覆盖App与Cloud Agent",
                entities=["GitHub", "GitHub Copilot"],
                action="扩展企业统一治理",
                event_object="Copilot App访问策略与Cloud Agent托管设置",
                event_date="2026-07-27",
                category="business_strategy",
                information_types=["github_update"],
                summary_raw=(
                    "Copilot App获得独立访问策略，同时App与Cloud Agent开始执行企业managed-settings.json，"
                    "可统一约束插件、市场、审批绕过和默认模型。"
                ),
                source_ids=[
                    "src-github-copilot-app-policy-20260727",
                    "src-github-copilot-managed-settings-20260727",
                ],
                source_urls=[app_policy_url, managed_url],
                claims=[
                    {
                        "claim": "Copilot App访问策略已与Copilot CLI分离",
                        "source_id": "src-github-copilot-app-policy-20260727",
                        "support_level": "direct",
                        "evidence_text": "官方页面明确新增独立的企业和组织级Copilot App政策。",
                    },
                    {
                        "claim": "Copilot App与Cloud Agent执行同一套企业managed-settings.json",
                        "source_id": "src-github-copilot-managed-settings-20260727",
                        "support_level": "direct",
                        "evidence_text": "官方页面列出插件、市场、权限绕过和模型选择等统一治理项。",
                    },
                ],
                authority=99,
                freshness=90,
                relevance=96,
                confidence="high",
                risk_flags=["none"],
                registry_id="registry-github-changelog",
            ),
            "dedup": dedup("keep_new", "new_theme"),
            "editorial": editorial(
                impact=91,
                novelty=90,
                content_value=94,
                product_value=91,
                evidence_quality=99,
                public_title="Copilot统一企业治理",
                subtitle="Agent从单一客户端走向全入口策略控制",
                summary=(
                    "GitHub把Copilot App访问权与CLI解耦，并让App和Cloud Agent接受同一套托管设置。"
                    "企业可以统一控制插件、市场、审批绕过和默认模型，Agent治理开始覆盖完整客户端矩阵。"
                ),
                why=[
                    "任何未纳管客户端都会成为权限缺口",
                    "Agent采用率增长推动集中策略和审计需求",
                    "模型选择、插件与命令审批正在合并为治理层",
                ],
                follow=[
                    "策略下发延迟与离线行为",
                    "Cloud Agent执行记录的审计深度",
                    "不同IDE与桌面客户端的策略一致性",
                ],
                conversions=[
                    "wechat_article",
                    "poster",
                    "product_prototype",
                    "deep_report",
                ],
                audiences=["enterprise_users", "developers", "founders"],
                selected_reason="两项官方更新构成同一企业治理主线，合并处理避免重复拆条。",
                visual_concept="企业策略中心向Copilot App、CLI、VS Code、JetBrains与Cloud Agent同步护栏",
                must_not_fabricate=[
                    "不得声称策略已经覆盖所有GitHub产品",
                    "不得虚构客户名单或采用率",
                ],
            ),
        }
    )

    entries.append(
        {
            "candidate": candidate(
                sequence=6,
                title_raw="Copilot App获得独立访问开关",
                entities=["GitHub", "GitHub Copilot"],
                action="新增独立访问策略",
                event_object="Copilot App企业访问控制",
                event_date="2026-07-27",
                category="developer_tools",
                information_types=["github_update"],
                summary_raw="Copilot App可由企业或组织单独启用、禁用或下放管理员决定。",
                source_ids=["src-github-copilot-app-policy-20260727"],
                source_urls=[app_policy_url],
                claims=[
                    {
                        "claim": "Copilot App拥有独立访问策略",
                        "source_id": "src-github-copilot-app-policy-20260727",
                        "support_level": "direct",
                        "evidence_text": "事实成立，但已被候选005的企业治理合并主题完整覆盖。",
                    }
                ],
                authority=99,
                freshness=90,
                relevance=86,
                confidence="high",
                risk_flags=["none"],
                registry_id="registry-github-changelog",
                status="rejected",
                rejection_reason="duplicate_event",
            ),
            "dedup": dedup(
                "reject_duplicate",
                "repeated",
                matched=["candidate-20260729-005"],
            ),
            "editorial": editorial(
                impact=75,
                novelty=20,
                content_value=70,
                product_value=65,
                evidence_quality=99,
                public_title="Copilot App独立开关",
                subtitle="企业可以单独控制桌面Agent入口",
                summary="该事实已被更完整的Copilot全客户端企业治理条目覆盖，单独成条会造成事件与观点重复。",
                why=["独立访问开关提高管理员控制能力"],
                follow=["组织级策略实际采用情况"],
                conversions=["poster"],
                audiences=["enterprise_users", "developers"],
                selected_reason="事实真实但与候选005高度重复，保留在内部淘汰池。",
                visual_concept="单一开关控制Copilot App入口",
                must_not_fabricate=["不得将重复事实包装为新增主线"],
            ),
        }
    )

    entries.append(
        {
            "candidate": candidate(
                sequence=7,
                title_raw="AI已经让专业岗位失去意义",
                entities=["OpenAI", "ChatGPT"],
                action="推测专业岗位失去意义",
                event_object="任务跨界被外推为岗位消失",
                event_date="2026-07-27",
                category="risk_counter_signal",
                information_types=["rumor", "research_report"],
                summary_raw=(
                    "部分传播可能把任务跨界研究解读为专业岗位即将失去意义，"
                    "但原始研究只观察任务组合变化，不能支持岗位消失结论。"
                ),
                source_ids=["src-openai-work-crossover-20260727"],
                source_urls=[openai_url],
                claims=[
                    {
                        "claim": "AI已经让专业岗位失去意义",
                        "source_id": "src-openai-work-crossover-20260727",
                        "support_level": "conflicting",
                        "evidence_text": "原始研究明确讨论任务跨界和岗位重组，并未证明专业岗位已失去意义。",
                    }
                ],
                authority=98,
                freshness=88,
                relevance=82,
                confidence="low",
                risk_flags=["unconfirmed"],
                registry_id="registry-openai-news",
                status="rejected",
                rejection_reason="low_confidence",
            ),
            "dedup": dedup("keep_new", "new_angle"),
            "editorial": editorial(
                impact=80,
                novelty=60,
                content_value=78,
                product_value=30,
                evidence_quality=25,
                public_title="专业岗位正在消失？",
                subtitle="任务跨界不等于职业已经被替代",
                summary="该结论超过原始研究证据边界，应作为内容误判风险，而不是今日新增事实。",
                why=["夸大结论容易制造职业焦虑"],
                follow=["长期就业和岗位描述数据"],
                conversions=["wechat_article"],
                audiences=["general_public", "students"],
                selected_reason="作为过度解读样本进入内部淘汰池和风险提醒。",
                visual_concept="任务迁移与岗位消失之间设置醒目的证据边界",
                must_not_fabricate=["不得把推测写成事实"],
            ),
        }
    )

    return {
        "schema_version": "1.0.0",
        "date": DATE,
        "timezone": "Asia/Shanghai",
        "generated_at": OBSERVED_AT,
        "title": "珩小派多元情报简报｜2026.07.29",
        "market_session": "in_session",
        "entries": entries,
        "content_opportunities": [
            {
                "wechat_title": "AI不是只让你做得更快，而是在让你跨界工作",
                "douyin_title": "一个人开始承担五个岗位的任务",
                "angle": "用OpenAI大样本研究解释任务跨界，重点服务一人公司、自由职业者和小团队。",
                "visual_direction": "一个人连接设计、营销、技术、分析和法务五个任务岛，标注任务迁移而非岗位消失。",
                "related_candidate_ids": ["candidate-20260729-001"],
            },
            {
                "wechat_title": "GitHub为何开始在Actions执行前增加人工闸门？",
                "douyin_title": "恶意工作流还没跑，就被GitHub拦住了",
                "angle": "从凭据窃取和供应链攻击解释自动化审批、最小权限与审计的重要性。",
                "visual_direction": "CI流水线、风险扫描、凭据保险箱和人工批准四段结构。",
                "related_candidate_ids": [
                    "candidate-20260729-002",
                    "candidate-20260729-003",
                ],
            },
            {
                "wechat_title": "AI Coding下一阶段：不是更会写，而是更可控",
                "douyin_title": "Copilot开始管Token、模型、MCP和权限了",
                "angle": "把JetBrains可观测更新与Copilot全客户端治理合并，拆解企业AI Coding控制面。",
                "visual_direction": "IDE与企业策略中心之间连接模型、Token、MCP、插件、审批和遥测模块。",
                "related_candidate_ids": [
                    "candidate-20260729-004",
                    "candidate-20260729-005",
                ],
            },
        ],
        "product_opportunity": {
            "title": "一人公司AI任务边界与Agent治理台",
            "target_users": ["一人公司", "独立开发者", "使用多个AI Coding工具的小团队"],
            "pain_point": "用户难以判断哪些任务适合跨界交给AI，也无法统一查看模型、Token、MCP、权限和执行风险。",
            "mvp": [
                "记录任务原属岗位、当前执行者与使用模型",
                "汇总Token、AI credits、工具调用和耗时",
                "展示MCP、文件、终端和URL访问权限",
                "对高风险命令和跨岗位任务设置人工确认",
                "生成每周任务跨界与成本复盘",
            ],
            "seven_day_feasibility": True,
            "payment_signal": "medium",
            "competition_level": "medium",
            "hxp_advantage": "珩小派同时具备一人公司实践、AI Coding工作流和情报内容沉淀，可先从自用工具验证。",
            "evidence_candidate_ids": [
                "candidate-20260729-001",
                "candidate-20260729-004",
                "candidate-20260729-005",
            ],
            "gates": {
                "clear_users": True,
                "recurring_pain": True,
                "payment_signal": True,
                "seven_day_mvp": True,
                "differentiation": True,
            },
        },
        "risk_reminder": {
            "title": "不要把任务跨界写成岗位已经消失",
            "risk_type": "unconfirmed_claim",
            "description": (
                "OpenAI研究观察到用户借助AI承担其他职业的任务，但这不等于专业岗位已经被替代。"
                "内容应区分任务迁移、岗位重组和就业净变化三个层次。"
            ),
            "safe_wording": [
                "任务边界正在变化",
                "部分用户开始承担其他职业的任务",
                "长期岗位影响仍需持续观察",
            ],
        },
        "weekly_threads": {
            "keywords": [
                "任务跨界",
                "一人公司",
                "AI Coding治理",
                "OpenTelemetry",
                "Token预算",
                "MCP权限",
                "供应链安全",
            ],
            "strongest_trend": "AI能力正在从生成与补全进入跨岗位执行，同时企业把可观测、成本、权限和安全护栏纳入统一治理。",
            "deep_dive_topic": "从任务跨界到Agent治理：一人公司如何扩大能力而不失去控制",
            "productization_opportunity": "面向一人公司和小团队的任务边界、模型成本、工具权限与执行审计控制台",
        },
    }


def main() -> int:
    source_dir = RUN_DIR / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    for record in build_sources():
        write_json(source_dir / f"{record['source_id']}.json", record)
    write_json(RUN_DIR / "candidate-pool.json", build_pool())
    result = run_daily(
        run_dir=RUN_DIR,
        weights_path=ROOT / "config/editorial-weights.json",
        config_path=ROOT / "config/daily-run.json",
        mode="archived_real_sources",
        review_status="pending",
    )
    print(
        f"PASS generated {result['run_id']} with "
        f"{result['selected_counts']['new_items']} selected items"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
