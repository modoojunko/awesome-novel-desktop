"""volume-plan-ai — 分卷规划三端点契约（规划台 / 3 套方案 / 展开卷纲 / 卷纲体检）

矩阵：
- options 成功：2–3 套、四字段齐、focus_axis 互不相同、不落库、计量入账、出参含
  note/volume_estimate/warnings；申报未知实体 → warnings；两次校验失败 → 降级纯文本（不 502）；
- options 主线空：422 提示先完成主线，AI 不被触达、不计量；
- options 免费档：403（生成类归 PRO），AI 不被触达；
- expand 成功：四字段齐（四件事）＋ checks ≤3 ＋ plan_line 回显＋七条硬规则逐字入包；不落库；
- expand 缺四件事：重试一次后降级纯文本 ＋ 每次尝试计量；
- 体检：免费可用（三组、无章节时 none 占位、evidence 独立字段、判据逐字入包）、只读不拦；
- 升级路径：旧库缺 plan_line 列 → 经「新版本新建自己的库＋副本搬运」落位（不再就地补列）。

用法：
    cd client/backend
    python -m pytest tests/test_volume_plan_ai.py -v
"""

import asyncio
import json
import os
import tempfile
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient


def _rules_sections() -> tuple[str, str]:
    """与生产同源切分规则片段（逐字对拍用；源＝PROMPT_PACK_DEV_DIR，c-prompt-source-flip）。"""
    from prompts import load as _load

    src = _load("volume_rules")
    i = src.find("【体检判据】")
    return src[:i].strip(), src[i:].strip()

# ── Test environment (isolated temp DB + data root) ──────────────────────
_tmp_db = tempfile.NamedTemporaryFile(suffix="_vpa.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_volume_plan_ai_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

from sqlalchemy import select, text  # noqa: E402

import auth_local.service as _service  # noqa: E402
from auth_local.deps import require_novel_model  # noqa: E402
from auth_local.middleware import get_current_user  # noqa: E402
from db import async_session, get_db  # noqa: E402
from filesystem.storage import get_storage  # noqa: E402
from main import app  # noqa: E402
from models import Novel  # noqa: E402
from models.token_log import TokenLog  # noqa: E402
from models.user import User  # noqa: E402


def _layered_prompt(kwargs) -> str:
    """分层协议下的全文（system＋user 合并读——内容断言不关心落在哪一段）。"""
    return str(kwargs.get("system") or "") + "\n" + str(kwargs["messages"][0]["content"])


_CFG_PATH = os.path.join(_tmp_data_root, "config.json")
USER_ID = "vpa_user"

def _set_tier(tier: str, api_key: str = "sk-test"):
    _service.CONFIG_FILE = _CFG_PATH
    _service.save_local_config(
        {"tier": tier, "expires_at": _future_iso() if tier != "none" else "", "api_key": api_key}
    )


def _future_iso(days: int = 30) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).date().isoformat()


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
    # 本书模型门控：本模块测内容/其他门控，模型就绪另测
    app.dependency_overrides[require_novel_model] = lambda: True
    yield
    app.dependency_overrides.clear()


def _events(event_type: str) -> list[dict]:
    """本地事件表直查（度量断言用）：该类型事件的 payload 列表，按时间序。"""

    async def _s():
        async with async_session() as session:
            rows = (await session.execute(
                text("SELECT payload FROM events WHERE event_type = :t ORDER BY created_at"),
                {"t": event_type},
            )).all()
            return [json.loads(r[0]) for r in rows]

    return _run_async(_s())


def _ensure_user():
    """播种 USER_ID 的真实用户行——TokenLog 对 users/novels 有 FK（PRAGMA ON），
    record_usage 的 commit 异常会被静默回滚（计量断言将恒 0），必须先有用户行。
    幂等；建表发生在 TestClient lifespan，故在 _mk_project（client 已就绪）里调。"""

    async def _s():
        async with async_session() as session:
            if await session.get(User, USER_ID) is None:
                session.add(
                    User(id=USER_ID, email=f"{USER_ID}@test.local", password_hash="x")
                )
                await session.commit()

    _run_async(_s())


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


STORY_ARC = {
    "fullstory": "林野是旧街区的夜班巡护员，血案频发后被卷入猎杀血族之路；中段对抗升级，"
    "发现体内饥渴在喂养怪物；结局是清算之夜的对决与放下。",
    "ending": {
        "scene": "破晓前的旧街区，林野收刀靠在墙边",
        "hero": "活着，但不再完整",
        "tone": "带着寒意的释然",
    },
}

VALID_PLANS_SOURCE = {
    "plans": [
        {"spine": "林野为查身世与豢养派旧贵族做交易，代价是替他们清掉一个叛徒",
         "conflict": "想查真相，与双手沾血——清叛徒就是入伙",
         "ending": "他拿到情报，也第一次被人称为「刽子手」",
         "focus": "侧重代价——把「回不去」在这一卷里就付清",
         "focus_axis": "代价"},
        {"spine": "林野与豢养派旧贵族结盟换取线索，盟约里藏着互相利用",
         "conflict": "信谁，与防谁——盟约的每一条都对他有利也对他有害",
         "ending": "盟约成立，而他在盟约末尾发现自己的名字被排在牺牲一侧",
         "focus": "侧重关系——盟约的成立与代价",
         "focus_axis": "关系"},
        {"spine": "林野顺着身世线索追到旧档案，发现大火另有其人",
         "conflict": "想确认，与怕确认——答案如果不在这边，她追的到底是什么。",
         "focus": "侧重认知——问题的性质从求生变成求证",
         "focus_axis": "认知"},
    ],
    "note": "",
    "volume_estimate": "按结局的清算夜倒推，全书约 3 卷",
}

VALID_PLANS = json.dumps(VALID_PLANS_SOURCE, ensure_ascii=False)

VALID_EXPAND = json.dumps(
    {
        "name": "血酬",
        "summary": "林野为查身世跟豢养派旧贵族做交易，代价是替他们清掉一个叛徒。",
        "conflict": "想查真相，与双手沾血——清叛徒就是入伙。",
        "ending": "盟约里他的名字排在牺牲一侧，而他签了。",
        "antagonist_type": "人物",
        "antagonist_line": "执法官雷——点名要他停手",
        "plants": ["那把猎血短刃的来历被旧贵族提起"],
        "reveals": ["纵火的命令出自血族议会"],
        "chapter_target": 40,
        "checks": [
            "作者原句只提交易与清叛徒，未提身世真相是否在本卷揭晓，是否过快？",
            "叛徒身份需从既有势力里选，不添新人物。",
        ],
    },
    ensure_ascii=False,
)


class _FakeAIClient:
    def __init__(self, replies: list[str]):
        self._replies = list(replies)
        self._default = replies[-1] if replies else ""
        self.calls: list[dict] = []

    @property
    def last_kwargs(self) -> dict:
        return self.calls[-1] if self.calls else {}

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(kwargs.get("usage"), dict):
            kwargs["usage"].update({"tokens_in": 100, "tokens_out": 200})
        reply = self._replies.pop(0) if self._replies else self._default
        return reply


def _setup_ai(monkeypatch, replies: list[str]):
    fake = _FakeAIClient(replies)

    async def _factory(novel_id=None):
        return fake

    monkeypatch.setattr("volumes.ai_plan.get_ai_client_for_novel", _factory)
    return fake


# ── 夹具：建书 / 建卷 / 计数 ────────────────────────────────────────────────


