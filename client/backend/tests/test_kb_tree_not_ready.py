"""空树行为测试（c-kb-tree-cdn）：树未同步＝总结/提炼明确不可用，不造本地知识。

KB_TAXONOMY_PATH 指到不存在的文件 → kb.taxonomy 返回规范化空树；
run_summarize/run_refine 必须返回 tree_not_ready；graph/tree 200 + tree.ready=false。
API 用例走真 TestClient：config.json 写本地会话（middleware 同款口径）。
"""

import asyncio
import os
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from db import async_session
from models.kb import KbEntry

_TMP_DATA_ROOT = os.environ.get("DATA_ROOT", "./data")
_CFG_PATH = os.path.join(_TMP_DATA_ROOT, "config.json")
_TOKEN = "tree-not-ready-token"


@pytest.fixture
def empty_tree(monkeypatch):
    """指到不存在的树文件 → 空树；用例结束还原夹具树。"""
    monkeypatch.delenv("KB_TAXONOMY_PATH", raising=False)
    from kb import taxonomy as taxonomy_mod

    taxonomy_mod.reload()
    yield
    taxonomy_mod.reload()


@pytest.fixture
def local_session():
    """config.json 写一个新鲜会话（get_current_user 只核对 token/用户名/30 天）。"""
    from auth_local import middleware as _middleware
    from auth_local import service as _service

    _service.CONFIG_FILE = _CFG_PATH
    _middleware.CONFIG_FILE = _CFG_PATH
    _service.save_local_config({
        "token": _TOKEN,
        "username": "tree-user",
        "last_login_at": datetime.now(UTC).isoformat(),
        "expires_at": (datetime.now(UTC) + timedelta(days=30)).date().isoformat(),
    })
    yield {"id": "tree-user"}
    if os.path.exists(_CFG_PATH):
        os.remove(_CFG_PATH)


def _run(coro):
    return asyncio.run(coro)


def _seed_material(uid: str, genre: str = "玄幻") -> None:
    async def _go():
        async with async_session() as db:
            db.add(KbEntry(
                user_id=uid, genre=genre, concept="手法", concept_id=f"{genre}:手法",
                title="素材", payload_json='{"instruction": "先守后攻", "scene": "打斗"}',
                instruction="先守后攻再反制，攻防要换手",
                origin="material", status="active", rev=1, src_kind="manual",
            ))
            await db.commit()

    _run(_go())


def test_summarize_空树拒绝(empty_tree):
    from kb.summarize import run_summarize

    uid = "u-empty-sum"
    _seed_material(uid)

    async def _go():
        async with async_session() as db:
            return await run_summarize(db, user_id=uid, genre="玄幻", trigger="manual")

    summary, error = _run(_go())
    assert summary is None and error == "tree_not_ready", (summary, error)


def test_refine_空树拒绝(empty_tree):
    from kb.refine import run_refine

    async def _go():
        async with async_session() as db:
            return await run_refine(db, user_id="u-empty-refine", genre="玄幻", llm=True)

    summary, error = _run(_go())
    assert summary is None and error == "tree_not_ready", (summary, error)


def test_auto_summarize_空树跳过(empty_tree):
    from kb.summarize import maybe_auto_summarize

    _seed_material("u-empty-auto")
    assert _run(maybe_auto_summarize(user_id="u-empty-auto")) == []


def test_taxonomy_helpers_空树不抛(empty_tree):
    from kb.taxonomy import node_for, nodes, parent_chain

    assert nodes() == {}
    assert node_for("文风", "tone") is None
    assert parent_chain("craft_root") == []
    assert parent_chain("anything") == []


def test_graph_tree_空树降级_200(empty_tree, local_session):
    async def _seed():
        async with async_session() as db:
            db.add(KbEntry(
                user_id="tree-user", genre="玄幻", concept="",
                concept_id="",
                title="写作知识", payload_json="{}", instruction="", definition="",
                schema_json="", origin="summary", status="active", version=1,
                parent_id="",
            ))
            await db.commit()

    _run(_seed())
    from main import app

    with TestClient(app) as client:
        resp = client.get(
            "/api/kb/graph/tree",
            headers={"Authorization": f"Bearer {_TOKEN}"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["tree"]["ready"] is False


def test_tree_sync_status_api_未安装(empty_tree, local_session):
    from main import app

    with TestClient(app) as client:
        resp = client.get(
            "/api/kb/tree/sync-status",
            headers={"Authorization": f"Bearer {_TOKEN}"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["ready"] is False
