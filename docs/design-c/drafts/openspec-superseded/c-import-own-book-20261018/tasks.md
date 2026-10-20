## 1. 原型先行（C端；S端无改动）

- [ ] 1.1 将 `docs/design-c/drafts/ai-novel-c端-导入自有书-原型.src.html` 与构建/自检脚本迁入 `docs/design-c/prototypes/` 的对应屏文件，更新脚本内路径；验证：重放 `python3 .../build-ownbook-proto.py && python3 .../check-ownbook-proto.py` 三项全过，产物无残留占位符
- [ ] 1.2 第 2 步补章节级修正：误识别章「忽略/删除」、删除确认弹层、risk 显式勾选（「我了解质量风险，仍要导入」）、无卷/有卷/切分/挪边界/合并/改名/折叠全交互；验证：原型内逐项操作可完成，`check-ownbook-proto.py` PASS，更新对应截图
- [ ] 1.3 第 3 步/任务/开书补大书段 UI：任务详情「第 X/N 段」、费用/时间按段累加、失败段重跑、开书确认/执行（2 秒后显示四段真实计数）/回执、失败/取消「跳过设定直接开书」；验证：切屏截图覆盖四种状态，文案无「后台会跟进」
- [ ] 1.4 在 `docs/design-c/prototypes/ADJUSTMENTS.md` 登记本批偏差：原型基于实抓当前系统、开书 2 秒延迟规则、原文/历史章标签、切分编辑器无单章跨卷；验证：每条有原因、截图路径与影响屏
- [ ] 1.5 双端影响判定：本 change 仅 C端、不触碰 `base.css` 令牌与共享组件词表（依据 proposal `Design Impact`）；验证：`git diff --stat` 无 `server/` 与 `@cross` 共享段；若实现中新增共享类，另开双端同批任务并跑 `node scripts/design-cross.mjs`
- [ ] 1.6 登记新增用户可见词：「原文/历史章」「已完成·待开书」「已开书」「导入/拆书」写入 `docs/ux/design-language.html` §5/§6/§13 与 C端 `client/frontend/scripts/design-vocab.mjs`；验证：`npm run design:lint` 通过，文档与白名单同键；不新增裸 hex、emoji 或未登记字号

## 2. 解析与结构契约（Phase 1）

- [ ] 2.1 以 `deconstruct/textparse.py` 统一 txt 解析，`novels/importer.py` 改为适配层；验证：pytest 覆盖 UTF-8/GBK/Big5、无卷、单章、误识别章，且同一文件在两处解析出的章数/标题一致
- [ ] 2.2 第 1 步解析产出冻结 manifest（`source_sha256`、`parser_version`、`encoding`、`char_count`、逐章 `char_start/end`、卷范围、warnings、risk）；验证：`/import/parse` 返回新增字段，manifest 可按区间切片还原正文
- [ ] 2.3 增加临时导入会话 `import_id` 与 TTL，A 路 persist / B 路建任务复用同一 manifest，避免重复上传；验证：过期/缺失 `import_id` 返回可执行错误，清理任务不误删使用中的源
- [ ] 2.4 落结构契约 `volumes: [{title, chapter_from, chapter_to}]` 与前端/后端共享校验（覆盖 1..M、连续、每卷≥1、无重叠/缺口）；验证：pytest + vitest 对同一组 fixtures 给出相同 valid/error，缺口/重叠/空卷均 400
- [ ] 2.5 归一函数：章标题剥「第X章/回/节」序号、卷标题剥「第N卷」序号、全书号由卷序+卷内序计算；验证：fixtures 覆盖原文带序号/不带序号/重复序号，界面与提示词只拼一次
- [ ] 2.6 50MB 上限与字数无上限：HTTP 层拒绝超限，解析不设字数上限，A 路落库按批写入；验证：50MB 边界测试 + 180 万字/240 章 manifest 可解析

## 3. A 路落库与 imported 消费面（Phase 1）

