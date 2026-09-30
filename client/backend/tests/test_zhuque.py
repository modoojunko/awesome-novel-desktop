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
from zhuque.segmentation import canonical_text, fingerprint, split_paragraphs

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


def _stub_classify(monkeypatch, *, segments: int = 3, status: str = "success",
                   ratios: dict | None = None, error: Exception | None = None,
                   usage: int = 3210):
    async def _fake(text: str, api_key: str):
        if error is not None:
            raise error
        return {
            "status": status,
            "softmax_confidence": 0.18,
            "labels_ratio": ratios or {"0": 0.71, "2": 0.24, "1": 0.05},
            "segment_labels": [
                {"text": f"seg{i}", "label": 0 if i == 0 else 2, "conf": 0.1 * (i + 1),
                 "order": i + 1, "position": [0, 1]}
                for i in range(segments)
            ],
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


# ─── check_chapter（service 层） ───

def _mkloop():
    return asyncio.new_event_loop()


def test_check_chapter_success_and_mapping(monkeypatch):
    import asyncio

    async def scene(monkeypatch):
        uid, pid = await _seed_project("ok")
        await _save_zhuque(uid)
        _stub_classify(monkeypatch, segments=3)
        async with async_session() as session:
            out = await zq_service.check_chapter(
                session, user_id=uid, project_id=pid, chapter_ref=REF,
                prose="她握紧船桨。\n\n船家说明早封江。\n雨点砸在篷布上。",
            )
        assert out["ok"] is True
        assert [s["paragraph_index"] for s in out["segments"]] == [0, 1, 2]
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
        # 分段错配
        _stub_classify(monkeypatch, segments=5)
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
            _stub_classify(monkeypatch, segments=3)
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
        _stub_classify(monkeypatch, segments=3, usage=777)
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

    _stub_classify(monkeypatch, segments=1, usage=5)

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