def _mk_project(client, *, with_arc: bool = True) -> str:
    _ensure_user()
    name = f"vpa-{uuid.uuid4().hex[:6]}"
    r = client.post("/api/novels", json={"name": name})
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]
    if with_arc:

        async def _seed():
            session = async_session()
            proj = await session.get(Novel, pid)
            root = proj.root_path
            await session.close()
            story = await get_storage().read_yaml(root, "story.yaml") or {}
            story["story_arc"] = STORY_ARC
            await get_storage().write_yaml(root, "story.yaml", story)

        _run_async(_seed())
    return pid


def _volume_count(pid: str) -> int:
    async def _count():
        async with async_session() as session:
            rows = await session.execute(
                text("select count(*) from volumes where novel_id = :pid"), {"pid": pid}
            )
            return rows.scalar()

    return _run_async(_count())


def _token_log_count(pid: str) -> int:
    async def _count():
        async with async_session() as session:
            rows = await session.scalars(
                select(TokenLog).where(
                    TokenLog.user_id == USER_ID, TokenLog.project_id == pid
                )
            )
            return len(list(rows))

    return _run_async(_count())


# ═══════════════ 3 套可行走法 ═══════════════


class TestVolumeOptions:
    def test_success_returns_distinct_plans_and_not_persisted(self, client, monkeypatch):
        _set_tier("trial")
        pid = _mk_project(client)
        fake = _setup_ai(monkeypatch, [json.dumps(VALID_PLANS_SOURCE, ensure_ascii=False)])

        r = client.post(f"/api/novels/{pid}/volumes/ai/options", json={"line": ""})
        assert r.status_code == 200, r.text
        d = r.json()
        plans = d["plans"]
        assert 2 <= len(plans) <= 3
        axes = [p["focus_axis"] for p in plans]
        assert len(axes) == len(set(axes))  # 侧重轴互不相同
        for p in plans:
            assert p["spine"] and p["conflict"] and p["ending"] and p["focus"]
        # 不落库：卷数仍为 0
        assert _volume_count(pid) == 0
        # 计量入账
        assert _token_log_count(pid) >= 1
        # 出参契约：note / volume_estimate / warnings / similar
        assert "note" in d and "volume_estimate" in d
        assert d["similar"] is False
        assert d["warnings"] == []  # 申报实体 ⊆ 设定（本样本未申报 → 空差集）
        # 素材块顺序（spec：素材包顺序按端点写死）：主线在结局之前
        system = _layered_prompt(fake.last_kwargs)
        assert "清算" in system
        assert 0 <= system.find("【全书主线】") < system.find("【结局（作者写的）】")
        # 判定类预算：显式 4096（tasks 2.4；client 默认 1024 装不下三套 JSON）
        assert fake.calls[0]["max_tokens"] == 4096

    def test_unknown_declared_entity_becomes_warning(self, client, monkeypatch):
        """模型申报了设定里没有的势力 → 差集回传 warnings（不 422、不拦）。"""
        _set_tier("trial")
        pid = _mk_project(client)
        payload = {
            "plans": VALID_PLANS_SOURCE["plans"],
            "note": "",
            "volume_estimate": "约 3 卷",
            "cast": ["林野"],
            "factions": ["夜巡议会"],  # 设定里不存在
        }
        _setup_ai(monkeypatch, [json.dumps(payload, ensure_ascii=False)])
        r = client.post(f"/api/novels/{pid}/volumes/ai/options", json={"line": ""})
        assert r.status_code == 200, r.text
        assert any("夜巡议会" in w for w in r.json()["warnings"])

    def test_invalid_output_degrades_to_text_after_retry(self, client, monkeypatch):
        """两次校验失败 → 200 降级纯文本（spec：不 502），两次尝试都被计量。"""
        _set_tier("trial")
        pid = _mk_project(client)
        fake = _setup_ai(monkeypatch, [json.dumps({"plans": []})])
        r = client.post(f"/api/novels/{pid}/volumes/ai/options", json={"line": ""})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["degraded"] is True and d["text"] is not None
        assert len(fake.calls) == 2  # 重试一次
        assert _token_log_count(pid) >= 2  # 每次尝试都计量

    def test_mainline_empty_422_and_ai_not_called(self, client, monkeypatch):
        _set_tier("trial")
        pid = _mk_project(client)

        async def _strip_arc():
            session = async_session()
            proj = await session.get(Novel, pid)
            root = proj.root_path
            await session.close()
            story = await get_storage().read_yaml(root, "story.yaml") or {}
            story["story_arc"] = {}
            await get_storage().write_yaml(root, "story.yaml", story)

        _run_async(_strip_arc())
        fake = _setup_ai(monkeypatch, [json.dumps({"plans": []})])
        r = client.post(f"/api/novels/{pid}/volumes/ai/options", json={"line": ""})
        assert r.status_code == 422
        assert "主线" in r.json()["detail"]
        assert fake.calls == []  # AI 不被触达

    def test_free_tier_403_and_ai_not_called(self, client, monkeypatch):
        _set_tier("none")
        pid = "vpa-free"
        fake = _setup_ai(monkeypatch, [json.dumps({"plans": []})])
        r = client.post(f"/api/novels/{pid}/volumes/ai/options", json={"line": ""})
        assert r.status_code == 403
        assert fake.calls == []  # AI 不被触达（免费档生成类归 PRO）

    # ── 目标卷号解析（c-vol-options-prev-ending）：上一卷结尾按 vol_no 解析，缺省＝下一卷 ──

    def _seed_archived_chapter(self, pid: str, vol_no: int, chapter_no: int, summary: str) -> None:
        from models.chapter import Chapter
        from models.volume import Volume

        async def _s():
            async with async_session() as session:
                vol = (await session.execute(
                    select(Volume).where(Volume.project_id == pid, Volume.volume_no == vol_no)
                )).scalar_one()
                session.add(Chapter(
                    project_id=pid, volume_id=vol.id, chapter_no=chapter_no,
                    ref=f"vol-{vol_no}-ch-{chapter_no}", title=f"第{chapter_no}章",
                    status="archived", summary=summary,
                ))
                await session.commit()

        _run_async(_s())

    def _prev_block(self, prompt: str) -> str:
        """【上一卷的结尾】块单独摘出（user 段）——system 规则与【已拆卷】里也出现
        各卷卷末字样，须从最后一处标记切，再截到【作者这一卷的想法】。"""
        tail = prompt.rsplit("【上一卷的结尾】", 1)[1]
        return tail.split("【作者这一卷的想法】")[0]

    def test_explicit_vol_no_uses_actual_archived_ending(self, client, monkeypatch):
        """①vol_no=2 且第 1 卷有归档章 → 注入实际收尾（非主线起步）。"""
        _set_tier("trial")
        pid = _mk_project(client)
        client.post(f"/api/novels/{pid}/volumes", json={"title": "血酬", "ending": "盟约成立，他签了"})
        self._seed_archived_chapter(pid, 1, 12, "信标当众暴露，舰队连夜改航")
        fake = _setup_ai(monkeypatch, [VALID_PLANS])
        r = client.post(f"/api/novels/{pid}/volumes/ai/options", json={"line": "", "vol_no": 2})
        assert r.status_code == 200, r.text
        prev = self._prev_block(_layered_prompt(fake.last_kwargs))
        assert "信标当众暴露" in prev
        assert "第1卷 · 实际收尾（第12章）" in prev
        assert "来自主线全景" not in prev  # 不再是首卷口径

    def test_default_vol_no_falls_back_to_next(self, client, monkeypatch):
        """②缺省 vol_no → max+1（与 expand 同构）：既有 1 卷时按第 2 卷解析＝第 1 卷预期结局。"""
        _set_tier("trial")
        pid = _mk_project(client)
        client.post(f"/api/novels/{pid}/volumes", json={"title": "血酬", "ending": "盟约成立，他签了"})
        fake = _setup_ai(monkeypatch, [VALID_PLANS])
        r = client.post(f"/api/novels/{pid}/volumes/ai/options", json={"line": ""})
        assert r.status_code == 200, r.text
        prev = self._prev_block(_layered_prompt(fake.last_kwargs))
        assert "盟约成立，他签了" in prev
        assert "第1卷 · 预期结局" in prev

    def test_first_volume_uses_fullstory_start(self, client, monkeypatch):
        """③空书缺省（max=0→1）与显式 vol_no=1 都走主线全景起步，第一卷行为不变。"""
        _set_tier("trial")
        pid = _mk_project(client)
        fake = _setup_ai(monkeypatch, [VALID_PLANS])
        for body in ({"line": ""}, {"line": "", "vol_no": 1}):
            r = client.post(f"/api/novels/{pid}/volumes/ai/options", json=body)
            assert r.status_code == 200, r.text
            assert "来自主线全景" in self._prev_block(_layered_prompt(fake.last_kwargs))

    def test_replan_existing_volume_never_self_feeds(self, client, monkeypatch):
        """④重规划已有卷 vol_no=2 → 注入第 1 卷收尾＋来源标注，不把本卷卷末当进场。"""
        _set_tier("trial")
        pid = _mk_project(client)
        client.post(f"/api/novels/{pid}/volumes", json={"title": "血酬", "ending": "第1卷的收尾锚点"})
        client.post(f"/api/novels/{pid}/volumes", json={"title": "长夜", "ending": "第2卷自己的卷末"})
        fake = _setup_ai(monkeypatch, [VALID_PLANS])
        r = client.post(f"/api/novels/{pid}/volumes/ai/options", json={"line": "", "vol_no": 2})
        assert r.status_code == 200, r.text
        prev = self._prev_block(_layered_prompt(fake.last_kwargs))
        assert "第1卷的收尾锚点" in prev
        assert "第1卷 · 预期结局" in prev  # 来源标注钉：恒 1 口径下这里是「第一卷 · 来自主线全景」
        assert "第2卷自己的卷末" not in prev

    def test_prev_volume_deleted_gives_placeholder(self, client, monkeypatch):
        """⑤vol_no=3 且第 2 卷已删 → 「（上一卷不存在）」占位，不 500。"""
        _set_tier("trial")
        pid = _mk_project(client)
        client.post(f"/api/novels/{pid}/volumes", json={"title": "血酬"})
        client.post(f"/api/novels/{pid}/volumes", json={"title": "长夜"})
        r_del = client.delete(f"/api/novels/{pid}/volumes/vol-2")
        assert r_del.status_code == 200, r_del.text
        fake = _setup_ai(monkeypatch, [VALID_PLANS])
        r = client.post(f"/api/novels/{pid}/volumes/ai/options", json={"line": "", "vol_no": 3})
        assert r.status_code == 200, r.text
        assert "（上一卷不存在）" in self._prev_block(_layered_prompt(fake.last_kwargs))


