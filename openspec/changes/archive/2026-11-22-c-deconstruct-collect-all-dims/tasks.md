# Tasks — c-deconstruct-collect-all-dims

## 1. 后端：按维收录与候选

- [x] 1.1 `kb/deconstruct_import.py`：`DIM_LABELS`、`entry_dim`（SDK src_key 前缀→维度）、
      `find_collected_keys`（收录/预览共用去重查询）。
- [x] 1.2 `collect_task_to_kb(..., dims=None)`：全量映射后再按维过滤（保 src_key 全局序号稳定）；
      未知维忽略；无 dims＝全量（脚本/reconcile 不变）。
- [x] 1.3 `deconstruct/router.py`：新增 `GET /tasks/{id}/collect-candidates`（分组 count/collected＋
      角色清单＋题材；RESULT_READY 才有内容；撤回书 403）。
- [x] 1.4 `POST /tasks/{id}/collect-to-kb`：可选 body `{dims, genre}`；状态门放宽到
      `service.RESULT_READY`；成功写 `exported_at`（徽标消费）。
- [x] 1.5 `to-library` 透传 `genre`；`library/service.import_from_deconstruct(genre_override=...)`。
- [x] 1.6 角色候选投影抽 `_character_candidate_items` helper（两出口共用）。

## 2. 前端：收录面板改全维

- [x] 2.1 `lib/deconstructApi.ts`：`CollectCandidates/CollectResult`、`getCollectCandidates`、
      `collectToKb`（解包 `{ok,data}`）、`toLibrary(..., genre?)`。
- [x] 2.2 `TaskDetailPage.tsx`：候选状态、分组勾选（默认全选未收过）、角色区（灰态/换名）、
      题材为空时的补选下拉、合并提交（先 dims 后角色）与合并 toast；失败留面板。
- [x] 2.3 卡片/面板文案：第三卡「把这次拆出来的写法、设定和角色收进知识库」；无内容原因可行动。
- [x] 2.4 收录范围跟随结果目录勾选：维度→产物文件名走 `DECONSTRUCT_DIMS` 单源；未勾的组/角色区
      从面板与提交里一起拿掉（重新勾上恢复）；勾中产物都不可收时给原因并禁用提交。

## 3. 测试

- [x] 3.1 后端：dims 过滤只落所选维＋src_key 稳定回归＋未知维忽略；候选端点四态矩阵、
      style-only 可收、仅 intro 时禁用、dims/genre 生效、exported_at/徽标；to-library genre 透传；
      撤回书 collect-candidates 403。
- [x] 3.2 前端：API wrapper 两条＋信封解包；组件混合/纯文风/纯角色/无内容/加载失败重试/分组勾选/
      全收过禁用/两种失败文案/题材补选；结果目录取消勾选后组收窄、角色区隐藏、提交载荷不含未勾维。
- [x] 3.3 e2e：`character-library.spec.ts` 桩切 `collect-candidates`＋`collect-to-kb`；角色用例断言
      只调 to-library；style-only 用例断言 dims/genre 载荷；未勾写作文风用例断言 dims 只剩 techniques。

## 4. 登记与门禁

- [x] 4.1 `docs/design-c/prototypes/ADJUSTMENTS.md` 2026-11-21 条目（drafts 资产、不进 parity）。
- [x] 4.2 本 change 的 delta 写入 `specs/deconstruct-book/spec.md`。
- [x] 4.3 门禁：后端 pytest 四文件 87 passed；前端 tsc 净；Vitest 131 passed；coverage exit 0
      （TaskDetailPage 新代码无未覆盖行）；`design:lint` 仅存量 preview.html emoji；e2e
      `character-library.spec.ts` 本 change 两用例 2 passed（同文件其余 4 例在 main 同环境复现红，
      存量、需生产基座，非本 change 引入）。
