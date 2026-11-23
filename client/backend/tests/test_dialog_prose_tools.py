"""对话框编排生成正文·助手工具测试（c-agent-dialog-prose 批D）。

- kb_search_craft：题材域过滤／剧情重合打分排序／零重合＝未命中回话/concept 校验
- read_write_prompt：服务端组装稿单源（含概要与告警面）
- draft_prose_plan：章校验/prompt 上限/picks 三域解析与无效 id 如实回话/归档拒做
"""

import asyncio
import tempfile
import uuid

from assistant.tools import ToolContext, _read_write_prompt
from assistant.tools_cards import _draft_prose_plan
from assistant.tools_kb import _kb_search_craft
from db import async_session
from kb.service import create_entry
from models.chapter import Chapter
from models.project import Novel
from models.user import User
from models.volume import Volume


def _run(coro):
    return asyncio.run(coro)


async def _seed(genre: str = "都市异能", archived: bool = False):
    """书＋章＋两条手法条目（一条贴「体温计」剧情、一条无关）。返回 (uid, novel_id, ctx, ids)。"""
    uid = f"dp{uuid.uuid4().hex[:8]}"
    root = tempfile.mkdtemp(prefix=f"dp_{uid}_")
    async with async_session() as db:
        db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x", display_name="对话框正文"))
        novel = Novel(
            user_id=uid, name="对话框正文书", slug=uuid.uuid4().hex[:12],
            root_path=root, source="manual", current_phase="write",
        )
        db.add(novel)
        await db.flush()
        vol = Volume(project_id=novel.id, volume_no=1, title="卷")
        db.add(vol)
        await db.flush()
        ch = Chapter(
            project_id=novel.id, volume_id=vol.id, chapter_no=1, ref="vol-1-ch-1",
            title="第七章", summary="林野用体温计试探血族弱点", primary_mood="疑",
            challenge="弄清水银不动意味着什么",
            plot_items='["林野留下新体温计，水银不动"]',
            plot_stage="冲突初现",
            **({"archived_at": __import__("datetime").datetime.utcnow()} if archived else {}),
        )
        db.add(ch)
        id_a = (await create_entry(
            db, user_id=uid, genre=genre, concept="手法",
            title="体温计反转", payload={"instruction": "用体温计反应递减设陷阱，物件推进不新增剧情。", "scene": "日常"},
            instruction="体温计反转：给主角一件暗藏玄机的物件，借反应递减泄底。",
        ))[0].id
        id_b = (await create_entry(
            db, user_id=uid, genre=genre, concept="手法",
            title="今昔对比塑军", payload={"instruction": "今昔对比塑军：两段蒙太奇写军队变化。", "scene": "打斗"},
            instruction="今昔对比塑军：两段蒙太奇写军队变化。",
        ))[0].id
        await db.commit()
        novel_id = novel.id
    # story.yaml 在会话外写（storage 写面走 ProjectSetting KV——嵌套会话撞 SQLite 锁）
    from filesystem.storage import get_storage

    await get_storage().write_yaml(root, "story.yaml", {"genre": genre, "synopsis": "血族试探"})
    ctx = ToolContext(novel_id=novel_id, root_path=root, user_id=uid)
    return uid, novel_id, ctx, [id_a, id_b]


def test_kb_search_craft_按剧情重合排序_题材内():
    _uid, _nid, ctx, ids = _run(_seed())

    async def _go():
        return await _kb_search_craft(ctx, chapter_ref="vol-1-ch-1")

    res = _run(_go())
    assert res.ok
    assert "体温计反转" in res.summary and f"id: {ids[0]}" in res.summary
    # 无关条目（今昔对比塑军）与剧情零重合——不进候选（宁缺毋滥）
    assert "今昔对比塑军" not in res.summary


def test_kb_search_craft_零重合明说未命中():
    _uid, _nid, ctx, _ids = _run(_seed())

    async def _go():
        return await _kb_search_craft(ctx, query="量子纠缠的实验室日常")

    res = _run(_go())
    assert res.ok
    assert "没有与这段剧情相关的条目" in res.summary