- [ ] 3.1 Schema 迁移：`chapters.status` 支持 `imported`、`chapters.origin/imported_at`、四域章档 `origin`、`books.import_token`、`chapter_dossier_coverage`；验证：迁移幂等、旧库 fixture 升级后 schema 指纹符合预期
- [ ] 3.2 新 `importPersist`：接收 `import_id + name + volumes + import_token`，单事务建书/卷/章/正文，章状态 `imported`，`seed_settings=false`；验证：API 测试断言无模板设定、重复请求返回同一本书、失败整笔回滚
- [ ] 3.3 frontier 跳过 imported：首个 `status not in (archived, imported)`；全导入/全归档返回待写 N+1；`is_writable` 保持「有正文可写」，不新增历史章只读；验证：pytest 覆盖全导入/混合/全归档、导入章 PUT 200、未来无正文章 409
- [ ] 3.4 前端 `hereTarget` 与章节树「继续写作」分离：会话优先（允许编辑中的导入章），无会话回 frontier；树入口恒 N+1；验证：vitest 覆盖导入书首次续写 43、编辑第 10 章后树入口仍 43
- [ ] 3.5 `story_state` 折叠 imported 的 accepted 基线行，A 路无基线整块缺席，stale 跳过并注明；验证：pytest 覆盖有基线/无基线/stale 三态
- [ ] 3.6 章节树/归档页/预览加「原文」标签，概览加原文计数、完本进度排除 `origin=import`；验证：vitest 覆盖 42 章全导入（原文 42、已归档 0、续写 43）
- [ ] 3.7 旧导入书 backfill：`source=import` 的非归档章 draft→imported、全部章 `origin=import`、archived 保留；验证：迁移 fixture 打开旧书后续写 43、预览标原文、不再落第 1 章
- [ ] 3.8 旧 `ImportNovelModal`/`ImportPreviewTree` 退役，新向导 Step 1/2/3 接 A 路；验证：vitest 覆盖只收 txt、risk 勾选、无卷新增/切分、忽略/删除、A 路立即建书；e2e A 路通过

## 4. B 路任务与分段（Phase 2）

- [ ] 4.1 `deconstruct_jobs` 增 `source/structure_json/manifest_json/source_sha256/parser_version/segments_json/segment_index/open_*` 字段；导入建任务带结构、不建书；验证：API 测试断言任务存在、书不存在、结构/manifest 原样可取
- [ ] 4.2 分段器按活动章序切段（每段 ≤60 万字，单章超限独占一段）；dispatcher 串行跑段、写 `segment_index`、段失败只重跑该段；验证：pytest 用 180 万字/240 章 fixture 断言 3 段，段 2 失败重跑后段 1/3 不重复
- [ ] 4.3 任务清单按 `source` 分「导入/拆书」、顶部筛选、导入任务页头标「导入」、无导出出口；验证：vitest 覆盖筛选/标签/无导出、清单三态与详情页头
- [ ] 4.4 交接通知与完成确认：创建后落任务清单/详情，文案含「应用内继续/不要关闭应用/关闭会暂停、下次打开继续」；完成行「已完成·待开书」＋「开书」；已开书「进入书内」；验证：vitest + e2e 断言文案，不出现「后台会跟进」
- [ ] 4.5 分段产物按域合并（meta 后段非空覆盖；世界/角色/关系/伏笔按键去重合并；主线按弧拼接；逐章基线不跨段）；验证：pytest 三组合并 fixture，冲突有确定结果

## 5. 逐章基线与章档（Phase 2）

- [ ] 5.1 开书时从 `dims_json.cards.entries` 映射四域基线（设定/关系/伏笔锚定/出场角色），写 `origin=import` + accepted，物品/认知写 coverage `not_extracted`；验证：pytest 断言 42 章各有基线、无 42 次 AI 调用、伏笔台账不双写
- [ ] 5.2 `archive/dossier.py` 读取放宽到 archived/imported（imported 只返回 origin=import accepted 行），`rows_only` 不误伤 A 路；验证：pytest 覆盖 imported 行可读、A 路空、作者否决行不消费
- [ ] 5.3 「补算」fill_missing：只补指定域、不替换已 accepted、不自动归档、不级联 stale；验证：pytest 覆盖补物品后设定/关系行逐字不变
- [ ] 5.4 编辑导入章置 `dossier_stale`，章档/写作页提示下游影响并提供补算入口；单章归档默认沿用基线、显式重提才走四域提取；验证：pytest + vitest 覆盖 stale 提示、归档不重提、显式重提覆盖警示
- [ ] 5.5 回执列明基线覆盖章数、「首尾约 6000 字，中段可能未覆盖；物品/认知未提取」与补算入口；验证：开书回执快照断言，文案不出现内部术语

## 6. 开书状态机与出口（Phase 2）

