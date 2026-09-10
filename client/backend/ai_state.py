"""AI 模型调用分层：解析层（②）与判定层（③）。

genre-signup-redesign D11/D12/D13。本模块只做两件事：

- **解析层** `effective_model(novel)`：把「本书用哪个模型」解析成唯一答案——
  `novel.ai_model` 是唯一权威源；`writing-style.yaml` 的 `writing_model` 只是
  `haiku/sonnet` 别名（客户端层 `AIClient.resolve` 用），**字面模型名一律忽略**。
- **判定层** `compute_ai_state(novel, config, has_user_key)`：AI 就绪状态的单一
  事实源（前端只读、门控复用，不得另写判据）。

`member_required` 由门控层（`require_ai_access`）前置判定——本函数不查会员，
只回答「会员之外，这本书的模型链路为什么不可用」。

判定优先级（D13）：`invalid > no_key > missing_model > ready`
（`member_required` 由调用方最高优先前置）。
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.api_config import ApiConfig
from models.project import Novel
from models.user import User

# 与前端 `detail.reason` 共用同一枚举（D13）
AI_STATES = ("ready", "member_required", "no_key", "missing_model", "invalid")


def parse_models(models_field: Any) -> list[str]:
    """`ApiConfig.models` 是 JSON 文本（可为 None/空串/非法）→ list[str]。

    容忍度与 `refresh-models` 落库口径一致：非列表、含非字符串项一律丢弃。
    """
    if not models_field:
        return []
    if isinstance(models_field, list):
        raw = models_field
    else:
        try:
            raw = json.loads(models_field)
        except (json.JSONDecodeError, TypeError, ValueError):
            return []
    if not isinstance(raw, list):
        return []
    return [m for m in raw if isinstance(m, str) and m.strip()]


def effective_model(novel: Novel | None) -> str:
    """本书模型（权威源＝`novel.ai_model`）。

    不读 `writing_model`——那是 `haiku/sonnet` 别名偏好，不是模型绑定。
    """
    if novel is None:
        return ""
    return (novel.ai_model or "").strip()


def model_is_bound(novel: Novel | None, config: ApiConfig | None) -> bool:
    """绑定谓词：`ai_model` 非空且 ∈ 该配置的模型列表。

    `ready` 判据与 `set_project_model` 的写入校验**共用本谓词**（D10/D12）——
    `refresh-models` 后旧模型被移除时不再误报 ready。
    """
    if novel is None or config is None:
        return False
    model = effective_model(novel)
    if not model:
        return False
    return model in parse_models(config.models)


# 连接测试失败态（O-9：Key 填了但无效不能算就绪）。瞬时类（timeout/网络）同样
# 视为「最近一次测试失败」——恢复出口是重测，不是假装就绪。
FAILED_TEST_STATUSES = {"auth_error", "timeout", "network_error", "error", "not_found"}


def config_key_usable(config: ApiConfig | None) -> bool:
    """本书绑定配置的 Key 是否可用：非空 且 最近一次连接测试非失败态（O-9）。"""
    if config is None or not (config.api_key or "").strip():
        return False
    return (config.last_test_status or "ok") not in FAILED_TEST_STATUSES


def has_usable_key(config: ApiConfig | None) -> bool:
    """兼容旧名：配置 Key 可用性（不含连接测试维度）。"""
    return bool(config is not None and (config.api_key or "").strip())


def compute_ai_state(
    novel: Novel | None,
    config: ApiConfig | None,
    has_user_key: bool,
) -> str:
    """AI 就绪状态单一判定（D10/D13）。

    参数：
      novel        本书（None＝尚无书，按 missing_model）
      config       本书绑定的 ApiConfig（可为 None＝已被删除）
      has_user_key 用户是否有任一可用 Key（含旧 User 字段/config.json 兜底）

    返回值 ∈ AI_STATES（不含 member_required——那是门控层前置）。
    """
    if novel is None:
        return "missing_model"

    config_id = (novel.ai_config_id or "").strip()
    model = effective_model(novel)

    # R8：删配置后 ai_config_id 置空而 ai_model 保留 → invalid（不是 missing_model）
    if not config_id and model:
        return "invalid"

    # no_key 粒度＝**本书绑定配置级**（spec D13）：绑了配置就看该配置的 Key；
    # 未绑配置时才回退「用户是否有任一可用 Key」。
    if config_id:
        if not config_key_usable(config) and config is not None:
            return "no_key"
        if not has_user_key and config is None:
            return "no_key"
    elif not has_user_key:
        return "no_key"

    if not config_id or not model:
        return "missing_model"

    if config is None:
        return "invalid"

    # O-8 存量错配：model 不在配置的模型列表（写入校验只挡新增，判定层兜存量）
    if not model_is_bound(novel, config):
        return "invalid"

    return "ready"


async def user_has_ai_key(db: AsyncSession, user_id: str) -> bool:
    """用户是否有任一可用 Key（ApiConfig → 旧 User 字段 → config.json 兜底）。

    与门控层 `require_ai_access` 的 Key 判据同源——判定层的入参只在这里取一次。
    """
    try:
        result = await db.execute(
            select(ApiConfig)
            .where(
                ApiConfig.user_id == user_id,
                ApiConfig.status == "active",
                ApiConfig.api_key != "",
            )
            .limit(1)
        )
        if result.scalar_one_or_none():
            return True
    except Exception:  # noqa: BLE001, S110
        pass

    try:
        result = await db.execute(select(User).where(User.id == user_id))
        u = result.scalar_one_or_none()
        if u and u.api_key:
            return True
    except Exception:  # noqa: BLE001, S110
        pass

    from auth_local.service import get_local_config

    return bool(get_local_config().get("api_key"))


async def ai_state_for_novel(
    db: AsyncSession, novel: Novel | None, user_id: str
) -> dict[str, Any]:
    """完整 AI 就绪态（含会员维度）——`GET /novels/{id}/ai-model` 的下发源。

    前端门控只读 `ai_state` 一个字段、一次分派（D13）；`reason` 与 `ai_state`
    同枚举，供错误兜底直接复用。
    """
    from auth_local.deps import ai_access_granted  # 门控层，避免反向依赖

    config = None
    if novel is not None and novel.ai_config_id:
        config = await db.get(ApiConfig, novel.ai_config_id)
    if not ai_access_granted():
        state = "member_required"
    else:
        state = compute_ai_state(novel, config, await user_has_ai_key(db, user_id))

    message = (
        no_key_message(config if novel is not None else None)
        if state == "no_key"
        else state_message(state)
    )
    return {
        "ai_state": state,
        "effective_model": effective_model(novel),
        "reason": state,
        "message": message,
    }


def no_key_message(config: ApiConfig | None) -> str:
    """`no_key` 文案区分「未配置」/「测试失败，请检查」（O-9）。"""
    if config is not None and (config.api_key or "").strip():
        return "API Key 连接测试失败 — 请检查或重测"
    return "暂无可用 API Key — 先去「模型配置」添加"


def state_message(state: str) -> str:
    """状态 → 用户可读文案（前端也可自行映射；后端统一口径避免两处措辞漂移）。"""
    return {
        "ready": "已就绪",
        "member_required": "AI 是会员功能 — 开通 PRO 或试用后可用",
        "no_key": "暂无可用 API Key — 先去「模型配置」添加",
        "missing_model": "先在本书选择模型",
        "invalid": "本书绑定的模型已失效 — 重新选择模型",
    }.get(state, "AI 暂不可用")
