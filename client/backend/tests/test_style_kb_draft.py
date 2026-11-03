"""按题材从知识库取文风草稿（c-style-kb-fill）。

覆盖：无题材空草稿；文风/文笔全槽位映射；同题材优先＋跨题材通用兜底；
场景条目/别题材/archived 排除；身份 tone/pov/register 兜底；上限；
官方基线（c-kb-baseline）并入、hide 覆盖排除。
"""

import asyncio
import json
import uuid

from fastapi.testclient import TestClient

from auth_local.middleware import get_current_user
from db import async_session
from kb.service import create_entry
from main import app
from models.kb import KbBaselineEntry, KbBaselineOverlay, KbEntry
from models.project import Novel
from models.user import User


def _run(coro):
    return asyncio.run(coro)


async def _seed(theme: str = "悬疑") -> dict:
    uid = f"skb{uuid.uuid4().hex[:8]}"
    slug = f"skb-{uuid.uuid4().hex[:8]}"
    async with async_session() as db:
        db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x", display_name="文风草稿"))
        novel = Novel(
            user_id=uid,
            name="草稿测试书",
            slug=slug,
            root_path=f"./data/{slug}",
            source="manual",
            current_phase="settings",
        )
        db.add(novel)
        await db.commit()
    if theme:
        from filesystem.storage import get_storage

        await get_storage().write_yaml(novel.root_path, "story.yaml", {"genre": theme})
    return {"uid": uid, "novel_id": novel.id, "root": novel.root_path}


def _client(seed: dict) -> TestClient:
    async def _override():
        return {"id": seed["uid"]}

    app.dependency_overrides[get_current_user] = _override
    return TestClient(app)


def _mk(seed: dict, *, genre: str, concept: str, title: str, payload: dict, when=None) -> str:
    async def _go():
        async with async_session() as db:
            instr = (
                payload.get("role")
                or payload.get("rule")
                or payload.get("craft")
                or payload.get("banned")
                or payload.get("tic_pattern")
                or payload.get("sample")
                or payload.get("text")
                or title
            )
            entry, gate, err = await create_entry(
                db,
                user_id=seed["uid"],
                genre=genre,
                concept=concept,
                title=title,
                payload=payload,
                instruction=str(instr),
                when_json=when or {},
            )
            assert entry is not None, (err, gate.errors)
            return entry.id

    return _run(_go())


def _set_status(entry_id: str, status: str) -> None:
    async def _go():
        async with async_session() as db:
            row = await db.get(KbEntry, entry_id)
            row.status = status
            await db.commit()

    _run(_go())


def _get(c: TestClient, seed: dict) -> dict:
    r = c.get(f"/api/novels/{seed['novel_id']}/settings/style/kb-draft")
    assert r.status_code == 200, r.text
    return r.json()


def test_没定题材_返回空草稿():
    seed = _run(_seed(theme=""))
    data = _get(_client(seed), seed)
    assert data["theme"] == ""
    assert data["counts"]["total"] == 0
    assert data["role"] == "" and data["rules"] == [] and data["craft"] == []


def test_全槽位映射_同题材优先_通用兜底():
    seed = _run(_seed("悬疑"))
    _mk(seed, genre="悬疑", concept="文风", title="叙事身份",
        payload={"slot": "role", "role": "贴着主角写的第三人称"})
    _mk(seed, genre="悬疑", concept="文风", title="示范段 1",
        payload={"slot": "sample", "sample": "他把打火机按了三次才点着。"})
    _mk(seed, genre="悬疑", concept="文笔", title="身份硬约束",
        payload={"slot": "rule", "rule": "每章至少留一个没解释的细节"})
    _mk(seed, genre="悬疑", concept="文笔", title="物件代情绪",
        payload={"slot": "craft", "craft": "紧张就写手在做什么"})
    _mk(seed, genre="悬疑", concept="文笔", title="与此同时",
        payload={"slot": "banned_word", "banned": "与此同时"})
    _mk(seed, genre="悬疑", concept="文笔", title="不是而是句式",
        payload={"slot": "tic", "tic_pattern": "不是.{1,10}而是", "tic_severity": "high"})
    # 跨题材通用：身份重复 → 去重后仍用同题材那条；另加一条只存在于通用的规则
    _mk(seed, genre="", concept="文风", title="通用身份",
        payload={"slot": "role", "role": "通用叙事身份"})
    _mk(seed, genre="", concept="文笔", title="通用规则",
        payload={"slot": "rule", "rule": "先讲发生了什么，再烘托情绪"})

    data = _get(_client(seed), seed)
    assert data["theme"] == "悬疑"
    assert data["role"] == "贴着主角写的第三人称"
    assert data["rules"] == ["每章至少留一个没解释的细节", "先讲发生了什么，再烘托情绪"]
    assert data["craft"] == ["紧张就写手在做什么"]
    assert data["banned_words"] == ["与此同时"]
    assert data["style_samples"] == ["他把打火机按了三次才点着。"]
    assert data["tic_patterns"][0]["pattern"] == "不是.{1,10}而是"
    assert data["tic_patterns"][0]["severity"] == "high"
    assert data["counts"]["total"] == 7


