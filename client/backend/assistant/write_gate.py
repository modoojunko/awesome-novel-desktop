"""write_gate——写类工具的授权梯度（c-writing-agent 批B 2.5-2.7）。

方案 B 轻量自研（架构师三评推荐）：openworker 的「档位思路」整抄（ApprovalOutcome
档位词汇 engine.py L43-59、Decision 结构 permissions.py L245-257、durable pending
conversations.py L206-219），代码自研 ≈360 行，判定顺序照 evaluate 骨架（地板→档位
→域检查→兜底），域检查实体化（路径 scoping → 目标实体∈本书）。

档位（boss 拍板⑥）：
  confirm_each（默认）——每写必确认：停车发授权卡，作家批了才执行
  allow_book        ——本书内实体写自动放行（写完落回执＋撤销 chip，审计 stage=auto_allowed）
  allow_all         ——跨书小变更也放行（一期工具面全在本书内，行为与 allow_book 等价，留位）

硬地板（任何档位不可越，永远弹卡 human_only）：删除全书 / 批量删章 / 覆盖已确认
设定 / 变更授权档位本身。「agent 不能给自己授权」= 结构性缺席：档位变更不进工具
注册表，入口只在设置页。

停车-恢复：asyncio.Event waiter（openwriter inbox.py L104/L334-368 的核心 ~40 行）
＋ POST /approve resolve；待决授权持久化（assistant_messages role=event、
payload.pending_gate、status=streaming）——重启后未决卡标记过期自动拒绝（审计完整），
跨重启续跑挂账二期。
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any

# 授权档位（开放变量，写入 assistant_sessions.grants_json）
TIER_CONFIRM_EACH = "confirm_each"
TIER_ALLOW_BOOK = "allow_book"
TIER_ALLOW_ALL = "allow_all"
KNOWN_TIERS = (TIER_CONFIRM_EACH, TIER_ALLOW_BOOK, TIER_ALLOW_ALL)

# 硬地板工具名（任何档位都弹卡；「改档位」结构性缺席——不注册进 TOOL_REGISTRY，
# 此处列名仅为授权卡文案与文档引用）
HARD_FLOOR_TOOLS = frozenset(
    {"delete_book", "batch_delete_chapters", "overwrite_confirmed_setting", "set_permission_tier"}
)


@dataclass
class GateDecision:
    """openwriter Decision 结构（permissions.py L245-257）四字段的对应物。

    allowed=True      —— 直接执行（本书/全部授权放行）
    needs_user=True   —— 停车弹授权卡（含 human_only 硬地板）
    两者皆 False      —— 被拒（非诊断性 reason 给 agent，完整理由给作家）
    """

    allowed: bool = False
    needs_user: bool = False
    human_only: bool = False
    reason: str = ""
    # 授权卡预览载荷：将改实体/字段/新值（inbox.py args_preview 模式对应物）
    preview: dict[str, Any] = field(default_factory=dict)


def evaluate(tool_name: str, args: dict[str, Any] | None, *, tier: str) -> GateDecision:
    """纯函数判定（输入工具名＋参数＋档位，输出 Decision——不依赖循环实现，
    文本协议动作与未来原生 tool_calls 共用同一闸）。"""
    args = args or {}
    tier = tier if tier in KNOWN_TIERS else TIER_CONFIRM_EACH

    # ① 硬地板：先于一切档位（openworker「自保护地板先于模式」骨架）
    if tool_name in HARD_FLOOR_TOOLS:
        return GateDecision(
            needs_user=True,
            human_only=True,
            reason="此操作不可自动执行",
            preview=_preview(tool_name, args),
        )

    # ② 档位
    if tier == TIER_ALLOW_BOOK:
        return GateDecision(allowed=True, reason="本书授权放行", preview=_preview(tool_name, args))
    if tier == TIER_ALLOW_ALL:
        return GateDecision(allowed=True, reason="全局授权放行", preview=_preview(tool_name, args))

    # ③ 兜底：默认档逐次确认
    return GateDecision(
        needs_user=True, reason="默认档每写必确认", preview=_preview(tool_name, args)
    )


def _preview(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """授权卡的写入范围预览（实体/字段/新值）。"""
    return {"tool": tool_name, "args": args}


class ApprovalParking:
    """授权停车场：循环内 await 一张卡的批复（openwriter inbox waiter 核心）。

    pending: gate_id → {"event": asyncio.Event, "decision": None|"approved"|"denied"}
    resolve 后 set 唤醒；未决项可列出（/approve 路由与前端授权卡对账）。
    跨重启续跑挂账二期；进程内 pending 在进程死亡时自然消失（该 run 已死，
    持久化的待决记录由 session_store 侧过期收尾）。
    """

    def __init__(self) -> None:
        self._pending: dict[str, dict[str, Any]] = {}

    def register(self, gate_id: str | None = None) -> str:
        gate_id = gate_id or uuid.uuid4().hex[:12]
        self._pending[gate_id] = {"event": asyncio.Event(), "decision": None}
        return gate_id

    async def wait(self, gate_id: str, timeout: float | None = 300.0) -> str:
        entry = self._pending.get(gate_id)
        if entry is None:
            return "denied"
        event: asyncio.Event = entry["event"]
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except TimeoutError:
            entry["decision"] = "denied"
        return str(entry["decision"])

    def resolve(self, gate_id: str, decision: str) -> bool:
        entry = self._pending.get(gate_id)
        if entry is None or entry["decision"] is not None:
            return False
        entry["decision"] = "approved" if decision == "approved" else "denied"
        entry["event"].set()
        return True

    def discard(self, gate_id: str) -> None:
        self._pending.pop(gate_id, None)


# 进程级停车场（单用户桌面应用：进程内单例足够，判例 job_runner 的 Lock 思路按
# gate_id 分键）
PARKING = ApprovalParking()