# ═══════════════ 展开卷纲草稿 ═══════════════


class TestVolumeExpand:
    def test_success_returns_draft_and_not_persisted(self, client, monkeypatch):
        _set_tier("trial")
        pid = _mk_project(client)
        fake = _setup_ai(monkeypatch, [VALID_EXPAND])
        line = "林野为查身世，跟豢养派的旧贵族做交易拿情报，代价是替他们清掉一个叛徒"
        r = client.post(f"/api/novels/{pid}/volumes/ai/expand", json={"line": line})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["vol_no"] >= 1  # 出参不再回显 plan_line（已退役）
        draft = d["draft"]
        for k in ("name", "summary", "conflict", "ending", "chapter_target"):
            assert draft[k], f"{k} 不应为空"
        assert "goal" not in draft  # 字段瘦身：草稿不再产出「整体目标」
        assert draft["antagonist_type"] in ("人物", "难题", "环境", "自我", "势力", "")
        assert 0 <= len(draft["checks"]) <= 3
        # 不落库：卷数仍为 0（采纳才写卷表）
        assert _volume_count(pid) == 0
        # 计量入账
        assert _token_log_count(pid) >= 1
        # 素材包含上一卷的结尾与作者那一句；七条硬规则逐字入包（文本单源对拍）
        system = _layered_prompt(fake.last_kwargs)
        assert "上一卷的结尾" in system
        assert line in system
        hard, _crit = _rules_sections()
        assert hard in system

    def test_empty_line_422(self, client, monkeypatch):
        _set_tier("trial")
        pid = _mk_project(client)
        r = client.post(f"/api/novels/{pid}/volumes/ai/expand", json={"line": ""})
        assert r.status_code == 422
        assert "先写一句" in r.json()["detail"]

    def test_incomplete_fields_degrade_and_metering(self, client, monkeypatch):
        _set_tier("trial")
        pid = _mk_project(client)
        # 只回 summary 的残缺输出 → 重试一次后降级纯文本（spec：不 502）＋ 计量留痕
        fake = _setup_ai(monkeypatch, [json.dumps({"summary": "只有主旨"}, ensure_ascii=False)])
        r = client.post(
            f"/api/novels/{pid}/volumes/ai/expand", json={"line": "林野第一次主动出城"}
        )
        assert r.status_code == 200
        assert r.json()["degraded"] is True
        assert len(fake.calls) == 2
        assert _token_log_count(pid) >= 2  # 两次尝试都留痕


# ═══════════════ 卷纲体检（标准档起，c-tier-gating-completion 收门）═══════════════


class TestVolumeCheck:
    def test_three_groups_and_none_placeholder(self, client, monkeypatch):
        # 报告形状钉：三组齐、零章节 none 占位、证据独立字段、判据逐字入包。
        # 卷体检归 ai-plan（标准档起）——原「免费档能 200 即证明不挂门禁」断言随四档
        # 收门翻转；免费 403 由 tests/test_ai_feature_http.py 钉。
        _set_tier("trial")
        pid = _mk_project(client)
        r = client.post(f"/api/novels/{pid}/volumes", json={"title": "第一卷"})
        assert r.status_code in (200, 201), r.text

        reply = json.dumps(
            {
                "groups": [
                    {"name": "对主线", "items": [
                        {"status": "ok", "text": "进场接得上全景的「他从哪起步」。", "evidence": "预期结局"},
                        {"status": "warn", "text": "卷末偏虚：只是状态描述，缺看得见的代价。", "evidence": "预期结局"},
                    ]},
                    {"name": "对设定", "items": [
                        {"status": "warn", "text": "伏笔与台账 H-0001 是同一件事，重复埋。", "evidence": "H-0001"},
                    ]},
                    {"name": "对已写内容", "items": [
                        {"status": "none", "text": "还没有章节——写到之后，这里换成实际写出来的对照。"},
                    ]},
                ]
            },
            ensure_ascii=False,
        )
        fake = _setup_ai(monkeypatch, [reply])
        # trial 含 ai-plan 过档位门（体检随时可重复、只读不拦语义不变）
        r = client.post(f"/api/novels/{pid}/volumes/vol-1/ai/check")
        assert r.status_code == 200, r.text
        d = r.json()["report"]
        names = [g["name"] for g in d]
        assert names == ["对主线", "对设定", "对已写内容"]
        flat = [it for g in d for it in g["items"]]
        statuses = {it["status"] for it in flat}
        assert statuses <= {"ok", "warn", "none"}
        assert any(it["status"] == "none" for it in flat)  # 第三组占位
        # 证据独立字段（spec：供代码侧断言）
        assert any(it.get("evidence") == "H-0001" for it in flat)
        # 体检判据逐字入包（文本单源对拍）
        _hard, crit = _rules_sections()
        assert crit in _layered_prompt(fake.last_kwargs)


