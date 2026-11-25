"""产卡摘要（c-card-digest）：摘要＝卡内容的人话提炼，单卡 1500 封顶。

回归锚点（2026-11-25 真机，设定·简介页）：简介三条候选里模型只看到
「第一条全文＋第二条开头」，对作家说「第二个被截断了」；另有八个工具
只回一句「已出卡」，卡里写了什么模型完全不知道。
"""

import pytest

# 注册表入口必须先加载：tools ↔ tools_settings 是既有循环导入，
# 直接 import tools_settings 会撞半初始化模块（生产链路本来就是先导 tools）。
import assistant.tools  # noqa: F401,E402
from assistant.card_digest import (  # noqa: E402
    CARD_DIGEST_BUDGET,
    digest_candidates,
    digest_report,
    digest_text,
    flatten_fields,
)

# ── helper 本体 ─────────────────────────────────────────────────────────


def test_candidates_full_text_with_count_and_tail():
    items = [
        {"label": "候选一", "synopsis": "第一条正文，钩子在这里。"},
        {"label": "候选二", "synopsis": "第二条正文，收束在这里。"},
        {"label": "候选三", "synopsis": "第三条正文，结尾在这里。"},
    ]
    out = digest_candidates(
        "简介候选已出", items, lambda c: f"{c['label']}：{c['synopsis']}"
    )
    assert "（共 3 条）" in out
    assert "1. 候选一：第一条正文，钩子在这里。" in out
    assert "3. 候选三：第三条正文，结尾在这里。" in out
    assert "还没写进书里" in out
    assert "不用重跑" in out
    assert "{'candidates'" not in out


def test_candidates_over_budget_marks_remaining():
    items = [f"第{i}条" + "正" * 400 for i in range(1, 6)]
    out = digest_candidates("简介候选已出", items, lambda x: x)
    assert len(out) <= CARD_DIGEST_BUDGET + 10
    assert "条在卡上看" in out or "本条续在卡上" in out
    assert "{'" not in out


def test_report_lists_problems_and_counts_ok():
    items = [
        {"name": "世界观", "status": "ok"},
        {"name": "简介", "status": "miss", "note": "缺钩子"},
        {"name": "题材", "status": "warn", "note": "偏窄"},
        {"name": "角色", "status": "ok"},
    ]
    out = digest_report(
        "体检完成",
        items,
        status_of=lambda x: x["status"],
        render=lambda x: f"{x['name']}：{x.get('note', '')}",
    )
    assert "问题 2 条，正常 2 条" in out
    assert "1. 简介：缺钩子" in out
    assert "2. 题材：偏窄" in out
    assert "世界观" not in out  # 达标条目不逐条占字数
    assert out.endswith("）")


def test_report_no_problems():
    out = digest_report(
        "体检完成",
        [{"status": "ok"}, {"status": "ok"}],
        status_of=lambda x: x["status"],
        render=lambda x: "x",
    )
    assert "问题 0 条，正常 2 条" in out
    assert "没有发现要处理的问题。" in out


def test_text_long_is_clipped_with_pointer():
    out = digest_text("世界观候选已出", "字" * 5000)
    assert len(out) <= CARD_DIGEST_BUDGET + 20
    assert "全文在卡上" in out
    assert out.endswith(("…", "）"))


def test_flatten_fields_never_dumps_dict():
    out = flatten_fields(
        {"fullstory": "走向", "ending": {"scene": "画面", "hero": "", "tone": "基调"}}
    )
    assert "fullstory：走向" in out
    assert "scene：画面" in out
    assert "hero" not in out  # 空值不占行
    assert "{" not in out


