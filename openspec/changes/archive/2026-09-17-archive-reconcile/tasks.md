# Tasks

> 实现与验证全部落地（收尾归档轮：legacy 退役＋补齐测试；测试首跑撕出多个实现 bug 并已修，见第 5 节）。

## 1. 后端——schema 与迁移

- [x] 1.1 `models/character.py`：character_relations +origin_chapter_id（FK SET NULL）；`models/chapter.py`：ChapterCharacter +state_change；新 `models/reconcile.py`：ChapterReconcile（novel_id/chapter_id FK CASCADE、kind、status、payload、时间戳）——验证：`tests/test_reconcile.py::TestModelAndUpsert`（级联删除/未决覆盖/已决留痕）
- [x] 1.2 迁移：main.py 幂等 ALTER（origin_chapter_id/state_change）＋schema 指纹；存量 ch_ref→origin_chapter_id 一次性解析回填（SQL 关联 chapters.ref；幂等，可解析外留空）——验证：`tests/test_legacy_archive_and_refs.py`（纯增量迁移原地不存档）＋回填 SQL 重跑无常改
- [x] 1.3 导出/导入接线：chapters 段含 state_change；relations 段含 origin_chapter（ref 形式）＋导入 ref→id 重绑；chapter_reconcile 界外不随包——验证：**删库救回演练** `tests/test_zz_disaster_recovery_drill.py`（导出→drop_all/create_all 清库→导入→逐层断言恢复＋界外零行）

## 2. 后端——归档拆分与收尾服务

- [x] 2.1 `archive/service.py` 同步段维持（archives/mentioned/threads/状态迁移）；AI 收尾迁后台单飞线程（backup/export._job 模式）；归档响应返 `reconcile_started`——验证：`tests/test_archive_ai_summary.py`（同步段单次摘要＋收尾启动标志）
- [x] 2.2 收尾服务：五类 prompt（设定变化/关系/伏笔含证据句/世界要素/角色状态；world 类含 set 归属）＋同键未决覆盖＋已决留痕；采纳写回走对象自身服务；失败置 failed 保留 payload——验证：`tests/test_reconcile.py`（五类写回/lore 分支/覆盖留痕/失败留 payload）
- [x] 2.3 端点：`GET /reconcile`（行＋进度聚合）、accept/reject/retry（409 族、retry 仅失败行）；**legacy 退役**：`update_character_states` YAML 追加路径删除（legacy 键与数据保留）、归档响应去除一次性 lore 建议（改提案制，前端世界面板暂存区同步退役）——验证：`TestEndpoints`＋`test_archive_ai_summary.py` 新契约
- [x] 2.4 提示词与体检不回归：未确认提案不注入——验证：`tests/test_reconcile.py::TestNotInjected`（pending 行记号不出现在 to_prompt/material_markdown）
- [x] 2.5 后端全量回归——验证：第 5 节数字

## 3. 前端——两页签与收尾 UI

- [x] 3.1 `ChapterWorkspace`：「设定」页签两子视图＋「操作」页签（回退卡/重写卡/收尾区）——验证：`NovelWorkspace.test.tsx`＋e2e 工作台用例
- [x] 3.2 「操作」页签收尾区：进度聚合、逐条采纳/驳回/失败重试；免费档 PRO 占位——验证：`src/__tests__/ReconcilePane.test.tsx` 5 例
- [x] 3.3 收尾状态轮询（归档章挂载即拉＋5s；免费不轮询）——验证：`ReconcilePane.test.tsx` 免费档零请求＋e2e 轮询可见
- [x] 3.4 原型与登记：storyline.html 为事实源；文案过 §13——验证：ADJUSTMENTS #27 登记
- [x] 3.5 e2e 全链：`e2e/reconcile.spec.ts`——①PRO：绑桩模型（本地 stub /v1/models＋chat.completions 按类别回预置 JSON）→归档→后台收尾产出五类提案→**采纳**（世界设定真写回带 origin）与**驳回**；②免费档：收尾区 PRO 占位且零 /reconcile 请求。未确认不进提示词由 2.4 直证

## 4. 回归与门禁

- [x] 4.1 `tsc`／`design:lint`／`vitest` 全绿；parity 不受影响——验证：第 5 节
- [x] 4.2 后端 pytest 全绿＋ruff——验证：第 5 节
- [x] 4.3 导出/导入演练：含 state_change/origin_chapter 的包跨机恢复＋删库救回演练——验证：`test_zz_disaster_recovery_drill.py`

## 5. 收尾轮：测试首跑撕出的实现 bug（全数已修）

1. `_upsert_pending` 往 DateTime 列塞 ISO 字符串 → SQLite TypeError（收尾任务一落行即炸）→ 走列 server_default
2. `reconcile_router._chapter_by_ref` 用 `Chapter.novel_id`（不存在）→ GET 列表恒 500 → 改 `project_id`
3. `_chapter_and_novel` 同因（retry 恒 500）→ 同修
4. `GET /reconcile` 把 `user["id"]` 当 user dict 传入 → 恒 500 → 传 dict
5. `apply_accept` world 分支条目缺 `set` → lore-apply 恒 ValueError（采纳必失败）→ set 归属（白名单外回落 extra）＋prompt 补 set 指引
6. `apply_accept` world 路径硬编码 `settings/world.yaml`（应用读 `world-setting.yaml`）→ 写进野文件 → 走 KEY_TO_PATH 单源
7. `apply_accept` hooks 分支函数内 `import select` 函数级遮蔽 → UnboundLocalError（hooks 采纳必崩）→ 移除内层 import
8. accept 端点缺 commit → 200 但行状态不落库（前端永远待确认）→ 补提交
9. `_upsert_pending` 返回 id 前未 flush → 返回 None → flush 后返回
10. ReconcilePane 免费档仍轮询收尾接口 → 免费不发请求

**验证数字（本机全量）**：后端 pytest 1093 passed（新增 test_reconcile 10＋drill 1；brand/entitlement 2 条为「只挂 client/」姿势的仓库根相对路径假红，与本变更无关）；vitest 348 passed（新增 ReconcilePane 5）；e2e 全量含新增 reconcile 2 例；ruff+tsc+design:lint 全过。
