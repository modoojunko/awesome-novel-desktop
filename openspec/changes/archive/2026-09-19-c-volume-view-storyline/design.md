## Context

- 设计事实源：`docs/design-c/drafts/storyline.html`（#27 口径：drafts 目录为唯一事实源、不入像素 parity 基线；**当前 untracked，本 change 补入库**）。卷视图相关段**以符号名检索为准**（行号随盘刷新：`volTabs`≈3063、`volDraft`≈3078、`volReadHTML`≈3090、`volEditHTML`≈3122、`volOutlineHTML`≈3173、`volChaptersHTML`≈3195、`volumeEditorHTML`≈3208、`aiVolHTML`≈3408；卷域投影 `relsHTML(0, order, false)`/`hooksHTML(0, order)` 按卷末章 order 截断）、纯文本装配 `volOutlineText`（1609-1620：行标签「本卷主旨/核心矛盾/整体目标/预期结局/关键节点（单行 ｜ 编号）/本卷待埋伏笔/本卷待揭信息」，全空返回占位符）。
- 现状：`VolumePanel.tsx` 是 book.html PR4 旧面板（常编辑态、9 标量＋4 子表）；后端 `models/volume.py` 同代；右栏卷模式＝三张「规划中」卡；卷素材消费方仅吃 `volume_summary`（4 文件 8 处，`ctx.volume_summary`）。
- **约束与事实（评审核实，与初稿判断相反者已修正）**：
  - 启动期 `legacy_archive.archive_if_legacy` 在一切 DDL 之前执行（main.py:66-72），`classify_drift` 对「删表/删列」判 `breaking` → 三件套整库留档（db 改名 `.legacy-<stamp>`）＋空库启动（既有 doctrine，由 `tests/conftest.py:126-137`、`scripts/upgrade_drill.py:309-326` 固化）。**无用户口径下这就是本 change 的迁移路径**：不做旧数据映射、不建白名单档、不写 DROP 迁移；本机库首启留档重置为已登记影响。
  - 备份/恢复链：`backup/importer.py:519-525` 函数体内 import 待删模型（删模型即 ImportError，恢复整体失败）、`:594-625` 用旧 kwargs 构造 Volume——**必须同批换代**（这是让代码能跑，不是兼容层）；`backup/format.py:1-10` 契约「删键/改布局＝升版」→ 本版升 `format_version: 4`，但**不做 N-1 读窗**（无用户，旧包不承诺可导入）；`backup/export.py:126-130` 与 `novels/router.py:659-670` 两条导出链自动带新字段；约 21 个 roundtrip 用例经 importer fixture 连带（按新格式更新，不写兼容分支）。
  - `main.py` 的六条旧列 ADD COLUMN **必须精确删除**（两块：213-219 direction_method；234-268 emotional_arc/arc_mode/primary_drive/info_gap_start/info_gap_end；**保留** 220-233 的 template_name/core_conflict 与 269-275 的 chapter_target 三条保留列补列——按区间粗删会吃掉 `except/pass` 语法）。残留风险经评审核正：指纹戳相等时 `classify_drift` 根本不跑（legacy_archive 短路 `current`），故不会「二次留档」；真实后果是死列在新库长期存在，**下一次 additive 变更**（戳失配才跑分类）会被旧列判成 breaking → 整库留档重置。
  - `get_volume` 的 `chapters` 含旧稿支线章（ghost：status=archived＋has_prose，`chapters/rewrite.py:55-72` 建行），直接用会把 ghost 计进「已归档」并混入台账（`list_volumes` 已主线过滤，`volumes/service.py:28-31`）。
  - book 屏 parity **有活跃 volume 用例与在库基线**（`e2e/design-parity-book.spec.ts:252-259`、`docs/design-c/baselines/book.volume.{app,proto,diff}.png`）；ADJUSTMENTS #27 原文只指「四子表滚出截图」，不等于整屏不在基线（初稿 design 断言有误，已改）。
  - 章工作台「信息差对齐」块（`ChapterWorkspace.tsx:151-197`＋`OgPane.tsx`）消费退役字段，须显式退役。
  - 建章入口是树行内输入（`OutlineTree.tsx:142-160`）而非弹窗；`Rail` 卷模式当前无 data 通路；章页签现役类名 `.ch-tabs/.chtab`（book.css:259-266）。

