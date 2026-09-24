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

        async def _mk():
            async with async_session() as session:
                session.add(Volume(project_id=pid, volume_no=1, title="空纲卷"))
                await session.commit()

        _run_async(_mk())
        fake = _setup_ai(monkeypatch, VALID_SELFCHECK)
        r = client.post(f"/api/novels/{pid}/volumes/vol-1/chapters/ai-directions", json={})
        assert r.status_code == 422, r.text
        # 三项缺项点名（主旨/冲突/卷末）——文案作家语言，不吐内部列名
        assert "卷纲还没填全" in r.json()["detail"]
        assert "卷末收在哪里" in r.json()["detail"]
        assert fake.calls == []  # 空门槛先于模型调用

    def test_directions_requires_volume_ending(self, client, monkeypatch):
        """只缺「卷末」也要拦（spec：主旨/冲突/卷末 三项关键项）。"""
        pid = _seed_multi(client, [])

        async def _mk():
            async with async_session() as session:
                session.add(Volume(
                    project_id=pid, volume_no=1, title="缺卷末卷",
                    summary="沉舟捡到信标", core_conflict="想自己查清，与得靠船队", ending=None,
                ))
                await session.commit()

        _run_async(_mk())
        fake = _setup_ai(monkeypatch, VALID_SELFCHECK)
        r = client.post(f"/api/novels/{pid}/volumes/vol-1/chapters/ai-directions", json={})
        assert r.status_code == 422, r.text
        assert "卷末收在哪里" in r.json()["detail"]
        assert fake.calls == []


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


# ── 出卡校验阶梯（tasks 3.2/3.3/3.5 的缺失验证面）────────────────────────
CARDS = [
    {"axis": "线索", "title": "同名档案", "plot": "她调出那份记录，最后一页被撕掉了",
     "obstacle": "旧档堆不对活人开放", "ending": "她把残角收进怀里", "acts": ["她：调档"],
     "stage": "矛盾升级", "cast": ["沉舟"], "factions": [], "places": ["旧档堆"],
     "why": "撕页钩子立住了", "gap": ""},
    {"axis": "关系", "title": "船队的条件", "plot": "船队长开价换航线",
     "obstacle": "让出航线＝交出一半生存空间", "ending": "她换来留在船上的许可",
     "acts": ["船队长：开价"], "stage": "矛盾升级", "cast": [], "factions": [], "places": [],
     "why": "让出航线真的疼", "gap": ""},
    {"axis": "危机", "title": "突击清查", "plot": "清查队登船前她带信标出逃",
     "obstacle": "挨船搜舱，藏无可藏", "ending": "信标暴露——全港都知道",
     "acts": ["清查队：搜舱"], "stage": "重要转折", "cast": [], "factions": [], "places": [],
     "why": "外部事件当面压上来", "gap": ""},
]


def _directions_reply(cards=None, *, axes=None, reasons=None, weakest="递增"):
    cards = cards if cards is not None else CARDS
    axes = axes if axes is not None else [c["axis"] for c in cards]
    n = len(cards)
    ranks = {d: [1] + [2] * (n - 1) for d in ("反转", "递增", "推进", "拉力")}
    rs = reasons if reasons is not None else {
        "反转": "最后一页被撕掉了", "递增": "旧档堆不对活人开放",
        "推进": "她调出那份记录", "拉力": "她把残角收进怀里",
    }
    return json.dumps(
        {"diff": {"axes": axes, "one_liner": [f"推向{i + 1}" for i in range(n)]},
         "directions": cards, "ranks": ranks, "reasons": rs, "checks": [], "note": ""},
        ensure_ascii=False,
    )


def _seed_vol(client, *, target: int | None = None, ending: str = "船头转向母港旧址") -> str:
    """建书＋建一卷（卷纲三问齐，可指定章数目标/卷末）。"""
    name = f"cpa3d-{uuid.uuid4().hex[:6]}"
    r = client.post("/api/novels", json={"name": name})
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]

    async def _s():
        async with async_session() as session:
            if await session.get(User, USER_ID) is None:
                session.add(User(id=USER_ID, email=f"{USER_ID}@test.local", password_hash="x"))
                await session.flush()
            session.add(Volume(
                project_id=pid, volume_no=1, title="第一卷",
                summary="沉舟捡到一枚不属于人类纪元的导航信标",
                core_conflict="想自己查清，与得靠船队", ending=ending, chapter_target=target,
            ))
            await session.commit()

    _run_async(_s())
    return pid