def test_kb_search_craft_无题材不硬检():
    _uid, _nid, ctx, _ids = _run(_seed(genre=""))

    async def _go():
        return await _kb_search_craft(ctx, query="体温计")

    res = _run(_go())
    assert res.ok
    assert "还没设定题材" in res.summary


def test_kb_search_craft_concept_校验():
    _uid, _nid, ctx, _ids = _run(_seed())

    async def _go():
        return await _kb_search_craft(ctx, query="体温计", concept="情节")

    res = _run(_go())
    assert not res.ok
    assert "手法" in res.summary


def test_read_write_prompt_组装稿含本章素材():
    _uid, _nid, ctx, _ids = _run(_seed())

    async def _go():
        return await _read_write_prompt(ctx, "vol-1-ch-1")

    res = _run(_go())
    assert res.ok
    assert "体温计" in res.summary  # 概要/剧情条目进组装稿
    assert "服务端组装稿" in res.summary


def test_draft_prose_plan_出卡_条目与提示词全文():
    _uid, _nid, ctx, ids = _run(_seed())

    async def _go():
        return await _draft_prose_plan(
            ctx, "vol-1-ch-1", "【本章剧情走向（分条）】\n- 林野用体温计试探血族弱点",
            picks=[{"entry_id": ids[0], "reason": "章纲已安排物件试探桥段"}],
        )

    res = _run(_go())
    assert res.ok and res.card is not None
    assert res.card["kind"] == "prose_plan"
    payload = res.card["payload"]
    assert payload["chapter_ref"] == "vol-1-ch-1"
    assert payload["chapter_title"] == "第七章"
    assert "体温计" in payload["prompt"]
    assert len(payload["picks"]) == 1
    assert payload["picks"][0]["entry_id"] == ids[0]
    assert payload["picks"][0]["title"] == "体温计反转"
    assert payload["picks"][0]["reason"] == "章纲已安排物件试探桥段"
    assert payload["has_existing_prose"] is False


def test_draft_prose_plan_无效id如实回话_零命中语义():
    _uid, _nid, ctx, ids = _run(_seed())

    async def _go():
        return await _draft_prose_plan(
            ctx, "vol-1-ch-1", "提示词全文", picks=[{"entry_id": "no-such-id"}, {"entry_id": ids[0]}]
        )

    res = _run(_go())
    assert res.ok
    payload = res.card["payload"]
    assert payload["invalid_entry_ids"] == ["no-such-id"]
    assert len(payload["picks"]) == 1
    assert "1 个条目 id 无效" in res.summary


def test_draft_prose_plan_零picks_未命中语义():
    _uid, _nid, ctx, _ids = _run(_seed())

    async def _go():
        return await _draft_prose_plan(ctx, "vol-1-ch-1", "提示词全文", picks=[])

    res = _run(_go())
    assert res.ok
    assert "未命中" in res.summary
    assert res.card["payload"]["picks"] == []


def test_draft_prose_plan_归档拒做():
    _uid, _nid, ctx, _ids = _run(_seed(archived=True))

    async def _go():
        return await _draft_prose_plan(ctx, "vol-1-ch-1", "提示词全文")

    res = _run(_go())
    assert not res.ok
    assert "已归档" in res.summary


def test_draft_prose_plan_缺prompt引导先取组装稿():
    _uid, _nid, ctx, _ids = _run(_seed())

    async def _go():
        return await _draft_prose_plan(ctx, "vol-1-ch-1", "")

    res = _run(_go())
    assert not res.ok
    assert "read_write_prompt" in res.summary


def test_draft_prose_plan_超长prompt拒收():
    _uid, _nid, ctx, _ids = _run(_seed())

    async def _go():
        return await _draft_prose_plan(ctx, "vol-1-ch-1", "字" * 16001)

    res = _run(_go())
    assert not res.ok
    assert "超长" in res.summary


def test_域收口_三工具全登记():
    from assistant.scopes import tools_for_thread, validate_scopes
    from assistant.tools import TOOL_REGISTRY

    names = {t.name for t in TOOL_REGISTRY}
    assert validate_scopes(names) == []
    thread_tools = tools_for_thread("ch:prose")
    assert {"kb_search_craft", "read_write_prompt", "draft_prose_plan"} <= thread_tools
