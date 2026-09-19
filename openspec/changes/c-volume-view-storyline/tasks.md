> 实现纪律（用户 2026-09-19 指定）：代码定位一律先走 CodeGraph——`codegraph explore "<符号/问题>"`（仓库已建 `.codegraph/`，AGENTS.md 口径），再退回 grep/find；改任何符号前先看其 blast radius。

## 0. 原型与登记先行（UI 变更固定首任务）

- [x] 0.1 `git add docs/design-c/drafts/storyline.html`（设计事实源现为 untracked，先入库）；核验原型卷视图段就绪（**以符号名检索为准**，行号随盘刷新：`volOutlineText`≈1609／`volReadHTML`≈3090／`volEditHTML`≈3122／`volOutlineHTML`≈3173／`volChaptersHTML`≈3195／`volumeEditorHTML`≈3208／卷域截断 `relsHTML(0, order, false)`、`hooksHTML(0, order)`／`aiVolHTML`≈3408）。验证：文件在 `git status` 中不再是 untracked
- [x] 0.2 `docs/design-c/prototypes/ADJUSTMENTS.md` 登记条先行（登记项清单，正文随实现收口）：①章数目标编辑态保留可编辑＋布局口径；②卷域动作清单暂缺另行立项（原型 `aiVolHTML` 动作段领先于实现，勿照补）；③装配全空返回空串（非原型占位符）；④结构模板字面沿产品单源「起承転結」；⑤章工作台「信息差对齐」块随字段换代退役；⑥book.html 卷纲段过时＋book 屏 parity `volume` case 处置；⑦卷域投影截至本卷末（原型截断语义）＋伏笔归类/关系图例为原型外新增标注；⑧本机库首启留档重置＋备份 N-1 读窗豁免（无用户口径）；⑨待写口径取 frontier（首个未归档章，含草稿），原型 `pendingInfo`（首个拟定章＋末端占位）为有意偏差；⑩ N-1 恢复演练豁免（新格式自身 roundtrip 仍须全绿）。验证：条目落盘可 grep
- [x] 0.3 **c-workbench-outline-fixes ② 摘除**（须在该 change 归档前完成，故前置于此）：摘其 `specs/workbench/spec.md` 的「章数目标布局」requirement（含 2 scenario）、`tasks.md` 对应条、登记条；代码面（旧 VolumePanel/.field.chtarget）随本 change 自然消失。验证：该 change 四件套复核一致（② 不再存在，①③ 保留）

## 1. 后端：模型换代与迁移验证（沿既有留档 doctrine，零新增迁移机制）

- [x] 1.1 `models/volume.py` 换代：volumes 加 `goal/ending`（VARCHAR 300）、`plants/reveals`（TEXT）；新子表 `VolumeCastMember`/`VolumePlotNode`（沿 `_VolumeChildMixin`）；删六旧列与四旧子表模型；`models/__init__.py` re-export 同批清理；`volumes/__init__.py` 过时 docstring（"双写 YAML"）顺手修。验证：import 冒烟＋ruff 全绿
- [x] 1.2 `main.py`：**精确删除**六条旧列 ADD（两块：213-219；234-268），保留 220-233（template_name/core_conflict）与 269-275（chapter_target）三条补列；**不写 DROP 迁移**（换代走既有留档路径）。死列残留的真实后果＝未来加法迁移被 `classify_drift` 误判 breaking（评审核正，非二次留档）。验证：✅ upgrade_drill boot-new 三件套留档＋空库启动断言过；PRAGMA/sqlite_master 断言脚本通过（六旧列不在/四旧子表不在/新列新子表齐）；二次启动 current（指纹戳短路）。注：drill 的 export-v2 阶段失败为存量问题（main 基线同败，UNIQUE users.email），与本 change 无关
- [x] 1.3 迁移口径验证（既有机制零改动）：留档文件 `.legacy-*` 在盘、既有只读检测端点可见；本机 docker 栈重建后首启即完成重置（作为前端 e2e 前置步骤写进 runbook 注记）。验证：演练/手工启动实测通过

## 2. 后端：接口与仓储

- [x] 2.1 `volumes/schemas.py` 换代：新字段集＋行长纪律（who 50/target 150/change 150/node text 300/逐行 ≤150/行数上限 200）；`plants/reveals` 契约＝`list[str]`＋归一 validator（`\r\n→\n`、逐行 strip、丢空行）；`node.stage` 用枚举 422；显式 `extra="ignore"`；`chapter_target` 补清空通道（删除字段语义）。验证：422 用例（超长/非法 stage/行数超限）＋往返用例
- [x] 2.2 `volumes/service.py` get/put 换代：`get_volume` 章节改**主线过滤**＋逐行补 `outline_summary`（取 `Chapter.summary`）＋补 `ghost_count`；PUT 沿 clear→flush→insert 整族替换；删旧 `_DETAIL_SCALARS`/`_replace_children` 旧字段。验证：pytest（往返含行序、主线过滤、ghost_count、清空 chapter_target）
- [x] 2.3 `repositories/volume_repo.py`：删死码 `get_info_gap_by_root`（引用待删模型）；`get_summary_by_root` 改名 `get_outline_by_root` 并**载入 `Volume(+selectinload plot_nodes)` 调用 `volumes/render.volume_outline_text` 返回装配文本**（接线点，勿只改名）。验证：grep 全仓无残留＋装配单测经此路径断言含节点行