class TestDirectionsValidation:
    def test_happy_path_material_and_grades(self, client, monkeypatch):
        """出卡成功：素材八块齐、字母齐、计量入账、不落库。"""
        pid = _seed_vol(client, target=6)
        fake = _setup_ai(monkeypatch, _directions_reply())
        r = client.post(f"/api/novels/{pid}/volumes/vol-1/chapters/ai-directions", json={})
        assert r.status_code == 200, r.text
        d = r.json()
        assert len(d["directions"]) == 3 and len(d["grades"]) == 3
        assert d["grades"].count("S") <= 1  # 鸽笼：至多一张 S
        system = fake.calls[-1]["system"]
        for block in ("【进场（本章从哪接）】", "【本卷卷纲（四问）】", "【章数配额】"):
            assert block in system, block
        # 空数据块不出现占位符（tasks 2.4 口径）：本用例的书没题材/人物
        # （「世界铁律」四字在硬规则里出现，故只查素材块标题形态）
        for block in ("【题材与节奏】", "【核心人物】"):
            assert block not in system, block
        assert "【世界铁律】\n" not in system
        assert "【伏笔台账】" not in system  # 不给台账（防提前揭）
        # 不落库：卷内章数仍 0
        from sqlalchemy import text as _t

        async def _q():
            async with async_session() as s:
                return (
                    await s.execute(_t("select count(*) from chapters where novel_id = :p"), {"p": pid})
                ).scalar()

        assert _run_async(_q()) == 0

        # 计量入账（tasks 3.7）：operation 名独立，含失败留痕口径
        from sqlalchemy import select as _sel

        from models.token_log import TokenLog

        async def _logs():
            async with async_session() as s:
                rows = (await s.scalars(_sel(TokenLog).where(TokenLog.project_id == pid))).all()
                return [r.operation for r in rows]

        ops = _run_async(_logs())
        assert "chapter_directions" in ops, ops

    def test_quota_four_states(self, client, monkeypatch):
        """配额四态：未设/还剩 N/已排满/末章——「已排满」不得报成「未设目标」。"""
        # 未设目标
        pid = _seed_vol(client)
        fake = _setup_ai(monkeypatch, _directions_reply())
        client.post(f"/api/novels/{pid}/volumes/vol-1/chapters/ai-directions", json={})
        assert "（目标章数未设）" in fake.calls[-1]["system"]
        # 已排满：目标 1 章、已排 1 章（非末章）
        pid2 = _seed_vol(client, target=1)
        _seed_multi_chapters(pid2, 1)
        client.post(f"/api/novels/{pid2}/volumes/vol-1/chapters/ai-directions", json={})
        sys2 = fake.calls[-1]["system"]
        assert "已排满甚至超出目标章数" in sys2
        assert "未设" not in sys2
        # 末章：目标 1 章、已排 0 章
        pid3 = _seed_vol(client, target=1)
        client.post(f"/api/novels/{pid3}/volumes/vol-1/chapters/ai-directions", json={})
        sys3 = fake.calls[-1]["system"]
        assert "本章是本卷末章" in sys3
        assert "【结局（作者写的）】" in sys3  # 末章给结局块（硬规则 5 引用它）

    def test_new_place_warns(self, client, monkeypatch):
        """越纲：卡面申报的地点不在已知集合 → warnings（不拦）。"""
        pid = _seed_vol(client)
        cards = [dict(CARDS[0], places=["幽灵港口"]), CARDS[1], CARDS[2]]
        _setup_ai(monkeypatch, _directions_reply(cards))
        d = client.post(f"/api/novels/{pid}/volumes/vol-1/chapters/ai-directions", json={}).json()
        assert any("幽灵港口" in w for w in d["warnings"]), d["warnings"]
        assert len(d["directions"]) == 3  # 卡仍可用

    def test_same_axis_dropped(self, client, monkeypatch):
        """三轴必须互不相同：重复轴丢卡（余量不足则重试，最终降级）。"""
        pid = _seed_vol(client)
        # 第 2 张与第 1 张同轴 → 丢第 2 张；剩 2 张（线索/危机）→ 不降级
        same = [CARDS[0], dict(CARDS[1], axis="线索"), CARDS[2]]
        _setup_ai(monkeypatch, _directions_reply(same, axes=["线索", "线索", "危机"]))
        d = client.post(f"/api/novels/{pid}/volumes/vol-1/chapters/ai-directions", json={}).json()
        assert [c["axis"] for c in d["directions"]] == ["线索", "危机"]
        assert any("重复" in w for w in d["warnings"]), d["warnings"]

    def test_all_same_axis_degrades(self, client, monkeypatch):
        """三张全同轴 → 只剩 1 张 → 走重试阶梯，三次后降级（不 500、不出错批）。"""
        pid = _seed_vol(client)
        same = [CARDS[0], dict(CARDS[1], axis="线索"), dict(CARDS[2], axis="线索")]
        _setup_ai(monkeypatch, _directions_reply(same, axes=["线索", "线索", "线索"]))
        r = client.post(f"/api/novels/{pid}/volumes/vol-1/chapters/ai-directions", json={})
        assert r.status_code == 200, r.text
        assert r.json().get("degraded") is True

    def test_non_dict_shapes_not_500_all_B(self, client, monkeypatch):
        """模型把 diff/ranks 拍平成数组 → 不 500：卡照出，名次形态不合法只让各维不计分（全 B）。"""
        pid = _seed_vol(client)
        bad = json.dumps(
            {"diff": ["加速", "关系"], "directions": CARDS, "ranks": [1, 2, 3],
             "reasons": "不是对象", "checks": "不是数组", "note": None},
            ensure_ascii=False,
        )
        fake = _setup_ai(monkeypatch, bad)
        r = client.post(f"/api/novels/{pid}/volumes/vol-1/chapters/ai-directions", json={})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("degraded") is not True  # 卡面结构合法，不该降级
        assert len(d["directions"]) == 3
        assert d["grades"] == ["B", "B", "B"]  # 名次不可读 → 无人得分；不重抽
        assert len(fake.calls) == 1

    def test_unverifiable_reasons_do_not_retry(self, client, monkeypatch):
        """依据对不上卡面字段 → 参考文本而已：一次调用、字母照出、不再有「不出等级」。"""
        pid = _seed_vol(client)
        bad_reasons = {"反转": "这是一个非常精彩的反转", "递增": "旧档堆不对活人开放",
                       "推进": "她调出那份记录", "拉力": "她把残角收进怀里"}
        fake = _setup_ai(monkeypatch, _directions_reply(reasons=bad_reasons))
        d = client.post(f"/api/novels/{pid}/volumes/vol-1/chapters/ai-directions", json={}).json()
        assert len(fake.calls) == 1, "依据瑕疵不得消耗重试预算"
        assert d["grades"] == ["S", "B", "B"], d  # 名次合法 → 字母照出（默认样本：卡 1 四维全第一）
        assert not any("不出等级" in w for w in d["warnings"]), d["warnings"]