## Goals / Non-Goals

**Goals:**
- 卷视图（中栏＋右栏卷态）对齐 storyline.html；卷纲素材装配单源化；数据模型干净换代（走既有留档重建路径，零兼容层）＋备份契约同步升版。

**Non-Goals:**
- 卷域 AI 动作实装（需新端点，另行 propose）；章纲页签本身；顶栏计数修复（在途 fixes ①）；结构模板枚举扩档/改字面；主线状态机。

## Decisions

1. **数据模型：两新标量＋两 TEXT 行单＋两新子表；旧列旧表迁移即删。**
   - `volumes` 新列：`goal VARCHAR(300)`、`ending VARCHAR(300)`、`plants TEXT`、`reveals TEXT`；新子表 `volume_cast_members(volume_id, sort_order, who 50, target 150, change 150)`、`volume_plot_nodes(volume_id, sort_order, stage 50, text 300)`（沿 `_VolumeChildMixin`）。
   - **wire 契约钉死**：`plants/reveals` 在 API 层是 `list[str]`（与原型数据模型、前端 list 操作一致），storage 为单 TEXT 列 `\n` join；schemas 侧加 `field_validator`（`\r\n→\n` 归一、逐行 strip、丢空行、逐行 ≤150、行数上限 200），**装配函数复用同一归一函数**，禁止两套语义。GET detail 回写（`OutlineTree.tsx:475-479`、`useWorkbench.ts:376-379`）在此契约下天然往返；schemas 显式声明 `extra="ignore"` 固化行为。
   - 删除六旧列＋四旧子表；`repositories/volume_repo.py:63-89` 死码 `get_info_gap_by_root` 同批删；`models/__init__.py` re-export 同批清；`main.py` 六条旧列 ADD 按块精删（见 Context）。旧数据不映射（无用户；两代字段无一一对应）。
2. **迁移：沿既有 doctrine——留档重建，零新增机制（无用户口径）。**
   - 破坏性 schema 差异 → 三件套整库留档 + 空库新 schema（create_all 建新表），**不写 DROP 迁移、不建白名单档、不做旧字段映射**。旧库文件保留在 `.legacy-*`（既有只读检测端点可查）。
   - 唯一必做的代码动作：精确删 `main.py` 六条旧列 ADD（见 Context 的块区间；保留三条保留列补列）；模型删除后旧子表名不再进 metadata，create_all 不会重建，`models/__init__.py` 的 re-export 同批清理。
   - 已接受影响（登记）：本机现存书库首启被留档重置（无用户，数据可弃；留档文件在盘上）。备选（已否，按用户 2026-09-19 口径）：白名单原地迁移——为无用户场景引入并维护一套新机制，收益为零。
3. **备份包契约：FORMAT_VERSION 3→4，不做 N-1 读窗（无用户，旧包不承诺可导入）。**
   - `importer.py` 卷段换代：删旧模型 import，按新键建 Volume＋两新子表；**不写旧键映射、不写容错分支**。版控沿用「≤当前版本可过、>当前版本拒绝」的既有形状（数值升 4）。
   - 既有 roundtrip 用例按新格式更新（不新增兼容用例）；`backup-restore` spec 中「破坏性版本 N-1 恢复演练」对本版按无用户口径**登记豁免**（不出旧版包就没有可恢复对象），新格式自身往返仍须全绿。
