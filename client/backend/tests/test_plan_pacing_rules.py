"""c-plan-pacing-rules：位置感知分片＋本地节奏提醒＋卷纲高潮义务的契约测试。

矩阵：
- 选择器边界：vol1ch1→ch1、vol1ch2/3→golden3、vol2ch1→vol_start、vol2ch2→无片段；同状态重拆幂等；
- 片段加载：`## ` 版本头剥离、正文首行即标题；四片段对拍钉子（关键句逐字在场）；
- 出卡渲染：⓪位置行首位＋既有①→⑧逐字不挪；ch1/golden3/vol_start 片段按位置注入、卷中普通章无片段；
- 升档提醒：低三档停同档 3 章触发（目标=下一档）、非同档/含高三档/末章/剩余≤1 不触发；
- 排满提示：排满且未触达高潮爆发 → warnings 追加；触达过 → 不追加；不拦卡；
- 拆卷：expand vol1 注入「开卷即入戏」片段、vol2 空串；options 恒不含片段；hard_rules 与单源逐字同包；
- 体检：模型回四组 → 报告四组透传（对节奏组）。

用法：
    cd client/backend
    python -m pytest tests/test_plan_pacing_rules.py -v
"""

import asyncio
import json
import os
import tempfile
import uuid

import pytest
from fastapi.testclient import TestClient

# ── 隔离环境（先设 env 再 import app）─────────────────────────────────
_tmp_db = tempfile.NamedTemporaryFile(suffix="_ppr.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_plan_pacing_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

import auth_local.service as _service  # noqa: E402
from auth_local.deps import require_novel_model  # noqa: E402
from auth_local.middleware import get_current_user  # noqa: E402
from chapters.ai_plan import POS_FRAGMENTS, chapter_position_tags  # noqa: E402
from db import async_session, get_db  # noqa: E402
from main import app  # noqa: E402
from models.chapter import Chapter  # noqa: E402
from models.user import User  # noqa: E402
from models.volume import Volume  # noqa: E402
from volumes.ai_plan import _rules_sections, load_fragment  # noqa: E402

_CFG_PATH = os.path.join(_tmp_data_root, "config.json")
USER_ID = "ppr_user"
_PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "prompts")


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
    # trial 档（expires 未来＋有 key）→ 生成类 PRO 门禁放行，免逐用例翻档
    _service.CONFIG_FILE = _CFG_PATH
    _service.save_local_config({"tier": "trial", "expires_at": "2099-12-31", "api_key": "sk-test"})
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


class _FakeAIClient:
    def __init__(self, replies):
        self._replies = list(replies)
        self.calls: list[dict] = []

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(kwargs.get("usage"), dict):
            kwargs["usage"].update({"tokens_in": 10, "tokens_out": 20})
        return self._replies[min(len(self.calls) - 1, len(self._replies) - 1)]


def _setup_ai(monkeypatch, replies) -> _FakeAIClient:
    fake = _FakeAIClient(replies if isinstance(replies, list) else [replies])

    async def _factory(novel_id=None):
        return fake

    monkeypatch.setattr("volumes.ai_plan.get_ai_client_for_novel", _factory)
    return fake


# ── 夹具：按 (卷号, 章规格) 落库；章规格支持 stage ─────────────────────
def _seed(client, vols: list[tuple[int, list[dict]]], *, target: int | None = None) -> str:
    name = f"ppr-{uuid.uuid4().hex[:6]}"
    r = client.post("/api/novels", json={"name": name})
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]

    async def _s():
        async with async_session() as session:
            if await session.get(User, USER_ID) is None:
                session.add(User(id=USER_ID, email=f"{USER_ID}@test.local", password_hash="x"))
                await session.flush()
            for vol_no, chs in vols:
                vol = Volume(
                    project_id=pid, volume_no=vol_no, title=f"第{vol_no}卷",
                    summary="沉舟捡到一枚不属于人类纪元的导航信标",
                    core_conflict="想自己查清，与得靠船队",
                    ending="船头转向母港旧址", chapter_target=target if vol_no == 1 else None,
                )
                session.add(vol)
                await session.flush()
                for ch in chs:
                    session.add(
                        Chapter(
                            project_id=pid, volume_id=vol.id, chapter_no=ch["no"],
                            ref=f"vol-{vol_no}-ch-{ch['no']}", title=f"第{ch['no']}章",
                            has_prose=False, status="outline",
                            summary=ch.get("summary", ""), plot_stage=ch.get("stage", ""),
                        )
                    )
            await session.commit()

    _run_async(_s())
    return pid