def _seed_multi_chapters(pid: str, n: int) -> None:
    async def _s():
        async with async_session() as session:
            from sqlalchemy import select as _sel

            vol = (await session.execute(_sel(Volume).where(Volume.project_id == pid))).scalars().first()
            for i in range(1, n + 1):
                session.add(Chapter(
                    project_id=pid, volume_id=vol.id, chapter_no=i,
                    ref=f"vol-1-ch-{i}", title=f"第{i}章", has_prose=False, status="outline",
                ))
            await session.commit()

    _run_async(_s())


class TestAdoptContract:
    def test_adopt_validates_stage_before_create(self, client):
        """排上路径的闭集校验真的生效（曾因键名不匹配成死代码）：越界 422 且不建章。"""
        pid = _seed_vol(client)
        r = client.post(
            f"/api/novels/{pid}/volumes/vol-1/chapters",
            json={"title": "越界章", "plot": "剧情", "stage": "高潮"},
        )
        assert r.status_code == 422, r.text
        assert "阶段只能是" in r.json()["detail"]  # 作家语言，不吐内部列名

        from sqlalchemy import text as _t

        async def _q():
            async with async_session() as s:
                return (
                    await s.execute(_t("select count(*) from chapters where novel_id = :p"), {"p": pid})
                ).scalar()

        assert _run_async(_q()) == 0

    def test_adopt_validates_acts_length(self, client):
        pid = _seed_vol(client)
        r = client.post(
            f"/api/novels/{pid}/volumes/vol-1/chapters",
            json={"title": "长行动章", "acts": ["x" * 61]},
        )
        assert r.status_code == 422, r.text
        assert "本章行动单行不超过 60 字" in r.json()["detail"]

    def test_adopt_idempotent_by_client_token(self, client):
        """同一 client_token 重放 → 同一章（spec「重复提交 SHALL 幂等」）。"""
        pid = _seed_vol(client)
        body = {"title": "幂等章", "plot": "捡到信标", "client_token": "tok-e2e-1"}
        r1 = client.post(f"/api/novels/{pid}/volumes/vol-1/chapters", json=body)
        r2 = client.post(f"/api/novels/{pid}/volumes/vol-1/chapters", json=body)
        assert r1.status_code == r2.status_code == 200, r2.text
        assert r1.json()["ref"] == r2.json()["ref"] == "vol-1-ch-1"

        from sqlalchemy import text as _t

        async def _q():
            async with async_session() as s:
                return (
                    await s.execute(_t("select count(*) from chapters where novel_id = :p"), {"p": pid})
                ).scalar()

        assert _run_async(_q()) == 1