# ── 病 A：简介/题材/伏笔的摘要 ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_settings_intro_draft_summary_has_all_three(monkeypatch):
    from assistant import tools_settings

    async def _ok(ctx):
        return True

    async def fake_intro(novel_id, action, user_id, body=None):
        return {
            "candidates": [
                {"label": "铁匠", "synopsis": "第一条正文，结尾甲。"},
                {"label": "仓管", "synopsis": "第二条正文，结尾乙。"},
                {"label": "守关BOSS", "synopsis": "第三条正文，结尾丙。"},
            ],
            "act": "replace",
        }

    monkeypatch.setattr(tools_settings, "_project_ok", _ok)
    monkeypatch.setattr("assistant.caps.settings.intro_ai_action", fake_intro)
    ctx = tools_settings.ToolContext(novel_id="n", root_path="", user_id="u")
    res = await tools_settings._settings_intro(ctx, "draft")

    assert res.ok is True
    assert "（共 3 条）" in res.summary
    for label in ("铁匠", "仓管", "守关BOSS"):
        assert label in res.summary
    # 回归：旧实现里第三条一个字都进不了摘要
    assert "第三条正文，结尾丙。" in res.summary
    assert "{'candidates'" not in res.summary
    assert res.card["payload"]["result"]["candidates"][2]["label"] == "守关BOSS"


@pytest.mark.asyncio
async def test_settings_intro_check_lists_gaps_and_taboo(monkeypatch):
    from assistant import tools_settings

    async def _ok(ctx):
        return True

    async def fake_intro(novel_id, action, user_id, body=None):
        return {
            "six_segments": [
                {"name": "钩子", "status": "missing", "note": "没有悬念", "excerpt": ""},
                {"name": "主角", "status": "ok", "note": "", "excerpt": "陆沉"},
            ],
            "taboo": {"hits": [{"rule": "开篇说教", "excerpts": ["第一段"]}]},
            "verdict": "weak",
        }

    monkeypatch.setattr(tools_settings, "_project_ok", _ok)
    monkeypatch.setattr("assistant.caps.settings.intro_ai_action", fake_intro)
    ctx = tools_settings.ToolContext(novel_id="n", root_path="", user_id="u")
    res = await tools_settings._settings_intro(ctx, "check")

    assert "判定：偏弱" in res.summary
    assert "问题 2 条，正常 1 条" in res.summary
    assert "钩子：没有悬念" in res.summary
    assert "触线·开篇说教" in res.summary
    assert "主角" not in res.summary  # 达标段只计数


@pytest.mark.asyncio
async def test_settings_field_genre_points_are_listed(monkeypatch):
    from assistant import tools_settings

    async def _ok(ctx):
        return True

    async def fake_field(novel_id, user_id, stype, field, context=None):
        return {
            "value": [
                {"value": "看点A", "note": "说明A"},
                {"value": "看点B", "note": "说明B"},
            ]
        }

    monkeypatch.setattr(tools_settings, "_project_ok", _ok)
    monkeypatch.setattr("assistant.caps.settings.generate_settings_field", fake_field)
    ctx = tools_settings.ToolContext(novel_id="n", root_path="", user_id="u")
    res = await tools_settings._settings_field(ctx, "genre", "core_promise", "主要看什么")

    assert "1. 看点A（说明A）" in res.summary
    assert "2. 看点B（说明B）" in res.summary
    assert "{'value'" not in res.summary


@pytest.mark.asyncio
async def test_settings_field_forbidden_maps_tag_to_label(monkeypatch):
    from assistant import tools_settings

    async def _ok(ctx):
        return True

    async def fake_field(novel_id, user_id, stype, field, context=None):
        return {"value": [{"tagId": "forbidden:no-deus-ex-machina"}]}

    monkeypatch.setattr(tools_settings, "_project_ok", _ok)
    monkeypatch.setattr("assistant.caps.settings.generate_settings_field", fake_field)
    ctx = tools_settings.ToolContext(novel_id="n", root_path="", user_id="u")
    res = await tools_settings._settings_field(ctx, "genre", "forbidden_list", "绝对禁止")

    assert "禁天降外援" in res.summary  # tagId → 中文标签，不是 slug
    assert "no-deus-ex-machina" not in res.summary