class TestCheckRunEvent:
    def test_check_logs_check_run_with_warn(self, client, monkeypatch):
        """度量（PRD §7）：check_run{warn} 判据条数由服务端数出来。"""
        _set_tier("trial")
        pid = _mk_project(client)
        client.post(f"/api/novels/{pid}/volumes", json={"title": "第一卷"})
        reply = json.dumps(
            {
                "groups": [
                    {"name": "对主线", "items": [
                        {"status": "warn", "text": "坎未填。", "evidence": "对抗物"},
                        {"status": "ok", "text": "进场接得上。", "evidence": "进场"},
                    ]},
                    {"name": "对设定", "items": [
                        {"status": "warn", "text": "伏笔重复埋。", "evidence": "H-0001"},
                        {"status": "none", "text": "还没有章节。"},
                    ]},
                ]
            },
            ensure_ascii=False,
        )
        _setup_ai(monkeypatch, [reply])
        before = len(_events("check_run"))  # 模块级共享库：只看本次新增
        r = client.post(f"/api/novels/{pid}/volumes/vol-1/ai/check")
        assert r.status_code == 200, r.text
        assert _events("check_run")[before:] == [{"vol_no": 1, "warn": 2}]


class TestPlanAnchor:
    def test_first_volume_anchor_from_synopsis(self, client):
        """首卷锚点＝全景起步（story.yaml.story_arc.fullstory 前段）。"""
        _set_tier("trial")
        pid = _mk_project(client)
        r = client.get(f"/api/novels/{pid}/volumes/plan-anchor?vol_no=1")
        assert r.status_code == 200, r.text
        d = r.json()["prev_ending"]
        assert "林野" in d["text"]  # 全景起步句
        assert "第一卷" in d["source"]

    def test_second_volume_anchor_requires_prev(self, client):
        _set_tier("trial")
        pid = _mk_project(client)
        r = client.get(f"/api/novels/{pid}/volumes/plan-anchor?vol_no=2")
        assert r.status_code == 200, r.text
        assert "上一卷不存在" in r.json()["prev_ending"]["text"]


# ═══════════════ 升级路径（c-db-per-version：代内补列已退役）═══════════════


class TestMigrationNoInPlaceDdl:
    def test_additive_chain_retired(self):
        """`ADDITIVE_COLUMNS`/`apply_additive_columns` 随版本化命名退役。

        列/表形状变化不再就地补列，改由「新版本新建自己的库 + 从旧库副本搬运」
        承接（列交集 + 中性回填）——所以这两个符号必须不存在（防回归：任何形式
        的就地 ALTER 都是数据风险）。
        """
        import db_lifecycle

        assert not hasattr(db_lifecycle, "ADDITIVE_COLUMNS")
        assert not hasattr(db_lifecycle, "apply_additive_columns")

    def test_old_library_without_plan_line_migrates_with_backfill(self, tmp_path):
        """旧库缺 plan_line 列 → 搬运到新库后该列存在且旧行可读（中性回填）。"""
        import sqlite3

        from sqlalchemy import create_engine as _create_engine

        import models  # noqa: F401 —— 注册全表
        from db import Base
        from db_lifecycle import compute_schema_fingerprint
        from migration.engine import run_migration
        from schema_version import db_filename_for

        cur = db_filename_for("0.25")
        active = tmp_path / cur
        se = _create_engine(f"sqlite:///{active}")
        Base.metadata.create_all(se)
        se.dispose()

        old = tmp_path / "novel-v0.24.db"
        conn = sqlite3.connect(old)
        conn.execute(
            "CREATE TABLE novels (id TEXT PRIMARY KEY, user_id TEXT, name TEXT, slug TEXT,"
            " root_path TEXT, current_phase TEXT, status TEXT, total_volumes INTEGER,"
            " total_chapters INTEGER, created_at TIMESTAMP, updated_at TIMESTAMP)"
        )
        conn.execute(
            "CREATE TABLE volumes (id TEXT PRIMARY KEY, novel_id TEXT, volume_no INTEGER,"
            " title TEXT, summary TEXT, chapter_count INTEGER, created_at TIMESTAMP,"
            " updated_at TIMESTAMP)"  # 旧库无 plan_line
        )
        conn.execute(
            "INSERT INTO novels VALUES ('n1','u1','书','s','./data/s','write','active',1,1,"
            "'2026-01-01 00:00:00','2026-01-02 00:00:00')"
        )
        conn.execute(
            "INSERT INTO volumes VALUES ('v1','n1',1,'第一卷','概要',0,"
            "'2026-01-01 00:00:00','2026-01-02 00:00:00')"
        )
        conn.commit()
        conn.close()

        rep = run_migration(tmp_path, "novel-v0.24.db", active)
        assert rep["status"] == "ok", rep
        con = sqlite3.connect(f"file:{active}?mode=ro", uri=True)
        try:
            cols = [r[1] for r in con.execute("PRAGMA table_info(volumes)")]
            row = con.execute("SELECT volume_no, title, plan_line FROM volumes").fetchone()
        finally:
            con.close()
        assert "plan_line" in cols, "新库自带该列（create_all 全量）"
        assert row == (1, "第一卷", None), "旧行经列交集搬运过来，缺列按中性值落位"
        assert rep["source_version"] == "0.24"
        # 源库不被就地 DDL（字节不变由引擎测试覆盖；此处钉列集合不变）
        con = sqlite3.connect(f"file:{old}?mode=ro", uri=True)
        try:
            src_cols = [r[1] for r in con.execute("PRAGMA table_info(volumes)")]
        finally:
            con.close()
        assert "plan_line" not in src_cols, "源库绝不被就地补列"
        assert compute_schema_fingerprint(Base.metadata)


# ═══════════════ c-volume-antagonist：迁移/聚合/退役/batch ═══════════════