def _directions_reply() -> str:
    cards = [
        {"axis": "线索", "title": "同名档案", "plot": "她调出那份记录，最后一页被撕掉了",
         "obstacle": "旧档堆不对活人开放", "ending": "她把残角收进怀里", "acts": ["她：调档"],
         "stage": "矛盾升级", "cast": [], "factions": [], "places": [], "why": "钩子", "gap": ""},
        {"axis": "关系", "title": "船队的条件", "plot": "船队长开价换航线",
         "obstacle": "交出一半生存空间", "ending": "她换来留下的许可", "acts": ["船队长：开价"],
         "stage": "矛盾升级", "cast": [], "factions": [], "places": [], "why": "疼", "gap": ""},
        {"axis": "危机", "title": "突击清查", "plot": "清查队登船前她带信标出逃",
         "obstacle": "藏无可藏", "ending": "信标暴露", "acts": ["清查队：搜舱"],
         "stage": "重要转折", "cast": [], "factions": [], "places": [], "why": "压上来", "gap": ""},
    ]
    return json.dumps(
        {"diff": {"axes": ["线索", "关系", "危机"], "one_liner": ["推向一", "推向二", "推向三"]},
         "directions": cards,
         "ranks": {d: [1, 2, 3] for d in ("反转", "递增", "推进", "拉力")},
         "reasons": {d: "理由" for d in ("反转", "递增", "推进", "拉力")},
         "checks": [], "note": ""},
        ensure_ascii=False,
    )


# ═══════════════ 选择器（纯函数边界）═══════════════


class TestPositionTags:
    @pytest.mark.parametrize(
        "global_ch,ch_no,expected",
        [
            (1, 1, ["ch1"]),
            (2, 2, ["golden3"]),
            (3, 3, ["golden3"]),
            (3, 1, ["golden3", "vol_start"]),  # 叠加合法：既是全书第 3 章、又是新卷第 1 章
            (4, 1, ["vol_start"]),
            (4, 2, []),
            (30, 7, []),
        ],
    )
    def test_boundaries(self, global_ch, ch_no, expected):
        assert chapter_position_tags(global_ch, ch_no) == expected

    def test_pure_idempotent(self):
        assert chapter_position_tags(1, 1) == chapter_position_tags(1, 1)
        assert chapter_position_tags(4, 1) == chapter_position_tags(4, 1)


# ═══════════════ 片段文件（版本头剥离＋对拍钉子）═══════════════


def test_fragment_headers_stripped():
    for fname in POS_FRAGMENTS.values():
        frag = load_fragment(fname)
        assert not frag.startswith("##"), fname
        assert "##" not in frag.split("\n", 1)[0], fname  # 头注释不漏进提示词
    assert load_fragment("pos_ch1").startswith("【本章是全书第 1 章】")
    assert load_fragment("volume_pos_first").startswith("【本卷是全书第 1 卷】")