@pytest.mark.asyncio
async def test_hooks_draft_and_check_summaries(monkeypatch):
    from assistant import tools_settings

    async def _ok(ctx):
        return True

    async def fake_hooks(novel_id, action, user_id, body=None):
        if action == "check":
            return {
                "checks": [
                    {"code": "F-001", "status": "warn", "note": "到期未收"},
                    {"code": "F-002", "status": "ok", "note": ""},
                ]
            }
        return {
            "candidates": [
                {"description": "铁匠锤子的裂痕", "type": "mystery", "priority": 1},
                {"description": "仓库里的乱码卷", "type": "clue", "priority": 2},
            ]
        }

    monkeypatch.setattr(tools_settings, "_project_ok", _ok)
    monkeypatch.setattr("assistant.caps.settings.hooks_ai_action", fake_hooks)
    ctx = tools_settings.ToolContext(novel_id="n", root_path="", user_id="u")

    draft = await tools_settings._make_hooks_tool("draft", "起草").fn(ctx)
    assert "[悬念·高] 铁匠锤子的裂痕" in draft.summary
    assert "[线索·中] 仓库里的乱码卷" in draft.summary
    assert "（共 2 条）" in draft.summary

    check = await tools_settings._make_hooks_tool("check", "体检").fn(ctx)
    assert "问题 1 条，正常 1 条" in check.summary
    assert "F-001：到期未收" in check.summary
    assert "F-002" not in check.summary


# ── 病 B：原本零内容的八个工具 ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_worldbuilding_draft_puts_text_in_summary(monkeypatch):
    from assistant.tools import ToolContext, _draft_worldbuilding

    async def fake_draft(novel_id, user_id, body):
        return {"value": "力量来自契约，代价是记忆。", "topic": body["topic"]}

    monkeypatch.setattr("assistant.caps.world.draft_world_cap", fake_draft)
    res = await _draft_worldbuilding(
        ToolContext(novel_id="n", root_path="", user_id="u"), topic="力量体系"
    )
    assert "力量体系" in res.summary
    assert "力量来自契约，代价是记忆。" in res.summary
    assert "还没写进书里" in res.summary


def test_world_check_digest_lists_problems():
    from assistant.tools import _world_check_digest

    out = _world_check_digest(
        {
            "items": [
                {"name": "力量体系", "status": "warn", "note": "与铁律冲突"},
                {"name": "势力", "status": "ok", "note": ""},
            ],
            "verdict": "有 1 处冲突",
        }
    )
    assert "世界观体检完成（有 1 处冲突）" in out
    assert "力量体系：与铁律冲突" in out
    assert "问题 1 条，正常 1 条" in out


@pytest.mark.asyncio
async def test_arc_draft_summary_has_fullstory_and_ending(monkeypatch):
    from assistant.tools import ToolContext
    from assistant.tools_cards import _draft_arc

    async def fake_arc(novel_id, action, user_id, input_text="", constraints=""):
        return {
            "value": {
                "fullstory": "陆沉从矿工做到术士。",
                "ending": {"scene": "关门那一刻", "hero": "成了守门人", "tone": "冷"},
            }
        }

    monkeypatch.setattr("assistant.caps.settings.arc_ai_action", fake_arc)
    res = await _draft_arc(
        ToolContext(novel_id="n", root_path="", user_id="u"), action="draft"
    )
    assert "全书走向：陆沉从矿工做到术士。" in res.summary
    assert "结局画面：关门那一刻" in res.summary
    assert "主角终态：成了守门人" in res.summary
    assert "还没写进书里" in res.summary


