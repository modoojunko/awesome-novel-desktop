# Tasks

> 实现已落地并全量回归（见第 4 节证据）；随本变更归档。

## 0. 评审前置修复（P0，已落地）

- [x] 0.1 主线性单源 `chapters/scope.py`：frontier（含 revert 基序）与书架统计接入 `ghost_of IS NULL` 唯一构造入口——验证：`tests/test_rewrite.py::TestFrontierNotHijacked`（重写已归档章后旧稿不抢 frontier）
- [x] 0.2 ref 解析单源 `lib/chapterRef.ts`（判别联合）替换工作台 11 处裸正则＋NovelWorkspace 白名单改走单源——验证：`src/__tests__/chapterRef.test.ts`（解析表＋源码守卫：别处出现 `-ch-(\d+)` 直接挂）
- [x] 0.3 指纹门禁纯增量迁移：`legacy_archive.classify_drift`＋`archive_if_legacy(…, metadata)`＋main.py 指纹戳刷新——验证：`tests/test_legacy_archive_and_refs.py`（additive 不改名/破坏性留档/不可读留档）

## 1. 后端（已落地）

- [x] 1.1 合成端点 `POST /api/novels/{id}/chapters/{ref}/rewrite`：内容寻址快照（`{ref}-r{8hex}`）＋归档章解锁＋下游 stale 置位，一事务；拒 ghost 源 409／无正文 409——验证：`tests/test_rewrite.py`（全链/幂等/409 族）
- [x] 1.2 `chapters.stale` 列＋单写入口清除（save_chapter 统一清）——验证：`test_stale_cleared_on_own_save`
- [x] 1.3 契约字段：卷章树章条目 `stale`（且 chapter_count 取主线实测）；章详情 `stale`；`/ghosts` 加 `origin(revert|rewrite)`＋`created_at`——验证：`test_rewrite_full_chain` 契约断言
- [x] 1.4 产物寻址单源 `backup.format.belongs_to_ref` 接入 importer（prompts/archives 边界匹配）——验证：`tests/test_legacy_archive_and_refs.py::TestBelongsToList`（含前缀碰撞与旧稿后缀）

## 2. 前端（已落地）

- [x] 2.1 `useChapterData.flush()`（落盘并等待；重写确认前置）——验证：类型面＋e2e 全链（旧稿含最后一段）
- [x] 2.2 操作页签「重写这一章」卡（has_prose 且非支线）＋影响面确认弹窗（旧稿/后续/设定三行）＋快照期间禁用——验证：`src/__tests__/rewriteFlow.test.tsx`（RewriteModal 三行/busy）
- [x] 2.3 确认流：flush → 合成端点 → 解锁后 reload → 树刷新（useWorkbench.refresh＋useOutline.refetchTree）→ 落正文页签聚焦——验证：`e2e/chapter-rewrite.spec.ts` ①
- [x] 2.4 角标三面：树行 `.tag-stale`（`data-testid="ch-stale"`）／设定投影提示（`ch-stale-note`）／右栏「操作」统计（`staleDownstream` props 注入）；正文保存成功刷新树消角标；归档提示在下游有角标时追加说明——验证：`rewriteFlow.test.tsx`＋e2e ②③
- [x] 2.5 样式 `.tag-stale`（虚线中性；避开 cfg 摘要 `.tag`）＋`.rw-list` 确认弹窗——验证：design:lint 过
- [x] 2.6 e2e 波及核验：全量 e2e 绿（含既有 modals/免费流用例）

## 3. 旧稿只读查看（已落地）

- [x] 3.1 点旧稿可打开：`parseChapterRef` 判别联合＋白名单修复后，旧稿行在正文页签呈现 contenteditable=false 只读——验证：e2e ④

## 4. 回归证据（全部本机全量执行）

- [x] 4.1 后端全量 pytest：**1080 passed**（含新增 test_rewrite 6 例＋test_legacy_archive_and_refs 12 例）；仅 brand/entitlement 2 条共享契约对拍在 client/ 整目录挂载姿势下为已知基线红（挂载假红，非回归）——命令：client/ 整目录挂载容器内 `pytest tests/`
- [x] 4.2 前端 vitest 全量 345 passed（含 chapterRef 4 例、rewriteFlow 3 例）＋tsc 零错误＋design:lint 通过
- [x] 4.3 C端 e2e 全量：**145 passed / 0 failed / 14 skipped**（含新增 chapter-rewrite 全链一例）
- [x] 4.4 `openspec validate chapter-rewrite --strict` → archive（workbench/chapter-data 增量 sync）
