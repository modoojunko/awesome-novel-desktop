"""朱雀检测后端行为测试（c-zhuque-ai-detect）。

矩阵：
- 隔离（P0）：仅配朱雀时生成判「未配置大模型」（user_has_ai_key False、
  get_ai_client_for_user None）；列表/批量状态不返回朱雀行；绑定直取拒绝
- 配置：单槽 upsert（新建/更新/软删复活）、撞名 409、空串保 Key、删除
- 切分 golden：NBSP/CRLF 归一、空白行剔除、指纹稳定（前后端同管道）
- check_chapter：成功映射、分段错配 502、空正文/超上限/未配置/在途 409
- 端点：200 形状、401/429 映射、免费档 403、记账（model=zhuque、汇总排除）
"""

import asyncio
import os
import tempfile

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select

from ai_client import get_ai_client_for_user
from ai_state import user_has_ai_key
from api_configs.service import get_batch_status, get_usage_summary, get_user_api_configs
from auth_local.deps import require_ai_access as _raa
from auth_local.middleware import get_current_user
from db import async_session
from main import app
from models.api_config import ApiConfig
from models.project import Novel
from models.user import User
from models.volume import Volume
from models.chapter import Chapter, ChapterContent
from zhuque import service as zq_service
from zhuque.segmentation import align_segments, canonical_text, fingerprint, split_paragraphs

REF = "vol-1-ch-1"
_UIDS: dict[str, str] = {}


async def _seed_project(prefix: str) -> tuple[str, str]:
    root = tempfile.mkdtemp(prefix=f"test_zq_{prefix}_")
    slug = f"zq-{prefix}-{os.path.basename(root)[-10:]}"
    uid = f"zq-{prefix}-{os.path.basename(root)[-12:]}"
    async with async_session() as session:
        session.add(User(
            id=uid, email=f"{slug}@test.local", password_hash="x",
            display_name="朱雀测试", api_key="", api_base_url="", api_model="",
        ))
        session.add(Novel(
            user_id=uid, name="朱雀书", slug=slug, root_path=root,
            source="manual", current_phase="write",
        ))
        await session.flush()
        proj = (await session.scalars(select(Novel).where(Novel.root_path == root))).one()
        vol = Volume(project_id=proj.id, volume_no=1, title="第一卷")
        session.add(vol)
        await session.flush()
        ch = Chapter(
            project_id=proj.id, volume_id=vol.id, chapter_no=1,
            ref=REF, title="第1章", status="writing", word_count=40, has_prose=True,
        )
        session.add(ch)
        await session.flush()
        session.add(ChapterContent(
            chapter_id=ch.id,
            prose="她握紧船桨，风声很大。\n\n船家说渡口明早封江。\n  \n雨点砸在篷布上。",
        ))
        await session.commit()
        _UIDS[proj.id] = uid
        return uid, proj.id


async def _save_zhuque(uid: str, key: str = "eo-mk-test") -> None:
    async with async_session() as session:
        await zq_service.save_config(session, uid, key)


def _stub_classify(monkeypatch, *, merge_every: int = 2, status: str = "success",
                   ratios: dict | None = None, error: Exception | None = None,
                   usage: int = 3210, raw_labels: list | None = None):
    """桩按请求文本构造**合并分段**（c-zhuque-seg-align：模拟真实上游行为——

    EdgeOne 朱雀网关按自身规则并段，segment 数≠本地非空段数；对齐靠 text 拼接）。
    merge_every=N＝每 N 段并一个上游段；raw_labels 直接给段表（构造截断/改写样本）。
    """

    async def _fake(text: str, api_key: str):
        if error is not None:
            raise error
        labels = raw_labels
        if labels is None:
            paras = [s.strip() for s in text.split("\n") if s.strip()]
            labels = []
            for i in range(0, len(paras), merge_every):
                labels.append({
                    "text": "\n".join(paras[i:i + merge_every]),
                    "label": 0 if i == 0 else 2, "conf": 0.1 * (len(labels) + 1),
                    "order": len(labels) + 1, "position": [0, 1],
                })
        return {
            "status": status,
            "softmax_confidence": 0.18,
            "labels_ratio": ratios or {"0": 0.71, "2": 0.24, "1": 0.05},
            "segment_labels": labels,
            "usage": {"total_tokens": usage},
            "makers_models_usage": {"total_tokens": usage},
        }

    monkeypatch.setattr("zhuque.client.classify", _fake)


def _client(uid: str):
    c = TestClient(app)
    c.__enter__()
    app.dependency_overrides[get_current_user] = lambda: {"id": uid}
    app.dependency_overrides[_raa] = lambda: True
    return c