@pytest.mark.asyncio
async def test_arc_check_summary_lists_problems(monkeypatch):
    from assistant.tools import ToolContext
    from assistant.tools_cards import _draft_arc

    async def fake_arc(novel_id, action, user_id, input_text="", constraints=""):
        return {
            "value": {
                "checks": [
                    {"name": "开头接结局", "status": "warn", "note": "方向反了"},
                    {"name": "故事连贯", "status": "ok", "note": ""},
                ]
            }
        }

    monkeypatch.setattr("assistant.caps.settings.arc_ai_action", fake_arc)
    res = await _draft_arc(
        ToolContext(novel_id="n", root_path="", user_id="u"), action="check"
    )
    assert "问题 1 条，正常 1 条" in res.summary
    assert "开头接结局：方向反了" in res.summary


def test_volume_check_digest_keeps_group_name_and_evidence():
    from assistant.tools_cards import _volume_check_digest

    out = _volume_check_digest(
        "vol-2",
        {
            "report": [
                {
                    "name": "人物一致性",
                    "items": [
                        {"status": "warn", "text": "配角动机断层", "evidence": "ch-7"},
                        {"status": "ok", "text": "主角动机连贯"},
                    ],
                }
            ]
        },
    )
    assert "「vol-2」体检完成" in out
    assert "人物一致性·配角动机断层（依据：ch-7）" in out
    assert "问题 1 条，正常 1 条" in out


@pytest.mark.asyncio
async def test_draft_names_lists_candidates(monkeypatch):
    from assistant import tools_cards

    async def fake_project_client(ctx):
        return object(), object()

    async def fake_ai_json(client, system, user_text, *, max_tokens=2048):
        return {
            "candidates": [
                {"name": "格罗姆", "rationale": "铁匠味"},
                {"name": "卡奥斯", "rationale": "守关味"},
            ]
        }

    monkeypatch.setattr(tools_cards, "_project_and_client", fake_project_client)
    monkeypatch.setattr(tools_cards, "_ai_json", fake_ai_json)
    res = await tools_cards._draft_names(
        tools_cards.ToolContext(novel_id="n", root_path="", user_id="u"), kind="主角"
    )
    assert "格罗姆——铁匠味" in res.summary
    assert "卡奥斯——守关味" in res.summary


@pytest.mark.asyncio
async def test_diverge_tools_put_content_in_summary(monkeypatch):
    from assistant import tools_cards

    async def fake_project_client(ctx):
        return object(), object()

    async def fake_chars(client, system, user_text, *, max_tokens=2048):
        return {
            "characters": [
                {
                    "name": "莉娅",
                    "role": "配角",
                    "persona": "仓库管理员",
                    "origin_note": "主线缺一个内鬼",
                }
            ]
        }

    async def fake_branches(client, system, user_text, *, max_tokens=2048):
        return {
            "branches": [
                {"title": "查内鬼", "line": "会长开始排查", "origin_note": "冲突升级"}
            ]
        }

    monkeypatch.setattr(tools_cards, "_project_and_client", fake_project_client)
    ctx = tools_cards.ToolContext(novel_id="n", root_path="", user_id="u")

    monkeypatch.setattr(tools_cards, "_ai_json", fake_chars)
    chars = await tools_cards._diverge_character_group(ctx, premise="公会仓库出事")
    assert "莉娅（配角）：仓库管理员" in chars.summary
    assert "锚点：主线缺一个内鬼" in chars.summary

    monkeypatch.setattr(tools_cards, "_ai_json", fake_branches)
    branches = await tools_cards._diverge_plot_branches(ctx, current_direction="仓库出事")
    assert "查内鬼：会长开始排查" in branches.summary
    assert "锚点：冲突升级" in branches.summary


# ── 读取预算 / 工具步折叠行 ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_read_settings_intro_keeps_1500_chars(monkeypatch):
    """预算 800→2000：1500 字简介不再被截半。"""
    import filesystem.storage as _st
    from assistant.tools import ToolContext, run_tool

    long_synopsis = "字" * 1500

    class _Storage:
        async def read_yaml(self, root, path):
            return {"synopsis": long_synopsis} if path == "story.yaml" else {}

    monkeypatch.setattr(_st, "get_storage", lambda: _Storage())
    res = await run_tool(
        ToolContext(novel_id="n", root_path="/r", user_id="u"),
        "read_settings",
        {"area": "intro"},
    )
    assert res.summary == long_synopsis