class TestAntagonistColumns:
    """对抗物/坎字段的升级路径＝**新的库名 + 副本搬运**（代内补列已退役）。

    等价断言替换旧的两条（旧库缺列 → apply_additive_columns 补齐 → ORM 读写）：
    新库自带宽列（create_all 全量建出），旧库经搬运把行带过来、缺列按中性值落位。
    """

    def test_fresh_library_has_columns(self, tmp_path):
        import sqlite3 as _sq

        from sqlalchemy import create_engine as _ce

        import models  # noqa: F401
        from db import Base

        fresh = tmp_path / "novel-v0.25.db"
        se = _ce(f"sqlite:///{fresh}")
        Base.metadata.create_all(se)
        se.dispose()
        con = _sq.connect(f"file:{fresh}?mode=ro", uri=True)
        try:
            vcols = [r[1] for r in con.execute("PRAGMA table_info(volumes)")]
            hcols = [r[1] for r in con.execute("PRAGMA table_info(novel_hooks)")]
        finally:
            con.close()
        assert "antagonist_type" in vcols and "antagonist_line" in vcols
        assert "planned_volume_no" in hcols

    def test_old_library_migrates_without_in_place_ddl(self, tmp_path):
        """旧库缺 antagonist/坎列 → 搬运到新库后列在、旧行可读；源库零改动。"""
        import sqlite3 as _sq

        from sqlalchemy import create_engine as _ce

        import models  # noqa: F401
        from db import Base
        from migration.engine import run_migration
        from schema_version import db_filename_for

        active = tmp_path / db_filename_for("0.25")
        se = _ce(f"sqlite:///{active}")
        Base.metadata.create_all(se)
        se.dispose()

        old = tmp_path / "novel-v0.24.db"
        con = _sq.connect(old)
        con.execute("CREATE TABLE novels (id TEXT PRIMARY KEY, user_id TEXT, name TEXT)")
        con.execute("CREATE TABLE volumes (id TEXT PRIMARY KEY, novel_id TEXT, volume_no INTEGER,"
                    " title TEXT, summary TEXT, chapter_count INTEGER, plan_line VARCHAR(150))")
        con.execute("INSERT INTO novels (id, user_id, name) VALUES ('n1','u1','旧书')")
        con.execute("INSERT INTO volumes (id, novel_id, volume_no, title, summary, chapter_count,"
                    " plan_line) VALUES ('v1','n1',1,'第一卷','概要',0,NULL)")
        con.commit()
        con.close()
        before_cols = None

        rep = run_migration(tmp_path, "novel-v0.24.db", active)
        assert rep["status"] == "ok", rep
        con = _sq.connect(f"file:{active}?mode=ro", uri=True)
        try:
            vcols = [r[1] for r in con.execute("PRAGMA table_info(volumes)")]
            row = con.execute("SELECT volume_no, title, antagonist_type FROM volumes").fetchone()
        finally:
            con.close()
        assert "antagonist_type" in vcols, "新库自带宽列"
        assert row == (1, "第一卷", None), "旧行经列交集搬运，缺列中性落位"
        con = _sq.connect(f"file:{old}?mode=ro", uri=True)
        try:
            before_cols = [r[1] for r in con.execute("PRAGMA table_info(volumes)")]
        finally:
            con.close()
        assert "antagonist_type" not in before_cols, "源库绝不被就地补列（无就地 DDL 路径）"


class TestRetiredKeys:
    def test_put_rejects_retired_keys_422(self, client):
        _set_tier("trial")
        pid = _mk_project(client)
        client.post(f"/api/novels/{pid}/volumes", json={"title": "第一卷"})
        r = client.put(f"/api/novels/{pid}/volumes/vol-1", json={"goal": "x"})
        assert r.status_code == 422
        assert "退役" in r.text
        r2 = client.put(f"/api/novels/{pid}/volumes/vol-1", json={"plants": ["a"]})
        assert r2.status_code == 422

    def test_goal_merged_into_ending_tail(self, client):
        """旧卷 goal 非空 → GET 卷纲 ending 尾句并入、goal 不再独立回显。"""
        _set_tier("trial")
        pid = _mk_project(client)
        client.post(f"/api/novels/{pid}/volumes", json={"title": "第一卷"})

        async def seed():
            async with async_session() as s:
                from sqlalchemy import text as _t
                await s.execute(_t(
                    "UPDATE volumes SET goal='局面：她没有退路' WHERE novel_id=:p"
                ), {"p": pid})
                await s.commit()

        _run_async(seed())
        r = client.get(f"/api/novels/{pid}/volumes/vol-1")
        d = r.json()
        assert "局面：她没有退路" in d.get("ending", "")
        assert "goal" not in d and "template_name" not in d and "plan_line" not in d
        assert "plants" not in d and "reveals" not in d

        # 幂等（检视 P1-3）：读到的 ending（已并 goal）原样存回 → 不得再拼一遍；
        # 固化时顺手清 goal 列，此后 GET 稳定。
        merged = d["ending"]
        client.put(f"/api/novels/{pid}/volumes/vol-1", json={"ending": merged})
        d2 = client.get(f"/api/novels/{pid}/volumes/vol-1").json()
        assert d2["ending"] == merged
        assert d2["ending"].count("局面：她没有退路") == 1
        # 再存一次（第二次保存）也不重复
        client.put(f"/api/novels/{pid}/volumes/vol-1", json={"ending": d2["ending"]})
        d3 = client.get(f"/api/novels/{pid}/volumes/vol-1").json()
        assert d3["ending"] == merged


class TestAggregateCast:
    def _mkvol_with_ch(self, client):
        _set_tier("trial")
        pid = _mk_project(client)
        client.post(f"/api/novels/{pid}/volumes", json={"title": "第一卷"})
        return pid

    def test_no_chapters_empty_array(self, client):
        pid = self._mkvol_with_ch(client)
        d = client.get(f"/api/novels/{pid}/volumes/vol-1").json()
        assert d["cast_members"] == []

    def test_chapter_chars_aggregate_and_villain(self, client):
        pid = self._mkvol_with_ch(client)
        client.post(f"/api/novels/{pid}/volumes/vol-1/chapters", json={"title": "第一章"})
        client.put(f"/api/novels/{pid}/volumes/vol-1", json={
            "antagonist_type": "人物", "antagonist_line": "执法官雷——点名要他停手"})
        # 章纲出场角色（经章对象写入链——直接进 outline.characters）
        ch_ref = client.get(f"/api/novels/{pid}/volumes").json()[0]["chapters"][0]["ref"]
        client.put(f"/api/novels/{pid}/chapters/{ch_ref}", json={
            "outline": {"summary": "x", "characters": ["林野", "老聋", "执法官雷"]}})
        d = client.get(f"/api/novels/{pid}/volumes/vol-1").json()
        names = [c["name"] for c in d["cast_members"]]
        assert names == ["林野", "老聋", "执法官雷"]  # 去重保序
        villain = next(c for c in d["cast_members"] if c["name"] == "执法官雷")
        assert villain["role"] == "反派"
        assert all(c["role"] == "" for c in d["cast_members"] if c["name"] != "执法官雷")

    def test_protagonist_pinned_first_and_ghost_excluded(self, client):
        """主角置顶（聚合集里有时排最前）＋旧稿支线章不参与（检视 P1-6）。"""
        pid = self._mkvol_with_ch(client)
        # 主角卡：走角色表（role='主角' 唯一索引）
        r = client.post(f"/api/novels/{pid}/characters", json={
            "name": "林野", "role": "主角", "brief": "夜班巡护员"})
        assert r.status_code in (200, 201), r.text
        client.post(f"/api/novels/{pid}/volumes/vol-1/chapters", json={"title": "第一章"})
        ch_ref = client.get(f"/api/novels/{pid}/volumes").json()[0]["chapters"][0]["ref"]
        client.put(f"/api/novels/{pid}/chapters/{ch_ref}", json={
            "outline": {"summary": "x", "characters": ["老聋", "林野"]}})
        d = client.get(f"/api/novels/{pid}/volumes/vol-1").json()
        assert [c["name"] for c in d["cast_members"]] == ["林野", "老聋"]  # 主角置顶

        # 旧稿支线章（ghost_of 非空）的出场角色不入聚合
        async def _ghost():
            async with async_session() as s:
                from sqlalchemy import text as _t
                await s.execute(_t(
                    "UPDATE chapters SET ghost_of='vol-1-ch-1' WHERE ref=:r"
                ), {"r": ch_ref})
                await s.commit()

        _run_async(_ghost())
        d2 = client.get(f"/api/novels/{pid}/volumes/vol-1").json()
        assert d2["cast_members"] == []
        assert d2["ghost_count"] == 1