class TestPlanCard:
    def test_plan_card_maps_five_fields(self, client):
        """回改卡面：五段键路径正确（summary 在 outline 内）——e2e 曾因读错路径拿到空剧情。"""
        pid = _seed_multi(client, [
            (1, [{"no": 1, "status": "outline", "exit": "藏进夹层"}]),
        ])
        from sqlalchemy import select as _sel

        async def _fill():
            async with async_session() as s:
                row = (
                    await s.scalars(
                        _sel(Chapter).where(Chapter.project_id == pid, Chapter.ref == "vol-1-ch-1")
                    )
                ).first()
                row.title = "信标进舱"
                row.summary = "捡到信标"
                row.challenge = "没人信她"
                row.chapter_acts = "沉舟：藏信标"
                row.plot_stage = "重要转折"
                await s.commit()

        _run_async(_fill())
        d = client.get(f"/api/novels/{pid}/chapters/vol-1-ch-1/plan-card").json()
        assert d["title"] == "信标进舱"
        assert d["plot"] == "捡到信标"
        assert d["challenge"] == "没人信她"
        assert d["ending"] == "藏进夹层"
        assert d["acts"] == ["沉舟：藏信标"]
        assert d["stage"] == "重要转折"
        assert d["next_no"] == 1
        assert "entry_text" in d and "entry_source" in d

    def test_plan_card_404(self, client):
        pid = _seed_multi(client, [(1, [{"no": 1}])])
        r = client.get(f"/api/novels/{pid}/chapters/vol-1-ch-9/plan-card")
        assert r.status_code == 404


# ── 模板契约＋卷纲聚光（提示词对齐修复的钉子）────────────────────────────
def test_split_template_scene_state_rules():
    """章卡模板钉住「客观局面」三处：硬规则 10、acts 含在场者、checks 缺席示例；负面清单不破。"""
    with open(
        os.path.join(os.path.dirname(__file__), "..", "prompts", "chapter_split.prompt"),
        encoding="utf-8",
    ) as f:
        src = f.read()
    assert "10. 剧情写整个场面，不只写主角" in src
    assert "在场其他人物的关键动作也各占一条" in src
    assert "这一章没出场" in src
    assert "【伏笔台账】" not in src and "【主线全景】" not in src  # 负面清单（§5）不破


def test_split_template_ending_natural_breakpoint():
    """章尾钉住「自然断点」：规则 4 教局面不教钩子，ending 定义呼应；末章例外（规则 5）保留。"""
    with open(
        os.path.join(os.path.dirname(__file__), "..", "prompts", "chapter_split.prompt"),
        encoding="utf-8",
    ) as f:
        rule4 = next(
            line for line in f.read().splitlines() if line.startswith("4. ")
        )
    assert "自然断点" in rule4
    assert "悬念道具" in rule4
    assert "还没完" not in rule4
    with open(
        os.path.join(os.path.dirname(__file__), "..", "prompts", "chapter_split.prompt"),
        encoding="utf-8",
    ) as f:
        src = f.read()
    assert "停在场面状态（剧情自然断点）" in src  # ending 字段定义呼应
    assert "5. 素材标注「本章是本卷末章」时例外" in src  # 末章收卷不变


def test_selfcheck_template_pull_natural_breakpoint():
    """章级自检的「拉力」问句与生成模板同批：自然断点口径，钩子导向问法退役。"""
    with open(
        os.path.join(os.path.dirname(__file__), "..", "prompts", "chapter_selfcheck.prompt"),
        encoding="utf-8",
    ) as f:
        pull = next(
            line
            for line in f.read().splitlines()
            if line.startswith("- 拉力（只看本章结尾）")
        )
    assert "自然断点" in pull
    assert "还没完" not in pull