@pytest.mark.asyncio
async def test_read_settings_world_empty_shell_returns_placeholder(monkeypatch):
    """世界 yaml 存在但八格全空：不能回空串（真机工具行空白）。"""
    import filesystem.storage as _st
    import volumes.ai_plan as _vp
    from assistant.tools import ToolContext, run_tool

    class _Storage:
        async def read_yaml(self, root, path):
            return {"name": ""} if path.endswith("world-setting.yaml") else {}

    monkeypatch.setattr(_st, "get_storage", lambda: _Storage())
    monkeypatch.setattr(_vp, "render_red_lines", lambda raw: [])
    monkeypatch.setattr(_vp, "world_summary_text", lambda raw: "")
    res = await run_tool(
        ToolContext(novel_id="n", root_path="/r", user_id="u"),
        "read_settings",
        {"area": "world"},
    )
    assert res.summary == "（世界设定还没有内容）"


def test_step_note_takes_first_line_and_marks_clip():
    from assistant.loop import _step_note

    summary = "简介候选已出（共 3 条）：\n1. 候选一：正文\n2. 候选二：正文"
    # 首行标题＋首个条目作区分位（回放去重不会把两次不同产出并成一步）
    assert _step_note(summary) == "简介候选已出（共 3 条）：1. 候选一：正文"

    # 单行摘要行为不变
    assert _step_note("（世界设定还没有内容）") == "（世界设定还没有内容）"

    long_item = "候选" + "字" * 400
    note = _step_note(f"简介候选已出（共 3 条）：\n{long_item}")
    # 首条目只带 60 字作区分位，不把整段正文塞回折叠行
    assert len(note) <= 80
    assert note.endswith("…")

    # 单行超长摘要仍按 220 上限裁并加省略号
    long_line = "候选" + "字" * 400
    clipped = _step_note(long_line)
    assert len(clipped) == 220
    assert clipped.endswith("…")


def test_as_check_items_humanizes_name_note():
    """世界体检出参 {name,status,note} 不再以 str(dict) 画到报告卡上。"""
    from assistant.tools import _as_check_items

    out = _as_check_items(
        [
            {"name": "力量体系", "status": "warn", "note": "与铁律冲突"},
            {"name": "势力", "status": "ok", "note": ""},
        ]
    )
    assert out[0] == {"status": "warn", "text": "力量体系：与铁律冲突"}
    assert out[1] == {"status": "ok", "text": "势力"}
    assert all("{" not in it["text"] for it in out)


def test_step_note_distinguishes_two_generations():
    """同工具同标题、不同产出 → 折叠行必须不同（否则回放合并成「同样步骤 ×2」）。"""
    from assistant.loop import _step_note

    a = "简介候选已出（共 3 条）：\n1. 铁匠：第一个方案"
    b = "简介候选已出（共 3 条）：\n1. 仓管：第二个方案"
    assert _step_note(a) != _step_note(b)