def test_场景条目与别题材_archived_都不进来():
    seed = _run(_seed("悬疑"))
    _mk(seed, genre="悬疑", concept="文笔", title="场景规则",
        payload={"slot": "rule", "rule": "打斗句长不超过 12 字"}, when={"scene": "打斗"})
    _mk(seed, genre="都市", concept="文笔", title="别题材规则",
        payload={"slot": "rule", "rule": "别题材的规则"})
    gone = _mk(seed, genre="悬疑", concept="文笔", title="已归档规则",
                payload={"slot": "rule", "rule": "已经归档的规则"})
    _set_status(gone, "archived")
    # 概念不在 文风/文笔 的条目也不进来
    _mk(seed, genre="悬疑", concept="世界设定", title="世界",
        payload={"part": "stage", "content": "末世之后"})

    data = _get(_client(seed), seed)
    assert data["counts"]["total"] == 0
    assert data["rules"] == []


def test_身份兜底_tone_pov_register_拼一句():
    seed = _run(_seed("志怪/民俗灵异"))
    _mk(seed, genre="志怪/民俗灵异", concept="文风", title="基调",
        payload={"slot": "tone", "text": "冷、克制，不解释怪事"})
    _mk(seed, genre="志怪/民俗灵异", concept="文风", title="视角",
        payload={"slot": "pov", "text": "第三人称有限视角"})
    data = _get(_client(seed), seed)
    assert data["role"] == "冷、克制，不解释怪事；第三人称有限视角"
    assert data["counts"]["role"] == 1


def test_硬约束上限_20条():
    seed = _run(_seed("悬疑"))
    for i in range(25):
        _mk(seed, genre="悬疑", concept="文笔", title=f"规则 {i}",
            payload={"slot": "rule", "rule": f"规则第 {i} 条"})
    data = _get(_client(seed), seed)
    assert len(data["rules"]) == 20
    assert data["counts"]["rules"] == 20


def _mk_baseline(
    seed: dict, *, genre: str, concept: str, slot: str, payload: dict, instruction: str = ""
) -> str:
    """直接落一条官方基线（c-kb-baseline lower 层），返回 src_key。"""
    src_key = f"test:{uuid.uuid4().hex}"

    async def _go():
        async with async_session() as db:
            db.add(
                KbBaselineEntry(
                    entry_id=str(uuid.uuid4()),
                    src_key=src_key,
                    pack_version=1,
                    genre=genre,
                    concept=concept,
                    slot=slot,
                    title="官方基线",
                    instruction=instruction or str(payload.get("role") or payload.get("rule") or "官方基线"),
                    when_json="{}",
                    payload_json=json.dumps(payload, ensure_ascii=False),
                    content_sha256="x" * 64,
                )
            )
            await db.commit()

    _run(_go())
    return src_key


def test_官方基线也进草稿():
    # 基线是设备级（不按账号分行）→ 用本文件未用过的题材，避免跨用例串行
    seed = _run(_seed("谍战"))
    _mk_baseline(seed, genre="谍战", concept="文风", slot="role",
                 payload={"slot": "role", "role": "官方基线的叙事身份"})
    _mk_baseline(seed, genre="谍战", concept="文笔", slot="rule",
                 payload={"slot": "rule", "rule": "官方基线的硬约束"})
    data = _get(_client(seed), seed)
    assert data["role"] == "官方基线的叙事身份"
    assert data["rules"] == ["官方基线的硬约束"]