class TestHooksBatch:
    def test_batch_dedup_and_create(self, client):
        _set_tier("trial")
        pid = _mk_project(client)
        # 先建一条 active
        client.post(f"/api/novels/{pid}/hooks", json={"description": "信标的应答周期与三百年前记录不一致"})
        r = client.post(f"/api/novels/{pid}/hooks/batch", json={"items": [
            {"description": "信标的应答周期与三百年前的记录不一致", "planned_volume_no": 2},  # 近似重复
            {"description": "老聋在启航前夜出现在港口的理由", "planned_volume_no": 1},  # 全新
        ]})
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert len(d["created"]) == 1 and d["created"][0]["code"].startswith("#H-")
        assert len(d["skipped"]) == 1
        assert d["skipped"][0]["reason"] == "duplicate"
        assert d["skipped"][0]["existing_code"] == "#H-0001"
        # planned_volume_no 落库回读
        hooks = client.get(f"/api/novels/{pid}/hooks").json()["data"]["items"]
        planned = [h for h in hooks if h["planned_volume_no"] == 1]
        assert planned and planned[0]["description"].startswith("老聋")

    def test_batch_empty_items(self, client):
        _set_tier("trial")
        pid = _mk_project(client)
        r = client.post(f"/api/novels/{pid}/hooks/batch", json={"items": []})
        assert r.status_code == 200
        assert r.json()["data"] == {"created": [], "skipped": []}

    def test_batch_logs_hooks_registered_event(self, client):
        """度量（PRD §7）：入册与查重拦截都落本地 events 表（服务端才知道查重结果）。"""
        _set_tier("trial")
        pid = _mk_project(client)
        client.post(
            f"/api/novels/{pid}/hooks",
            json={"description": "信标的应答周期与三百年前记录不一致"},
        )
        before = len(_events("hooks_registered"))  # 模块级共享库：只看本次新增
        client.post(f"/api/novels/{pid}/hooks/batch", json={"items": [
            {"description": "信标的应答周期与三百年前的记录不一致"},  # 重复
            {"description": "老聋在启航前夜出现在港口的理由"},  # 全新
        ]})
        assert _events("hooks_registered")[before:] == [{"created": 1, "dupe_skipped": 1}]


class TestMetricsEvents:
    """度量落点（PRD §7 / tasks 5.3）：前端意图事件白名单 + 总开关 + 体检事件。"""

    def test_client_event_whitelist(self, client):
        _set_tier("trial")
        _mk_project(client)
        ok = client.post("/api/events", json={
            "event_type": "plan_entry_open", "payload": {"tier": "pro"},
        })
        assert ok.status_code == 200 and ok.json()["ok"] is True
        assert _events("plan_entry_open") == [{"tier": "pro"}]
        # 白名单外一律 422（不做通用写入口）
        bad = client.post("/api/events", json={"event_type": "whatever"})
        assert bad.status_code == 422
        assert _events("whatever") == []

    def test_payload_must_be_object(self, client):
        _set_tier("trial")
        _mk_project(client)
        r = client.post("/api/events", json={"event_type": "pick_select", "payload": "x"})
        assert r.status_code == 200
        assert _events("pick_select") == [{}]

    def test_switch_off_writes_nothing(self, client, monkeypatch):
        """可关（PRD §7）：NOVEL_EVENTS=off → 收下不落库。"""
        _set_tier("trial")
        _mk_project(client)
        monkeypatch.setenv("NOVEL_EVENTS", "off")
        r = client.post("/api/events", json={"event_type": "desk_expand", "payload": {}})
        assert r.status_code == 200 and r.json()["skipped"] is True
        assert _events("desk_expand") == []


# ═══════════════ c-volume-antagonist 2.x：契约扩展 ═══════════════


class TestReviewFixes:
    """检视整改回归（P2-5/P2-6/P2-1）：闭集、坎名字入差集、同毫秒双条不撞主键。"""

    def test_sanitize_plans_content_fields_pass_through_complete(self):
        """c-field-truncation-alignment 终版：spine/conflict/ending/antagonist_line
        完整直通（旧 40/40/40/150 硬切退役）——超长内容逐字保留进卡与提示词。"""
        from volumes.ai_plan import _sanitize_plans

        long_conflict = "教" * 300
        long_ending = "局" * 400
        parsed = {"plans": [
            {"spine": "甲", "conflict": long_conflict, "ending": long_ending,
             "antagonist_line": "坎" * 200, "focus_axis": "代价"},
            {"spine": "乙", "conflict": "c2", "ending": "e2", "focus_axis": "关系"},
        ]}
        out = _sanitize_plans(parsed)
        assert out is not None
        assert out["plans"][0]["conflict"] == long_conflict
        assert out["plans"][0]["ending"] == long_ending
        assert out["plans"][0]["antagonist_line"] == "坎" * 200

    def test_options_focus_axis_closed_set(self, client, monkeypatch):
        """模型自造侧重轴不收（FR-2 闭集）。"""
        from volumes.ai_plan import FOCUS_AXES, _sanitize_plans

        parsed = {"plans": [
            {"spine": "甲", "conflict": "c", "ending": "e", "focus_axis": "自造轴A"},
            {"spine": "乙", "conflict": "c", "ending": "e", "focus_axis": "自造轴B"},
        ]}
        out = _sanitize_plans(parsed)
        assert out is not None
        assert all(p["focus_axis"] in FOCUS_AXES for p in out["plans"])

    def test_options_warns_invented_antagonist_name(self, client, monkeypatch):
        """坎（人物型）点到的名字不在设定里 → warnings 提示（不再只靠 cast 字段）。"""
        from volumes.ai_plan import _antagonist_candidates

        assert _antagonist_candidates([
            {"antagonist_type": "人物", "antagonist_line": "执法官雷——点名要他停手"},
            {"antagonist_type": "难题", "antagonist_line": "信号封装层"},
            {"antagonist_type": "势力", "antagonist_line": "拾荒船队·规矩不同"},
        ]) == ["执法官雷", "拾荒船队"]

        _set_tier("trial")
        pid = _mk_project(client)
        plans = json.dumps({
            "plans": [
                {"spine": "甲", "conflict": "c", "ending": "e", "focus_axis": "代价",
                 "antagonist_type": "人物", "antagonist_line": "凭空捏造将军——要他停手"},
                {"spine": "乙", "conflict": "c", "ending": "e", "focus_axis": "关系",
                 "antagonist_type": "难题", "antagonist_line": "信号的封装层"},
            ],
            "cast": [], "factions": [], "note": "", "volume_estimate": "",
        }, ensure_ascii=False)
        _setup_ai(monkeypatch, [plans])
        r = client.post(f"/api/novels/{pid}/volumes/ai/options", json={"line": ""})
        assert r.status_code == 200, r.text
        assert any("凭空捏造将军" in w for w in r.json()["warnings"])

    def test_events_same_millisecond_both_persist(self, client):
        """同一用户同一毫秒两条事件都要落库（旧主键 {ms}_{uid} 会撞 UNIQUE 丢一条）。"""
        _set_tier("trial")
        _mk_project(client)
        before = len(_events("desk_manual_create"))
        for _ in range(2):
            client.post("/api/events", json={
                "event_type": "desk_manual_create", "payload": {"vol_no": 1}})
        rows = _events("desk_manual_create")
        assert len(rows) - before == 2


class TestReviewFixes2:
    """第二轮检视整改回归（卷名兜底）。"""

    def test_create_volume_empty_title_falls_back(self, client):
        """卷名可空：服务端兜底「第N卷」（VolumeCreate.title 已放宽为空）。"""
        _set_tier("trial")
        pid = _mk_project(client)
        r = client.post(f"/api/novels/{pid}/volumes", json={})
        assert r.status_code in (200, 201), r.text
        d = client.get(f"/api/novels/{pid}/volumes").json()
        assert d[0]["title"] == "第1卷"
        # 第二卷同样兜底（不因空名撞 UNIQUE/空标题）
        client.post(f"/api/novels/{pid}/volumes", json={"title": "   "})
        d2 = client.get(f"/api/novels/{pid}/volumes").json()
        assert [v["title"] for v in d2] == ["第1卷", "第2卷"]