# ─── 隔离（P0） ───

def test_zhuque_only_key_is_not_a_writer_model():
    async def scene():
        uid, _ = await _seed_project("iso")
        await _save_zhuque(uid)
        async with async_session() as session:
            assert await user_has_ai_key(session, uid) is False
            from ai_client import get_ai_client_for_user as _gcfu
            with pytest.raises(ValueError, match="未配置 API Key"):
                await _gcfu(uid)
            assert await get_user_api_configs(session, uid) == []
            assert await get_batch_status(session, uid) == []
        return uid

    loop = _mkloop()
    try:
        uid = loop.run_until_complete(scene())
    finally:
        loop.close()
    _UIDS.pop(uid, None)


def test_for_novel_rejects_zhuque_binding(monkeypatch):
    import asyncio

    async def scene():
        from ai_client import get_ai_client_for_novel

        uid, pid = await _seed_project("bind")
        await _save_zhuque(uid)
        async with async_session() as session:
            cfg = await zq_service.get_zhuque_config(session, uid)
            novel = (await session.scalars(
                select(Novel).where(Novel.id == pid)
            )).one()
            novel.ai_config_id = cfg.id
            novel.ai_model = "any"
            await session.commit()
        with pytest.raises(ValueError):
            await get_ai_client_for_novel(pid)
        return uid

    uid = asyncio.new_event_loop().run_until_complete(scene())
    _UIDS.pop(uid, None)


# ─── 配置 upsert ───

def test_upsert_lifecycle(monkeypatch):
    import asyncio

    async def scene():
        uid, _ = await _seed_project("life")

        async with async_session() as session:
            st = await zq_service.save_config(session, uid, "key-one")
            assert st["configured"] is True
            # 更新（active → 更新密钥）
            await zq_service.save_config(session, uid, "key-two")
            # 删除 → 软删
            assert await zq_service.delete_config(session, uid) is True
            cfg = await zq_service.get_zhuque_config(session, uid)
            assert cfg.status == "deleted"
            # 复活（软删行写新 Key）
            st = await zq_service.save_config(session, uid, "key-three")
            assert st["configured"] is True
            cfg = await zq_service.get_zhuque_config(session, uid)
            assert cfg is not None
            rows = (await session.scalars(
                select(ApiConfig).where(ApiConfig.user_id == uid)
            )).all()
            assert len(rows) == 1
        return uid

    uid = asyncio.new_event_loop().run_until_complete(scene())
    _UIDS.pop(uid, None)


def test_upsert_name_conflict_with_llm_config(monkeypatch):
    import asyncio

    async def scene():
        uid, _ = await _seed_project("conf")
        async with async_session() as session:
            session.add(ApiConfig(
                user_id=uid, name=zq_service.ZHUQUE_NAME, vendor="deepseek",
                vendor_display_name="DeepSeek", base_url="https://api.deepseek.com",
                api_key="enc", status="active",
            ))
            await session.commit()
            with pytest.raises(ValueError, match="已被其他配置使用"):
                await zq_service.save_config(session, uid, "k")
        return uid

    uid = asyncio.new_event_loop().run_until_complete(scene())
    _UIDS.pop(uid, None)


# ─── 切分 golden ───

def test_segmentation_golden():
    raw = "她握紧船桨。\r\n船家说明早封江。\n\n  \n\u00a0雨点砸在篷布上。\n"
    paras = split_paragraphs(raw)
    assert paras == ["她握紧船桨。", "船家说明早封江。", "雨点砸在篷布上。"]
    # 指纹稳定：同规范文本同指纹；NBSP/CRLF 差异不影响
    assert fingerprint(raw) == fingerprint("她握紧船桨。\n船家说明早封江。\n雨点砸在篷布上。")
    assert canonical_text("A\n\nB") == "A\nB"


