## Why

2026-09-17 storyline.html 写作工作台改版（ADJUSTMENTS #27 ①-⑫）只落了章对象视图（页签/右栏/弹窗），**卷视图整页漏改**（用户 2026-09-19 指出）：中栏选中卷仍是 book.html PR4 时代的旧卷纲面板（常编辑态、弧线模式/主导驱动力/冲突阶梯/章节规划/角色发声旧字段集），右栏卷选中态还挂着三张「规划中」卡；而原型里卷视图已是「四页签 + 查看/编辑两态卷纲页 + 随页签卷语境右栏」的全新设计。

## What Changes

- **BREAKING 卷纲数据模型换代（无用户，干净方案，不做旧字段兼容读）**：
  - 新增：整体目标 `goal`、预期结局 `ending`、本卷登场人物 `cast[{who,target,change}]`、本卷关键剧情节点 `nodes[{stage,text}]`、本卷埋下伏笔 `plants[]`、本卷揭露信息 `reveals[]`（后两类一行一条）。
  - 保留：本卷主旨 `summary`、结构模板 `template_name`、章数目标 `chapter_target`、核心矛盾 `core_conflict`、卷名 `title`（编辑入口移入卷纲编辑表单，树上铅笔改名维持现状）。
  - 退役（迁移时删除，不读不写）：`direction_method`、`emotional_arc`、`arc_mode`、`primary_drive`、`info_gap_start`、`info_gap_end`、`stages`、`conflict_ladders`、`chapter_plans`、`character_voices`。
- **卷视图改四页签**：选中卷 = 头部（卷 · 分卷计划 / N 章 / 已归档 N 章）＋页签「卷纲｜本卷章节｜角色关系｜伏笔」【范围拍板 2026-09-19：按原型整页四页签实现（含本卷章节台账与卷域关系/伏笔投影），不拆分为单页签范围】。
- **卷纲页签查看/编辑两态**：查看态=卷基础信息、本卷剧情（核心矛盾/整体目标/预期结局）、本卷登场人物（台账）、本卷关键剧情节点、伏笔与信息披露、章节拆分说明、本卷进度线（已归档/草稿/拟定/待写）；点「编辑卷纲」进编辑态（保存/取消，沿用脏守卫）。
- **本卷章节页签**：本卷章节台账（状态随行）＋旧稿支线提示＋「在本卷新增一章」（仅主线待写位在本卷时可用）。
- **角色关系/伏笔页签卷域复用**：全书关系图＋本卷边高亮（卷内只读）；伏笔台账按本卷埋下/回收过滤投影。
- **右栏卷选中态换语境面板**：三张「规划中」卡退役，改为随卷页签切换的引导语＋统计卡；**卷域 AI 动作清单不随本 change 实装**（补全本卷章纲/节奏体检/卷末钩子等需新端点，另行 propose）。
- **卷纲素材装配单源升级**：提示词六来源「大纲 · 卷纲」、写章背景「本卷概要」、卷纲冲突检测素材，统一从「仅卷摘要」升级为卷纲纯文本（行标签与格式逐字对齐原型 `volOutlineText`；只做剧情规划口径，不含角色言行；全空返回空串以维持「未填=chars 0」）。
- **迁移沿既有留档 doctrine（无用户，不做兼容层）**：破坏性 schema 换代走既有「指纹不符→三件套留档→空库新 schema」路径——不建白名单档、不写旧列 DROP 迁移、不做旧数据映射；本机库首启留档重置为已登记影响。备份包同步 `format_version: 4`，**不做 N-1 读窗**（旧包不承诺可导入）。
- **章工作台「信息差对齐」块随旧字段退役（显式，非静默）**：该块读取本 change 退役的 `info_gap_start/end` 与 `chapter_plans`，随批删除并登记（`ChapterWorkspace.tsx`＋`OgPane.tsx`＋对应 e2e）。
- **与在途 c-workbench-outline-fixes 的关系（评审裁定）**：其 ②（章数目标布局）摘除——四件套同步收窄（含其 workbench delta 的那条 requirement）；其 ①（顶栏计数一致性）③（批量确认空态禁用）保留，且建议**先合**（其 `refetchTree` 修复让本 change 卷视图刷新链路更可靠；本 change 首启若触发迁移，其验证需要现成数据）。

## Capabilities

### New Capabilities
- `volume-outline`：卷视图（四页签）与卷纲页——字段集两态呈现、进度线、本卷章节台账、卷域关系/伏笔投影、卷纲文本装配单源、数据模型换代。

### Modified Capabilities
- `workbench`：右栏「AI 辅助」面板需求中「卷选中态右栏形态不变」改为「随卷页签切换的引导语＋统计卡；无动作清单（无占位纪律不破）」；未选中卷时右栏维持通用空态说明。
- `prompt-crafting`：「大纲 · 卷纲」来源内容由「本卷概要」升级为卷纲纯文本（行标签对齐原型）；未填卷纲空态语义不变。
- `backup-restore`：format_version 演进为 4（卷纲删键升版，版本演进规则照既有形状）；卷纲段契约换代（新键集合）；**N-1 读窗与 N-1 恢复演练对本版豁免**（无用户，旧包不承诺可导入；本版验收＝留档断言＋新格式自身 roundtrip，登记）。
- `workbench-3-label`：「卷节点点击弹出右侧抽屉（卷纲编辑）」已漂移且与新形态冲突 → REMOVED，ADDED「卷节点点击打开中栏卷视图（卷 · 分卷计划）」承接。
- `volume-chapter-service`：`update_volume` 卷纲字段「只写 YAML」旧口径退役（卷纲全字段 DB 单源，YAML 仅派生/留痕）。

