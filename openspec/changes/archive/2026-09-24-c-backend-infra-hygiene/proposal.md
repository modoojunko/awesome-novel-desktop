## Why

本轮复审在 C端 后端留了四处小而实的缺陷，共性都是「守卫不完整」：

1. **迁移端点白名单半途而废**：`dismiss`/`cleanup` 已走 `validate_candidate_filename`（resolve 收敛在数据目录内），但真正会读文件、会 ATTACH 的 `start`/`preview` 仍直采 `source_filename`；`engine.py` 的 `ATTACH DATABASE '{staged}'` 为 f-string 拼接——文件名含 `'` 即破坏语句，`..` 可把 staging 副本写出目录外。
2. **退役键硬拒漏键**：`volumes/schemas.py` 的退役元组缺 `plot_nodes`——旧客户端按旧契约 `PUT /volumes/{ref}` 携带 `plot_nodes` 会 200 但静默不落库，与 `cast_members` 等六键的硬拒口径自相矛盾。
3. **非法卷引用 500**：`chapters/ai_plan.py` 三处 `int(strip_suffix(vol_ref).replace("vol-", ""))` 直接 `int()`——非法 `vol_ref` 抛 ValueError 变 500，同族入口已有 `_validate_ref` → 400 的先例。

## What Changes

- `start`/`preview` 入参先过 `validate_candidate_filename`（与 dismiss/cleanup 同源）；engine 的 ATTACH 语句对路径做 SQL 字面量转义（双写 `'`）防御纵深。
- 卷纲退役键元组补 `plot_nodes`——携带即 422，消除「200 但不落库」的静默无效写入。
- `chapters/ai_plan.py` 三处 ref 解析改显式校验：非法 `vol_ref` 返回 400 与可读文案，不再 500。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `db-generation`: 新增「迁移端点入参必须经白名单与参数化」要求（start/preview 与 dismiss/cleanup 同源校验，ATTACH 禁裸拼接）。
- `volume-outline`: 新增「退役字段硬拒清单须完备」要求（补 `plot_nodes`，语义与既有六键一致）。
- `chapter-plan-ai`: 新增「非法卷引用必须 400」要求。

## Design Impact

- 不适用：无用户可见界面改动（仅错误码与错误文案口径），不触共享段，无需原型先行。

## Impact

- `client/backend/migration/router.py`、`migration/engine.py`、`volumes/schemas.py`、`chapters/ai_plan.py`。
- 测试：迁移端点 400/白名单用例、卷纲 422 用例、ai_plan 400 用例。
- 无前端改动（前端本就不发这些键/非法 ref）。