- [ ] 6.1 `open_state/open_claim/open_stage/open_receipt_json` 状态机与原子 claim；验证：并发两次开书只有一次成功，另一次返回「正在开书」，不写重复数据
- [ ] 6.2 阶段回执幂等：book/settings/volumes/chapters 各阶段完成写回执，重试跳过已完成阶段；验证：pytest 模拟阶段 3 失败后重试，阶段 1/2 不重复、阶段 3/4 完成
- [ ] 6.3 重构 `deconstruct/apply.py::import_book`：接收确认结构与 manifest，`seed_settings=false`，导入任务 `condense_world=false`；世界压缩移到拆书收尾；验证：开书过程无模型调用、手工任务旧出口回归不变
- [ ] 6.4 源 sha 校验与 `need_reupload`：源缺失/变更不写任何阶段；部分态书不在书架露出，任务行「开书未完成·继续开书」；验证：pytest + vitest 覆盖 sha 不一致、继续开书、书架过滤
- [ ] 6.5 确认页「调整结构」仅允许在未建书阶段回第 2 步，更新 `structure_json`；部分态禁止并给出口；验证：API 测试 + 原型交互
- [ ] 6.6 开书弹窗确认/执行/回执：执行先按钮 loading，1.2–2 秒未完成再显示四段真实计数；完成后回执列写入/未写入/未提取；验证：vitest fake timers 覆盖快/慢两态，e2e 走通回执进入书内
- [ ] 6.7 失败/取消降级 `chapters_only`：只灌章节、不写设定/基线、不另建空书、重复点返回同一本；验证：pytest + vitest，进行中任务不出现该入口

## 7. 模型、配额与费用前置（Phase 2）

- [ ] 7.1 后端 `require_project_limit` 补到 A 路 persist、B 路任务创建与开书三处；B 路建任务前跑模型探针；验证：pytest 覆盖配额满 4xx、无模型不建任务、探针失败不产生任务
- [ ] 7.2 前端第 3 步模型行/未配禁用/去配置、配额满 notice 与禁用创建；验证：vitest 覆盖四种组合（模型有/无 × 配额有/无），直接导入始终可选
- [ ] 7.3 费用/时间按解析出的字数与章数计算：token=字数×1.5–2.5、时间=0.5–0.8 分钟/章＋8–10 分钟收尾、±30%、按段累加、A 路 0 token；验证：改字数/章数快照随之变化，不写死示例值

## 8. 大书与性能（Phase 2）

- [ ] 8.1 A 路 180 万字/240 章 smoke：解析、结构确认、落库、打开书、续写 241；验证：隔离栈 e2e，章节列表搜索/虚拟滚动可用
- [ ] 8.2 B 路 3 段端到端（AI 桩）：任务详情段进度、段 2 失败只重跑段 2、开书回执「3 段完成」与基线覆盖章数；验证：pytest + e2e
- [ ] 8.3 开书 p90 打点与 2 秒延迟呈现；50MB 解析内存/耗时记录；验证：性能记录写入 change 目录，四段进度在快路径不出现
- [ ] 8.4 大章节列表性能：>500 章搜索/筛选/虚拟滚动，不阻塞结构编辑；验证：前端性能测试/手工记录

## 9. 迁移、回归与发布

- [ ] 9.1 迁移与 backfill 全量回归：旧 import 书、旧手动拆书任务、旧 archived 导入章、空书；验证：pytest 迁移用例全绿，旧书续写 43、预览原文、完本进度不前进
- [ ] 9.2 后端回归：`cd client/backend && python -m pytest tests/ -v`；验证：全绿，新增用例覆盖 D3 消费面表逐行
- [ ] 9.3 前端单元/类型：`cd client/frontend && npx vitest run` 与 `npx tsc --noEmit`；验证：全绿，新增向导/任务/开书/标签用例通过
- [ ] 9.4 E2E：A 路、B 路（桩）、旧书 backfill、大书 smoke；验证：隔离栈全绿，失败集合与基线 A/B 对比无新增
- [ ] 9.5 设计门禁：`cd client/frontend && npm run design:lint && npm run design:check`；验证：全绿；`design-cross` 不适用（仅 C端、不触共享段，依据 proposal Design Impact）；若新增共享类则补跑并记录结论
- [ ] 9.6 发布与沟通：发布说明写明「新导入仅 .txt，md/docx 入口退役」，旧书可读；备份/回滚步骤演练；验证：说明评审通过，回滚演练记录在 change 目录
- [ ] 9.7 回归结论回填：把 9.2–9.5 的实际命令输出摘要（通过数/失败数/像素差/耗时）写入本节；验证：无「待回填」字样才允许合入

## 回归门禁基线（立项阶段实测）

- 原型构建/自检：`python3 docs/design-c/drafts/build-ownbook-proto.py && python3 docs/design-c/drafts/check-ownbook-proto.py` → **三项全过 PASS**：6 个切屏 ID 对齐；290 个 class 全部可溯源（49 个 gl- graft 不计）；real.css 与 8 段宿主 DOM 逐字一致（263534 chars / 6085+3148+1238+4255+2687+49089+40352 chars）。
- 实现回归：9.2–9.5 的命令在实现阶段执行并回填实际输出；未回填不得合入。当前立项阶段不把未跑的测试写成通过。