## 3. 后端：装配单源与消费点

- [x] 3.1 新增 `volumes/render.py::volume_outline_text`：行标签与格式逐字对齐 `volOutlineText`（1609-1620：本卷主旨/核心矛盾/整体目标/预期结局/关键节点单行 ｜ 编号/本卷待埋伏笔/本卷待揭信息），空段整行略过，**全空返回空串**；复用 schemas 归一函数。验证：单测断言行标签、单行 ｜ 格式、空段、全空空串
- [x] 3.2 8 处消费点同批切换并改名 `ctx.volume_summary→ctx.volume_outline`：`write/chapter_writer.py`（声明:133/gate:196/文案:203-204/文案:365-366）、`write/prompt_sources.py:76`、`write/ai_check.py:103`、`chapters/ai_draft.py:348-349,397-398`；`tests/conftest.py:144/167` 形参同步改名；多行文本下「本卷概要：」前缀文案定一版（小节标题或保留前缀，随批写死）。验证：`ctx.volume_summary` 与 `get_summary_by_root` 全仓 grep 清零（不含历史文档）
- [x] 3.3 pytest 收口：prompt-sources 投影「卷纲含节点行/不含言行」＋「全空 chars=0」断言；`tests/test_volume_chapter_crud.py` 结构化往返用例改写为新字段集。验证：✅ 全量 pytest 1214 passed（含新增 test_volume_render 2 例、改写 crud/layer3、conftest 改名）；uvx ruff 触碰文件全绿

## 4. 后端：备份链（format v4，无兼容分支）

- [x] 4.1 `backup/format.py`：`FORMAT_VERSION` 3→4（卷纲删键升版）；版本门槛形状照旧（≤4 过、>4 拒）；**docstring 里「导入端保留 N-1 读窗」措辞同批更正**（读窗按当次 change 裁定、本版豁免）。验证：format 单测
- [x] 4.2 `backup/importer.py` 卷段换代：删旧模型 import（:519-525 函数体内 import）；按新键建 Volume＋两新子表；**不写旧键映射/容错分支**（N-1 豁免已登记）。验证：新格式包导入用例绿
- [x] 4.3 导出两链回归：`backup/export.py:126-130`、`novels/router.py:659-670` 带新字段正确导出；`tests/test_backup_roundtrip.py` 层 3 改写为新字段断言；连带 21 个经 importer fixture 的用例按新格式更新（不新增兼容用例）。验证：✅ backup 全家＋rewrite/drill 全绿（test_backup_roundtrip 15 passed，Layer3 断言 v4 字段逐字往返）

## 5. 前端：卷视图四页签与卷纲两态

