"""章档端点族（c-chapter-dossier D4/5.x）：单章 GET 形状、逐条/批量采纳、
删除已采纳、恢复、重归档竞态 409、跳过逃生阀、累计预览与消费同源。

用法：
    cd client/backend
    python -m pytest tests/test_dossier_endpoints.py -v
"""

import asyncio
import os
import tempfile

import pytest

_tmp_db = tempfile.NamedTemporaryFile(suffix="_dossier_api.db", delete=False)  # noqa: SIM115
_tmp_db.close()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = tempfile.mkdtemp(prefix="test_dossier_api_")

from fastapi.testclient import TestClient  # noqa: E402

from auth_local.middleware import get_current_user  # noqa: E402
from db import Base, async_session, engine  # noqa: E402
from main import app  # noqa: E402

_DOSSIER = {
    "settings": [
        {"area": "势力", "content": "守夜人接管城门", "evidence": "守夜人接管了城门",
         "status": "accepted"},
        {"area": "地理", "content": "渡口封航", "evidence": "", "status": "pending"},
    ],
    "relations": [
        {"owner": "林晚", "other": "阿蓟", "rel_type": "盟友",
         "change_note": "并肩", "evidence": "", "status": "pending"},
    ],
    "items": [
        {"name": "旧刀", "change_type": "obtain", "holder": "林晚",
         "detail": "", "evidence": "", "status": "pending"},
    ],
    "knowledge": [
        {"character": "阿蓟", "fact": "林晚的身份", "learned": False,
         "evidence": "", "status": "pending"},
    ],
}