# ── lore_suggest：章引用 / 卡面字段 ─────────────────────────────────────


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.mark.asyncio
async def test_lore_suggest_passes_chapter_ref_and_keeps_fields(monkeypatch):
    import assistant.caps.world as _world
    from assistant.tools import ToolContext, _lore_suggest

    seen: dict = {}

    async def fake_lore(novel_id, user_id, body):
        seen.update(body)
        return {
            "suggestions": [
                {
                    "key": "力量体系",
                    "value": "契约换记忆",
                    "set": "extra",
                    "origin": "vol-2-ch-1",
                }
            ],
            "chapter_ref": "vol-2-ch-1",
        }

    monkeypatch.setattr(_world, "lore_suggest_cap", fake_lore)
    res = await _lore_suggest(
        ToolContext(novel_id="n", root_path="", user_id="u"), chapter_ref="vol-2-ch-1"
    )

    assert seen == {"chapter_ref": "vol-2-ch-1"}
    assert res.ok is True
    cand = res.card["payload"]["candidates"][0]
    # pick 渲染用的两个键
    assert cand["name"] == "extra·力量体系"
    assert cand["rationale"] == "契约换记忆"
    # 写回 lore-apply 认的四个键不许丢
    assert (cand["key"], cand["value"], cand["set"], cand["origin"]) == (
        "力量体系",
        "契约换记忆",
        "extra",
        "vol-2-ch-1",
    )
    assert "extra·力量体系：契约换记忆" in res.summary
    assert "（共 1 条）" in res.summary


@pytest.mark.asyncio
async def test_lore_suggest_defaults_to_frontier_chapter(monkeypatch):
    import assistant.caps.world as _world
    import db as _db
    from assistant.tools import ToolContext, _lore_suggest

    seen: dict = {}

    async def fake_lore(novel_id, user_id, body):
        seen.update(body)
        return {"suggestions": [{"key": "势力", "value": "公会", "set": "factions"}]}

    async def fake_frontier(db, novel_id):
        return {"frontier": {"ref": "vol-3-ch-2"}}

    monkeypatch.setattr(_world, "lore_suggest_cap", fake_lore)
    monkeypatch.setattr(_db, "async_session", lambda: _FakeSession())
    monkeypatch.setattr("chapters.frontier.frontier_info", fake_frontier)

    await _lore_suggest(ToolContext(novel_id="n", root_path="", user_id="u"))
    assert seen == {"chapter_ref": "vol-3-ch-2"}


@pytest.mark.asyncio
async def test_lore_suggest_no_chapter_returns_human_message(monkeypatch):
    import db as _db
    from assistant.tools import ToolContext, _lore_suggest

    async def fake_frontier(db, novel_id):
        return {"frontier": {}}

    monkeypatch.setattr(_db, "async_session", lambda: _FakeSession())
    monkeypatch.setattr("chapters.frontier.frontier_info", fake_frontier)

    res = await _lore_suggest(ToolContext(novel_id="n", root_path="", user_id="u"))
    assert res.ok is False
    assert "先去正文页写一章" in res.summary
    assert res.card is None


@pytest.mark.asyncio
async def test_lore_suggest_empty_result_is_not_a_failure(monkeypatch):
    import assistant.caps.world as _world
    from assistant.tools import ToolContext, _lore_suggest

    async def fake_lore(novel_id, user_id, body):
        return {"suggestions": []}

    monkeypatch.setattr(_world, "lore_suggest_cap", fake_lore)
    res = await _lore_suggest(
        ToolContext(novel_id="n", root_path="", user_id="u"), chapter_ref="vol-1-ch-1"
    )
    assert res.ok is True
    assert "没提出新的世界要素" in res.summary
    assert res.card["payload"]["candidates"] == []


@pytest.mark.asyncio
async def test_lore_suggest_empty_chapter_guides_writer(monkeypatch):
    """空章是常见入口：把接口原话换成可执行的下一步。"""
    from fastapi import HTTPException

    import assistant.caps.world as _world
    from assistant.tools import ToolContext, _lore_suggest

    async def fake_lore(novel_id, user_id, body):
        raise HTTPException(400, "章节正文为空，无法提取世界要素")

    monkeypatch.setattr(_world, "lore_suggest_cap", fake_lore)
    res = await _lore_suggest(
        ToolContext(novel_id="n", root_path="", user_id="u"), chapter_ref="vol-1-ch-2"
    )
    assert res.ok is False
    assert "先写一章正文" in res.summary
    assert "vol-1-ch-2" in res.summary
