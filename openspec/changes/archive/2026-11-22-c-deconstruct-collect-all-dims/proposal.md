# c-deconstruct-collect-all-dims — 拆书「收进知识库」收全维（文风/技法/世界不再被角色门槛挡住）

## Why

作家只勾「写作文风／写作技法」拆出来的批次，点「收进知识库」只得到「这批产物里没有角色设定，无法收录」。第三出口在 #1021 只是**文案改名**（角色库→知识库），前端仍调角色库专用的
`library-candidates` / `to-library`，这两条接口只读 `products.characters`。后端通用收录端点
`collect-to-kb`（手法/文风/文笔/世界/角色五类映射）一直存在但从未接线——非角色维度的拆书产物
在界面上没有任何入口能收进知识库。

## What Changes

- 第三出口改为「本批能收的内容」：`GET /collect-candidates` 返回非角色维分组（写作技法/写作文风/
  世界设定，条数＋已入库条数）＋角色清单＋推算题材；面板按组勾选，角色保留逐张勾选与换名；
  一次提交先 `collect-to-kb`（dims）再 `to-library`（picks）。
- **收录范围跟随结果目录勾选**（boss 2026-11-21：不勾选的不录进知识库）：面板只列勾中产物对应的
  维度/角色区，勾选集变化时同步收窄，未勾产物 MUST NOT 入库；勾中的产物都不可收时提示原因并禁用。
- `collect-to-kb` 接受可选 body `{dims, genre}`：按勾选维收、补选题材；无 body 维持全量
  （批量脚本/版本 reconcile 口径不变）；状态门放宽到 RESULT_READY；成功后写 `exported_at`
  （「已完成未取结果」徽标消费）。
- **关键约束**：dims 过滤必须在 SDK 全量映射**之后**做——`src_key` 是全局自增序号
  （`prefix:seq`），先裁产物会让剩余维度键前移、与已入库键错位。
- 产物题材为空时面板让作家补选一次（默认落「未定题材」）；角色实例同归所选题材。
- 无角色但其它维度可收＝可用（本次报障场景）；完全没有可收维度才禁用并说明原因。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `deconstruct-book`：「结果目录与出口勾选」第三出口由「收进角色库」改为「收进知识库」全维收录
  （分组勾选/角色清单/题材补选/状态矩阵/徽标口径/无内容禁用）。

## Design Impact

- **受影响端**：C端。
- **受影响屏**：拆书完成详情「选择去向」弹层第三卡与内联面板（`TaskDetailPage`）。
- **对象状态**：分组行「已全部收过」＝行灰态不可勾；提交成功 toast 合并两类计数；失败留面板并
  重取候选灰态。
- **与原型关系**：拆书屏是 drafts 运行资产，不在 `design:check` 像素矩阵；drafts 原型出口弹层
  仍是双卡旧形态（#1021 已上线三卡但原型未回写），本 change 不追补 drafts；已按硬性流程在
  `docs/design-c/prototypes/ADJUSTMENTS.md` 登记偏差。
- **共享段**：零改动（未触碰 `base.css` 令牌与基础类家族）。
- **设计工件**：实现侧自查（design:lint / tsc / 组件测试 / e2e）。

## Impact

- `client/backend/kb/deconstruct_import.py`：`DIM_LABELS` / `entry_dim` / `find_collected_keys`；
  `collect_task_to_kb(dims=...)` 全量映射后过滤。
- `client/backend/deconstruct/router.py`：`collect-candidates` 端点；`collect-to-kb` body/状态门/
  `exported_at`；角色候选投影抽 helper；`to-library` 透传 genre。
- `client/backend/library/service.py`：`import_from_deconstruct(genre_override=...)`。
- `client/frontend/src/lib/deconstructApi.ts`：`CollectCandidates` / `CollectResult` /
  `getCollectCandidates` / `collectToKb`；`toLibrary` genre。
- `client/frontend/src/components/tools/TaskDetailPage.tsx`：面板分组＋角色区＋题材下拉＋合并提交。
- 测试：`tests/test_kb_deconstruct_import.py`、`tests/test_deconstruct_import_async.py`、
  `tests/test_charlib_deconstruct_exit.py`、`tests/test_deconstruct_withdrawn_gate.py`；
  `src/__tests__/toolsApi.test.ts`、`toolsDetail.test.tsx`；`e2e/character-library.spec.ts`。
- 兼容：`library-candidates` / `to-library` 保留（角色富实例路径不变）；无 body 的
  `collect-to-kb` 行为不变。
