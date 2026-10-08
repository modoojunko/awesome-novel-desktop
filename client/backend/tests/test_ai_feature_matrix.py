"""五档 × feature key 门禁矩阵（tier-plan-four-tiers tasks 1.6）。

**必须走真实依赖**：直调真实 `require_ai_access`（test_ai_member_gate 直调先例）＋
config.json 种子＋隔离临时库——**禁用 dependency_overrides**（override 会整段
绕过 key 判定，测不到 feature_required）。feature 标注经桩 request 注入
（scope["route"].endpoint.__ai_feature__，与 FastAPI ≥0.115 真实装配同形）。

口径（2026-10-05 拍板）：free=全锁；standard=ai-plan/chapter-review/
settings-ai-fields/style-suggest 放行、ai-generate/ai-detect 403(pro)、
ai-plot/ai-polish/style-quant 403(max)；pro/trial=pro 全放（trial 同权含朱雀）、
MAX 件 403(max)；max=全放。未配 Key 一律 503（过档位门后判）。
"""

import asyncio
import os
import tempfile
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

# ── 隔离环境（先于业务模块导入；test_ai_member_gate 同款）──
_tmp_db = tempfile.NamedTemporaryFile(suffix="_feat_matrix.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_feat_matrix_")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

import auth_local.service as _service  # noqa: E402

_CFG_PATH = os.path.join(_tmp_data_root, "config.json")
_FAKE_KEY = "".join(("sk-", "test-placeholder"))  # noqa: FLY002
_FUTURE = (datetime.now(UTC) + timedelta(days=30)).date().isoformat()

from sqlalchemy import delete  # noqa: E402

from auth_local.deps import (  # noqa: E402
    ai_feature,
    require_ai_access,
    require_tier_access,
)
from db import Base, async_session, engine  # noqa: E402
from models.api_config import ApiConfig  # noqa: E402
from models.user import User  # noqa: E402
from zhuque import service as _zq_service  # noqa: E402

_UID = "featmatrixuser"


def _run(coro):
    return asyncio.run(coro)


def _seed(tier: str, with_key: bool = True):
    _service.CONFIG_FILE = _CFG_PATH
    cfg = _service.get_local_config()
    cfg.update({
        "tier": tier,
        "expires_at": _FUTURE if tier not in ("none", "free") else "",
        "api_key": _FAKE_KEY if with_key else "",
    })
    _service.save_local_config(cfg)


def _req(feature: str):
    """桩 request：scope["route"].endpoint 带 __ai_feature__（真实装配同形）。"""
    async def _endpoint() -> None:  # pragma: no cover - 仅作标注载体
        return None
    ai_feature(feature)(_endpoint)
    return SimpleNamespace(scope={"route": SimpleNamespace(endpoint=_endpoint)})


def _call(feature: str | None):
    async def run():
        async with async_session() as session:
            req = _req(feature) if feature else None
            return await require_ai_access({"id": _UID}, session, req)
    return _run(run())


def _call_tier_only(feature: str | None):
    """键自持门（`require_tier_access`）：无 session/Key 判据，只会员＋档位。"""
    async def run():
        req = _req(feature) if feature else None
        return await require_tier_access({"id": _UID}, req)
    return _run(run())


@pytest.fixture(scope="module", autouse=True)
def _env():
    _run(_create_tables())
    _run(_create_user())
    yield


async def _create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _create_user():
    async with async_session() as session:
        session.add(User(id=_UID, email="featmatrix@test.local",
                         password_hash="x" * 64))
        await session.commit()


def _expect_403(feature: str, reason: str, tier_required: str | None = None):
    with pytest.raises(Exception) as e:
        _call(feature)
    assert e.value.status_code == 403
    assert e.value.detail["reason"] == reason
    if tier_required is not None:
        assert e.value.detail["tier_required"] == tier_required


# ── 非会员：member_required（快照缺省→分支 4 名单外档位）──
def test_free_blocked_member_required():
    _seed("free")
    _expect_403("ai-plan", "member_required")


def test_none_blocked_member_required():
    _seed("none")
    _expect_403("ai-generate", "member_required")


# ── standard：管流程放行，正文/朱雀 403(pro)，MAX 件 403(max) ──
def test_standard_ai_plan_pass():
    _seed("standard")
    assert _call("ai-plan") is True


def test_standard_style_suggest_pass():
    assert _call("style-suggest") is True


def test_standard_ai_generate_403_pro():
    _expect_403("ai-generate", "feature_required", "pro")


def test_standard_ai_detect_403_pro():
    _expect_403("ai-detect", "feature_required", "pro")


def test_standard_ai_plot_403_max():
    _expect_403("ai-plot", "feature_required", "max")


