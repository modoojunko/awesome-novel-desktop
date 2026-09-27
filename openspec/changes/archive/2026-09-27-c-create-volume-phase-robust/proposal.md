# c-create-volume-phase-robust — 建卷阶段记账宽容化（write 阶段补建卷 500 修复）

## Why

2026-09-27 演示栈实锤：书写到一半（`current_phase=write`）重规划第一卷，抽卡「确认这一套，成卷」→
`POST /volumes` 恒 500（`ValueError: Cannot transition from write to outline`），选中的卡永远落不了库。

根因：`volumes/service.py create_volume` 用严格版 `update_phase(project, "outline")` 做阶段记账，
阶段机 `ALLOWED_TRANSITIONS` 只许 `write→archive`——书已推进到 prompt/write 后补建卷必抛 ValueError→500。
仓里早有同类先例与正确口径：`write/router.py _advance_phase`（「阶段机只进不退，跳过推进而非抛 500」）
与 novel-workspace spec（「phase 只是『最近一次操作』的记账」），建卷漏用了这套口径。

## What Changes

- `workflow/engine.py` 新增 `advance_phase(project, new_phase)`（宽容推进、只进不退单源）：
  同阶段幂等、合法迁移才置位、非法回退静默跳过返 False，不抛 ValueError。
- `create_volume` 阶段记账改走 `advance_phase`；存量 `init` 行走前进捷径直接记 `outline`
  （新建书创建即 `settings`，`init` 仅存量——原严格版对 init 同样 500）。
- `write/router.py _advance_phase` 委托 `engine.advance_phase`（口径单源，行为不变）。
- 前端零改动（落库失败提示链原样，修后自然走通）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `volume-chapter-service`: `create_volume` requirement 的阶段记账条款由「`update_phase("outline")` runs
  idempotently」收窄为「幂等＋宽容（只进不退）」：非法回退跳过而非 500，建卷不因阶段机失败。

## Impact

- `client/backend/workflow/engine.py`、`client/backend/volumes/service.py`、`client/backend/write/router.py`。
- 测试：`test_volume_chapter_crud`（服务级 4 例）、`test_workflow_api`（API 级 2 例，含 PRO gate 真实拦截环境）。
- 前端零改动。
