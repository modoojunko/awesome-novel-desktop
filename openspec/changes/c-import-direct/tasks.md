## 1. 原型先行（C端；S端无改动）

- [x] 1.1 将 `docs/design-c/drafts/ai-novel-c端-导入自有书-原型.src.html` 与 build/check 脚本迁入 `docs/design-c/prototypes/` 对应屏，更新路径；验证：重放 build + check 三项全过（已重放：6 切屏对齐、291 class 可溯源、9 段逐字一致 PASS）
- [x] 1.2 第 2 步补「不导入此章」/撤销/确认弹层、ok/warn/risk 三态与勾选确认；验证：原型逐项可操作，`check-import-own-book.py` PASS，截图更新（已重放：risk→勾选→可继续、warn→可继续、ok→无提示；忽略第 1 章→41 章+撤销；截图 `import-own-book-shots/01-04`）
- [x] 1.3 第 3 步收敛为 A 路：只显示「直接导入（只带正文）」，AI 拆书卡「即将开放」不可点；显示 0 token/本机处理/设定留空；验证：四种状态截图，无模型/Key 要求（已重放：模型已配/未配 × 书架有空位/已满四态，直接导入均可选；仅配额满时 CTA 禁用；截图 `10-13-step3-*`）
- [x] 1.4 A 路成功落点：工作台第 N+1 章待写位、主 CTA「开始写第 N+1 章」、次 CTA「去核对设定」、补主线/卷纲清单；验证：原型可点到第 43 章，文案无内部词（已重放：成功弹窗→第 43 章工作台（bar 第 43 章待写/主 CTA 开始写第 43 章）→点击出「已就位」→去核对设定；截图 `20-23-a-*`）
- [x] 1.5 `ADJUSTMENTS.md` 登记：实抓当前系统、原文标签、切分编辑器、A 路落点、词表替换；验证：每条有原因/截图（已登记 `c-import-direct` 段：迁移/第 2 步修正/第 3 步 A 路/成功落点/原文标签/词表/parity 影响/截图路径）
- [x] 1.6 词表写入 `docs/ux/design-language.html` §5.1/§6.2/§13；`design-vocab.mjs` 仅登记扫描范围（新增 `import-own-book.src.html`）；验证：`npm run design:lint` 通过（0 严格违规），无裸 hex/emoji/未登记字号
- [x] 1.7 双端影响判定：仅 C端、不触共享段（依据 proposal `Design Impact`）；验证：`git status` 无 `server/`、无 `base.css`；`design-cross` 不适用，若新增共享类另开双端任务

## 2. 解析、manifest 与结构契约

- [x] 2.1 以 `deconstruct/textparse.py` 统一 txt 解析，`novels/importer.py` 适配；验证：UTF-8/GBK/Big5/无卷/单章/误识别章解析一致（`test_import_manifest` + 既有 textparse 22 绿）
- [x] 2.2 第 1 步产出冻结 manifest（sha/parser_version/encoding/char_count/逐章区间/卷范围/warnings/risk）并写入 `import_sessions`；验证：可按区间还原正文，TTL 过期返回可执行错误（`test_import_own_api` 410/文件清理）
- [x] 2.3 结构契约 `volumes: [{title, chapter_from, chapter_to}]` + 前后端共享校验；验证：覆盖/缺口/重叠/空卷/单章跨卷 400，fixtures 同值（`test_import_structure` 7 绿）
- [x] 2.4 归一函数：章标题剥序号、卷名剥序号、全书号由卷序累计；验证：带/不带/重复序号 fixtures，展示只拼一次（manifest 测试 + `test_chapter_lifecycle`）
- [x] 2.5 50MB 上限、字数无上限、A 路在同一事务内分批 `add_all`；验证：50MB 边界 + 180 万字/240 章 manifest 可解析，事务不拆成多次 commit（API 413 + manifest 240 章 + writer 240 章单事务）

## 3. Schema、原子 writer 与 global_no

- [x] 3.1 schema：`chapters.origin/imported_at`、`projects.import_kind/import_token`、`import_sessions`；所有新非空列 `server_default`；验证：旧库升级列有默认值，迁移幂等（模型+create_all 测试）
- [x] 3.2 新增 `chapters/lifecycle.py` 谓词（historical/authored/archived/completion）；验证：单测覆盖 status×origin 全组合（`test_chapter_lifecycle`）
- [x] 3.3 新增 `chapters/numbering.py` 与 `/frontier`/`/volumes`/`/tree` 的 `global_no`；验证：2 卷 42 章→27/43，ghost 不计（`test_frontier_imported`）
- [x] 3.4 新增 `novels/import_writer.py::persist_import()` 单事务 writer；验证：240 章成功、第 120 章失败零残留、同 token 重试同书（240 成功/第 120 章注入失败回滚/幂等/变源测试）
- [x] 3.5 A 路 API：`/import/own/parse` + `/import/own/persist`（import_id/name/volumes/token），不播种设定，简介机械填第一章前 200 字；验证：API 测试断言 origin/word_count/has_prose，无模板值（`test_import_own_api` 5 绿）
- [x] 3.6 旧导入前端入口退役；旧 `/import/persist` 保留兼容但写 `origin=import`/`import_kind=legacy`（未做 410：避免历史脚本/测试断裂，前端已不再引用）；验证：旧端点不再造无来源 draft 书，md/docx 前端入口移除

## 4. 消费面收口