4. **卷纲文本装配单源：`volumes/render.py::volume_outline_text(detail) -> str`**（`settings/render.py` 同型先例；新增依赖边为 `write/* → volumes.render` 单向——与 settings.render 先例同向，用 codegraph 复核无环）。接线点写死：`volume_repo.get_outline_by_root` 载入 `Volume`（selectinload `plot_nodes`）后调用装配函数返回文本（不让消费侧各自拼装）。
   - 行标签与分节**逐字对齐 `volOutlineText`（1609-1620）**：`- 本卷主旨：…`／`- 核心矛盾：…`／`- 整体目标：…`／`- 预期结局：…`／`- 关键节点：1. 〈阶段〉：〈内容〉 ｜ 2. …`（单行 ｜ 连接）／`- 本卷待埋伏笔：a ｜ b`／`- 本卷待揭信息：x ｜ y`；空段整行略过。
   - **一处有意偏差（登记 ADJUSTMENTS）**：全空返回空串而非原型占位符「（卷纲未填）」——维持 `prompt-sources` 既有「未填=chars 0/empty=true」断言；占位语义由来源投影的未填标注承担。
   - 8 处消费点同批切换并将 `ctx.volume_summary` 更名 `ctx.volume_outline`（`chapter_writer.py` 声明/gate/两文案、`prompt_sources.py`、`ai_check.py`、`ai_draft.py` 两处）；`get_summary_by_root`→`get_outline_by_root`。
5. **前端结构：`VolumeWorkspace` 自持 tab＋detail，经 onRailData 式回调上抛右栏数据（与章模式完全同构）；tab state 不上提。**
   - `VolumeWorkspace.tsx` 取代 VolumePanel：头部（`nodeLabel()` 全标签＋N 章/已归档 N 章）＋`.ch-tabs/.chtab` 页签族＋内容 switch；选中卷变更回落「卷纲」；卷未选中/空书时右栏维持通用空态说明。
   - 卷纲两态：查看态六分组＋进度线；编辑态（卷名｜结构模板｜章数目标＋六组编辑控件）；保存/取消；脏守卫沿 `volumeDirtyRef` 并**接进 `go()`（现仅查 settingsDirtyRef）**，否则「离开卷视图拦截」不可达。
   - 卷纲数据：`get_volume` 章节**主线过滤＋补 `outline_summary`（台账「章纲一句话」的数据源，取 `Chapter.summary`）＋`ghost_count`（旧稿支线汇总）**；`chapter_count` denorm 列不用于头部件数（用返回的 chapters 长度口径）。
   - 进度线语义：已归档／草稿／拟定三段为**互斥计数**（archived／has_prose∧¬archived／¬has_prose∧¬archived），待写＝定位段（主线 frontier 章在本卷时「第 N 章」，否则「不在本卷」）。frontier 口径＝首个未归档章（**含草稿**，与排队门禁/bar-here 同源；前端取不到时经 `GET /frontier` 补取，禁用 `hereTarget` 续写端点代替）。**与原型有意偏差（登记）**：原型 `pendingInfo` 的待写＝首个拟定章（无正文）＋末端占位；产品改取 frontier 以与写章门禁（非 frontier 章 409）一致。新增一章门控＝frontier 章在本卷（同一定义单源）。
   - 本卷章节页签：台账行＝章号·题名＋`outline_summary`＋成稿状态；跳转走 `focusNode`；ghost 汇总＝`ghost_count`；「在本卷新增一章」复用 `wb.createChapter`＋**树行内输入同款交互**（app 无建章弹窗，原「复用弹窗」表述已修正；该入口为卷页签内新造按钮，不改 `OutlineTree.tsx` 既有区域，避让在途 fixes ①③ 同文件冲突）。
   - 卷域投影（对齐原型截断语义）：关系页签＝**截至本卷末章 order** 的关系图（只读，无按章高亮、无增删）；伏笔页签＝截至本卷末的台账投影（标注本卷埋下/本卷回收/跨卷悬置）；两组件加 `scope`/`asOfOrder` props，取数沿用书级端点、截断前端派生。
   - Rail 卷分支：删三张「规划中」卡**及同分支的 `LockedCard`（「大纲阶段的 AI 能力正在规划中」）与「规划中的能力」小节头**（仅删卷分支引用，`PlannedFeat` 组件保留——章模式免费档仍用）；改 `.rail-assist` 语境面板（引导语＋`.rail-stats` 统计卡；统计与中栏同源 selector，缺章纲口径＝`outline_status !== "confirmed"`）；不渲染动作清单。卷语境上抛数据与章模式 `railData` **按 mode 隔离或卸载即清空**（防未选中卷时残留统计卡违反 workbench delta 的未选中口径）。
