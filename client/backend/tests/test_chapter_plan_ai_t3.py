"""c-chapter-plan-ai T3：章级自检的草稿契约（三组：衔接/配额/剧情吸引力）。

原型里「AI 看一眼这一章」在手写卡底条——**排上之前**就能点，此时章尚未落库。
故自检不吃 chapter_ref 读库，卡面草稿随请求体携带（entry_text 供衔接组比对）。

矩阵：
- 排上前自检：200，衔接/配额（本地）＋四维短评（AI）；草稿真的进了提示词；
- 衔接漂移：卡面进场与本次重新派生的不一致 → link.ok=False「上一章结尾已变化」；
- 卡面未带进场：无可比对 → 不判漂移（不误报 warn）；
- 配额越界：目标 1 章、已排 1 章、再拆 → quota.ok=False；
- AI 组失败：本地两组照常返回（不 502、不 500）。

用法：
    cd client/backend
    python -m pytest tests/test_chapter_plan_ai_t3.py -v
"""

import asyncio
import json
import os
import tempfile
import uuid

import pytest
from fastapi.testclient import TestClient

# ── 隔离环境（先设 env 再 import app：见 s-server-test-infra 先例）─────────
_tmp_db = tempfile.NamedTemporaryFile(suffix="_cpa3.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_chapter_plan_ai_t3_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

import auth_local.service as _service  # noqa: E402
from auth_local.deps import require_novel_model  # noqa: E402
from auth_local.middleware import get_current_user  # noqa: E402
from db import async_session, get_db  # noqa: E402
from main import app  # noqa: E402
from models import Novel  # noqa: E402
from models.chapter import Chapter  # noqa: E402
from models.user import User  # noqa: E402
from models.volume import Volume  # noqa: E402

_CFG_PATH = os.path.join(_tmp_data_root, "config.json")
USER_ID = "cpa3_user"


def _run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _override_get_db():
    async with async_session() as session:
        yield session


async def _override_current_user():
    return {"id": USER_ID}


@pytest.fixture(autouse=True)
def _setup_overrides():
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_current_user
    app.dependency_overrides[require_novel_model] = lambda: True
    # 默认 trial（免费档每档限 1 项目，建书会被 403 挡住——与门禁无关的干扰）
    _service.CONFIG_FILE = _CFG_PATH
    _service.save_local_config({"tier": "trial", "expires_at": "2099-12-31", "api_key": "sk-test"})
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# ── AI 打桩（与 test_volume_plan_ai 同构：_generate 在 volumes.ai_plan 里取 client）──
class _FakeAIClient:
    def __init__(self, reply: str = "", boom: bool = False):
        self._reply = reply
        self._boom = boom
        self.calls: list[dict] = []

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(kwargs.get("usage"), dict):
            kwargs["usage"].update({"tokens_in": 100, "tokens_out": 200})
        if self._boom:
            raise RuntimeError("boom")
        return self._reply


def _setup_ai(monkeypatch, reply: str = "", *, boom: bool = False) -> _FakeAIClient:
    fake = _FakeAIClient(reply, boom)

    async def _factory(novel_id=None):
        return fake

    monkeypatch.setattr("volumes.ai_plan.get_ai_client_for_novel", _factory)
    return fake


VALID_SELFCHECK = json.dumps(
    {
        "critiques": {
            "反转": "撕页钩子立住了",
            "递增": "阻力偏程序化",
            "推进": "处境真的变了",
            "拉力": "停在决定上",
        },
        "weakest": "递增",
    },
    ensure_ascii=False,
)


# ── 夹具：书 + 卷（可带目标章数/已排章）──────────────────────────────────
def _seed(client, *, chapter_target: int | None = None, chapters: int = 0, exit_text: str = "") -> str:
    """建书（走 API，保证 root_path 等派生字段齐）＋直接落卷/章（不经 UI）。"""
    name = f"cpa3-{uuid.uuid4().hex[:6]}"
    r = client.post("/api/novels", json={"name": name})
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]

    async def _s():
        async with async_session() as session:
            if await session.get(User, USER_ID) is None:
                session.add(User(id=USER_ID, email=f"{USER_ID}@test.local", password_hash="x"))
                await session.flush()
            vol = Volume(
                project_id=pid, volume_no=1, title="第一卷",
                summary="沉舟捡到一枚不属于人类纪元的导航信标", core_conflict="想自己查清，与得靠船队",
                chapter_target=chapter_target,
            )
            session.add(vol)
            await session.flush()
            for i in range(1, chapters + 1):
                session.add(
                    Chapter(
                        project_id=pid, volume_id=vol.id, chapter_no=i,
                        ref=f"vol-1-ch-{i}", title=f"第{i}章", has_prose=False, status="outline",
                        ladder_exit=exit_text if i == chapters else "",
                    )
                )
            await session.commit()

    _run_async(_s())
    return pid


