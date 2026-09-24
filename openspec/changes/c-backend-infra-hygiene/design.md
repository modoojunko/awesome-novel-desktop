## Context

见 proposal.md。落地相关现状（实勘）：

- `migration/router.py`：`dismiss`（:241-247）与 `cleanup` 已用 `validate_candidate_filename`（`db_lifecycle.py:495-516`，白名单形状＋resolve 收敛＋非活跃库）；`start`（:144-155）与 `preview`（:191）仍 `Path(DATA_ROOT) / body.source_filename` 直采。
- `migration/engine.py:266`：`tgt.execute(f"ATTACH DATABASE '{staged}' AS mig_src")`——staged 由 `staging / source_filename` 拼出，文件名未过形状校验。
- `volumes/schemas.py:87-93`：`_retired_reject` 元组 = template_name/plan_line/goal/plants/reveals/cast_members，缺 `plot_nodes`（同 change 退役的 VolumePlotNode 表）。
- `chapters/ai_plan.py:339,366,513`：`int(strip_suffix(vol_ref).replace("vol-", ""))` 裸 `int()`。

## Goals / Non-Goals

**Goals:**

- 迁移端点全家走同一入参校验；ATTACH 语句无注入面。
- 卷纲退役键清单完备；章域 AI 非法引用 400。

**Non-Goals:**

- config.json 路径收敛 `paths.py` 单源——与测试桩（各模块自持 CONFIG_FILE 属性供 monkeypatch）耦合，独立立项避免顺手改坏夹具。
- HTTP 客户端模块级复用——P3 且横跨 auth_local 多处，独立立项。
- 不改 candidates/retention 端点行为（已过白名单）。

## Decisions

**D1：start/preview 复用 `validate_candidate_filename`，校验失败返回 400「文件名不合法或不在数据目录内」。**
与 dismiss/cleanup 同源——五端点同一把锁。备选（已弃）只加 `..` 检查：白名单形状已含名字合法性，单点维护。

**D2：ATTACH 路径做 SQL 字面量转义（双写 `'`）而非参数绑定。**
sqlite3 驱动不支持 ATTACH 参数绑定；白名单形状本就排除了引号，转义是纵深防御而非唯一防线。

**D3：`_retired_reject` 元组补 `plot_nodes`，文案沿用既有句式。**
`plot_nodes` 对应的 VolumePlotNode 表已在 c-volume-antagonist 退役（模型/读写全撤），硬拒清单漏它属于清单漂移。

**D4：ref 解析抽一个 `_vol_no(vol_ref)` 小助手，解析失败抛 `HTTPException(400, "卷引用不合法")`。**
三处同型调用一次收口；与 `chapters/router.py` 的 `_validate_ref` → 400 先例对齐。

## Risks / Trade-offs

- [start/preview 加校验可能拒掉历史构造的合法但形状特殊的文件名] → 白名单形状即规格口径（db-generation「候选白名单按形状枚举」）；构造用例随测试覆盖。
- [422/400 文案变化影响 e2e] → 相关断言同批核对（全量 e2e 绿为验收）。

## Migration Plan

分支内实施；无数据迁移；回滚 = revert 提交。
