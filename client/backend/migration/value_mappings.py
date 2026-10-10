"""值域降级映射登记表（c-legacy-drill-gate）——遗留旧值被新库值域约束拒收时，
允许按本表「降级」成合法值保住整行；登记表是唯一单源，引擎按表执行、零临场决策。

══════════════════════════ 贡献规范（改表必读） ══════════════════════════

1. **同笔声明**：给用户表加值域类约束（CHECK/枚举/收紧值域）的变更，MUST 在本表
   同一笔声明该列的遗留值映射与保守默认——否则样本重放门禁
   （tests/test_legacy_replay_gate.py）拿历史世代样本重放时撞到拒收即红，合不进去。
2. **宁低勿高**：状态类旧值 SHALL 映射到保守端（`writing→draft` 而非 `done`）——
   降错了用户重标一次状态；降高了是假完成。默认值同样取保守端。
3. **无映射不落笔**：查询 API 返回 None（无条目）＝禁降级，该行按行损失如实报
   缺口。MUST NOT 为了门禁转绿而预写没有真实遗留形态依据的映射。
4. **映射依据要真实**：映射键来自真实存在过的历史形态（样本登记表
   tests/legacy_samples.py 是证据库）；迁移事故判例 MUST 同时入册样本表。
5. **内容字段永不降级**：本表只允许收状态/标记/计数类元数据列；标题/正文/设定
   内容被拒时不降级——宁可报缺口走备份包通道，不替用户编内容。

条目形态::

    VALUE_MAPPINGS = {
        ("chapters", "status"): ValueRule(
            mapping={"writing_v2": "draft", "writing_v1": "draft"},
            default="draft",  # 未登记旧值的保守兜底
        ),
    }
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ValueRule:
    """单列的降级规则：mapping＝精确旧值→新值；default＝未登记旧值的保守兜底。"""

    mapping: dict[str, str] = field(default_factory=dict)
    default: str | None = None


# {(表名, 列名): ValueRule}——初始为空是诚实的：当前用户表尚无值域约束。
# 第一笔值域约束落地时这里出现第一条目（贡献规范第 1 条）。
VALUE_MAPPINGS: dict[tuple[str, str], ValueRule] = {}


def lookup_degradation(table: str, column: str, value: str) -> str | None:
    """查某旧值的降级去向；None＝该列未声明降级，引擎 MUST NOT 改值。

    三级：精确映射命中 → 映射值；条目在而无精确键 → 保守 default；
    条目都不在 → None（含 value 为 None/空串的直通：不构成拒收面，直接放行 None）。
    """
    if value is None or value == "":
        return None
    rule = VALUE_MAPPINGS.get((table, column))
    if rule is None:
        return None
    hit = rule.mapping.get(value)
    if hit is not None:
        return hit
    return rule.default