def test_align_segments_merge_and_mismatch():
    # 上游把 4 段并为 2 个分段：响应仍逐段 4 条，合并段共享 label/conf
    paras = ["第一段。", "第二段。", "第三段。", "第四段。"]
    labels = [
        {"text": "第一段。\n第二段。", "label": 0, "conf": 0.3},
        {"text": "第三段。\n第四段。", "label": 1, "conf": 0.9},
    ]
    out = align_segments(paras, labels)
    assert [s["paragraph_index"] for s in out] == [0, 1, 2, 3]
    assert [(s["label"], s["confidence"]) for s in out] == [
        (0, 0.3), (0, 0.3), (1, 0.9), (1, 0.9),
    ]
    # 整章并 1 段（实测短文行为）：全段落共享
    out = align_segments(paras, [{"text": "\n".join(paras), "label": 2, "conf": 0.5}])
    assert all(s["label"] == 2 and s["confidence"] == 0.5 for s in out)
    # 容错层：上游吞掉段边界换行（精确拼接不等、去空白相等）仍逐段映射
    out = align_segments(paras, [
        {"text": "第一段。第二段。", "label": 0, "conf": 0.3},
        {"text": "第三段。第四段。", "label": 1, "conf": 0.9},
    ])
    assert [(s["label"], s["confidence"]) for s in out] == [
        (0, 0.3), (0, 0.3), (1, 0.9), (1, 0.9),
    ]
    # 前端标注带分组依赖 paragraph_index 连续 0..N-1（c-zhuque-mark-band 前提钉）
    assert [s["paragraph_index"] for s in out] == [0, 1, 2, 3]
    # 空 seg_labels（上游无段）→ segment_mismatch（不做空映射）
    with pytest.raises(ValueError, match="segment_mismatch"):
        align_segments(paras, [])
    # 截断/改写（拼接≠请求文本）→ segment_mismatch
    with pytest.raises(ValueError, match="segment_mismatch"):
        align_segments(paras, [{"text": "第一段。\n第二段。", "label": 0, "conf": 0.3}])
    with pytest.raises(ValueError, match="segment_mismatch"):
        align_segments(paras, [{"text": "第一段。 第二段。", "label": 0, "conf": 0.3}])


# ─── check_chapter（service 层） ───

def _mkloop():
    return asyncio.new_event_loop()


def test_check_chapter_success_and_mapping(monkeypatch):
    import asyncio

    async def scene(monkeypatch):
        uid, pid = await _seed_project("ok")
        await _save_zhuque(uid)
        _stub_classify(monkeypatch)
        async with async_session() as session:
            out = await zq_service.check_chapter(
                session, user_id=uid, project_id=pid, chapter_ref=REF,
                prose="她握紧船桨。\n\n船家说明早封江。\n雨点砸在篷布上。",
            )
        assert out["ok"] is True
        # 桩默认两段并一组（3 段→上游 2 分段），响应仍逐段 3 条；段 1/2 同属合并段 0
        assert [s["paragraph_index"] for s in out["segments"]] == [0, 1, 2]
        assert [s["label"] for s in out["segments"]] == [0, 0, 2]
        assert [s["confidence"] for s in out["segments"]] == [0.1, 0.1, 0.2]
        assert out["summary"]["human_ratio"] == 0.71
        assert out["prose_hash"] == fingerprint("她握紧船桨。\n船家说明早封江。\n雨点砸在篷布上。")
        return uid

    import unittest
    loop = _mkloop()
    try:
        loop.run_until_complete(scene(monkeypatch))
    finally:
        loop.close()


def test_check_chapter_error_branches(monkeypatch):
    from zhuque.client import ZhuqueUpstreamError

    async def scene(monkeypatch):
        uid, pid = await _seed_project("err")
        # 未配置
        with pytest.raises(ValueError, match="zhuque_not_configured"):
            async with async_session() as session:
                await zq_service.check_chapter(
                    session, user_id=uid, project_id=pid, chapter_ref=REF, prose="有正文"
                )
        await _save_zhuque(uid)
        # 空正文
        with pytest.raises(ValueError, match="empty_prose"):
            async with async_session() as session:
                await zq_service.check_chapter(
                    session, user_id=uid, project_id=pid, chapter_ref=REF, prose="  \n "
                )
        # 超上限
        with pytest.raises(ValueError, match="prose_too_long"):
            async with async_session() as session:
                await zq_service.check_chapter(
                    session, user_id=uid, project_id=pid, chapter_ref=REF, prose="字" * 30001
                )
        # 上游 401
        _stub_classify(monkeypatch, error=ZhuqueUpstreamError(401, "bad key"))
        with pytest.raises(ZhuqueUpstreamError):
            async with async_session() as session:
                await zq_service.check_chapter(
                    session, user_id=uid, project_id=pid, chapter_ref=REF, prose="有正文"
                )
        # 上游截断（text 拼接≠请求文本）
        _stub_classify(monkeypatch, raw_labels=[
            {"text": "一。\n二。", "label": 0, "conf": 0.1, "order": 1, "position": [0, 5]},
        ])
        with pytest.raises(ValueError, match="segment_mismatch"):
            async with async_session() as session:
                await zq_service.check_chapter(
                    session, user_id=uid, project_id=pid, chapter_ref=REF,
                    prose="一。\n二。\n三。",
                )
        # 在途 409
        key = (uid, pid, REF)
        zq_service._inflight.add(key)
        try:
            _stub_classify(monkeypatch)
            with pytest.raises(ValueError, match="zhuque_check_in_progress"):
                async with async_session() as session:
                    await zq_service.check_chapter(
                        session, user_id=uid, project_id=pid, chapter_ref=REF, prose="一。\n二。\n三。"
                    )
        finally:
            zq_service._inflight.discard(key)
        return uid

    loop = _mkloop()
    try:
        loop.run_until_complete(scene(monkeypatch))
    finally:
        loop.close()