- [x] 5.1 `novel/volume/{types,form}.ts` 换代：新字段集＋`VolumeChapterMeta` 补 `outline_summary`、`VolumeDetail` 补 `ghost_count`；plants/reveals 以 `string[]` 直接持有。验证：✅ tsc --noEmit 绿（worktree 全量）
- [x] 5.2 `VolumeWorkspace.tsx` 新建取代 VolumePanel：头部（「卷 · 分卷计划」引导＋`nodeLabel()` 全标签＋主线 N 章/已归档 N 章）＋`.ch-tabs/.chtab` 页签族＋内容 switch；tab 自持（选中卷变更回落「卷纲」）；经 onRailData 式回调上抛右栏数据（与章模式同构，tab 不上提；**与章模式 `railData` 按 mode 隔离或卸载即清空**）；`NovelWorkspace.tsx` 挂载与右栏数据通路接线。验证：vitest 页签切换＋切卷回落＋右栏数据上抛/清空用例
- [x] 5.3 卷纲查看态：六分组＋空态文案逐字对齐原型＋「编辑卷纲」入口。验证：vitest 空态与回显用例
- [x] 5.4 卷纲编辑态：卷名｜结构模板｜章数目标（标签单行、提示下移小字、可清空）；主旨/核心矛盾必填；人物行/节点行增删（stage 六档）；埋下伏笔/揭露信息多行一行一条；保存/取消。验证：vitest 两态往返/必填拦截/清空章数目标/取消丢弃用例
- [x] 5.5 本卷进度线：已归档/草稿/拟定**互斥计数**（archived／has_prose∧¬archived／¬has_prose∧¬archived）＋待写＝frontier 定位段（首个未归档章，**含草稿**；`GET /frontier` 补取，禁用 `hereTarget` 代替）。验证：vitest「2 归档+1 草稿(首个未归档)+1 拟定 → 待写 第 3 章」与「不在本卷」用例
- [x] 5.6 本卷章节页签：台账（章号·题名＋`outline_summary`＋状态）＋跳转 `focusNode`＋ghost 汇总（`ghost_count`）＋「在本卷新增一章」（门控＝frontier 章在本卷，与 5.5 同一定义单源；复用 `wb.createChapter`＋树行内输入同款交互，本组件内新造按钮，不改 `OutlineTree.tsx` 既有区域）。验证：vitest 门控/跳转/ghost 提示用例
- [x] 5.7 卷域投影：`RelationsGraphPane`/`HooksPane` 加 `asOfOrder`/`scope` props（截至本卷末截断；无增删；伏笔标注本卷埋/收/跨卷悬置）。验证：vitest 截断与归组用例
- [x] 5.8 信息差块退役：删 `ChapterWorkspace.tsx:151-197` fetch 与 `OgPane.tsx` `infoGap` prop/渲染。验证：tsc 绿＋grep `infoGap` 无残留
- [x] 5.9 脏守卫接线：`volumeDirtyRef` 接入 `NovelWorkspace.go()` 统一离开检查（现仅 `settingsDirtyRef`）。验证：vitest/手测「编辑中切节点被拦截」

## 6. 前端：右栏与样式

- [x] 6.1 `Rail.tsx` 卷分支重写：删**卷分支**的三张「规划中」卡＋同分支 `LockedCard`（「大纲阶段的 AI 能力正在规划中」）与「规划中的能力」小节头（`PlannedFeat` 组件保留给章模式免费档）；改 `.rail-assist` 语境面板（四页签引导语＋统计卡，与中栏同源 selector，缺章纲口径＝`outline_status !== "confirmed"`，取数失败降级「—」）；不渲染动作清单；未选中卷维持通用空态。验证：vitest 四页签统计＋降级＋未选中兜底用例
- [x] 6.2 `design/book.css` 卷视图业务段（头部/进度线/台账/空态；类名映射 app 现役族 `.cfg/.field/.hp-ledger` 等，禁抄 storyline 类名；零 base.css 改动）。验证：✅ design:lint 违规集与 main 基线逐字一致（preview.html/AcctMenu 存量，本 change 零新增）
- [x] 6.3 文案自查：按钮词全动词、无内部术语、语气词限 info/ok/warn/err、空态/提示逐字对齐原型（含「旧稿支线 N 章 · 已脱离主线，不计入本书设定」）。验证：`npm run design:check` 全绿＋逐条对照原型截图

## 7. e2e 与 parity

- [ ] 7.1 存量改写：`e2e/workbench-features.spec.ts`（:231-285 信息差块、:287-345 卷纲旧面板断言、**:550-552 `remount()` 的「卷摘要」文案断言**）；`e2e/free-writing-flow.spec.ts:198-202`；`e2e/design-parity-book.spec.ts` volume case 处置（默认下线 case＋登记「卷纲屏事实源转 storyline.html」；`docs/design-c/baselines/book.volume.*.png` 同步清理；gate 若改判「重录」则 book.html 换稿重拍）。验证：三文件跑绿
- [ ] 7.2 卷视图新 e2e 最小覆盖：选卷→四页签切换→编辑卷纲保存→进度线与右栏语境断言。验证：新 spec 绿
- [ ] 7.3 全量门禁：**重建 C端 docker 容器后容器内全量 pytest**（既定规矩）＋`tsc --noEmit && npm run build`＋全量 e2e＋vitest 全量（S端零涉及，不适用双端 cross）。验证：各套全绿留输出

## 8. 收尾核账

- [ ] 8.1 ADJUSTMENTS 登记条定稿（0.2 清单逐条落实）＋book.html 卷纲段标过时＋`docs/ux/design-language.html:247` SubTable 示例随四子表退役留待更新登记。验证：条目可 grep
- [ ] 8.2 c-workbench-outline-fixes 收窄复核：0.3 已执行摘除，此处仅复核其四件套一致（② 不存、①③ 完整）并跟进其归档状态。验证：该 change `openspec validate` 绿
- [ ] 8.3 specs 核账：**6 张 delta** 与实现一致（volume-outline／workbench／prompt-crafting／backup-restore／volume-chapter-service／workbench-3-label）；book.html 卷纲段过时标 + design-language SubTable 示例待更新登记。验证：`openspec validate c-volume-view-storyline --strict` 全绿