def test_position_fragment_ch1_ending_aligned():
    """#488 位置片段章尾行与硬规则 4 同口径：「大钩」导向词退役，密度要求原词保留。"""
    with open(
        os.path.join(os.path.dirname(__file__), "..", "prompts", "pos_ch1.prompt"),
        encoding="utf-8",
    ) as f:
        ch1 = f.read()
    assert "大钩" not in ch1
    assert "不收场、不喘息" in ch1  # pacing 对拍钉子原样存活
    assert "停在新麻烦刚炸开、主角还没接招的局面" in ch1


def test_volume_named_character_spotlights_into_cast(client, monkeypatch):
    """c-plan-material-fullinfo：人物块＝全名单——卷纲点名者自然在包，6 张上限与聚光换位退役。

    旧口径：>6 张时卷纲点名的配角挤进队尾卡（聚光单换位）；全量后该机制退役，
    全册进块，覆盖只增不减（场景名留作历史标识）。
    """
    from sqlalchemy import select as _sel

    from models.character import Character

    pid = _seed_vol(client, target=6)

    async def _seed_cast():
        async with async_session() as s:
            vol = (await s.scalars(_sel(Volume).where(Volume.project_id == pid))).first()
            vol.antagonist_line = "执法官老聋点名要她停手——船队通行证被扣"
            s.add(Character(novel_id=pid, seq=1, name="沉舟", role="主角", persona="见习导航员，不信教科书"))
            for i in range(2, 7):
                s.add(Character(novel_id=pid, seq=i, name=f"船员{i}", role="配角", persona=f"船员{i}的专属人设标记"))
            s.add(Character(novel_id=pid, seq=7, name="老聋", role="配角", persona="港务局的眼线，只在雾天出现"))
            await s.commit()

    _run_async(_seed_cast())
    fake = _setup_ai(monkeypatch, _directions_reply())
    r = client.post(f"/api/novels/{pid}/volumes/vol-1/chapters/ai-directions", json={})
    assert r.status_code == 200, r.text
    system = fake.calls[-1]["system"]
    block = system.split("【核心人物】\n", 1)[1].split("\n\n", 1)[0]
    assert "港务局的眼线，只在雾天出现" in block  # 卷纲点名者进块（全量，无需换位）
    assert "见习导航员，不信教科书" in block  # 主角置顶不动
    lines = [ln for ln in block.splitlines() if ln.startswith("- ")]
    assert len(lines) == 7  # 全名单：角色表 7 张全进（SHALL NOT 截到 6 张）
    assert "船员6的专属人设标记" in block  # 队尾不再让位


def test_chapter_material_world_block_and_volume_cardless(client, monkeypatch):
    from sqlalchemy import select as _sel  # noqa: E402

    """c-plan-material-fullinfo：⑩ 世界观块（全量势力）＋⑥ 本卷无卡名单进拆章素材。"""
    from filesystem.storage import get_storage
    from models.chapter import ChapterCharacter  # noqa: E402

    pid = _seed_vol(client, target=6)

    async def _s():
        async with async_session() as session:
            vol = (await session.scalars(
                _sel(Volume).where(Volume.project_id == pid)
            )).first()
            ch = Chapter(project_id=pid, volume_id=vol.id, chapter_no=1,
                         ref="vol-1-ch-1", title="信标")
            session.add(ch)
            await session.flush()
            session.add(ChapterCharacter(chapter_id=ch.id, sort_order=0, character_name="哑叔"))
            await session.commit()

    _run_async(_s())

    async def _w():
        session = async_session()
        proj = await session.get(Novel, pid)
        root = proj.root_path
        await session.close()
        await get_storage().write_yaml(root, "settings/world-setting.yaml", {
            "stage": "灰港旧街区",
            "factions": [{"name": "夜巡守夜人", "note": "暗中向血族出售巡逻路线换取停战的官方巡护组织"}],
        })

    _run_async(_w())
    fake = _setup_ai(monkeypatch, _directions_reply())
    r = client.post(f"/api/novels/{pid}/volumes/vol-1/chapters/ai-directions", json={})
    assert r.status_code == 200, r.text
    system = fake.calls[-1]["system"]
    assert "【世界观】" in system and "出售巡逻路线换取停战" in system  # ⑩ 全量世界块
    assert "【无卡出场名单（本卷已拆章出现、未建卡）】" in system
    assert "哑叔（第1章）" in system  # 本卷口径