# ─── 端点 ───

def test_check_endpoint_mapping_and_usage(monkeypatch):
    import asyncio

    async def scene(monkeypatch):
        uid, pid = await _seed_project("ep")
        await _save_zhuque(uid)
        # 记账需要 User 行存在（FK）——seed 已建
        _stub_classify(monkeypatch, usage=777)
        c = _client(uid)
        try:
            r = c.post(f"/api/novels/{pid}/chapters/{REF}/zhuque-check", json={})
            assert r.status_code == 200
            body = r.json()
            assert body["ok"] is True and len(body["segments"]) == 3
            assert body["usage_tokens"] == 777
        finally:
            c.__exit__(None, None, None)
        # 记账：model=zhuque，且用量汇总排除
        async with async_session() as session:
            logs = (await session.scalars(
                select(__import__("models.token_log", fromlist=["TokenLog"]).TokenLog)
                .where(__import__("models.token_log", fromlist=["TokenLog"]).TokenLog.operation == "zhuque-check")
            )).all()
            assert any(l.model == "zhuque" and l.tokens_out == 777 for l in logs)
            summary = await get_usage_summary(session, uid)
            total_with = sum(
                (x.get("tokens") or 0) for x in summary.get("by_config", [])
            ) if isinstance(summary.get("by_config"), list) else 0
        return uid

    loop = _mkloop()
    try:
        loop.run_until_complete(scene(monkeypatch))
    finally:
        loop.close()


def test_check_endpoint_free_tier_403(monkeypatch):
    import asyncio

    async def scene(monkeypatch):
        uid, pid = await _seed_project("free")
        await _save_zhuque(uid)
        c = TestClient(app)
        c.__enter__()
        app.dependency_overrides[get_current_user] = lambda: {"id": uid}

        def _deny():
            raise HTTPException(403, detail={"reason": "member_required", "message": "AI 是会员功能"})

        app.dependency_overrides[_raa] = _deny
        try:
            r = c.post(f"/api/novels/{pid}/chapters/{REF}/zhuque-check", json={})
            assert r.status_code == 403
        finally:
            c.__exit__(None, None, None)
            app.dependency_overrides.clear()
        return uid

    loop = _mkloop()
    try:
        loop.run_until_complete(scene(monkeypatch))
    finally:
        loop.close()


def test_check_endpoint_upstream_401_and_429(monkeypatch):
    from zhuque.client import ZhuqueUpstreamError

    async def scene(monkeypatch):
        uid, pid = await _seed_project("up")
        await _save_zhuque(uid)
        _stub_classify(monkeypatch, error=ZhuqueUpstreamError(401, "bad key"))
        c = _client(uid)
        try:
            r = c.post(f"/api/novels/{pid}/chapters/{REF}/zhuque-check", json={})
            assert r.status_code == 401
        finally:
            c.__exit__(None, None, None)
            app.dependency_overrides.clear()
        _stub_classify(monkeypatch, error=ZhuqueUpstreamError(429, "quota"))
        c = _client(uid)
        try:
            r = c.post(f"/api/novels/{pid}/chapters/{REF}/zhuque-check", json={})
            assert r.status_code == 429
        finally:
            c.__exit__(None, None, None)
            app.dependency_overrides.clear()
        return uid

    loop = _mkloop()
    try:
        loop.run_until_complete(scene(monkeypatch))
    finally:
        loop.close()


def test_config_endpoints_lifecycle(monkeypatch):
    from zhuque.client import ZhuqueUpstreamError  # noqa: F401

    async def scene():
        uid, _ = await _seed_project("cfg")
        return uid

    _stub_classify(monkeypatch, usage=5)

    uid = asyncio.new_event_loop().run_until_complete(scene())
    c = _client(uid)
    try:
        assert c.get("/api/v1/zhuque/config").json()["configured"] is False
        r = c.put("/api/v1/zhuque/config", json={"api_key": "eo-mk-live"})
        assert r.json()["configured"] is True
        # 空串＝未提供：保留已存 Key
        r2 = c.put("/api/v1/zhuque/config", json={"api_key": ""})
        assert r2.json()["configured"] is True
        t = c.post("/api/v1/zhuque/test")
        assert t.json()["ok"] is True
        d = c.delete("/api/v1/zhuque/config")
        assert d.json()["ok"] is True
        assert c.get("/api/v1/zhuque/config").json()["configured"] is False
    finally:
        c.__exit__(None, None, None)
        app.dependency_overrides.clear()
    _UIDS.pop(uid, None)