def test_fragment_verbatim_pins():
    """四片段对拍钉子（改坏关键句 → 红）：与 spec/评审成稿逐字一致的关键约束。"""
    with open(os.path.join(_PROMPTS_DIR, "pos_ch1.prompt"), encoding="utf-8") as f:
        ch1 = f.read()
    assert "开场即冲突" in ch1 and "不写身份来历、不铺世界观、不写日常" in ch1
    assert "不收场、不喘息" in ch1
    with open(os.path.join(_PROMPTS_DIR, "pos_golden3.prompt"), encoding="utf-8") as f:
        g3 = f.read()
    assert "至少破一次预期" in g3 and "合格例" in g3 and "不合格例" in g3
    assert "困难比上一章更狠" in g3 and "三个方向兑现的手段互不相同" in g3
    with open(os.path.join(_PROMPTS_DIR, "pos_vol_start.prompt"), encoding="utf-8") as f:
        vs = f.read()
    assert "本章就让本卷核心冲突露头" in vs  # 禁「最迟第 3 章」类拖延措辞
    assert "最迟" not in vs
    assert "stage 不低于「冲突初现」" in vs
    with open(os.path.join(_PROMPTS_DIR, "volume_pos_first.prompt"), encoding="utf-8") as f:
        vf = f.read()
    assert "开卷即入戏" in vf and "不设铺垫期" in vf and "不晚于第 3 章" in vf


def test_volume_rules_eight_rules_with_rhythm_criteria():
    """rules 单源：八条（规则 8＝卷末点名高潮＋位置）＋体检判据「对节奏」组；锚点切分不破。"""
    hard, crit = _rules_sections()
    assert hard.startswith("【八条硬规则】")
    assert "8. 每卷要有自己的小高潮：卷末点名本卷高潮事件、大致落在卷内哪一段（前/中/后），再写交代。" in hard
    assert "7. 只铺结构" in hard  # 既有七条不动
    assert "对节奏：" in crit
    assert "对主线：" in crit and "对已写内容：" in crit
    assert crit.index("对节奏") < crit.index("对已写内容")  # 新组落在已写内容之前


# ═══════════════ 出卡渲染（位置行＋片段注入＋提醒＋排满提示）═══════════════


def _last_system(fake: _FakeAIClient) -> str:
    return fake.calls[-1]["system"]


class TestDirectionsRendering:
    def test_vol1_ch1_position_and_fragment(self, client, monkeypatch):
        pid = _seed(client, [(1, [])])
        fake = _setup_ai(monkeypatch, _directions_reply())
        r = client.post(f"/api/novels/{pid}/volumes/vol-1/chapters/ai-directions", json={})
        assert r.status_code == 200, r.text
        system = _last_system(fake)
        assert system.index("【本章位置】全书第 1 章｜本卷第 1 章") < system.index("【进场（本章从哪接）】")
        assert "【本章是全书第 1 章】" in system and "开场即冲突" in system
        assert "【本章是全书第 2–3 章】" not in system  # 只注入命中的角色

    def test_vol1_ch2_golden3(self, client, monkeypatch):
        pid = _seed(client, [(1, [{"no": 1, "stage": "冲突初现", "summary": "捡到信标"}])])
        fake = _setup_ai(monkeypatch, _directions_reply())
        client.post(f"/api/novels/{pid}/volumes/vol-1/chapters/ai-directions", json={})
        system = _last_system(fake)
        assert "【本章位置】全书第 2 章｜本卷第 2 章" in system
        assert "【本章是全书第 2–3 章】" in system and "至少破一次预期" in system
        assert "【本章是全书第 1 章】" not in system

    def test_vol2_ch1_vol_start_global_count(self, client, monkeypatch):
        """全局章号＝前卷已拆章数（滤 ghost）＋卷内序号；片段=vol_start 而非 golden3。"""
        pid = _seed(client, [
            (1, [
                {"no": 1, "stage": "卷末收束", "summary": "一"},
                {"no": 2, "stage": "卷末收束", "summary": "二"},
                {"no": 3, "stage": "卷末收束", "summary": "三"},
            ]),
            (2, []),
        ])
        fake = _setup_ai(monkeypatch, _directions_reply())
        r = client.post(f"/api/novels/{pid}/volumes/vol-2/chapters/ai-directions", json={})
        assert r.status_code == 200, r.text
        system = _last_system(fake)
        assert "【本章位置】全书第 4 章｜本卷第 1 章" in system
        assert "【本章是新卷的第 1 章】" in system and "本章就让本卷核心冲突露头" in system
        assert "【本章是全书第" not in system

    def test_mid_volume_no_fragment(self, client, monkeypatch):
        pid = _seed(client, [(1, [
            {"no": 1, "stage": "冲突初现", "summary": "一"},
            {"no": 2, "stage": "矛盾升级", "summary": "二"},
            {"no": 3, "stage": "重要转折", "summary": "三"},
        ])])
        fake = _setup_ai(monkeypatch, _directions_reply())
        client.post(f"/api/novels/{pid}/volumes/vol-1/chapters/ai-directions", json={})
        system = _last_system(fake)
        assert "【本章位置】全书第 4 章｜本卷第 4 章" in system
        for marker in ("【本章是全书第 1 章】", "【本章是全书第 2–3 章】", "【本章是新卷的第 1 章】"):
            assert marker not in system

    def test_resplit_same_state_same_prompt(self, client, monkeypatch):
        """幂等：同状态下两次出卡，位置行与片段逐字一致。"""
        pid = _seed(client, [(1, [])])
        fake = _setup_ai(monkeypatch, [_directions_reply(), _directions_reply()])
        client.post(f"/api/novels/{pid}/volumes/vol-1/chapters/ai-directions", json={})
        first = _last_system(fake)
        client.post(f"/api/novels/{pid}/volumes/vol-1/chapters/ai-directions", json={})
        assert _last_system(fake) == first

    def test_position_line_does_not_disturb_existing_blocks(self, client, monkeypatch):
        """⓪只加首位：既有块标题与顺序不受影响（既有用例的包含式断言之外的顺序钉）。"""
        pid = _seed(client, [(1, [])])
        fake = _setup_ai(monkeypatch, _directions_reply())
        client.post(f"/api/novels/{pid}/volumes/vol-1/chapters/ai-directions", json={})
        system = _last_system(fake)
        order = [system.index(m) for m in (
            "【本章位置】", "【进场（本章从哪接）】", "【本卷卷纲（四问）】", "【章数配额】", "硬规则："
        )]
        assert order == sorted(order)