class TestBossStepHint:
    """FR-11 boss 台阶提示：玄幻/都市系卷体检素材含，其余题材不含；
    且不落共享题材段（写章链 system 同源，不能跟着变）。"""

    @pytest.mark.parametrize(
        ("genre", "expect"),
        [("玄幻奇幻", True), ("都市日常", True), ("悬疑推理", False), ("", False)],
    )
    def test_hint_by_genre(self, client, monkeypatch, genre, expect):
        from genres.service import build_genre_section
        from volumes.ai_plan import _boss_step_hint

        # 助手单测（纯函数，不依赖 DB）
        assert bool(_boss_step_hint(genre)) is expect
        # 共享题材段不含这条（写章链与卷链共用同一份题材注入 → 只能在本模块追加）
        assert "BOSS" not in build_genre_section({"theme": genre, "sub_genre": ""})

    def test_check_material_includes_hint_for_fantasy(self, client, monkeypatch):
        _set_tier("trial")
        pid = _mk_project(client)
        client.post(f"/api/novels/{pid}/volumes", json={"title": "第一卷"})

        async def _seed_genre():
            async with async_session() as s:
                proj = await s.get(Novel, pid)
                root = proj.root_path
                await s.close()
                story = await get_storage().read_yaml(root, "story.yaml") or {}
                story["genre"] = "玄幻奇幻"
                await get_storage().write_yaml(root, "story.yaml", story)

        _run_async(_seed_genre())
        reply = json.dumps(
            {"groups": [
                {"name": "对主线", "items": [{"status": "ok", "text": "接得上。", "evidence": "进场"}]},
                {"name": "对设定", "items": [{"status": "ok", "text": "无冲突。"}]},
            ]},
            ensure_ascii=False,
        )
        fake = _setup_ai(monkeypatch, [reply])
        r = client.post(f"/api/novels/{pid}/volumes/vol-1/ai/check")
        assert r.status_code == 200, r.text
        assert "BOSS" in _layered_prompt(fake.calls[0])  # 分层：boss 提示随卷纲在 user 段


class TestContractExpansion:
    def test_expand_carried_answers_win(self, client, monkeypatch):
        """卡面/手写已答的四问带入 expand → 出参不被 AI 覆盖（作家答案胜出）。"""
        _set_tier("trial")
        pid = _mk_project(client)
        _setup_ai(monkeypatch, [VALID_EXPAND])
        r = client.post(f"/api/novels/{pid}/volumes/ai/expand", json={
            "line": "林野为查身世做交易",
            "conflict": "作家定的冲突",
            "antagonist_type": "人物",
            "antagonist_line": "执法官雷——点名要他停手",
            "ending": "作家定的卷末",
        })
        assert r.status_code == 200, r.text
        d = r.json()["draft"]
        assert d["conflict"] == "作家定的冲突"
        assert d["antagonist_type"] == "人物" and "执法官雷" in d["antagonist_line"]
        assert d["ending"] == "作家定的卷末"

    def test_options_plans_carry_antagonist_and_type_fallback(self, client, monkeypatch):
        """每套出参带 antagonist 两字段；类型非法回退「人物」。"""
        _set_tier("trial")
        pid = _mk_project(client)
        payload = {
            "plans": [
                {"spine": "走向甲", "conflict": "c", "ending": "e", "focus_axis": "代价",
                 "antagonist_type": "宇宙怪物", "antagonist_line": "雾带"},
                {"spine": "走向乙", "conflict": "c", "ending": "e", "focus_axis": "关系",
                 "antagonist_line": "账房"},
            ],
            "note": "", "volume_estimate": "",
        }
        _setup_ai(monkeypatch, [json.dumps(payload, ensure_ascii=False)])
        r = client.post(f"/api/novels/{pid}/volumes/ai/options", json={"line": ""})
        assert r.status_code == 200
        plans = r.json()["plans"]
        assert plans[0]["antagonist_type"] == "人物"  # 非法回退
        assert plans[0]["antagonist_line"] == "雾带"
        assert plans[1]["antagonist_type"] == ""  # 未填留空
        assert plans[1]["antagonist_line"] == "账房"

    def test_options_answered_goes_into_system(self, client, monkeypatch):
        """四问已答作为约束素材进 prompt（作家答过的不被改写）。"""
        _set_tier("trial")
        pid = _mk_project(client)
        fake = _setup_ai(monkeypatch, [json.dumps(VALID_PLANS_SOURCE, ensure_ascii=False)])
        r = client.post(f"/api/novels/{pid}/volumes/ai/options", json={
            "line": "", "conflict": "我的冲突", "antagonist_type": "自我",
            "antagonist_line": "体内饥渴", "ending": "我的卷末",
        })
        assert r.status_code == 200
        system = _layered_prompt(fake.last_kwargs)
        assert "我的冲突" in system and "体内饥渴" in system and "我的卷末" in system

    def test_check_material_has_antagonist_pair(self, client, monkeypatch):
        """体检素材含上一卷与本卷的坎两行（首卷＝无记录）。"""
        _set_tier("trial")
        pid = _mk_project(client)
        client.post(f"/api/novels/{pid}/volumes", json={
            "title": "第一卷", "antagonist_type": "环境",
            "antagonist_line": "母港制度——注销之后就没有回程"})
        reply = json.dumps({"groups": [
            {"name": "对主线", "items": [{"status": "ok", "text": "x"}]},
            {"name": "对设定", "items": [{"status": "ok", "text": "y"}]},
        ]}, ensure_ascii=False)
        fake = _setup_ai(monkeypatch, [reply])
        r = client.post(f"/api/novels/{pid}/volumes/vol-1/ai/check")
        assert r.status_code == 200, r.text
        system = _layered_prompt(fake.last_kwargs)
        assert "本卷的坎：环境·母港制度" in system
        assert "上一卷的坎：（无记录）" in system


# 模板契约逐字钉子已迁提示词仓（c-prompt-source-flip tests/test_templates_pins.py）。


def _seed_world(pid: str) -> None:
    async def _s():
        session = async_session()
        proj = await session.get(Novel, pid)
        root = proj.root_path
        await session.close()
        await get_storage().write_yaml(root, "settings/world-setting.yaml", {
            "stage": "灰港，蒸汽与煤气灯并存的工业港城，血族在夜禁后公开巡行。" * 6,
            "factions": [
                {"name": f"守夜人{i}", "note": f"守夜人{i}的立场注记，暗中向血族出售巡逻路线换取停战。" * 5}
                for i in range(3)
            ],
        })

    _run_async(_s())


def _plans_reply() -> str:
    return json.dumps({
        "plans": [
            {"spine": "甲走向", "conflict": "c", "ending": "e", "focus_axis": "代价",
             "antagonist_type": "难题", "antagonist_line": "信号的封装层"},
            {"spine": "乙走向", "conflict": "c", "ending": "e", "focus_axis": "关系",
             "antagonist_type": "环境", "antagonist_line": "母港制度"},
        ],
        "cast": [], "factions": [], "note": "", "volume_estimate": "",
    }, ensure_ascii=False)