# ─── 落库存档（c-zhuque-persist） ───


def test_zhuque_persist_roundtrip(monkeypatch):
    """检测成功落库→读回一致→重检覆盖一行；未检章 stored:false。"""
    import asyncio

    async def scene(monkeypatch):
        uid, pid = await _seed_project("persist")
        await _save_zhuque(uid)
        _stub_classify(monkeypatch)
        c = _client(uid)
        try:
            # 未检：stored:false
            g0 = c.get(f"/api/novels/{pid}/chapters/{REF}/zhuque-result")
            assert g0.status_code == 200 and g0.json() == {"stored": False}

            r = c.post(f"/api/novels/{pid}/chapters/{REF}/zhuque-check", json={})
            assert r.status_code == 200
            body = r.json()
            assert body["ok"] is True and body["checked_at"]

            g = c.get(f"/api/novels/{pid}/chapters/{REF}/zhuque-result")
            assert g.status_code == 200
            d = g.json()
            assert d["stored"] is True
            assert d["prose_hash"] == body["prose_hash"]
            assert d["checked_at"] == body["checked_at"]
            assert d["result"]["summary"]["human_ratio"] == 0.71
            assert len(d["result"]["segments"]) == 3

            # 重检覆盖：仍一行、checked_at 更新、结果为最新
            r2 = c.post(f"/api/novels/{pid}/chapters/{REF}/zhuque-check", json={})
            assert r2.status_code == 200
            g2 = c.get(f"/api/novels/{pid}/chapters/{REF}/zhuque-result").json()
            assert g2["checked_at"] >= d["checked_at"]
            async with async_session() as session:
                from models.chapter import Chapter as _Ch
                from models.zhuque import ZhuqueResultArchive
                _ch = (
                    await session.scalars(
                        select(_Ch).where(_Ch.project_id == pid, _Ch.ref == REF)
                    )
                ).first()
                rows = (
                    await session.scalars(
                        select(ZhuqueResultArchive).where(
                            ZhuqueResultArchive.chapter_id == _ch.id
                        )
                    )
                ).all()
                assert len(rows) == 1
                _ch_id = _ch.id
            return uid, pid, _ch_id
        finally:
            c.__exit__(None, None, None)
            app.dependency_overrides.clear()

    loop = _mkloop()
    try:
        uid, pid, ch_id = loop.run_until_complete(scene(monkeypatch))
    finally:
        loop.close()

    # 删章级联（独立 loop：复用播种库；其余用例的档行不作数，按本章 id 过滤）
    async def cascade():
        from models.chapter import Chapter
        from models.zhuque import ZhuqueResultArchive
        async with async_session() as session:
            rows = (
                await session.scalars(
                    select(ZhuqueResultArchive).where(
                        ZhuqueResultArchive.chapter_id == ch_id
                    )
                )
            ).all()
            assert len(rows) == 1
            ch = await session.get(Chapter, ch_id)
            await session.delete(ch)
            await session.commit()
            rows = (
                await session.scalars(
                    select(ZhuqueResultArchive).where(
                        ZhuqueResultArchive.chapter_id == ch_id
                    )
                )
            ).all()
            assert rows == []

    loop = _mkloop()
    try:
        loop.run_until_complete(cascade())
    finally:
        loop.close()
    _UIDS.pop(uid, None)


def test_zhuque_persist_not_configured_keeps_get_working(monkeypatch):
    """无 Key 时 GET 存档不受影响（读取零额度、不触检测）。"""
    import asyncio

    async def scene():
        uid, pid = await _seed_project("persistread")
        return uid, pid

    loop = _mkloop()
    try:
        uid, pid = loop.run_until_complete(scene())
    finally:
        loop.close()
    c = _client(uid)
    try:
        g = c.get(f"/api/novels/{pid}/chapters/{REF}/zhuque-result")
        assert g.status_code == 200 and g.json() == {"stored": False}
    finally:
        c.__exit__(None, None, None)
        app.dependency_overrides.clear()
    _UIDS.pop(uid, None)