def test_隐藏的官方基线条目不进草稿():
    seed = _run(_seed("军事"))
    secret = f"被藏起来的身份{uuid.uuid4().hex[:6]}"
    src_key = _mk_baseline(seed, genre="军事", concept="文风", slot="role",
                           payload={"slot": "role", "role": secret})

    async def _hide():
        async with async_session() as db:
            db.add(
                KbBaselineOverlay(
                    user_id=seed["uid"], src_key=src_key, action="hide", content=""
                )
            )
            await db.commit()

    _run(_hide())
    data = _get(_client(seed), seed)
    assert secret not in data["role"]


def test_官方基线被作者编辑过_用编辑后的文本():
    """merged 语义：编辑副本只在 instruction，草稿 SHALL 以它为准（不回退原件）。"""
    seed = _run(_seed("美食"))
    src_key = _mk_baseline(seed, genre="美食", concept="文风", slot="role",
                           payload={"slot": "role", "role": "原件身份"})

    async def _edit():
        async with async_session() as db:
            db.add(
                KbBaselineOverlay(
                    user_id=seed["uid"],
                    src_key=src_key,
                    action="edit",
                    content="作者改过的身份",
                    base_content_sha256="",
                )
            )
            await db.commit()

    _run(_edit())
    data = _get(_client(seed), seed)
    assert data["role"] == "作者改过的身份"


def test_基线payload缺文本时用instruction兜底():
    """不同包形状（如 payload 用 value）：槽位有落点就走 instruction，不静默丢条目。"""
    seed = _run(_seed("体育"))
    _mk_baseline(seed, genre="体育", concept="文风", slot="role",
                 payload={"slot": "role", "value": "值形态的身份"},
                 instruction="值形态的身份")
    data = _get(_client(seed), seed)
    assert data["role"] == "值形态的身份"


def test_身份兜底拼接按500字截断():
    """tone/pov/register 拼句可能超长；草稿先截到落库上限，避免保存时静默丢字。"""
    seed = _run(_seed("无限流"))
    for slot, ch in (("tone", "甲"), ("pov", "乙"), ("register", "丙")):
        _mk(seed, genre="无限流", concept="文风", title=slot,
            payload={"slot": slot, "text": ch * 200})
    data = _get(_client(seed), seed)
    assert len(data["role"]) == 500


def test_覆盖编辑不改写禁用词与句式正则():
    """instruction 覆盖只对正文型落点生效；禁用词/正则保留结构化值，不被散文顶替。"""
    seed = _run(_seed("架空古王朝"))
    src_key = _mk_baseline(seed, genre="架空古王朝", concept="文笔", slot="tic",
                           payload={"slot": "tic", "tic_pattern": "不是.{1,10}而是",
                                    "tic_severity": "high"},
                           instruction="别老写不是而是")

    async def _edit():
        async with async_session() as db:
            db.add(
                KbBaselineOverlay(
                    user_id=seed["uid"], src_key=src_key, action="edit",
                    content="作者改过的说明文字",
                )
            )
            await db.commit()

    _run(_edit())
    data = _get(_client(seed), seed)
    assert [t["pattern"] for t in data["tic_patterns"]] == ["不是.{1,10}而是"]


def test_同题材基线优先于跨题材通用_即使它走instruction兜底():
    """兜底补成员不得打乱题材优先序：role 取同题材那条，不跨组被通用条目抢位。"""
    seed = _run(_seed("校园长篇"))
    _mk(seed, genre="", concept="文风", title="通用身份",
        payload={"slot": "role", "role": "跨题材通用身份"})
    _mk_baseline(seed, genre="校园长篇", concept="文风", slot="role",
                 payload={"slot": "role", "value": "同题材值身份"},
                 instruction="同题材值身份")
    data = _get(_client(seed), seed)
    assert data["role"] == "同题材值身份"