def _run(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _ensure_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture(scope="module", autouse=True)
def _db():
    _run(_ensure_tables())
    yield


def _seed(*, status: str = "archived", dossier: dict | None = None) -> tuple[str, str]:
    """建书+卷+一章（长正文+可选章档）；返回 (nid, ch_ref)。"""
    from models.chapter import Chapter, ChapterContent
    from models.project import Novel
    from models.user import User
    from models.volume import Volume

    root = tempfile.mkdtemp(prefix="dossier_api_")
    uid = f"da-{os.path.basename(root)[-10:]}"

    async def _go():
        async with async_session() as s:
            s.add(User(id=uid, email=f"{uid}@t.local", password_hash="x",
                       display_name="端点", api_key="", api_base_url="", api_model=""))
            proj = Novel(user_id=uid, name="端点书", slug=f"da-{os.path.basename(root)}",
                         root_path=root, source="manual", current_phase="write")
            s.add(proj)
            await s.flush()
            vol = Volume(project_id=proj.id, volume_no=1, title="第一卷")
            s.add(vol)
            await s.flush()
            ch = Chapter(project_id=proj.id, volume_id=vol.id, chapter_no=1,
                         ref="vol-1-ch-1", title="第1章", status=status, has_prose=True)
            s.add(ch)
            await s.flush()
            s.add(ChapterContent(chapter_id=ch.id, prose="正文" * 60))
            await s.commit()
            return proj.id

    nid = _run(_go())
    if dossier is not None:
        from chapters.store import save_chapter

        # save_chapter 需要 root_path
        async def _root():
            async with async_session() as s:
                n = await s.get(Novel, nid)
                return n.root_path

        root = _run(_root())
        _run(save_chapter(root, "vol-1-ch-1", {"dossier": dossier}))
    _UID[nid] = uid
    return nid, "vol-1-ch-1"


_UID: dict[str, str] = {}


@pytest.fixture
def client():
    c = TestClient(app)
    c.__enter__()
    yield c
    app.dependency_overrides.clear()


def _auth(nid: str):
    app.dependency_overrides[get_current_user] = lambda: {"id": _UID[nid]}


def test_get_shape_and_progress(client):
    nid, ref = _seed(dossier=_DOSSIER)
    _auth(nid)
    r = client.get(f"/api/novels/{nid}/chapters/{ref}/dossier")
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["archived"] is True and got["stale"] is False
    assert got["progress"] == {"pending": 4, "accepted": 1, "rejected": 0}
    assert got["accepted_count"] == 1
    assert got["extraction"] is None and got["not_extracted"] is False
    domains = {row["domain"] for row in got["rows"]}
    assert domains == {"settings", "relations", "items", "knowledge"}


def test_not_extracted_flag_when_archived_without_rows(client):
    nid, ref = _seed()  # 归档但无章档无 job（模型未就绪放行后的态）
    _auth(nid)
    got = client.get(f"/api/novels/{nid}/chapters/{ref}/dossier").json()
    assert got["not_extracted"] is True


def test_accept_reject_restore_and_delete(client):
    nid, ref = _seed(dossier=_DOSSIER)
    _auth(nid)
    got = client.get(f"/api/novels/{nid}/chapters/{ref}/dossier").json()
    by_domain = {d: [r for r in got["rows"] if r["domain"] == d] for d in
                 ("settings", "relations", "items", "knowledge")}
    rel_id = by_domain["relations"][0]["id"]
    set_accepted_id = next(r["id"] for r in by_domain["settings"] if r["status"] == "accepted")
    pending_set_id = next(r["id"] for r in by_domain["settings"] if r["status"] == "pending")

    # 采纳关系行
    r = client.post(f"/api/novels/{nid}/chapters/{ref}/dossier/rows/{rel_id}",
                    json={"action": "accept"})
    assert r.status_code == 200 and r.json()["row"]["status"] == "accepted"
    # 已处理再动 → 409
    assert client.post(f"/api/novels/{nid}/chapters/{ref}/dossier/rows/{rel_id}",
                       json={"action": "reject"}).status_code == 409
    # 驳回→恢复
    item_id = by_domain["items"][0]["id"]
    assert client.post(f"/api/novels/{nid}/chapters/{ref}/dossier/rows/{item_id}",
                       json={"action": "reject"}).json()["row"]["status"] == "rejected"
    assert client.post(f"/api/novels/{nid}/chapters/{ref}/dossier/rows/{item_id}",
                       json={"action": "restore"}).json()["row"]["status"] == "pending"
    # 非驳回行恢复 → 409
    assert client.post(f"/api/novels/{nid}/chapters/{ref}/dossier/rows/{rel_id}",
                       json={"action": "restore"}).status_code == 409
    # 删除已采纳行成功；pending 行删除 → 409
    assert client.delete(f"/api/novels/{nid}/chapters/{ref}/dossier/rows/{set_accepted_id}").status_code == 200
    assert client.delete(f"/api/novels/{nid}/chapters/{ref}/dossier/rows/{pending_set_id}").status_code == 409


def test_batch_accept_by_domain_and_all(client):
    nid, ref = _seed(dossier=_DOSSIER)
    _auth(nid)
    base = f"/api/novels/{nid}/chapters/{ref}/dossier"
    r = client.post(f"{base}/rows", json={"action": "accept", "domain": "settings"})
    assert r.json()["updated"] == 1  # settings 域只有 1 条 pending（另 1 条已采纳）
    r = client.post(f"{base}/rows", json={"action": "reject", "domain": "relations"})
    assert r.json()["updated"] == 1
    r = client.post(f"{base}/rows", json={"action": "accept"})
    assert r.json()["updated"] == 2  # 剩 items+knowledge 两条 pending
    assert client.get(base).json()["progress"] == {
        "pending": 0, "accepted": 4, "rejected": 1,
    }
    assert client.post(f"{base}/rows", json={"action": "bogus"}).status_code == 400
    assert client.post(f"{base}/rows", json={"action": "accept", "domain": "nope"}).status_code == 400


def test_accept_dead_row_after_reextract_returns_409(client):
    """重归档竞态：旧行已被重建删除 → 采纳返回 409「章档已重新提取」。"""
    nid, ref = _seed(dossier=_DOSSIER)
    _auth(nid)
    base = f"/api/novels/{nid}/chapters/{ref}/dossier"
    old_id = client.get(base).json()["rows"][0]["id"]
    # 模拟重归档整体覆盖（清空重建）
    from chapters.store import save_chapter

    async def _root():
        from models.project import Novel

        async with async_session() as s:
            return (await s.get(Novel, nid)).root_path

    _run(save_chapter(_run(_root()), ref, {"dossier": {}}))
    r = client.post(f"{base}/rows/{old_id}", json={"action": "accept"})
    assert r.status_code == 409
    assert "重新提取" in r.json()["detail"]


def test_preview_matches_consumption_source(client):
    """累计预览与消费折叠同源（都来自 story_state_upto）。"""
    nid, ref = _seed(dossier=_DOSSIER)
    _auth(nid)
    # 全采纳后预览应含设定/关系/物品/认知
    client.post(f"/api/novels/{nid}/chapters/{ref}/dossier/rows", json={"action": "accept"})
    r = client.get(f"/api/novels/{nid}/dossier/preview", params={"up_to_ref": ref})
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["up_to_ref"] == ref
    assert got["counts"]["settings"] == 2
    assert got["counts"]["relations"] == 1
    assert got["domains"]["knowledge"][0]["character"] == "阿蓟"

    from write.story_state import story_state_upto

    state = _run(story_state_upto(nid, ref))
    assert [d["content"] for d in got["domains"]["settings"]] == \
        [d["content"] for d in state["settings"]]


def test_skip_escape_hatch_endpoint(client):
    nid, ref = _seed(status="writing", dossier=None)
    _auth(nid)
    r = client.post(f"/api/novels/{nid}/chapters/{ref}/dossier/skip")
    assert r.status_code == 200, r.text
    got = client.get(f"/api/novels/{nid}/chapters/{ref}/dossier").json()
    assert got["archived"] is True and got["not_extracted"] is True
    # 已归档再 skip → 409
    assert client.post(f"/api/novels/{nid}/chapters/{ref}/dossier/skip").status_code == 409


def test_extract_model_not_ready_409(client):
    nid, ref = _seed(status="archived", dossier=None)
    _auth(nid)
    r = client.post(f"/api/novels/{nid}/chapters/{ref}/dossier/extract")
    assert r.status_code == 409
    assert "model_not_ready" in r.json()["detail"]
