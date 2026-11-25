## ADDED Requirements

### Requirement: 拆书产物收进本地知识库（PRO）

- 拆书产物「收进知识库」端点（`POST /api/deconstruct/tasks/{task_id}/collect-to-kb`）SHALL 挂 `deconstruct`（PRO 起），与拆书任务/导出同档；标准（免费）SHALL 不可调用。
- 收进的目标 SHALL 是**本地层**（本书/用户知识库），SHALL NOT 写入官方层；收录后标准（免费）用户卸载/降档仍可读已收条目（已付费产物保留）。
- 收进 SHALL 支持按维度勾选（手法/文风/文笔/世界/角色等）与题材补填；不勾选不入库；幂等（已收过的自动跳过）。
- 拆书「取消/删除任务」SHALL 保持无档位门（止损动作），标准（免费）/过期用户仍可停止/删除存量任务。
- 拆书产物一键建书 SHALL 继续挂 `deconstruct-import`（MAX）；PRO 只能拆/看/导出/收库，不能一键建书。

#### Scenario: PRO 收进知识库

- **WHEN** PRO 用户完成拆书后勾选维度点「收进知识库」
- **THEN** 产物写入本地层并返回 collected/skipped；不写官方层

#### Scenario: 标准（免费）不能收库

- **WHEN** 标准（免费）用户对存量拆书任务点「收进知识库」
- **THEN** 返回 `feature_required`/`tier_required=pro`，显示 PRO 升级出口

#### Scenario: 取消/删除无门

- **WHEN** 标准（免费）或过期用户对存量拆书任务点取消/删除
- **THEN** 止损动作正常执行，不因档位返回 403

#### Scenario: MAX 一键建书

- **WHEN** PRO 用户点「一键建书」
- **THEN** 返回 `feature_required`/`tier_required=max`；MAX 用户可生成新书