class TestCadenceReminder:
    def test_flat_three_low_stages_triggers(self, client, monkeypatch):
        pid = _seed(client, [(1, [
            {"no": 1, "stage": "冲突初现", "summary": "一"},
            {"no": 2, "stage": "冲突初现", "summary": "二"},
            {"no": 3, "stage": "冲突初现", "summary": "三"},
        ])])
        fake = _setup_ai(monkeypatch, _directions_reply())
        client.post(f"/api/novels/{pid}/volumes/vol-1/chapters/ai-directions", json={})
        system = _last_system(fake)
        assert "【节奏提醒】已连续 3 章停在「冲突初现」没升档" in system
        assert "stage 至少「矛盾升级」" in system
        assert system.index("【上一章发生了什么】") < system.index("【节奏提醒】")  # ⑨在⑧后

    def test_escalating_stages_no_trigger(self, client, monkeypatch):
        pid = _seed(client, [(1, [
            {"no": 1, "stage": "开局铺垫", "summary": "一"},
            {"no": 2, "stage": "冲突初现", "summary": "二"},
            {"no": 3, "stage": "矛盾升级", "summary": "三"},
        ])])
        fake = _setup_ai(monkeypatch, _directions_reply())
        client.post(f"/api/novels/{pid}/volumes/vol-1/chapters/ai-directions", json={})
        assert "【节奏提醒】" not in _last_system(fake)

    def test_high_stage_no_trigger_and_final_no_trigger(self, client, monkeypatch):
        # 高三档在场（到顶无法再升）
        pid = _seed(client, [(1, [
            {"no": 1, "stage": "矛盾升级", "summary": "一"},
            {"no": 2, "stage": "矛盾升级", "summary": "二"},
            {"no": 3, "stage": "重要转折", "summary": "三"},
        ])])
        fake = _setup_ai(monkeypatch, _directions_reply())
        client.post(f"/api/novels/{pid}/volumes/vol-1/chapters/ai-directions", json={})
        assert "【节奏提醒】" not in _last_system(fake)
        # 末章（目标 4 已排 3）：收束义务优先，不催升档
        pid2 = _seed(client, [(1, [
            {"no": 1, "stage": "冲突初现", "summary": "一"},
            {"no": 2, "stage": "冲突初现", "summary": "二"},
            {"no": 3, "stage": "冲突初现", "summary": "三"},
        ])], target=4)
        fake2 = _setup_ai(monkeypatch, _directions_reply())
        client.post(f"/api/novels/{pid2}/volumes/vol-1/chapters/ai-directions", json={})
        assert "【节奏提醒】" not in _last_system(fake2)

    def test_cross_volume_reset(self, client, monkeypatch):
        """计数只在当前卷内：上卷末 3 章全低档，新卷第 2 章不触发。"""
        pid = _seed(client, [
            (1, [
                {"no": 1, "stage": "开局铺垫", "summary": "一"},
                {"no": 2, "stage": "开局铺垫", "summary": "二"},
                {"no": 3, "stage": "开局铺垫", "summary": "三"},
            ]),
            (2, [{"no": 1, "stage": "冲突初现", "summary": "新卷一"}]),
        ])
        fake = _setup_ai(monkeypatch, _directions_reply())
        client.post(f"/api/novels/{pid}/volumes/vol-2/chapters/ai-directions", json={})
        assert "【节奏提醒】" not in _last_system(fake)