6. **文案与状态语言**：按钮词动词；空态/提示文案逐字对齐原型（含「旧稿支线 N 章 · 已脱离主线，不计入本书设定」）；禁用态＝disabled＋title；类名映射到 app 现役族（`.cfg`/`.field`/`.hp-ledger` 等，禁把 storyline 的 `.cfgset/.ledger/.rowx/.flist` 整段抄进业务层）；零 base.css 改动。

## Risks / Trade-offs

- [本机库（含现存测试书）首启留档重置] → 已接受（无用户拍板）；留档文件 `.legacy-*` 在盘可查；重建书成本低（测试书无正文）。
- [旧列 ADD 语句漏删 → 二次留档] → tasks 1.2 显式删除并验证「首启留档一次后，二次启动判定 current」。
- [备份链漏改 → 恢复失败/旧格式残留] → importer 换代用例＋新格式 roundtrip 八层断言；**不新增任何兼容分支**。
- [信息差块退役被当成功能回退] → ADJUSTMENTS 显式登记「PR6 增强项随字段换代退役」＋e2e 用例同批改写。
- [book 屏 parity volume case 僵持] → 二选一（下线 case＋登记「卷纲屏事实源转 storyline.html」／book.html 卷纲段换稿重录基线），本设计取**下线＋登记**（与 #27「book.html 不随 storyline 批改动」一致）；gate 可改判。
- [改后端未重建容器→e2e 假失败] → 沿 runbook 既有条目：后端改动后 docker 栈重建再跑。

## Migration Plan

1. 后端换代：models/schemas/service/render/消费点；删 main.py 旧列 ADD 语句；pytest 全绿（roundtrip、volumes crud 按新格式改写）。
2. 迁移验证（既有机制，零新代码）：旧形态 fixture 库启动 → 断言三件套留档＋空库新 schema；二次启动判定 current；**此验证绿后前端才开跑**（本机栈首启会留档重置）。
3. 备份链：FORMAT_VERSION 4＋importer 卷段换代；导出两链回归；roundtrip 八层断言。
4. 前端：VolumeWorkspace 四页签＋两态＋右栏＋信息差块退役；vitest 全绿；docker 栈重建后 e2e（含三件存量改写＋卷视图新覆盖）。
5. 原型登记：storyline.html 入库；ADJUSTMENTS 新条（偏差：章数目标可编辑＋布局、卷域动作暂缺、装配全空返回空串、枚举字面沿产品、信息差块退役、parity volume case 处置、aiVolHTML 动作段领先勿照补、本版留档重置与 N-1 豁免）；book.html 卷纲段标过时。
6. 回滚：代码 revert 后与已换代库再次「breaking」→ 留档重置（无用户，可接受）；不做「revert 即回退」承诺。如需保数据：回装新代码后导入 v4 资产包（旧代码会拒绝 v4 包），或直接取用 `*.legacy-*` 留档文件。

## Open Questions

- book 屏 parity `volume` case：下线＋登记（本设计取此）vs book.html 卷纲段换稿重录——gate 拍板。
- 结构模板字面「起承転結」（产品）vs 原型「起承转結」：建议沿产品单源不改字面，登记偏差。
- `workbench-3-label` spec「卷节点点击弹出右侧抽屉（卷纲编辑）」（spec:28-38）与整页中栏卷视图直接冲突且早已漂移：本 change 已补该能力 MODIFIED delta（改写为中栏卷视图口径），归档时核对。`volume-chapter-index` 经复查只列基础列、无过期内容，原指认作废。