class TestMaterialFullInfo:
    def test_options_world_full_and_volume_ledger(self, client, monkeypatch):
        """世界块全量（三家势力全进、无从略）＋已拆卷清单进 options 素材。"""
        _set_tier("trial")
        pid = _mk_project(client)
        _seed_world(pid)
        r1 = client.post(f"/api/novels/{pid}/volumes", json={
            "title": "第一卷", "summary": "猎杀越多越失控",
            "conflict": "与自己的兽性赛跑", "antagonist_type": "自我",
            "antagonist_line": "体内的血源饥渴", "ending": "带着饥渴走进黎明"})
        assert r1.status_code in (200, 201), r1.text
        fake = _setup_ai(monkeypatch, [_plans_reply()])
        r = client.post(f"/api/novels/{pid}/volumes/ai/options", json={"line": ""})
        assert r.status_code == 200, r.text
        system = _layered_prompt(fake.last_kwargs)
        assert "守夜人0的立场注记" in system and "守夜人2的立场注记" in system  # 势力全量
        assert "另有" not in system  # 全量＝无从略注
        assert "【已拆卷】" in system and "卷1·第一卷" in system
        assert "坎：自我·体内的血源饥渴" in system

    def test_expand_ledger_excludes_target_volume(self, client, monkeypatch):
        """expand 的已拆卷清单排除目标卷自身（vol_no=2 展开时不含卷 2 行）。"""
        _set_tier("trial")
        pid = _mk_project(client)
        for t in ("第一卷", "第二卷"):
            r = client.post(f"/api/novels/{pid}/volumes", json={"title": t, "summary": "s"})
            assert r.status_code in (200, 201), r.text
        fake = _setup_ai(monkeypatch, [VALID_EXPAND])
        r = client.post(f"/api/novels/{pid}/volumes/ai/expand",
                        json={"line": "追查内鬼", "vol_no": 2})
        assert r.status_code == 200, r.text
        system = _layered_prompt(fake.last_kwargs)
        assert "卷1·" in system
        assert "卷2·第二卷" not in system

    def test_cardless_name_known_no_warning(self, client, monkeypatch):
        """出场名单无卡名字进已知侧：申报「哑叔」不进 warnings；无卡名单块进素材。"""
        from sqlalchemy import select as _select

        from models.chapter import Chapter, ChapterCharacter
        from models.volume import Volume

        _set_tier("trial")
        pid = _mk_project(client)
        rv = client.post(f"/api/novels/{pid}/volumes", json={"title": "第一卷", "summary": "s"})
        assert rv.status_code in (200, 201), rv.text

        async def _s():
            session = async_session()
            vol = (await session.scalars(
                _select(Volume).where(Volume.project_id == pid)
            )).first()
            ch = Chapter(project_id=pid, volume_id=vol.id, chapter_no=1,
                         ref="vol-1-ch-1", title="初夜")
            session.add(ch)
            await session.flush()
            session.add(ChapterCharacter(chapter_id=ch.id, sort_order=0, character_name="哑叔"))
            await session.commit()
            await session.close()

        _run_async(_s())
        plans = json.dumps({
            "plans": [
                {"spine": "甲", "conflict": "c", "ending": "e", "focus_axis": "代价",
                 "antagonist_type": "难题", "antagonist_line": "封装层"},
                {"spine": "乙", "conflict": "c", "ending": "e", "focus_axis": "关系",
                 "antagonist_type": "环境", "antagonist_line": "母港制度"},
            ],
            "cast": ["哑叔"], "factions": [], "note": "", "volume_estimate": "",
        }, ensure_ascii=False)
        fake = _setup_ai(monkeypatch, [plans])
        r = client.post(f"/api/novels/{pid}/volumes/ai/options", json={"line": ""})
        assert r.status_code == 200, r.text
        assert not any("哑叔" in w for w in r.json()["warnings"])  # 已知侧含无卡名
        system = _layered_prompt(fake.last_kwargs)
        assert "【无卡出场名单】" in system and "哑叔（第1章）" in system

    def test_check_material_has_world_block(self, client, monkeypatch):
        """卷体检素材含全量世界块（现状只注铁律不含世界块）。"""
        _set_tier("trial")
        pid = _mk_project(client)
        _seed_world(pid)
        client.post(f"/api/novels/{pid}/volumes", json={
            "title": "第一卷", "antagonist_type": "环境",
            "antagonist_line": "母港制度——注销之后就没有回程"})
        reply = json.dumps({"groups": [
            {"name": "对主线", "items": [{"status": "ok", "text": "x"}]},
            {"name": "对设定", "items": [{"status": "ok", "text": "y"}]},
        ]}, ensure_ascii=False)
        fake = _setup_ai(monkeypatch, [reply])
        r = client.post(f"/api/novels/{pid}/volumes/vol-1/ai/check")
        assert r.status_code == 200, r.text
        system = _layered_prompt(fake.last_kwargs)
        assert "【世界观】" in system
        assert "守夜人0的立场注记" in system  # 全量进体检


# ── c-plan-draw-exclude：重抽排除对拍 ────────────────────────────────────────


class TestDrawExclude:
    def test_options_exclude_drops_clashing_and_retries(self, client, monkeypatch):
        """撞车套（同轴且走向相似）丢弃后不足 2 套 → 既有重试；重试请求仍带禁令块。"""
        _set_tier("trial")
        pid = _mk_project(client)
        first = json.dumps({"plans": [
            {"spine": "护送密船出港——半路折返", "conflict": "c", "ending": "e", "focus": "", "focus_axis": "代价"},
            {"spine": "另一条走向完全不同", "conflict": "c", "ending": "e", "focus": "", "focus_axis": "关系"}],
            "cast": [], "factions": [], "note": "", "volume_estimate": ""}, ensure_ascii=False)
        second = json.dumps({"plans": [
            {"spine": "全新走向一号", "conflict": "c", "ending": "e", "focus": "", "focus_axis": "代价"},
            {"spine": "全新走向二号", "conflict": "c", "ending": "e", "focus": "", "focus_axis": "关系"}],
            "cast": [], "factions": [], "note": "", "volume_estimate": ""}, ensure_ascii=False)
        fake = _setup_ai(monkeypatch, [first, second])
        r = client.post(f"/api/novels/{pid}/volumes/ai/options", json={
            "line": "", "exclude": [{"axis": "代价", "line": "护送密船出港——半路折返"}]})
        assert r.status_code == 200, r.text
        d = r.json()
        assert len(d["plans"]) == 2
        assert all(p["spine"] != "护送密船出港——半路折返" for p in d["plans"])
        assert "已出过的方向（作者已否决）" in _layered_prompt(fake.calls[0])
        assert "已出过的方向（作者已否决）" in _layered_prompt(fake.calls[1])  # 重试同样带禁令块（禁令块住 user）

    def test_options_exclude_same_line_different_axis_kept(self, client, monkeypatch):
        """异轴同句＝不判撞车（短串 difflib 噪声守卫：须同轴且相似）。"""
        _set_tier("trial")
        pid = _mk_project(client)
        reply = json.dumps({"plans": [
            {"spine": "同一句话", "conflict": "c", "ending": "e", "focus": "", "focus_axis": "关系"},
            {"spine": "护航编队改走外海航道", "conflict": "c", "ending": "e", "focus": "", "focus_axis": "线索"}],
            "cast": [], "factions": [], "note": "", "volume_estimate": ""}, ensure_ascii=False)
        fake = _setup_ai(monkeypatch, [reply])
        r = client.post(f"/api/novels/{pid}/volumes/ai/options", json={
            "line": "", "exclude": [{"axis": "代价", "line": "同一句话"}]})
        assert r.status_code == 200, r.text
        assert len(r.json()["plans"]) == 2  # 轴不同＝保留
        assert len(fake.calls) == 1  # 无重试