class TestQuotaFullHint:
    def test_full_without_climax_warns(self, client, monkeypatch):
        pid = _seed(client, [(1, [
            {"no": 1, "stage": "冲突初现", "summary": "一"},
            {"no": 2, "stage": "矛盾升级", "summary": "二"},
        ])], target=2)
        _setup_ai(monkeypatch, _directions_reply())
        d = client.post(f"/api/novels/{pid}/volumes/vol-1/chapters/ai-directions", json={}).json()
        assert any("已排满但还没到高潮" in w for w in d["warnings"]), d["warnings"]
        assert len(d["directions"]) == 3  # 不拦卡

    def test_full_with_climax_no_warn(self, client, monkeypatch):
        pid = _seed(client, [(1, [
            {"no": 1, "stage": "矛盾升级", "summary": "一"},
            {"no": 2, "stage": "高潮爆发", "summary": "二"},
        ])], target=2)
        _setup_ai(monkeypatch, _directions_reply())
        d = client.post(f"/api/novels/{pid}/volumes/vol-1/chapters/ai-directions", json={}).json()
        assert not any("已排满" in w for w in d["warnings"]), d["warnings"]


# ═══════════════ 拆卷侧（expand 首卷片段／options 恒无片段／体检四组）═══════════════

_ARC = {
    "fullstory": "沉舟是见习导航员，捡到信标后被卷入航线争夺；中段对抗升级，发现信标在喂养她自己；结局是清算之夜的对决与放手。",
    "ending": {"scene": "雾散的旧港，她把信标抛回海里", "hero": "活着，但不再完整", "tone": "带着寒意的释然"},
}


def _mk_book(client) -> str:
    """建书＋种主线（options 端点有主线空门）。"""
    name = f"pprv-{uuid.uuid4().hex[:6]}"
    pid = client.post("/api/novels", json={"name": name}).json()["id"]

    async def _seed():
        from filesystem.storage import get_storage
        from models import Novel

        async with async_session() as session:
            proj = await session.get(Novel, pid)
            root = proj.root_path
        story = await get_storage().read_yaml(root, "story.yaml") or {}
        story["story_arc"] = _ARC
        await get_storage().write_yaml(root, "story.yaml", story)

    _run_async(_seed())
    return pid


