"""写法块批C测试（c-kb-write-block）：量化影子转写/冲突率=0/反馈端点/运行清单。"""

import asyncio
import json
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select as sel

from auth_local.middleware import get_current_user
from db import async_session
from kb.service import create_entry
from main import app
from models.chapter import Chapter
from models.kb import KbBookBinding, KbLibrary
from models.project import Novel
from models.user import User
from models.volume import Volume
from write.write_block import prepare_write_block


def _run(coro):
    return asyncio.run(coro)


async def _seed_book():
    uid = f"wc{uuid.uuid4().hex[:8]}"
    async with async_session() as db:
        db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x", display_name="批C"))
        novel = Novel(
            user_id=uid, name="批C书", slug=uuid.uuid4().hex[:12],
            root_path=f"./data/{uuid.uuid4().hex[:12]}", source="manual", current_phase="write",
        )
        db.add(novel)
        await db.flush()
        vol = Volume(project_id=novel.id, volume_no=1, title="卷")
        db.add(vol)
        await db.flush()
        db.add(Chapter(
            project_id=novel.id, volume_id=vol.id, chapter_no=1, ref="vol-1-ch-1",
            title="第一章", summary="与老祖正面交锋，硬撼对方底牌", primary_mood="燃",
            plot_stage="高潮爆发",
        ))
        q_entry, _g, e1 = await create_entry(
            db, user_id=uid, genre="", concept="文笔",
            title="打斗句长", payload={"slot": "rule", "rule": "交手时句长不超过12字"},
            instruction="交手时句长不超过12字", when_json={"scene": "打斗"},
        )
        assert q_entry is not None, str(e1)
        s_entry, _g, e2 = await create_entry(
            db, user_id=uid, genre="", concept="手法",
            title="借力打力", payload={"instruction": "借力打力，先让后攻。", "scene": "打斗"},
            instruction="借力打力，先让后攻。",
        )
        assert s_entry is not None, str(e2)
        # create_entry 已自动建手法/文笔 auto 库（批3 修复后 enabled=True）——查回并绑定
        libs = (await db.execute(
            sel(KbLibrary).where(KbLibrary.user_id == uid)
        )).scalars().all()
        for lib in libs:
            db.add(KbBookBinding(novel_id=novel.id, library_id=lib.id, enabled=True))
        await db.commit()
        return uid, novel.id, q_entry.id, s_entry.id


async def _write_quant_baseline(novel_id: str):
    """蒸馏书级量化基线（syntax 行）——影子覆盖的前提。"""
    from filesystem.paths import STYLE_QUANT_PATH
    from filesystem.storage import get_storage

    async with async_session() as db:
        novel = (await db.execute(sel(Novel).where(Novel.id == novel_id))).scalar_one()
        await get_storage().write_yaml(
            novel.root_path, STYLE_QUANT_PATH,
            {"confidence": 80, "baseline": {"syntax": {"value": "约18字", "tolerance": 20}}},
        )


async def _prepare(novel_id: str, uid: str):
    async with async_session() as db:
        return await prepare_write_block(
            db, novel_id=novel_id, chapter_ref="vol-1-ch-1", user_id=uid
        )


async def _chapter_shadow(novel_id: str) -> dict:
    async with async_session() as db:
        ch = (await db.execute(
            sel(Chapter).where(Chapter.project_id == novel_id)
        )).scalars().first()
        return json.loads(ch.style_shadow or "{}")


def test_量化转影子_冲突率零():
    uid, novel_id, qid, _sid = _run(_seed_book())
    _run(_write_quant_baseline(novel_id))
    block, _run_id, items = _run(_prepare(novel_id, uid))
    assert block is not None
    # 冲突率=0：量化条目不出现在块内（写法块只留定性手法）
    assert "句长不超过12字" not in block
    assert any("借力打力" in i["text"] for i in items)
    assert all(i["entry_id"] != qid for i in items)

    # 量化值落当章影子（既有 shadow_override_lines 渲染「本章覆盖」）
    rows = _run(_chapter_shadow(novel_id)).get("rows", {})
    assert "syntax" in rows and "知识库·" in rows["syntax"]["reason"]
    assert "12字" in rows["syntax"]["value"]

    # 幂等：再跑一次影子行不堆叠（同 dim 覆盖更新）
    _run(_prepare(novel_id, uid))
    assert _run(_chapter_shadow(novel_id)).get("rows", {}) == rows


def test_无基线_量化条目回退进块():
    uid, novel_id, qid, _sid = _run(_seed_book())
    # 书未蒸馏量化基线（root_path 无 style-quant.yaml）→ 量化条目回退进块
    block, _run_id, items = _run(_prepare(novel_id, uid))
    assert block is not None
    assert any(i["entry_id"] == qid for i in items)  # 无基线＝无双写冲突源 → 进块


def test_反馈端点与运行清单():
    uid, novel_id, _qid, sid = _run(_seed_book())

    async def _override():
        return {"id": uid}

    app.dependency_overrides[get_current_user] = _override
    try:
        with TestClient(app) as c:
            # 先触发一次选择（落 run）
            assert _run(_prepare(novel_id, uid))[0] is not None

            r = c.post(f"/api/kb/entries/{sid}/pref", json={"useful": False})
            assert r.status_code == 200, r.text
            data = r.json()["data"]
            assert data["drop_count"] == 1 and data["adopt_count"] == 0

            r2 = c.post(f"/api/kb/entries/{sid}/pref", json={"useful": True})
            assert r2.json()["data"]["adopt_count"] == 1

            runs = c.get(
                f"/api/kb/match-runs?novel_id={novel_id}&chapter_ref=vol-1-ch-1"
            ).json()["data"]["runs"]
            assert len(runs) == 1
            assert runs[0]["items"], "清单应有条目"

            r404 = c.post("/api/kb/entries/no-such/pref", json={"useful": True})
            assert r404.status_code == 404
    finally:
        app.dependency_overrides.clear()