## Impact

- **后端（client/backend）**：`models/volume.py`（新标量 goal/ending/plants/reveals ＋新子表 volume_cast_members/volume_plot_nodes，删旧四子表与六旧列）、`volumes/schemas.py`（VolumeUpdate 换代＋行长度纪律；`plants/reveals` wire＝`list[str]`，storage＝单 TEXT 列一行一条）、`volumes/service.py`（get/put 换代；`get_volume` 章节改主线过滤＋补 `outline_summary`/`ghost_count`）、`volumes/render.py`（装配单源，新文件）、`main.py`（**精确**删六条旧列 ADD 块（213-219/234-268），保留 template_name/core_conflict/chapter_target 三条补列；死列残留会让未来加法迁移被 `classify_drift` 误判 breaking；无 DROP 迁移代码）、`repositories/volume_repo.py`（`get_info_gap_by_root` 死码删除、`get_summary_by_root` 改名）、`backup/format.py`（FORMAT_VERSION 4）＋`backup/importer.py`（卷段换代到新键集，不写旧键映射）＋`backup/export.py` 与 `novels/router.py` 导出链回归。
- **消费点切换（装配单源）**：`write/prompt_sources.py`、`write/chapter_writer.py`（含 gate 与文案两处）、`chapters/ai_draft.py`（两处）、`write/ai_check.py` 共 4 文件 8 处，`ctx.volume_summary` 更名 `ctx.volume_outline`。
- **前端（client/frontend）**：`VolumePanel.tsx` 重写为 `VolumeWorkspace`（四页签容器）＋卷纲两态面板；`ChapterWorkspace.tsx`＋`OgPane.tsx` 信息差块退役；复用/扩展 `RelationsGraphPane`、`HooksPane`（卷域 props）；`Rail.tsx` 卷分支换语境面板（数据走上抛回调，与章模式同构）；`novel/volume/{types,form}.ts` 换代；`NovelWorkspace.tsx` 挂载与右栏数据通路；`design/book.css` 业务层新增卷视图段（复用 `.ch-tabs/.chtab` 等既有族，零 base.css 改动）。
- **原型与登记**：`docs/design-c/drafts/storyline.html` 为设计事实源（#27 口径）——**本 change 补入库**（现为 untracked）；`docs/design-c/prototypes/ADJUSTMENTS.md` 新登记条（偏差：章数目标编辑态保留可编辑＋布局口径、卷域动作清单暂缺另行立项、结构模板枚举字面沿产品单源、信息差块退役、book.html 卷纲段过时且 volume parity case 处置、原型 aiVolHTML 动作段领先实现勿照补、待写口径取 frontier（原型 pendingInfo 有意偏差）、卷域伏笔归类/关系图例为原型外新增、留档重置＋N-1 读窗与演练豁免）；book 屏 parity 的 `volume` 用例与 `book.volume.*.png` 基线随批处置（下线＋登记，或重录——二选一，见 design）。
- **测试**：后端 pytest（schema/service/装配/备份 roundtrip/卷纲 crud 改写；本机库首启留档重置的验证走既有升级演练）；前端 vitest（卷纲两态、页签、进度线、右栏语境）；e2e 存量三件改写（`workbench-features.spec.ts` 信息差＋卷纲段、`free-writing-flow.spec.ts`、`design-parity-book.spec.ts` volume case）＋卷视图最小新覆盖；design:lint/design:check。

## Design Impact

- 受影响端：**仅 C端**（client/frontend + client/backend 本机 SQLite）。S端 无涉及；不触两端共享段（base.css 令牌与基础组件类零改动，全部落业务层 book.css 与 workbench 组件）。
- 受影响屏/弹层：写作工作台 book 屏——中栏卷选中态（整页重构：头部＋四页签）、右栏卷选中态（语境面板）、顶栏无改动；删除确认等弹层不涉及。
- 对象状态（对照 design-language §5）：沿用既有语言——折叠块（details/cfg）、台账（ledger）、行编辑卡与「＋加一行」、btn 家族、禁用态（disabled＋title）、tag 徽；无新组件词汇、无第四种胶囊、语气词仍限 info/ok/warn/err。
- 是否需要原型先行：**原型已就绪**——storyline.html 即设计事实源（同 ADJUSTMENTS #27 口径：drafts 目录、未收编严格扫描、本 change 补入库）。注意：**book 屏 parity 存在活跃 `volume` 用例与在库基线**（`design-parity-book.spec.ts`、`baselines/book.volume.*.png`），随批显式处置（默认下线＋登记「卷纲屏事实源转 storyline.html」，或 book.html 换稿重录——见 design Open Questions）；本 change 在 ADJUSTMENTS.md 登记全部偏差与理由。
- 设计工件由谁产出：实现侧自查（全部为既有语言的重排；无新视觉形态）。