class TestVolumeSide:
    def test_expand_vol1_injects_first_volume_fragment(self, client, monkeypatch):
        pid = _mk_book(client)
        fake = _setup_ai(monkeypatch, json.dumps(
            {"name": "起", "summary": "她追信号欠下一条命", "conflict": "船队扣人",
             "ending": "高潮：夺回航线（后段）；她启程", "antagonist_type": "势力",
             "antagonist_line": "船队执法官", "plants": [], "reveals": [],
             "chapter_target": 6, "checks": [], "cast": [], "factions": []},
            ensure_ascii=False,
        ))
        r = client.post(f"/api/novels/{pid}/volumes/ai/expand", json={"line": "她为追信号把坐标押给船队", "vol_no": 1})
        assert r.status_code == 200, r.text
        system = fake.calls[0]["system"]
        assert "【本卷是全书第 1 卷】" in system and "开卷即入戏" in system and "不晚于第 3 章" in system
        hard, _crit = _rules_sections()
        assert hard in system  # 片段不挤掉单源规则（不拼进 hard_rules）
        assert "## v1" not in system  # 版本头不漏进提示词

    def test_expand_vol2_no_fragment(self, client, monkeypatch):
        pid = _mk_book(client)
        fake = _setup_ai(monkeypatch, json.dumps(
            {"name": "二", "summary": "她按航线找船队算账", "conflict": "执法官拦路",
             "ending": "高潮：对质执法官（后段）；航线易主", "antagonist_type": "人物",
             "antagonist_line": "执法官老聋", "plants": [], "reveals": [],
             "chapter_target": 5, "checks": [], "cast": [], "factions": []},
            ensure_ascii=False,
        ))
        r = client.post(f"/api/novels/{pid}/volumes/ai/expand", json={"line": "第二卷她要拿回航线", "vol_no": 2})
        assert r.status_code == 200, r.text
        system = fake.calls[0]["system"]
        assert "【本卷是全书第 1 卷】" not in system
        assert "开卷即入戏" not in system

    def test_options_never_gets_pacing_fragment(self, client, monkeypatch):
        pid = _mk_book(client)
        fake = _setup_ai(monkeypatch, json.dumps(
            {"plans": [
                {"spine": "她押坐标换线索", "conflict": "船队扣人", "ending": "她欠下一条命",
                 "focus": "代价", "focus_axis": "代价", "antagonist_type": "势力",
                 "antagonist_line": "船队执法官"},
                {"spine": "她黑进港务局查信号", "conflict": "港务局追查", "ending": "信标暴露",
                 "focus": "危机", "focus_axis": "危机", "antagonist_type": "势力",
                 "antagonist_line": "港务局"},
            ], "note": "", "volume_estimate": "5–8 章", "cast": [], "factions": []},
            ensure_ascii=False,
        ))
        r = client.post(f"/api/novels/{pid}/volumes/ai/options", json={"line": ""})
        assert r.status_code == 200, r.text
        for call in fake.calls:
            assert "开卷即入戏" not in call["system"]
            assert "开场即冲突" not in call["system"]

    def test_check_report_passes_four_groups(self, client, monkeypatch):
        """模型按新判据回四组 → 报告四组透传（≥2 组的既有校验不挡四组）。"""
        pid = _mk_book(client)
        r = client.post(f"/api/novels/{pid}/volumes", json={"title": "第一卷"})
        assert r.status_code in (200, 201), r.text
        reply = json.dumps(
            {"groups": [
                {"name": "对主线", "items": [{"status": "ok", "text": "进场接得上。"}]},
                {"name": "对设定", "items": [{"status": "ok", "text": "无违反铁律。"}]},
                {"name": "对节奏", "items": [
                    {"status": "warn", "text": "卷末未点名本卷高潮事件与位置。", "evidence": "卷末"},
                ]},
                {"name": "对已写内容", "items": [{"status": "none", "text": "还没有章节。"}]},
            ]},
            ensure_ascii=False,
        )
        fake = _setup_ai(monkeypatch, reply)
        resp = client.post(f"/api/novels/{pid}/volumes/vol-1/ai/check")
        assert resp.status_code == 200, resp.text
        names = [g["name"] for g in resp.json()["report"]]
        assert names == ["对主线", "对设定", "对节奏", "对已写内容"]
        _hard, crit = _rules_sections()
        assert crit in fake.calls[0]["system"]  # 「对节奏」判据逐字入包（文本单源对拍）