DRAFT = {
    "vol_ref": "vol-1",
    "entry_text": "",
    "title": "信标进舱",
    "plot": "沉舟在废弃星港捡到信标，先藏了下来",
    "challenge": "没人相信一个见习导航员",
    "ending": "她把信标藏进舱底夹层",
    "acts": ["沉舟：藏信标"],
    "stage": "开局铺垫",
}


class TestSelfcheckDraft:
    def test_pre_adopt_draft_three_groups(self, client, monkeypatch):
        """排上前（本卷 0 章）自检：三组齐；草稿五段真进了提示词；免费档不被门禁拒。"""
        pid = _seed(client)
        _service.save_local_config({"tier": "none", "expires_at": "", "api_key": "sk-test"})
        fake = _setup_ai(monkeypatch, VALID_SELFCHECK)

        r = client.post(f"/api/novels/{pid}/chapters/ai-selfcheck", json=DRAFT)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        # 衔接（本地）：本卷首章、卡面未带进场 → 不判漂移
        assert d["link"]["ok"] is True
        # 配额（本地）：未设目标章数
        assert d["quota"]["ok"] is True
        # 剧情吸引力（AI 只读）：四维短评＋最弱一维，不给字母
        assert set(d["critiques"]) == {"反转", "递增", "推进", "拉力"}
        assert d["weakest"] == "递增"
        assert not any(v in ("S", "A", "B") for v in d["critiques"].values())
        # 草稿进了提示词（系统消息逐字含本章剧情/阻力/落点）
        system = fake.calls[-1]["system"]
        assert "沉舟在废弃星港捡到信标" in system
        assert "没人相信一个见习导航员" in system
        assert "舱底夹层" in system

    def test_link_warn_on_entry_drift(self, client, monkeypatch):
        """卡面进场与本次重新派生的不一致 → 衔接组 warn（不拦，只提示）。"""
        pid = _seed(client, chapters=1, exit_text="她把信标藏进舱底夹层")
        _setup_ai(monkeypatch, VALID_SELFCHECK)
        # 已排 1 章 → 目标章号 2，进场＝第 1 章落点；卡面却显示别的
        r = client.post(
            f"/api/novels/{pid}/chapters/ai-selfcheck",
            json={**DRAFT, "entry_text": "（卡面旧的进场）"},
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["link"]["ok"] is False
        assert "上一章结尾已变化" in d["link"]["text"]

    def test_link_ok_when_entry_matches(self, client, monkeypatch):
        pid = _seed(client, chapters=1, exit_text="她把信标藏进舱底夹层")
        _setup_ai(monkeypatch, VALID_SELFCHECK)
        r = client.post(
            f"/api/novels/{pid}/chapters/ai-selfcheck",
            json={**DRAFT, "entry_text": "她把信标藏进舱底夹层"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["link"]["ok"] is True, r.json()

    def test_quota_warn_when_over_target(self, client, monkeypatch):
        """目标 1 章、已排 1 章，再拆下一章 → 配额组 warn（可拆，只提示）。"""
        pid = _seed(client, chapter_target=1, chapters=1)
        _setup_ai(monkeypatch, VALID_SELFCHECK)
        r = client.post(f"/api/novels/{pid}/chapters/ai-selfcheck", json=DRAFT)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["quota"]["ok"] is False
        assert "超出本卷目标 1 章" in d["quota"]["text"]

    def test_ai_group_failure_keeps_local_groups(self, client, monkeypatch):
        """AI 组失败：本地两组照常返回＋该组给引导文案（不 502/500）。"""
        pid = _seed(client)
        _setup_ai(monkeypatch, boom=True)
        r = client.post(f"/api/novels/{pid}/chapters/ai-selfcheck", json=DRAFT)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["link"]["ok"] is True and d["quota"]["ok"] is True
        assert d.get("degraded") is True
        assert "没看成" in d.get("hint", "")
        assert "critiques" not in d

    def test_ai_group_invalid_shape_degrades(self, client, monkeypatch):
        """AI 组输出不合形（缺维/字母越界）→ 该组降级，本地两组不受影响。"""
        pid = _seed(client)
        _setup_ai(monkeypatch, json.dumps({"critiques": {"反转": "只有一维"}, "weakest": "反转"}))
        r = client.post(f"/api/novels/{pid}/chapters/ai-selfcheck", json=DRAFT)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("degraded") is True and d["link"]["ok"] is True

    def test_unknown_volume_404(self, client, monkeypatch):
        pid = _seed(client)
        _setup_ai(monkeypatch, VALID_SELFCHECK)
        r = client.post(
            f"/api/novels/{pid}/chapters/ai-selfcheck", json={**DRAFT, "vol_ref": "vol-9"}
        )
        assert r.status_code == 404



# ── 卷级守卫（D12 末端门禁 / D14 重拆整卷）───────────────────────────────
def _seed_multi(client, vols: list[tuple[int, list[dict]]]) -> str:
    """建书＋按 (卷号, [章规格]) 落库。章规格：{"no": 1, "status": "outline", "prose": ""}。"""
    name = f"cpa3m-{uuid.uuid4().hex[:6]}"
    r = client.post("/api/novels", json={"name": name})
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]

    async def _s():
        async with async_session() as session:
            if await session.get(User, USER_ID) is None:
                session.add(User(id=USER_ID, email=f"{USER_ID}@test.local", password_hash="x"))
                await session.flush()
            for vol_no, chs in vols:
                vol = Volume(project_id=pid, volume_no=vol_no, title=f"第{vol_no}卷",
                             summary="沉舟捡到信标", core_conflict="想自己查清，与得靠船队")
                session.add(vol)
                await session.flush()
                for ch in chs:
                    session.add(
                        Chapter(
                            project_id=pid, volume_id=vol.id, chapter_no=ch["no"],
                            ref=f"vol-{vol_no}-ch-{ch['no']}", title=f"第{ch['no']}章",
                            has_prose=bool(ch.get("prose")), status=ch.get("status", "outline"),
                            ladder_exit=ch.get("exit", ""),
                        )
                    )
            await session.commit()

    _run_async(_s())
    return pid


class TestVolumeGuards:
    def test_frontier_gate_blocks_earlier_volume(self, client):
        """主线末端门禁：写作位在第 2 卷时第 1 卷不许排新章（409 且给出口）。"""
        pid = _seed_multi(client, [
            (1, [{"no": 1, "status": "archived", "prose": "写完了"}]),
            (2, [{"no": 1, "status": "outline"}]),
        ])
        r = client.post(f"/api/novels/{pid}/volumes/vol-1/chapters", json={"title": "插队章"})
        assert r.status_code == 409, r.text
        assert "写作位在第2卷" in r.json()["detail"]
        # 写作位所在卷及其之后照常
        r2 = client.post(f"/api/novels/{pid}/volumes/vol-2/chapters", json={"title": "正常章"})
        assert r2.status_code in (200, 201), r2.text

    def test_frontier_gate_allows_empty_volume_after(self, client):
        """全书零章（frontier 为 null）时不设门——第一卷照常可排。"""
        pid = _seed(client)
        r = client.post(f"/api/novels/{pid}/volumes/vol-1/chapters", json={"title": "第一章"})
        assert r.status_code in (200, 201), r.text

    def test_resplit_removes_only_planned_desc(self, client):
        """重拆整卷：只清拟定章、按章号降序删；有正文的章保留。"""
        pid = _seed_multi(client, [
            (1, [
                {"no": 1, "status": "archived", "prose": "有正文"},
                {"no": 2, "status": "outline"},
                {"no": 3, "status": "outline"},
            ]),
        ])
        r = client.post(f"/api/novels/{pid}/volumes/vol-1/chapters/resplit")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["removed"] == ["vol-1-ch-3", "vol-1-ch-2"]  # 降序（每步满足尾章守卫）
        assert d["kept"] == ["vol-1-ch-1"]
        # 库里只剩第 1 章；MAX+1 复用章号（不留空洞）
        r2 = client.post(f"/api/novels/{pid}/volumes/vol-1/chapters", json={"title": "重拆后"})
        assert r2.status_code in (200, 201), r2.text
        assert r2.json()["ref"] == "vol-1-ch-2"

    def test_resplit_noop_when_nothing_planned(self, client):
        """无拟定章时重拆是空操作（removed 空、有正文的章不动）。"""
        pid = _seed_multi(client, [(1, [{"no": 1, "status": "archived", "prose": "有正文"}])])
        d = client.post(f"/api/novels/{pid}/volumes/vol-1/chapters/resplit").json()
        assert d["removed"] == [] and d["kept"] == ["vol-1-ch-1"]


class TestDirectionsGate:
    def test_directions_requires_volume_outline(self, client, monkeypatch):
        """卷纲空门槛：卷纲（讲什么/主要冲突）全空 → 422 引导，AI 不被触达。"""
        pid = _seed_multi(client, [])  # 只建书，不落卷
        # 落一卷「只填标题」的空卷纲
        from sqlalchemy import text as _t

        async def _mk():
            async with async_session() as session:
                session.add(Volume(project_id=pid, volume_no=1, title="空纲卷"))
                await session.commit()

        _run_async(_mk())
        fake = _setup_ai(monkeypatch, VALID_SELFCHECK)
        r = client.post(f"/api/novels/{pid}/volumes/vol-1/chapters/ai-directions", json={})
        assert r.status_code == 422, r.text
        assert "卷纲为空" in r.json()["detail"]
        assert fake.calls == []  # 空门槛先于模型调用


class TestStaleSecondTrigger:
    def test_exit_change_via_endpoint_marks_next_stale(self, client):
        """回改第 1 章落点（走章纲 PUT）→ 第 2 章（已有正文）置「基于旧设定」。"""
        pid = _seed_multi(client, [
            (1, [
                {"no": 1, "status": "outline", "exit": "旧落点"},
                {"no": 2, "status": "draft", "prose": "第二章的正文"},
            ]),
        ])
        r = client.put(
            f"/api/novels/{pid}/chapters/vol-1-ch-1",
            json={"ladder_exit": "新落点：她烧掉了那张登记单"},
        )
        assert r.status_code == 200, r.text

        from sqlalchemy import text as _t

        async def _q():
            async with async_session() as s:
                return (
                    await s.execute(_t("select ref, stale, has_prose from chapters order by ref"))
                ).all()

        rows = _run_async(_q())
        assert dict((r[0], r[1]) for r in rows)["vol-1-ch-2"] == 1, rows

    def test_wording_tweak_does_not_mark(self, client):
        """措辞微调（trim 后相同）不触发。"""
        pid = _seed_multi(client, [
            (1, [
                {"no": 1, "status": "outline", "exit": "旧落点"},
                {"no": 2, "status": "draft", "prose": "第二章的正文"},
            ]),
        ])
        r = client.put(f"/api/novels/{pid}/chapters/vol-1-ch-1", json={"ladder_exit": "  旧落点  "})
        assert r.status_code == 200, r.text

        from sqlalchemy import text as _t

        async def _q():
            async with async_session() as s:
                return (
                    await s.execute(_t("select ref, stale from chapters order by ref"))
                ).all()

        rows = _run_async(_q())
        assert dict((r[0], r[1]) for r in rows)["vol-1-ch-2"] == 0, rows