def test_standard_style_quant_403_max():
    _expect_403("style-quant", "feature_required", "max")


def test_standard_ai_polish_403_max():
    _expect_403("ai-polish", "feature_required", "max")


def test_standard_prompt_panel_403_pro():
    """提示词面板＝PRO 专属：不是 PRO 就不能用（与「已配写作大模型 Key」判据叠加）——
    2026-10-08 口径，端点级钉住（前端 features.ts minTier=pro 同源）。"""
    _expect_403("prompt-panel", "feature_required", "pro")


# ── pro：正文＋朱雀放行，MAX 件 403 ──
def test_pro_ai_generate_pass():
    _seed("pro")
    assert _call("ai-generate") is True


def test_pro_prompt_panel_pass():
    assert _call("prompt-panel") is True


def test_pro_ai_detect_pass():
    assert _call("ai-detect") is True


def test_pro_ai_plot_403_max():
    _expect_403("ai-plot", "feature_required", "max")


# ── trial：= pro 同权（含朱雀），MAX 件仍锁 ──
def test_trial_ai_detect_pass():
    _seed("trial")
    assert _call("ai-detect") is True


def test_trial_ai_generate_pass():
    assert _call("ai-generate") is True


def test_trial_ai_plot_403_max():
    _expect_403("ai-plot", "feature_required", "max")


# ── max：全放 ──
def test_max_all_pass():
    _seed("max")
    for key in ("ai-plan", "ai-generate", "ai-detect", "ai-plot", "ai-polish", "style-quant"):
        assert _call(key) is True, key


# ── 直调无 request：二元语义（兼容保留）──
def test_direct_call_binary_semantics():
    _seed("pro")
    assert _call(None) is True


# ── 未配 Key：过了档位门后 503 ──
def test_member_without_key_503():
    _seed("pro", with_key=False)
    with pytest.raises(Exception) as e:
        _call("ai-generate")
    assert e.value.status_code == 503


# ── 键自持门（require_tier_access）：档位照拦，**不查大模型 Key** ──
def test_tier_only_gate_ignores_missing_key():
    """键自持使用口（朱雀检测）：PRO/trial 无任何大模型 Key 也放行
    （c-zhuque-config-keyless）。"""
    for tier in ("pro", "trial"):
        _seed(tier, with_key=False)
        assert _call_tier_only("ai-detect") is True, tier


def test_tier_only_gate_keeps_tier_blocks():
    _seed("free", with_key=False)
    with pytest.raises(Exception) as e:
        _call_tier_only("ai-detect")
    assert e.value.status_code == 403 and e.value.detail["reason"] == "member_required"
    _seed("standard", with_key=False)
    with pytest.raises(Exception) as e:
        _call_tier_only("ai-detect")
    assert e.value.status_code == 403 and e.value.detail["reason"] == "feature_required"


# ── 两个 Key 世界互不顶替（2026-10-08 口径）──
def test_zhuque_key_is_not_a_writing_model_key():
    """只配朱雀（无写作大模型）→ 大模型门 503，文案引导去配写作大模型。

    回归：门控的 Key 判据曾自建一条不看 vendor 的查询——朱雀行会被当成「已配大模型
    Key」放过门（用户随后在深处吃到不明错误）；判据已收归判定层 `user_has_ai_key`
    （`vendor="zhuque"` 排除 ＋ 可解密口径），与 `user_has_ai_key` 同源。
    """
    _seed("pro", with_key=False)

    async def _add_zhuque():
        async with async_session() as session:
            await _zq_service.save_config(session, _UID, "eo-mk-live")

    async def _clean():
        async with async_session() as session:
            await session.execute(delete(ApiConfig).where(ApiConfig.user_id == _UID))
            await session.commit()

    _run(_add_zhuque())
    try:
        with pytest.raises(Exception) as e:
            _call("ai-generate")
        assert e.value.status_code == 503
        assert "大模型" in str(e.value.detail)
    finally:
        _run(_clean())


# ── 完整快照在场时按快照档判定（快照单源）──
def test_snapshot_overrides_tier_label():
    _seed("pro")
    cfg = _service.get_local_config()
    cfg["entitlement"] = {
        "v": 2,
        "features": ["ai-plan", "ai-generate"],  # 快照无 ai-detect → 即便 tier=pro 也锁
        "limits": {"max_projects": None},
    }
    _service.save_local_config(cfg)
    _expect_403("ai-detect", "feature_required", "pro")
    assert _call("ai-generate") is True
    # 清快照还原
    cfg = _service.get_local_config()
    cfg.pop("entitlement", None)
    _service.save_local_config(cfg)
