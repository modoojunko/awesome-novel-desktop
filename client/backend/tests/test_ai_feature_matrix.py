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
from datetime import datetime, timedelta, timezone
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
_FUTURE = (datetime.now(timezone.utc) + timedelta(days=30)).date().isoformat()

from auth_local.deps import ai_feature, require_ai_access  # noqa: E402
from db import Base, async_session, engine  # noqa: E402
from models.user import User  # noqa: E402

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


# ── pro：正文＋朱雀放行，MAX 件 403 ──
def test_pro_ai_generate_pass():
    _seed("pro")
    assert _call("ai-generate") is True


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