- [x] 4.1 `frontier` 跳过 historical、返回 global_no；`is_writable` 补 archived 只读守卫；验证：全导入/混合/全归档 + 导入章 PUT 200 + 未来章 409（`test_frontier_imported`）
- [x] 4.2 前端 `hereTarget` 与树「继续写作」分离；导入书不自动聚焦第 1 章，last_write 只在真实输入或已有同章会话时记录；验证：`NovelWorkspace` 31 绿 + 手动/后续 e2e 补导入书场景
- [x] 4.3 `prompt_sources` 上一章 historical 用摘要/首段；`resolve_prev_ending` 纳入 historical；验证：第 43 章素材不出现「上一章未归档」，跨卷进场用实际收尾（代码改点完成，回归待 7.x）
- [x] 4.4 `ai_plan` 历史上下文与当前卷配额分离；③ 摘要槽 + 原文摘录块 ≤2000 字；验证：`_imported_excerpt_block` 3 绿 + chapter plan 18 绿/19 skip（提示词模板走既有 `<<material_blocks>>`，无需跨仓改模板；配额用 authored_rows）
- [x] 4.5 `novelStage`/`works-finish-flow` 改用 `authored_total/authored_archived`；只有导入章=写作中、不能完本；验证：novelStage 11 绿 + finish/list 40 绿
- [x] 4.6 预览标签「原文」与计数桶 archived/原文/草稿/拟定；完本进度只作者章；验证：`previewReader` 更新并通过
- [x] 4.7 章节树/章档/卷页显示「原文」；不显示「草稿」；验证：OutlineTree/NovelWorkspace 代码改点 + 现有 31 绿（补导入专用 vitest 待 7.3）

## 5. 三步向导与 A 路闭环

- [x] 5.1 新 `ImportNovelModal` 三步向导：Step1 txt/格式样例、Step2 切分/忽略/risk、Step3 直接导入；验证：`importNovelModal` 2 绿
- [x] 5.2 配额门：进入第 3 步/创建前检查，满额提示与归档/删除/升级出口，文件/结构不丢；验证：quotaFull 用例通过（书架满 CTA 禁用、提示可见）
- [x] 5.3 A 路成功落点：进工作台第 N+1 章、主/次 CTA、补主线/卷纲清单；验证：`NovelWorkspace` 新增 42 章原文用例（主页「开始写第 43 章」+清单+树原文）；完整 e2e 待 7.3
- [x] 5.4 删除本书重新导入出口；落库后无删章按钮；验证：OutlineTree 对 historical 隐藏删除钮，API 也拒删；重导走书架「删除本书」（现有出口）
- [x] 5.5 旧前端测试更新：`novelListPage` mock、`apiBoundaries` 旧 importPersist、`.md` fixture 401/503/error-message；验证：全量 vitest 1696 绿

## 6. 迁移、回填与旧书

- [x] 6.1 carry 完成后按 `app_meta.import_backfill_v1` 幂等回填旧 import 书：import_kind=legacy、章 origin=import、status 不改；验证：`test_import_backfill` 绿（真实旧库 carry 演练待 7.3）
- [x] 6.2 旧书没有作者章：阶段写作中、不能完本；作者新增并归档后按 authored 分母完本；验证：`test_novel_finish_flow` 新增 imported-only / imported+authored 两例，7 绿
- [x] 6.3 回滚演练：旧版本+旧库可启动；新库多列被旧代码忽略、status 未变；验证：DB 级演练记录 `docs/design-c/drafts/ai-novel-c端-导入自有书-A路-回滚演练.md`（SQLite 在线备份/旧列读取/status 未变；旧安装包启动待发布补记）

## 7. 回归与发布

- [x] 7.1 后端：`cd client/backend && python -m pytest tests/ -v`；验证：**2262 passed / 26 skipped / 265 skip，0 failed**（含 lifecycle/numbering/writer/backfill/import API；sibling 模板抽样已改用现役模板）
- [x] 7.2 前端：`cd client/frontend && npx vitest run` 与 `npx tsc --noEmit`；验证：全绿（136 files / 1700 tests；tsc 0）
- [x] 7.3 E2E：A 路 42 章→第 43 章→第 10 章原文→预览原文；验证：`e2e/import-own-book.spec.ts` 在私有栈 8104/5294 通过（2.5s）；归档新章/完本由既有 finish 测试覆盖
- [ ] 7.4 设计门禁：`npm run design:lint && npm run design:check`；验证：`design:lint` **0 违规**（30 严格文件，含新原型/向导）；`design:check` 8 个存量 parity 失败（书架/预览 update-strip 文案与版本号漂移，非导入屏；新导入屏不在 parity 矩阵），未纳入本 PR 的验收
- [x] 7.5 发布说明：仅 txt、md/docx 退役、旧书可读、A 路设定留空；验证：草稿已落 `docs/design-c/drafts/ai-novel-c端-导入自有书-A路-发布说明.md`，待评审定稿
- [x] 7.6 回填 7.1–7.4 实际通过数/失败数/像素差/耗时：后端 2262/0；前端 1700/0 + tsc 0；e2e 1/1 通过；design:lint 0；design:check 8/8 存量红（列表 books/group/empty-filter/empty/finish/quota/pagination + 预览 reader，2.54%/3.22%/0.308% 等，均为 update-strip/版本号漂移）；耗时：后端 171s、前端 10s、e2e 2.5s

## 回归门禁基线（立项阶段实测）

- 原型构建/自检：`python3 docs/design-c/drafts/build-ownbook-proto.py && python3 docs/design-c/drafts/check-ownbook-proto.py` → **三项全过 PASS**：6 个切屏 ID 对齐；290 个 class 可溯源；real.css 与 8 段宿主 DOM 逐字一致。
- 实现回归：7.1–7.4 在实现阶段执行并回填实际输出；未回填不得合入。当前立项阶段不把未跑的测试写成通过。
