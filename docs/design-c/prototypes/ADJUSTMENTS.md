# 原型基线的产品化调整登记（PR 1-3，2026-08-22）

原则：原型即 parity 基线。产品需要而原型未建模/含演示脚手架的部分，
**先改原型再同步实现**（设计先行，不私下偏移）。每条调整都在此登记。

只动 `list.html`（本屏基线）：

1. **appbar 移除「示例书 · 书工作台」导航链接**
   原型跨页演示导航，产品无此入口（用户的书从书架卡片进入）。窄屏
   `a[href="book.html"]` 隐藏规则随之失效可忽略（选择器不再命中）。

2. **page-head 增加「导入」btn-secondary（新建作品左侧）**
   产品功能：导入已有稿子（.md/.txt/.docx），spec-review-report §五确认
   原型未建模导入流程。按同一设计语言扩展（btn-secondary + upload 图标，
   图标路径 `M12 15V4M7 8l5-5 5 5M5 20h14`，与应用 src/components/icons.tsx 一致）。

3. **footer 文案 `© 2026 爱小说 · 界面重设计 v2 · 原型文件` → `© 2026 爱小说`**
   原型元信息不是产品文案。

4. **localStorage 空数组语义**
   `ainovel.books=[]` 显式表示空态（parity 用）；原来空数组会回落 SEED，
   导致设计好的 .empty 空态不可达。仅改守卫条件，SEED 数据不变。

未动原型、只在应用侧扩展的（不进 parity 截图，见 src/design/list.css 注释）：
- 卡片悬浮 ⋯ 菜单（重命名/删除）——默认 opacity 0，悬浮/聚焦才出现
- notice 提示条（试用/过期/Key 未配置）——parity 态全部隐藏
- 加载骨架、加载失败空态
- 新建弹窗类型「暂不选择」空选项（选填语义）

---

## PR 2（model-config.html）

只动 `model-config.html`（本屏基线）：

1. **appbar 移除「示例书 · 书工作台」导航链接 + 补「设置」按钮**
   同 list.html 调整 #1 的口径；设置按钮对齐应用全局 Navbar（list.html 已有）。

2. **footer 文案 `© 2026 爱小说 · 界面重设计 v2 · 原型文件` → `© 2026 爱小说`**
   同 list.html 调整 #3。

3. **localStorage 空数组语义**
   `ainovel.apiconfigs=[]` 显式空态（parity 用），原来空数组回落 SEED。
   仅改守卫条件，SEED 数据不变。同 list.html 调整 #4。

未动原型、只在应用侧扩展的（不进 parity 截图）：
- 迁移提示条（MigrationBanner）——仅老用户未迁移（profile.migration_completed=false）出现
- 用量面板最近更新文案——由真实 queried_at 算相对时间（parity 打桩 now →「刚刚」）
- 卡片测试失败 res 行——真实后端错误文案（原型模拟数据无此态）
- 「归档 AI 摘要」开关——从本屏迁至全局设置弹窗（PrefsModal 行），原型未建模该偏好

---

## PR 3（book.html）

只动 `book.html`（本屏基线）：

1. **章纲表单字段集替换为产品现行全字段（数据模型不动）**
   原型示例字段（卷纲定位/读者缺口/角色状态/钩子盘点/key_points 三锚点/情感基调/情绪钩子/兑现埋设/段落拆分/目标字数/本章提示词）→ 产品 OutlineEditor 全字段：
   章纲概要/关键事件/出场角色/地点/时间/叙事视角/视角指导/核心任务/读者当前状态/预期策略/预期细节说明/必须在本章回收/必须维持悬念/可部分推进/必须完成的变化/禁止事项/主情绪（9 选 + 自定义）/段落规划（行编辑：概要 + 目标字数，可增删/上移）。
   必填口径 REQUIRED 对齐后端 gate_chapter_ready 六项：核心任务/读者当前状态/预期策略/必须完成的变化/主情绪/段落规划（缺口 chip 标签 = 后端中文标签）。
   随之：章级「目标字数」移出表单（右栏进度卡就地编辑持有）；「本章提示词」组移除（提示词页签持有）；列表型字段（关键事件/出场角色/兑现三清单/禁止事项）以 textarea 一行一条呈现（产品 ListEditor 语义等价）。

2. **设定计数 6 → 7 项**
   ITEMS 增加「AI痕迹控制」（antiAI，可后补，未填）——产品设定树第 5 项；DESCS/BODIES/进度条/modnav 计数同步 /7。

3. **新章默认目标字数 4000 → 2000**
   对齐产品 DEFAULT_TARGET_WORDS = 2000（右栏进度卡百分比口径一致）。

4. **卷折叠初始态 `expanded: { v2: false }` → `expanded: {}`**
   演示脚手架的硬编码折叠不参与持久化；统一「默认全部展开，折叠是用户操作」，
   与应用树默认口径一致（parity 态两侧同为全展开）。

5. **树行渲染归档章 `.arch-tag`（大纲树 + 预览树）**
   CSS 已定义 `.ch .arch-tag`（含选中态配色）但演示 JS 未输出——补齐设计意图；
   产品归档章需在树中可辨识（c2 为归档示例）。

6. **三屏 `.btn` 统一 `letter-spacing: 0.01em`**
   book.html 的 `.btn` 已有该字距，list.html / model-config.html 缺失——设计系统
   同源规则不应分叉。以 book.html（最新稿）为准回填另两屏，应用 base.css 同步。

未动原型、只在应用侧扩展的（不进 parity 截图，或 parity 态取免费版）：
- 树行 hover 操作含「改名」铅笔（产品重命名功能，原型未建模）
- PRO 态右栏续写/润色/扩写为可用工具行（原型标「规划中」；免费态与原型一致）
- 版本历史/归档/升级 PRO：PR 3 沿用现有交互过渡，PR 5 弹窗化
- 提示词页签内部沿用现行 PromptManagementPage（段落提示词管理），外壳/badge 按原型
- 章纲面板保留 3s 自动保存（原型只有手动保存；后台自动保存不改确认状态，仅显式「保存草稿/确认章纲」触发自动确认）
- 归档章只读横幅带「恢复编辑」按钮（正文页顶 banner + confirm；原型 archCard 仅提示「本章已归档 · 只读查看」无操作入口——右栏 archCard 按原型，banner 为产品功能）

PR 3 收口时顺手修的两处应用侧 bug（无原型分歧，纯回归修复，不进 parity）：
- 预览视图 `/volumes` 无限拉取环——ArchivePage 挂载即调 onRefresh 且以其为 effect
  依赖，壳层传的内联箭头每次渲染换新引用，与 refresh→setVolumes→重渲染结成死循环
  （预览态约 9ms 一次请求）。壳层 memo onRefresh 引用后根治。
- 过渡期卷工作台页 h1 展示裸 title，未走 nodeTitle 单一事实源口径（#164：
  `第X卷 · 名称`，与大纲树标签一致）。改用 nodeLabel 派生。

---

## PR 5（book.html）—— 弹窗群 + spec-report 清账

原型侧零改动：modalDelete/modalUnlock/modalArchive/modalHistory/modalUpgrade/
modalAi/modalPrefs 标记与 CSS 在 PR 3/PR 4 已随屏落地（spec-report §6 两项已入原型）。
本 PR 全部为应用侧产品化扩展，逐条登记：

1. **升级 PRO 确认动作 → 跳 S 端门户**
   原型 `upgradeConfirm` 置 `S.pro=true`（演示语义）；产品无站内购买，
   PRO 来自 S 端会员（member-block 弹窗同口径）：确认升级取 `/auth/config`
   的 `portal_url` 新开页（无地址则 toast 提示）。弹窗视觉/文案按原型。

2. **版本历史行内「行/词对比」扩展（原型未建模 diff）**
   modalHistory ver-row 列表按原型；产品保留 VersionDiff（行/词对比）能力：
   非当前版本行尾追加 ghost「对比」按钮，点击在弹窗内展开对照视图、
   「返回列表」收回。恢复按原型直点直恢复（toast「已恢复至该版本」）。

3. **AI 弹窗提示词编辑真实生效**
   原型 aiPrompt 可编辑但演示不回传；产品新增 `GET …/write/prompt`
   （返回组装提示词 + 是否有章纲，供预填/aiHint）与 `POST …/write` 可选
   `prompt` 覆盖参数——编辑后的提示词真实用于生成（并照常存档供回看）。

4. **版本列表带字数（后端扩展）**
   原型 ver-row「版本 N · N 字」需要每版字数；产品 `GET /versions` 列表
   补 `words` 字段（快照 prose 去空白口径，与全书字数统计同源）。

5. **本书偏好弹窗（设置入口切换）**
   modalPrefs 三偏好 per-book 落库（localStorage `pref.book.{pid}.*`，
   全局默认兜底）：字号/行距作用于本书各章正文与预览；归档 AI 摘要接
   现有归档逻辑。appbar「设置」在 /novel/:id 内从全局偏好弹窗切到本书
   偏好弹窗（账号行 tier 来自 /auth/verify，免费态文案对齐原型
   「免费版 · 单机使用」，全局/本书两弹窗同口径；免费态「升级 PRO」链
   升级弹窗）；
   书架/模型配置屏仍用全局偏好弹窗。

6. **解锁链覆盖右栏全部 AI 工具（真 bug #1 修复口径）**
   原型只演示「AI 生成正文」的解除只读链；产品右栏续写/润色/扩写在
   归档章上同样先弹解除只读确认，解锁后继续原动作（选区在弹确认前捕获）。
   全部 AI 动作触发时自动切到正文页签并聚焦（真 bug #2）。

7. **润色/扩写对照弹窗重皮（ContrastPreviewModal）**
   原型未建模；从 daisyUI dialog 重绘为设计弹窗（wide + 原文/对照双栏 +
   拒绝/换一个/接受），保留 Enter 接受、失败重试。

8. **提示词管理页轻重皮 + 措辞（spec #9）**
   PromptManagementPage 内部从 daisyUI 色换设计 token（功能不动）；
   「生成提示词」→「生成段落提示词」。

9. **spec-report 其余项（复核后落地口径）**
   - #1 导入 ≤10MB：上传/拖放真实校验大小（此前只查扩展名）。
   - #2 导入预览统计：`共 N 章节` → `共 N 章节 · N 字`。
   - #8 保存失败态：「保存失败」+独立重试钮 → 聚合「保存失败 · 重试」单击重试。
   - 轻微 #1 序号：导入预览未命名兜底 `卷 1/第 1 章` → 中文数字（工作台
     侧 PR 3 已统一 nodeLabel 中文序号）。
   - 轻微 #3 措辞：设定面板「变更历史」→「变更时间线」、「用量统计」→「本书用量面板」。
   - 复核免改：#7 角色发声 label（查看态旧文案已随 PR 4 卷纲改版移除，
     现仅编辑态「下一卷想做的事」placeholder，即目标态）；轻微 #2 空卷
     hover 建章（PR 3 树 .acts hover 对空卷同样生效，已是目标态）。

---

## PR 4（book.html）—— 卷纲面板 / 设定视图 / 右栏 / 预览

只动 `book.html`（本屏基线）：

1. **卷纲面板字段集替换为产品现行全字段（数据模型不动）**
   原型演示字段（卷状态徽标/结构模板+阶段分配映射文本/核心冲突/情绪曲线/信息差文本/冲突阶梯文本/场景盘点文本）→ 产品 VolumeDetail 全字段：
   卷摘要*/结构模板（4 选：三幕式/起承転結/悬疑递进/人物弧线，「起承転結」为 PRD 种子值保留）/章数目标（1-9999，留空为不设）/核心冲突*（≤150）/弧线模式（5 选）/主导驱动力（5 选）/方向来源（选项文案中文、value 用产品编码 template/character_voice/manual）/情绪弧线（≤150）/信息差（开卷+收卷两栏，≤300）+ 四子表行内卡（阶段分配/冲突阶梯/章节规划/角色发声：行编辑实时写回、增删局部重渲；新行工厂——冲突层级号自增、章规划章号取现有 max+1；数字字段按产品口径钳制）。

2. **卷级状态概念移除（徽标恒「草稿」）**
   产品 VolumeDetail 无 status 字段（确认态只在章节）→ panel-head 徽标固定
   `<span class="badge warn">草稿</span>`；保存不再置 og.status、不再有
   「已确认/草稿」双分支 toast，统一 `《title》卷纲已保存`；done-note 不出现于卷纲。
   （树中卷行三态 dot 语义不变——按章纲/正文聚合推导，与产品一致。）

3. **设定 7 面板字段集替换为产品现行全字段（数据模型不动）+ Tabs→details.cfg 折叠组**
   原型演示占位（题材单行卡/世界 3 区/风格 4 区/伏笔空态/角色弹窗 demo）→ 产品 SETTINGS_TYPES 全字段：
   题材（当前题材卡+选择器；类型禁忌只读 chips/提示词注入段开关+分段注入 seg+注入预览/题材配置 4 组提示词 ListInputs/故事弧模板卡片可选中）、
   简介（≤500 字 textarea+右下 x/500 计数，详细说明块移除）、
   世界（地理 3/政治 4/规则 3，逐字段 AI 补全）、
   风格（叙事人设+3 组指令清单+基调=叙事角色+默认基调+3 清单，ADR-006 保存时合并）、
   AI痕迹控制（疲劳词 7 类逐类编辑/句式偏好 Tic 卡）、
   伏笔（活跃/已收束/废弃三分组，9 类钩子+优先级）、
   角色（左列角色行+14 字段三组折叠卡）。
   产品的表单 Tabs 统一折叠进 `.cfg` 折叠组（OgPane 同款 idiom）。

4. **AI 模型为第 8 个导航项（工具 tag，不计入 n/N 进度）**
   nav 渲染在 7 设定项之后追加 `data-k="aiModel"` 项（tag「工具」、badge 恒「已确认」）、
   panel 无「确认完成」脚注、注记「工具项 · 恒可用，不参与设定进度」。左栏计数仍 x/7。

5. **徽标两态化：done/empty（prog 样式保留但产品不可达）**
   产品设定无中间态 → 演示默认 done：题材/简介/风格，empty：世界/AI痕迹/伏笔/角色，
   左栏 3/7；编辑态不改徽标（保存后仍是 done）。

6. **题材选择器弹窗：6 产品分组 + 去「最近使用」+ 新建题材入口**
   GENRES 换产品 GENRE_CATEGORIES（都市系/历史系/玄幻系/悬疑系/科幻系/独立类型）；
   「最近使用」无产品数据落库 → 删组；弹窗头加「新建题材」text-btn（应用侧接 createGenre）。

7. **段落概要 textarea 化（spec #5，顺手修）**
   章纲面板 seg-row 段落概要：单行 input → `textarea rows=2`（可纵向拉伸），
   seg-row 顶部对齐；应用侧 OgPane 同步改。

8. **简介 x/500 计数（spec #3，顺手修）**
   textarea `maxlength=500`，右下 `.cnt` 实时 `${len}/500`；应用侧 SynopsisCard 同步。

9. **已确认面板保留保存路径（按钮改文案「保存修改」）**
   原型 done 态隐藏「确认完成」→ 已确认面板无任何保存入口，二次编辑无法落库
   （演示脚手架可接受，产品不可）。产品保留 panel-foot 主按钮，已确认态文案
   「保存修改」——只 save 不再 confirm；未确认态仍「确认完成」（先 save 后 confirm，
   gap3 口径）。原型侧不动（演示语义成立），仅应用侧扩展。

10. **AI 模型面板 parity 排除**
    原型 aiModel 为静态演示（当前/选项/历史/用量四块假数据）；产品渲染真实模型
    状态（configured/no_key/no_model/invalid 徽标）、可用模型选择（按配置分组）、
    变更历史（恢复入口）与真实用量统计（含饼图）——信息密度高于原型，不做像素
    比对。左栏导航项/进度条仍按原型 parity。

11. **伏笔空列表仍渲染「添加伏笔」按钮（原型 bug 修复）**
    hookRows 原实现空列表早退只渲染「暂无」→ 空项目永远无法添加第一条伏笔。
    改为空态注记 + 按钮恒渲染；应用侧同口径。

12. **预览语义：全书只读通读（旧归档阅读页退役）**
    原型预览 = 左树全部章（三态 dot/已归档 tag）+ 只读正文，任何章皆可读。
    产品旧「预览小说」仅归档章可读（ArchivePage/ArchiveReader）→ 按设计稿改为
    全书只读通读（草稿与归档章皆可读，正文按章拉取）；旧归档阅读页退役，
    「编辑跳回工作台」入口随之移除（预览为纯只读，modnav 即返回路径）。

13. **预览树选择为本地态，不回写写作视图选中**
    原型写作/预览共享同一份选中状态（点击预览树 = 切换工作台选中）。产品写作
    视图常驻挂载（保正文脏状态），隐藏态被预览切章会有静默脏丢风险 → 预览
    选中只落在预览内部（初始定档取写作视图当前章），离开即弃。
14. **章纲面板信息差只读块（PR6 功能增强，parity 不覆盖）**
    原型章纲面板无信息差元素。PR6「信息差对齐」在章纲 panel-head/desc 下新增
    只读块（.og-infogap：accent 竖条浅底，两行——本卷信息差起→止 + 本章信息差，
    卷未配置时不渲染），数据源 = 卷纲 §三 卷级字段 + §七章节规划行按章号对齐。
    属功能增强而非视觉复刻，原型不补元素；parity 章工作台 case 用 gapless 桩
    保持与原型一致（volume case 卷纲面板字段保留）。

15. **全局更新提示条新增（client-update-notify，PR 首任务原型先行）**
    list.html / book.html 在 appbar 之上新增 update-strip 全局层：.notice info
    语气（家族四条样式逐字同实现侧 list.css——原型本自不含该家族，需自含拷贝）
    + 既有 btn 词汇（secondary 主按钮「去下载」、ghost「查看更新内容」与关闭
    「知道了」沿用 MigrationBanner 先例词）。布局分两版：书架随内容栏
    min(100%,1080px) 居中（上距 20px），工作台全宽贴边（padding 12px 16px 0，
    appbar 口径）。无新增共享段类；update-strip 为业务层作用域。
    parity 口径：design-parity 书架屏 spec 需同步打桩 /api/update-check
    返回 v0.13 + 摘要「提升章纲 AI 起草的稳定性，修复若干问题」（与原型字面量
    一致），否则常显提示条将破坏像素基线；无更新场景基线不变（实现侧条件渲染）。

---

## 规范治理（2026-08-29，ux 标准层对齐）

1. **权威声明分层化**：`prototypes/CLAUDE.md` 从「全站唯一权威规范」降为**原型层规范**（token 逐字值 / 组件类尺寸 / 页面清单 / 避坑）；标准层权威归属 `docs/ux/design-language.html`（裁决见 `cross-end.html`），两层冲突时以标准层为准并回登本簿。`docs/ux/README.md` 分工节同步改为三层并指向本文件。
2. **六份规范块 token 对齐**：ux 五份文档（design-language / home / components / cross-end / audit）与 `prototypes/CLAUDE.md` §2 的 `:root` 逐字一致（23 个令牌）——补齐 `--font-display` 的 `'Iowan Old Style'`（4 份缺）、`--on-accent`（3 份缺）、`--shadow-pop`（3 份缺）。原型 HTML 未动（`--on-accent`/`--shadow-pop` 属实现层令牌，CLAUDE.md 注明不要求原型包含）。
3. **徽标命名迁移口径**：CLAUDE.md §3 注明 `.b`/`.badge` 为原型现状，实现层按 ux 标准 §6.2 收敛为 `.pill-*` 四角色；改名须先登记后一次完成，禁止两套类名长期并存。

同批顺带核出（未动，待原登记流程处理）：design-c/prototypes 新稿存在 3 处死控件（`.ai-fill`「AI 帮我填」、list `#btnImport`、model-config `#btnPrefs`——渲染有样式无行为）与 `.row-3 { repeat(3, 1fr) }` 裸 input 移动端溢出（§7.1 同款坑）；新 UI 的 `data-od-id` 仅 +1，设定 7 面板 / 卷纲 4 子表 / 章纲全字段暂进不了 parity 截图比对。

    追记（同 PR）：book.html 本地 `.btn-sm` padding 0 11px 为历史孤本漂移
    （list.html 与实现侧 base.css 均为 0 12px）——更新提示条三按钮累计
    6px 错位致 parity 超阈，对齐为 0 12px 收敛；book.html 其余 sm 按钮
    （novelbar 升级等）宽度 +2px，各 parity 场景复核通过。

## 静态首页改版（c-static-home，2026-08-29）

4. **`.welcome` 静态首页入口卡登记**：`/` 改版为免登录入口卡（设计源
   `docs/ux/home.html` home 态，用户已过稿；裁定 v2——`/` 免登录静态页，
   已登录自动跳书架）。组件落 `client/frontend/src/design/landing.css`
   本地段，**非共享段**（S端 无此页，无双端同批义务）。原营销版
   LandingPage（mkt-* 轻重皮）整体退役，`landing.css` 营销段随之清空。
   书架原型 `list.html` 不受影响（.welcome 只出现在 `/`，非 parity 对象）；
   书架三态（`.resume` 继续创作条/首启空态/满额墙）等品牌意见后另批登记。

## 静态首页重设计（c-home-redesign，2026-08-29）

5. **`home.html` 六变体评审稿立项**：c-static-home 上线的 welcome 入口卡被评
   「太丑」，按 OpenDesign 原型规范重做静态首页，出六变体（玄墨/卷首/朱印/
   断章/悬丝/对仗，slogan 均为用户定稿「人铸灵魂，AI 行笔墨」）供拍板，右下
   角切换器非基线。评审修订：应用户反馈移除 hero 区独立「爱」字图标（品牌
   图形收敛在 appbar logo）。本文件只承载设计评审；选定变体由实现侧落
   `landing.css` + `LandingPage.tsx` 后，选定变体转正为 home 页原型基线并回
   登本簿。未动既有四页基线。
   【回登 2026-08-29】用户拍板变体 a 玄墨并经三轮评审修订（品牌 lockup 三段式
   布局 + slogan「人铸灵魂，AI 行笔墨」+ 「直接开写/新手教程」路径卡 + 移除
   hero 独立爱字图标），已落地 landing.css + LandingPage.tsx；a 转正为 home
   页原型基线，b-f 保留作品牌 agent 迭代参考。新手教程暂指 GitHub 使用说明
   （站内引导流未立项）。

## 品牌评审修订（Brand Guardian，2026-08-29）

6. **品牌字标字距全局统一**：appbar `.logo` 与静态首页 `.brand-cn` 统一
   `letter-spacing: 0.08em`（原 hero 0.16em 偏散、appbar 无字距，同一资产
   两种排印）。五份原型 + base.css 六处 `.logo` 同批更新，parity 双侧同步。
   同批速赢：`.brand-en` 右夹线 `margin-left:-0.42em` 光学居中；`.brand-ver`
   加 tabular-nums 与 `.num` 同源；`.ink-glow` 改 `min()` 尺寸 + 透明端 55%
   防窄窗硬裁（墨晕化）。路径卡副文去「第一句」意象重复，改「落笔即存，
   想到哪写到哪」。待拍板：mark/wordmark 双轨规则（agent 倾向「mark 只存
   于 chrome，内容层纯文字字标」）。
   【拍板回登 2026-08-29】用户同意品牌 agent 方案 (b)：「爱」方标只存在于
   系统层（appbar/窗口/安装图标），内容层一律纯文字字标（letter-spacing
   0.08em）。规则已写入 design-language.html §七 布局骨架与本文件 §3。
   当前实现全合规；唯一非合规点：S端 AuthPage 授权表单的 brand-row 方标
   （内容层），留 S端 下一批 UI 收编时去除。design-language §七 全局壳的
   「/ 无 appbar、Footer 隐藏」过时描述一并按 c-static-home 后现状对齐。

## 书架三态落地（c-bookshelf-states，2026-08-29）

7. **list.html 升级三态**（回访/首启/满额，设计源 docs/ux/home.html，品牌 agent
   评审意见同批吸收）：books 态顶部新增 `.resume` 继续创作条（updated_at 最大
   者置顶直达，**该书从网格剔除避免同书双入口**）；empty 态由单行空卡升级为
   三步引导（`.first-run` 独占容器，非 .cards 网格项）；新增 quota 满额态
   （notice.info「免费版书架已满（1/1）」+ 主按钮带锁仍可点 + 网格尾
   `.lock-tile` 升级锁卡——主图标=锁，sparkle 只在出口按钮；「无限」营销腔
   弃用，与 notice 逐字同口径）。免费注入约定：`localStorage ainovel.member='0'`
   = 免费待遇（缺省=会员）。`resume .rm b` 用 fg 而非 ok 绿（页面内不出现
   双绿）；STEP 03 口播与 page-head sub 去重，改「第一句想到什么就写什么」。
   实现侧 `list.css` 本地段 + `NovelListPage` 同步；design:check books/empty/
   quota 三场景零漂移。
   【二次裁定回登 2026-08-29】用户拍板：继续创作条裁撤——「书架上每本书都有
   继续创作的简单状态就好，书架排序即修改时间倒排」。list.html/实现/list.css
   同步移除 .resume；书架网格显式按 updated_at 降序（最近有进展的排前面）；
   满额 notice + 锁定主按钮 + 升级锁卡保留。原型 resumeSlot/ainovel.member
   注入约定中 member 语义不变。

## 客服外跳入口（contact-support-page，2026-08-29）

8. **list.html / book.html appbar 加「联系客服」**：设置按钮旁新增
   `btn btn-ghost btn-sm` 同规格锚点按钮，原型内 href="#" 占位（落地实现为
   `<portal_url>/support` 外跳，target=_blank 新窗口）。按钮原样落地，预期
   零偏差（无新组件词汇、无档位变更）。未登录形态不加（官网落地页页脚覆盖）。

## backup-restore.html（备份导出/恢复导入，2026-09-04）

新屏原型（7 屏+子态，单文件，右下 .rv 屏切换器 / 左下 .rv2 子态切换器 / 数字键与 #2:s3 式 hash 直达）。
产出流程：UX 交互稿定流程与文案 → 本原型做视觉层；规格与偏差明细见 backup-restore.spec.md。
状态：停审批口（c-novel-export-roundtrip 设计阶段），批后随 change 实现收编为 parity 基线。

登记条目：

1. **评审脚手架非基线**：.rv / .rv2 / .rev-cap（形态对照小标）/ .rev-new（「新增」虚线角标）/ .demo-open（强制显示悬浮菜单）均为评审辅助，实现对照与 parity 截图排除（同 list.html 评审切换器先例）。

2. **进度步 locked 画进结构**：备份/恢复弹窗进度步与打包中态去掉 X 与取消（scrim 点击/Esc 语义随封装 Modal locked），「不可中断」由结构表达非文案。

3. **serif 30px 大百分比**：进度主数字用设计语言 §3.1 预留的 display 档（备份/恢复共用），不引入进度条新组件；.bk-* 新词汇清单见 spec（.bk-step-tag/.bk-files/.bk-row 等，实现时按需同源同步 list.css）。

4. **首启恢复卡主 CTA 用 primary**（偏离 EmptyState 默认约定，交互稿定稿）——待用户终裁，若驳回改回 EmptyState 默认档。

5. **⋯ 菜单删除色归位 err**：原型按设计语言 N6 画 err；现网 list.css 误用 warn，属顺手修正项（实现 PR 内同步）。

6. **敏感四层视觉**：勾选时就地 warn（L1）/完成页钥匙 warn（L2）/产物文件名自标识（L3）/恢复预览掩码+块级取消勾选（L4）——均为新屏内容，无现网对照。

## 模型配置弹窗加宽（config-modal-input-width，2026-09-05）

9. **model-config.html `#modalConfig .mcard` 460 → 520px（仅此弹窗，其余维持 460 家族档）**
   选供应商自动预填的 Base URL 最长 49 字符（Qwen `https://dashscope.aliyuncs.com/compatible-mode/v1`），
   13px 等宽需 382px，460px 弹窗的等宽文本区仅 384px——1.8px 卡线，真实环境字体度量稍宽即截断
   （用户实测「输入框不够长」）；API Key 常见 40-60 字符同样看不全。520px 提供约 444px 文本区，
   URL 稳放、≤55 字符 Key 全程可见（更长 Key 属密码框固有滚动，不追）。
   parity：本屏 parity 只截 configs/empty 页面级两场景，弹窗不进基线，零漂移；
   实现侧 `ApiConfigForm` Modal width 460→520 同步。

## 接口格式字段（c-api-format，2026-09-06）

10. **modalConfig Base URL label 行新增两态 .seg（OpenAI 格式 / Anthropic 格式）+ 新样式 .seg.lock**
    接口格式是 Base URL 的属性（厂商文档成对给两个地址，选择器与输入框同行，照抄视线不迁移）。
    厂商锁定矩阵：openai / anthropic / ollama 卡单格式锁定（.seg.lock 降透明禁点击，双端 base.css 共享段同批新增）；
    glm / kimi / deepseek / qwen / openai-compat 可切换。编辑态 seg 可点、供应商仍 vfix 锁定——
    换厂商=换一家服务（身份级，锁）；格式=同一家服务的两种报文契约（可改，改后模型列表与测试状态失效须重测）。
    .seg 组件样式与 base.css / book.html 同值；.label-row 为新增页面级布局类（model-config.css 同步）。

11. **Base URL 预填废除 + 无地址引导文案（拍板 2026-09-06）**
    选供应商不再写 value（VENDORS[].base 字段删除，520px 加宽的历史动机随之失效，宽度档维持不回退）；
    placeholder 随格式给示例域名（openai → https://api.openai.com / anthropic → https://api.anthropic.com）；
    切格式 / 换供应商均不改动已输入 URL，仅清测试结果；界面不提供任何厂商地址文案（GLM Coding Plan 帮助小字拍板删除，URL 照抄厂商文档自备）。
    parity：本屏 parity 只截 configs / empty 页面级两场景，弹窗不进基线（既有口径），零漂移；
    实现侧 ApiConfigForm 同批落地（seg 控件、锁定矩阵、api_format 随 create/update/test-connection 契约上送）。

## 底部状态条（c-version-account-visibility，2026-09-07）

12. **list.html / book.html / model-config.html 新增固定底部状态条 `.statusbar`（V3 落点，视觉稿已批）**
    用户拍板「版本号要常驻」，四变体视觉稿后定版 V3=窗口底部状态条（`docs/design-c/drafts/version-placement-draft.html`）。
    结构：左版权「© 2026 爱小说」+ 右版本号 `.sb-ver`（mono tabular-nums），26px 高、border-top 细线、
    muted 12px、z-index 30（scrim 40 之下，弹窗遮罩盖得住）、`position:fixed` 贴窗口底；
    `body { padding-bottom: 26px }` 预留防遮挡。三屏 `.pagefoot`（© 单行）随之退役删除——版权并入状态条，
    窗口底部只保留这一条（禁双底条）。`home.html` 豁免不加：落地页自带品牌页脚已含版本行（v0.9），
    营销页非应用态且页脚经三轮评审定稿；`index.html` 为设计说明页非应用态，不加。
    版本号字面量随 parity 打桩口径（运行时为真实烘焙版本）：list/book 场景 stub `update`（current=0.11）→ `v0.11`；
    model-config 场景 stub `none`（current=0.13）→ `v0.13`。
    实现侧同批落地：`StatusBar` 组件挂 `ClientShell`（路由 `/` 豁免同口径）、App 级 `<Footer />`（.pagefoot）退役、
    index.css 新增 `.statusbar` 业务层段（无共享段改动）、`.sb-ver` 样式与原型逐字同值。
    【追记（同 PR 评审修正）】工作台/登录须**真实让位 26px**，否则固定条盖住列底且 app 侧多 26px 幽灵滚动
    （body padding 对 overflow:hidden 的 flex 内容盒无效）：book.html 改用链内 `.sb-spacer`（.view flex:1
    随之收缩），实现侧 book.css `.wb` 高度 `calc(100vh - 48px - 26px)`、landing.css `.auth-wrap`
    `min-height: calc(100vh - 26px)`。list/model-config 内容自然增长，维持 body padding-bottom 口径不变。

13. **同批 rider：update-strip 字面量带当前版本对照（list.html / book.html）**
    更新提示条文案「发现新版本 v0.13」→「发现新版本 v0.13（当前 v0.11）」（client-update MODIFIED
    需求的对照文案，stub `update` 场景 current=0.11）。parity：两屏 update 场景基线随字面量同批重铸。

14. **同批弹窗版本行：list.html / book.html modalPrefs 底部加 muted 版本小字**
    两弹窗 `.mcard-foot` 左置版本行（`data-od-id="pref-version"`，v0.11 与本屏 stub 口径一致；
    book.html 用既有 `.note` 左置样式，list.html 内联同值）。设置弹窗账号行不加用户名到 book.html
    （本书偏好弹窗不新增账号身份，既有套餐文案行保持）。

    **存量观察（非本 change，待原登记流程处理）**：`book.html` 原型设定树为 7 项（无「主线」），
    而实现侧 story-arc 主线合并后设定为 8 项——book.settings 场景 parity 自主线合并起结构性超阈
    （主仓 baselines 停在 2026-08-29）。工作台原型随主线收编另批处理，本 change 不动。

15. **书架权益异常提示条（c-s-entitlement-sync，2026-09-06）**
    书架顶部新增条件渲染 notice（warn 语义，信息=「权益信息同步异常，已按套餐标准处理」+ 可复制问题详情 + 联系客服出口）。
    复用既有 .notice 组件形态（无新增组件/第四种胶囊）；仅 entitlement_degraded=true 时渲染，
    默认态不出现 → 书架 parity 基线（empty/quota 场景）零漂移，实现侧登记免原型改版。


16. **顶栏头像控制中心面板（c-account-control-center，2026-09-07）**
    三屏 appbar（list/book/model-config）动作区收敛为头像胶囊唯一入口：移除「联系客服」「设置」
    常驻按钮，新增 `.acct-trigger`（首字头像 + 四态套餐徽章 + caret）。list.html 设置弹窗
    （modalPrefs）整段退役，替换为 `.acct-menu` 控制中心面板（账号区头完整档 + 数据组备份/恢复 +
    模型配置 + 支持组客服外跳 + 退出登录轻确认 + 版本行）；book.html 面板工作台语境增挂
    「本书偏好」项承接原「设置」按钮（modalPrefs 本书偏好弹窗与其归档 seg 保留不动）。
    badge 三色沿用语气词映射：accent=PRO 会员、muted=免费版（含过期合并单档）/试用充裕、
    warn=试用临期（≤3 天含 0 天）与 S端失联变色（前端同步失败信号，文案不变仅换色）。
    用户名 >12ch 截断悬停见全文；外点白名单含触发钮防 toggle 双触发。

17. **创建期引导：本书模型 + 简介 + 题材（genre-signup-redesign，2026-09-09）**
    新增 `genre-signup.html`（自 `drafts/genre-signup-draft.html` v8.5 收编），承载创建期前两步的
    新交互：**三窗**＝① 本书模型（四态徽章 + 按 API 配置分组的卡片选择器 + 选择与生效分离确认键）
    → ② 简介（编辑框 + 「怎么写」六段模板折叠 + 右栏 AI 写作助手三能力）→ ③ 题材（六格 +
    右栏五行 AI），AI 反馈统一落左侧输入框下方 `.ai-sink`。

    **IA 偏差（有意）**：模型步写在流程条第 ① 步，但**不进 `SETTINGS_ITEMS`**（不参与 readiness/
    完成度判定与「确认即前进」序列）——它是 AI 前置引导步，非设定项。

    **组件归属**：`.rail-assist`（AI 写作助手卡）/`.ai-sink`（AI 结果区）为 **C端局部组件类**，
    只复用共享令牌（`--fg-soft`/`--surface`/`--border`），**不新增全局 token**、不进 base.css 共享段。

    **两处陈旧注释已修正**：原「（AI 前置，仅 PRO/MAX）」→「免费版也能配，差别只在右侧 AI 助手灰」；
    原「选中即保存，无确认键」→「选择与生效分离＝点行只标亮、点确认才落库」。

    **门禁范围**：本页**暂未纳入** `design-vocab.mjs` 的 `strictGlobs`（实现侧页面未落地，
    纳入会使 `design:check` 无对应实现而必红）；待实现收编后随原型基线一批纳入。

18. **角色设定改版（character-settings-v2，2026-09-13）**
    新增 `character-settings.html`（自 Downloads 工作稿 v6 收编，`data-od-id` 全量保留）。本页取代：
    `book.html` 内的旧角色面板（14 字段折叠卡）与 `ADJUSTMENTS.md:181` 登记的「角色（左列角色行 +
    14 字段三组折叠卡）」条目——两处保留为历史，不再作为该屏的实现依据。

    **词汇归属（复用，不新增胶囊/徽标档位）**：角色类型＝可点击胶囊 `.chip` / `.chip.on`；
    人物关系类型＝状态胶囊 `.pill` + 语气档；徽标只用 `ok / warn / prog / empty`；保存态对齐既有
    四态（`saving / saved / dirty / failed`）；体检逐项行用**新类名 `.chk-row`**（名称＋结论一行、
    依据一行），不覆盖既有 `.chk-line` 作用域；体检第四个取值命名 `conflict`（渲染走 err 色；值名
    不与传输失败态 `err` 撞名），**不进世界页结论白名单**。原型内 `.chip/.pill` 的尺寸与现役
    `book.css/base.css` 略有出入——**以现役为准**（原型尺寸仅示意）。

    **状态语义登记**：第三态文案定为「内容有变 · 待重新确认」（不含「已确认」字样，守 §5 S-R2
    「已确认→ok 绿」硬规则）；**常态「草稿」不再挂 warn 徽标**（§5 S-R3：警示徽标禁止常态化），
    未确认改为中性档位/副标题表达。删除/合并走卡内 `.ops-panel` + **输入角色名解锁确认**（L3 语义
    与 §12 一致，但机制是内联面板而非 `DeleteConfirmModal`——差异在此登记）。

    **落点声明**：体检与三处补全的 AI 结果一律落卡片内 `.ai-sink`（右栏只放按钮），沿用
    intro-genre 的「结果落对应槽位」规则；回执沿用面板脚 `.receipt`（单行、最近一条、切卡清空）。

    **门禁范围**：本文件已加入 `design-vocab.mjs` 的 `strictGlobs`（严格文件 26→27，lint 通过）；
    顺手清理 3 条失效登记项（`Footer.tsx` / `GenreEditModal.tsx` / `CharacterCreateModal.tsx`，
    文件均已不存在）。类名映射表（原型 164 类 → 现役复用 / `.settings-v` 局部新增）随 5.1a 落
    `book.css` 时同批产出。稿纸列宽（232/244/236）不绑定实现，以现役 `.three-col` / `.subsplit`
    几何为准。演示种子为 9 卡 10 关系（非 43——43 是压测词表）。

    **已知边界**：原型 `save-state` 仅演示 `saving → saved` 两态；`dirty / failed` 的形态以
    `ChapterWorkspace` 的现役四态实现为准，parity 基线不覆盖（靠 e2e）。


19. **设定屏·角色 parity 首跑（character-settings-v2 tasks 6.2，2026-09-14）**

    `design-parity-book.spec.ts` 参数化 `PROTO_FILE`，新增 `settings-characters` 场景：
    原型侧隐藏稿头/窗体标题栏并归一化满幅（body margin/padding、win 描边），比对裁剪
    以 col-tree 左缘→col-ai 右缘为内容锚点（容器 padding 差不造成整体错位）；应用侧
    打桩 43 卡聚合/单卡/关系/gate/readiness(4 缺=3+角色已填 4/8)/settings-status。

    **首跑揪出并已修**：① 应用 `.sub-wrap` 纵排把人物卡挤到可视区外 → `.char-sub`
    双栏（236px 列表 + 卡）；② 卡片区块顺序 错（人物关系在认知内核前）→ 按原型改为
    基础档案→认知内核→人物关系；③ 左树徽标把"已填"冒充"已确认"（5.4 登记过的纠正
    只改了面板头没改树）→ 树也走 stale>confirmed>filled 三级；④ 列表聚合补 specs:149
    要求的 首次出场（chapter_characters×chapters×volumes 一次 GROUP BY 取最小阅读序）
    与更新时间，卡 meta/列表副标换真字段；⑤ 右栏 chars 分支缺失（四能力孤岛）→
    CharsAiRail 接线；⑥ 原型演示数据对齐现役：右栏头行文案、3/8→4/8、草稿→已填、
    三栏网格 232/244→280/236（以现役 shell 为准）、别名 join 口径、更新于改日期时间。

    **遗留（skip 断言的理由）**：两套独立实现的内部间距节奏仍有差——树行起点差
    ~23px、面板头差 ~7px、模型设定行宽差 8px、字体光栅差异；0.2% 阈值按同源 CSS
    校准，不适用于跨实现比对。基线三张图照常落 `docs/design-c/baselines/`，逐项
    对齐间距后把 skip 换回阈值断言。认知六层/关系区在首屏之外，靠 e2e 覆盖。

20. **伏笔设定改版（foreshadow-settings-v2，2026-09-15）**
    新增 `foreshadow-settings.html`（自 `drafts/ai-novel-c端-伏笔设定.html` v3 终稿收编，
    `data-od-id` 全量保留）。本稿取代 `book.html` 设定段登记的「伏笔（活跃/已收束/废弃三分组，
    9 类钩子+优先级）」旧口径（PR 4 #3，留作历史）；实现依据以本稿＋
    `openspec/changes/foreshadow-settings-v2/specs/foreshadow-settings` 契约为准。

    **类名映射表（.kv 家族作用域化，避让世界面板现役 .kv-row/book.css:694）**：
    `.kv`→`.hk-kv`、`.kv-row`→`.hk-kv-row`、`.kv-k`→`.hk-kv-k`、`.kv-static`→`.hk-kv-static`、
    `.kv-hint`→`.hk-kv-hint`（`.kv-row.span2` 语义并入 `.hk-kv-row.span2`）。台账两行条目
    `.hk-item/.hk-dot/.hk-b/.hk-name/.hk-meta` 与分组头 `.sub-group-label`（g-dot 三色）为
    settings-v 作用域新类；其余（.cap/.cap-row/.seg-note/.badge/.btn/.input/.textarea/.opt/
    .text-btn/.save-state/.sub-empty/.receipt-bar/.ai-sink/.chk-line/.rail-assist/.tree-*/.
    sec-label/.sl-tag/.panel-foot）全部现役复用，不新增第四种胶囊/徽标档位。

    **状态语言登记**：状态点三色 活跃=实心 warn／已收束=实心 ok／废弃=muted 描边——台账点、
    分组头点、卡面状态徽标（.sl-tag st-*）、状态切换控件全链同源；面板徽标五态：
    还没有伏笔=empty／N 条待收束=warn／已确认 · N 条待收束=done／全部收束=ok／
    内容有变 · 待重新确认=warn（优先级最高，文案不含「已确认」，守 §5 S-R2）。
    保存四态（saving/saved/dirty/failed）落面板脚 .save-state（mono 小字）；「存草稿」
    按钮对伏笔隐藏。data-aiact=h1-h4；**空态 AI 旁路（btn-empty-ai）＝「编辑区零 AI 按钮」
    的唯一登记例外**，随 aiState 门控矩阵走（免费可见＋锁定）。

    **词汇修正（相对 v3 稿面，有意的偏差）**：类型下拉中文标签以后端词表单源
    `settings/hooks_model.py` 镜像为准——悬念/威胁/承诺/线索/关系伏笔/能力伏笔/情绪钩/
    选择钩/渴望钩（稿面 谜团/关系/力量/情感/选择/欲望 为草稿期旧词）；demo 候选标签同步。

    **评审脚手架（非基线，实现对照与 parity 截图排除）**：doc-head 稿头、win-titlebar、
    appbar「客服/设置」演示按钮、modnav 页签、右下 toast 演示。转正补 modnav（对齐
    character-settings.html 先例）；demo 内两处 id（badgeLedger/abandonedNote）改名
    stateBadge/dropNote——避让 design:lint 裸 hex 正则（`#bad`/`#aba` 命中），语义不变。

    **门禁范围**：本文件已加入 `design-vocab.mjs` 的 `strictGlobs`（严格原型 5→6，lint 通过）。

21. **文风设定改版（style-settings-v2，2026-09-15）**
    新增 `style-settings.html`（自 `drafts/ai-novel-c端-文风设定.html` 终稿收编）。
    面板内两页签（文字文风／量化参数）＝**页签回归例外**（design-language §7 tabs
    语言，仅面板内层级，面板间导航仍走左树）——用户拍板，替代单页长滚动。

    **类名映射表（settings-v 作用域新类，落 book.css 本地段）**：页签
    `.ptabs/.ptab`（+`.ptab-pro` 小徽，视觉档同 plan-badge 缩小）；锚定块
    `.fblock/.fb-head/.fb-no/.hint` 与锚定链 `.anchor-chain/.ac-node/.ac-arrow/.ac-note`；
    基线 `.dims/.dims-meta/.bx-row/.bx-head/.bx-name/.bx-dims/.bx-vals/.bx-note/
    .lock-btn/.five-bar/.fb-legend`；明细 `.det-row/.dk/.dv2`；蒸馏 `.sample-box/
    .sample-row/.s-name/.s-cnt/.s-check/.sample-total/.dist-step/.ds-no/.ds-b/.ds-ok/
    .portrait/.pz-head/.pz-note/.pz-ask/.pz-act`；空态复用 sub-empty 家族。
    **共享化**：`.hk-sec-label/.hk-sl-tag` 提升为 `.settings-v .sec-label/.sl-tag`
    （hk-* 保留别名，HooksSettingForm 不改名）。**组件扩展（不新增词表）**：
    `Cfg` +sum 摘要位、`ListEditor` +上移/`x/y` 计数（`.li-cnt`）。
    **不入库**（稿内演示残留）：src-card 家族、genre-grid/g-chip、badge.done、
    badge.acc（页签 PRO 小徽用 .ptab-pro）。

    **状态语言登记**：页签徽标 文字文风=「题材默认」ok→「已自定义 · N 处」warn；
    量化=「未蒸馏」empty→「置信度 N」acc；蒸馏三步完成=ok；锁定按钮 aria-pressed、
    五层条 aria-hidden。**data-od-id**：style-tabs/input-style-role/list-rules/
    list-craft/list-fewshots/field-*/chain-anchor/quant-*/lock-{row}/distill-*/
    author-portrait/btn-portrait-keep/btn-portrait-retry/sink-style-check。

    **门禁范围**：design-vocab.mjs strictGlobs 增补本文件（严格原型 6→7）。

---

22. **禁用词收编文风（banned-words-into-style，2026-09-16）**
    「禁用词句」独立面板退役，内容收编为文风卡硬约束区两个折叠组。三文件同批：

    **book.html**（settings 屏 parity 基线）：
    1. 设定左栏 `ITEMS` 去掉 `antiAI`（AI痕迹控制）项——内容菜单 8→7，
       末项变为伏笔；`DESCS` 同步摘除；「AI痕迹控制」措辞全清。
    2. 摘除 antiAI 面板渲染器与演示死数据（`FATIGUE_CATS`/`SET_ANTI`/`ticCards`）。
    3. 面板种子注释同步（空面板清单去 AI痕迹）。

    **style-settings.html**（文风卡基线）：
    4. 左栏示意 nav 去禁用词句项（与 book.html 同口径）。
    5. 硬约束区（②）后新增两个折叠组（Cfg，默认收起、组头 sum 常显「N 条」，
       设计语言高密度表单口径）：**禁用词**（词表 ≤100，模板按七类预填 37 条，
       `data-od-id="group-banned-words/list-banned-words"`）与**句式规则**
       （正则＋阈值＋严重度 ≤20 条，sub-block tics 形态，
       `data-od-id="group-tic-patterns/list-tic-patterns"`）；组头计数 `#bannedCount/
       #ticCount` 随增删同步。
    6. 文案改口：②硬约束 hint「通用的 AI 词句归『禁用词句』面板拦」→「归下方
       『禁用词』『句式规则』两组拦（同一处管体检）」；锚定体检 desc、蒸馏 ra-foot、
       lexicon note、AI 体检头/行 同步去面板指涉改组指涉。
    7. 设计注记补 ⑥（收编口径）；⑤ 历史注记不改写。

    **foreshadow-settings.html**：
    8. 左栏示意 nav 去禁用词句项；hookOkNote「确认即前进到『禁用词句』」→
       「确认后停留本格（已是最后一项）」；确认 toast 同步（伏笔成为末项）。

    **parity 影响**：settings CASE 只截左栏＋默认简介面板——左栏少一行即像素变化，
    基线需重录；文风卡新版面（两折叠组）不在现有 CASE 截图内，暂无新增 CASE
    （该卡交互多、折叠态多，等实现侧稳定后随 parity 重录一并评估）。
---

23. **书内行头归一（appbar-single-row，2026-09-16）**
    `book.html` 原双行头（appbar 48「logo＋返回我的小说＋账户」＋ novelbar 44
    「书名＋题材＋免费提示/PRO 徽＋升级钮」）并成**一行 48px**：logo（即返回入口，
    title「返回我的小说」，跳 list.html）｜书名｜题材胶囊｜**当前主线定位 bar-here**
    ｜账户胶囊。口径取自 `drafts/storyline.html`（写作工作台原型）顶栏段，用户拍板
    「行头归一以此为准」；省出一整条给正文。

    **砍掉的顶栏位**：「← 我的小说」返回链接（返回=点 logo）；免费提示 free-hint
    与「升级 PRO」钮（免费态标识收敛到账户胶囊档位徽「免费版」；升级入口仍在右栏
    locked 卡与本书偏好弹窗）。`applyPro()` 同步摘除 freeHint/proPill/btnUpgrade
    三处引用。

    **新增顶栏段 bar-here**：`bh-k 当前主线｜bh-rule｜bh-t 第 N 章＋题｜bh-prog
    卷序 · 已归档/总章＋prog-bar`。**v1 口径＝最新归档章为端点**（无归档落首章；
    空书留空槽），storyline.html 的拟定/待写 frontier 口径待主线状态机立项后切换。
    响应式三档随 storyline：≤1320px 藏题材、≤1180px 藏 bh-prog、≤920px 折行。

    **类名**：`.bar-here/.bh-k/.bh-rule/.bh-t(+.n)/.bh-prog/.bh-vol/.prog-bar`
    直接收编（storyline 同名），应用侧落 book.css 顶栏段并 `.bar-here` 前缀作用域；
    删 `.appbar .back`/`.novelbar`/`.free-hint`/`.pill-pro`（无其他使用点）。
    **data-od-id**：appbar-logo（原 back-to-list 退役）、current-position。

    **同步实现**：Navbar 书内变体退役（/novel/* 返回 null），合并头由
    NovelWorkspace 渲染（AcctMenu＋BookPrefsModal 随迁）；wb.volumes 即数据源。

24. **设定完成入口重设计（settings-done-entry，2026-09-16）**
    （编号沿革：本条与上方「书内行头归一」曾撞号 23，2026-09-16 按「先写者留号」后移为 24；
    `openspec/changes/archive/2026-09-16-settings-done-entry/` 内对 #23 的两处引用已同步改 #24。）
    新增 `settings-done-entry.html`（自 `drafts/ai-novel-c端-设定完成去写作.html` v2 合一版收编）。
    「设定 8/8」进度行在完成态升级为完成卡：`.settings-progress.done` 变体（ok-soft 底＋ok
    描边）＋ `.pb-check/.pb-badge/.done-btn/.done-foot` 词表；状态语言沿 §5 完成=ok 绿。
    **口径**：完成入口不再使用普通主按钮（长得和「保存」一样）；未完成态零像素变化。
    非基线演示元素：doc-head、win-titlebar、appbar/modnav、右下状态切换器与 toast。
    门禁范围：design-vocab.mjs strictGlobs 增补本文件。

25. **认知六层对齐理解层次（cog-logical-levels，2026-09-16）**
    认知区词表补两处**提示文案**（只读小字，无交互、无新形态）：
    ① 层头六问 hint `.cog-layer-hint`（他眼里的世界是什么样的？/ 他把自己当成谁？/
    他在乎什么？为什么做这些事？/ 他能做什么？怎么做到的？/ 遇到事，他会怎么做？/
    他身边有什么人、什么事？）；② s5 格位 hint——复用 base.css 既有 `.f-hint`（label 下
    一行小字：「他和这个世界到底是怎么回事？这条路走到头，他注定要面对什么？」）。
    词表双源：`character_model.py` ↔ `characterModel.ts` 的 `COG_LEVEL_HINTS`/
    `COG_FIELD_HINTS`（parity 用例对拍文案逐字）。
    **原型未同步本区**：认知六层在 `character-settings.html` 里位于首屏之外；角色屏 parity 用例
    （`design-parity-book.spec.ts` 的 `settings-characters` 条目）当前整体 skip（间距节奏待逐项
    对齐，见第 19 条）且截图裁剪只覆盖三栏首屏，认知区进不了像素基线。本批文案的覆盖＝实现侧
    vitest（层头渲染＋展开 s5 格断言）＋ e2e 文本断言（`settings-forms.spec.ts`
    「认知区提示」用例钉住层头 hint 与 `.cog-field .f-hint` 的 s5 原文）；故不加原型、不改基线。
    **口径**：一律大白话，「理解层次/NLP/上三层下三层/精神层/张力」等术语不上界面。

26. **顶栏「续写」＝回到上次退出前的进度（appbar-resume-session，2026-09-16）**
    用户拍板：bar-here 的「续写」不是跳队列末端开新章，而是**回到上次退出前的位置**
    （哪一章＋编辑器滚动位置）。设备本机 localStorage `pref.book.{pid}.last_write`
    （ref＋滚动比例＋ts；ProsePane 输入/滚动节流 1s 记录）；bar-here 主线端点随之
    **优先显示上次写到的章**，无记录回落「最新归档章」→ 首章。新增
    `.bh-tag/.bh-tag-live` 草稿徽（storyline .tag/.tag-live 同款收编改名，避让 cfg
    摘要 .tag）：端点章有正文未归档即显示「草稿」；「拟定」徽待主线状态机（自由
    写作模式无拟定态，该徽正确地不出现）。**data-od-id**：resume-cta。原型的队列
    门禁语义（拟定排队/末端开写）仍待状态机立项，本条不覆盖。

    **草稿徽语气登记**：取**中性**款（`.bh-tag-live` = fg 字色 + fg/38% 描边，非
    warn）——依 design-language §5 规则 **S-R3**「警示性的常态化徽标禁止（永久挂
    「草稿」warn 徽标会把警示日常化）」，bar-here 的「草稿」是恒显常态属性，故不上
    警示色；§5 令牌表「草稿 → warn」的映射适用于瞬时/非恒显状态位（如章节行
    dot-warn），两者不冲突。storyline 原型 `.tag-live` 同为中性款，收编一致。

27. **storyline.html 二三/四期行为整批登记（workbench-storyline-2-4，2026-09-17）**
    原型 storyline.html 为这批行为的唯一事实源（drafts 目录，未进原型基线扫描）；`book.html`
    基线不随批改动（新页签与弹窗属 storyline 范围）。逐项：
    ① **主线端点与排队门禁**：`GET /frontier`（首个未归档章；全归档→待写占位）；正文 PUT 与
    AI 写章对非 frontier/支线章返回 409，正文页就地只读横幅（复用既有只读家族文案）；bar-here
    主线口径由「最新归档章」切换为 frontier（上条第 26 项的回落链随之更新：会话→frontier→首章）。
    ② **回退与旧稿支线**：「操作」页签 `.revert-card`（data-od-id `revert-card`/`revert-btn`，
    不可逆二次确认）；被回退章 `ghost_of` 标记转支线只读（`.ghost-group`），派生数据按章序清除。
    ③ **角色关系页签**：storyline 同款确定性定距圆布图（`.relations-graph`，边标签「关系类型 ·
    立场」）＋文本清单兜底。
    ④ **文风本章影子**：「文风」页签（`.style-pane`/`.style-shadow`；**全档位**）——全书
    基线只读＋本章覆盖行手工增/改/还原（行内编辑＋添加行控件）＋AI 建议（PRO）；
    shadow 数据落 `chapters.style_shadow`（拍板③）。**档位口径 2026-09-17 拍板**：
    手工覆盖行免费（与全书文风三区同权），AI 建议归 PRO——原「免费占位」口径废止
    （spec 见 style-shadow-free-tier 归档，workbench 需求重写为「文风页签（全档位）」。
    ⑤ **剧情推演弹窗**（`.sim-*` 家族）：storyline sim modal 逐段复刻——按回合逐步展开、未定
    走法不能推进、「收进章纲」写「预期策略」（走法行=任一回合一拗→中途先接一次意外）；产物不
    落库。AI 失败回落原型同款确定性推演（弹窗永远可用）。
    ⑥ **提示词六来源**：「提示词」页签顶部 `.src-chips`＋`.psrc-list` 只读展示六处来源
    （chars/preview/未填标注），与写作组装链同源。
    ⑦ **章内「伏笔」页签**（第 8 个，原型 hooksHTML）：`.hooks-pane` 只读台账投影——
    汇总（N 条·M 悬置·本章埋/收）＋行（编号/描述/埋于第 N 章·题名/悬置｜已收｜已弃），
    本章埋下或回收的条目 `.hp-row.hit` 高亮；空态引导去「设定 · 伏笔」。
    ⑧ **右栏「AI 辅助」随页签面板**（原型 aiShell 各页签段）：`.rail-assist` 每页签
    引导语＋`.rail-stats` 统计卡＋`.rail-acts` 动作清单；~~未实现动作＝禁用＋「规划中」~~
    （用户拍板：先占位后续逐个补）——**该占位机制已退役**：补货批次全部完成（见 ⑫），
    动作清单不再有「规划中」，不可用一律 `disabled`；已实现动作：章纲（AI 起草/剧情推演）、
    正文（续写/润色/扩写沿用原工具卡，仅正文页签呈现）；文风调参等页签内已有动作不重复。
    ⑨ **重写这一章**（chapter-rewrite，原型 readActionsHTML/applyRewrite/m-ch-confirm）：
    「操作」页签 `.revert-card` 同款卡（data-od-id rewrite-card/rewrite-btn，仅有正文
    且非支线渲染）→ `.rw-list` 三行影响面确认弹窗（旧稿/后续/设定）→ 确认即事务：
    旧稿内容寻址快照入支线（`.ghost-row` 分组，ref=`{ref}-r{8hex}`）＋归档章解锁；
    下游章挂 `.tag-stale` 虚线中性角标（§5 常态徽标禁警示色；避让 cfg 摘要 `.tag`，
    data-testid=ch-stale），三面呈现（树行/设定投影 `ch-stale-note`/右栏操作统计
    `下游挂着旧设定 N 章`）；本章保存成功即刷树消角标。
    ⑩ **归档收尾计划预览＋关系页签按章投影**（原型 archivePlanHTML/relsHTML）：
    归档弹窗 `.arch-plan`（PRO 五件事＋「未确认不参与后续提示词」；免费档说明无
    提案）；「角色关系」页签本章边高亮（accent 加粗）＋行内「· 本章」标注、来源列
    （第 N 章·题名／开书设定·全书统一）与状态列（开书设定/随剧情演变/基于旧设定）、
    图下「还没连线」孤立点行。
    ⑪ **右栏「操作」页签两项动作不设入口（2026-09-17 设计修正）**：原型
    「生成本章变更摘要／生成下一章建议」的产物在原型里就地显示于 AI 面板结果卡；
    C端 右栏无结果区，且与既有消费面重复——变更摘要＝归档 AI 摘要（Archive.summary
    ＋ai_summary 开关）＋收尾提案（设定变化/关系/伏笔）＋设定页签「本章变化」；
    下一章建议＝下一章章纲的 AI 起草（以主线/前情/设定为输入）。故两项从占位清单
    撤销，不再列入补货批次。
    ⑫ **右栏检测/精修族落地＋三项重复动作撤销（2026-09-17 补货批次）**：⑧ 的占位清单
    按页签逐个补实现——检测族（六类 ai-check：`POST …/ai-check {kind}` 就地弹窗，finding
    列表/空态/重试，`data-testid=ai-check-list|ai-check-empty`）＝章纲「与卷纲冲突检测」、
    文风「文风一致性检查」「标记偏离段落」、关系「关系冲突检测」「建议补边」、伏笔
    「伏笔冲突检测」；精修族（`POST …/write/prompt/refine {mode}` 提案制弹窗，采纳走既有
    提示词保存链 `PUT …/prompts/write`，`data-testid=refine-preview|refine-adopt`）＝提示词
    「补全负向约束」「精简提示词」；章纲「补全缺失字段」＝`POST …/outline/fill-gaps`（AI
    产物回填章纲表单，落库走既有保存链），并在面板补 ⑧ 曾缺的「还缺」清单（原型
    `aiList('还缺')`）。**撤三个重复动作**（各与既有消费面同产出，同 ⑪ 口径）：
    「重新组装提示词」＝提示词页签内的「AI 润色」（组装＋落库同一动作，且粗组稿本就每次
    重算）；「本章关系变化检测」＝「操作」页签 reconcile 关系收尾（识别角色与物品变化＋
    待确认行）；「建议本章回收」＝reconcile 伏笔收尾的「收束」提案。产物一律不落库
    （检测/精修皆为提案制或表单承接）。同批把本原型内联的伏笔类型词表 `HOOK_TYPES`
    由草稿期旧词（谜团/关系/力量/情感/选择/欲望）校正为应用侧单源标签
    （悬念/威胁/承诺/线索/关系伏笔/能力伏笔/情绪钩/选择钩/渴望钩，见
    `client/backend/settings/hooks_model.py` 镜像）。
    **门控**：①-③ 免费可用；④ 影子手工编辑全档位、AI 建议 PRO（2026-09-17 拍板定案）、⑤ AI 归 PRO。
    **测试覆盖**：后端 pytest（frontier/ghost/style_shadow/plot_sim/prompt_sources）＋前端 vitest
    ＋e2e（plot-sim.spec.ts 等）；无原型像素基线（storyline 未收编严格扫描）。

---

## preview.html（阅读预览三栏，c-preview-reader，2026-09-17）

设计源：`docs/design-c/drafts/preview.html`（2026-09-17 设计侧会话产出）收编为本屏基线。
**原型即基线：本文件入库，baselines/ 比对 PNG 为本地产物不入库。**

只动 `preview.html`（新屏基线）：

1. **预览独立成屏，book.html `#viewPreview` 两栏段下线**
   原 book.html 预览 = 左树 + 只读正文两栏；本屏起预览为三栏阅读器
   （全书目录 / 阅读 / 配置与概览）。book.html 的 `#viewPreview` 段与其
   parity preview 场景迁移至本屏（design-parity-preview.spec.ts）。

2. **目录行状态：章纲三态 dot → 成稿状态标签（.pill 家族）**
   通读场景只需要成稿状态（拟定/草稿/已归档），章纲缺口细节归写作视图。
   设计稿自造的 `.tag/.tag.live/.tag.wip` 收敛为 `.pill` 家族
   （拟定=pill-faint、草稿=pill-accent、已归档=默认中性），第四态
   「待写」随产品状态机移除。**已归档优先**：archived 章无论有无正文一律已归档。

3. **章节行序号列（阿拉伯 mono `.no`）移除，单列 nodeLabel 全标签**
   产品序号单源 `nodeTitle.ts`（「第三章 · 静默带」，全局章号中文数字）；
   设计稿「第3章 + 标题」双列与单源口径冲突，按产品口径合并为一列。

4. **卷头拼串 bug 修正**：设计稿 `'第 '+v.name` 会渲染成「第 第一卷 · 星海初航」；
   收编稿改为 `<b>{卷全标签}</b> · {N} 章`。

5. **阅读主题补 `--pv-bg` 消费规则**
   设计稿三个主题类只定义 `--pv-bg/--pv-fg/--pv-muted` 变量、无任何规则消费
   `--pv-bg`（夜间档浅底浅字不可读）。收编稿 `.pv-prose-wrap` 补
   `background: var(--pv-bg); color: var(--pv-fg)`。护眼/夜间的 oklch 字面量
   为登记的 token 化例外（与设计稿逐字一致，不新开全站 token）。

6. **阅读配置持久化（新增）**：设计稿只持久化选中章；产品四轴（字号/字体/行距/主题）
   书级持久化（`pref.book.{pid}.read.*`），原型以 `ainovel.reading.v1` 演示同语义。

7. **下载成稿卡与弹层不在本屏基线**（归属 c-manuscript-download）
   设计稿右栏「导出成稿…」卡与导出弹层随该 change 修订后
   （文案「下载成稿」、PDF 项移除）再落本屏基线；本屏右栏只含
   全书概览 + 四组阅读配置。术语拍板：读者成稿动作 =「下载」，
   系统数据资产 =「备份/恢复」。

8. **token 映射（不新开）**：设计稿的 `--accent-ink`→`--accent-strong`、
   `--hl`→`--fg-soft`、`--faint`→就地 `color-mix`、`--radius-sm/pill`→
   `--radius`/999px。左栏宽沿用 `--col-left`（280px）不用设计稿 250px。

9. **初始章 = 首章**：设计稿默认选中「最后一章有正文的」；产品语义 =
   写作视图当前章（initialRef，ADJUSTMENTS #13 本地态口径），parity 态即首章。

10. **翻页控件例外登记**：阅读区「上一章 / 下一章」为翻页控件，
    非动词按钮词（design-language §13 惯例例外，与分页器同族）。

11. **壳层逐字同 book.html**（appbar/modnav/update-strip/tokens，
    `--radius-lg:14px`），种子数据（星海拾遗 3 卷 17 章）为演示数据，
    与 design-parity-preview stub 逐字段对齐。

---

## preview.html 下载弹层修订（c-manuscript-download，2026-09-17）

在 `preview.html`（c-preview-reader 收编稿）上做本 change 的原型修订：

1. **右栏「下载成稿」入口进基线**：设计稿「导出成稿…」按术语拍板改名「下载成稿…」
   （读者成稿动作 =「下载」；系统数据资产 =「备份/恢复」，本原型不再出现「导出」字样）。
2. **PDF 项移除（缓办拍板）**：首版格式 = Markdown / 纯文本 / Word 三项，PDF 不出现
   也不以禁用项占位；PDF 待阅读排版渲染管线另立版本后回补。
3. **重开弹层读回已完成态**：设计稿 `exOpen` 把 done 重置回 form；产品语义 =
   进行中关闭弹层为「后台运行」，重开可读到完成态与产出文件清单（spec 口径），按 spec 修正。
4. **弹窗底座**：原型内联 `.modal/.sheet` 简化底座仅作演示；实现走 `Modal` 组件
   （wbStyle 版式），像素基线只锁右栏入口卡与右栏区，弹层打开态不在基线场景内。
5. **实现侧新增词汇**：`.ex-fmt`（格式勾选行，role=checkbox 语义）/`.ex-path`（位置行）/
   `.ex-steps`（进度清单，等待/下载中/完成/失败四态，ok/err 语气字）/
   `.ex-done`（完成块）/`.ex-bar`（进度条）/`.dl-need-desktop`（无壳降级提示）。
6. **账号菜单备份项提示**同步收紧：`list.html` / `book.html` 同款文案
   「选择文件夹导出」→「选择文件夹保存」（术语分离，同批落实现与两份基线原型）。
7. **完成态补「再次下载」出口**（2026-09-18，#414 双路评审登记的遗留 P2）：弹层挂书工作台
   壳层常驻、`phase` 不随 `open` 复位（第 3 条要求重开读回完成态），完成态原本只有
   「打开文件夹」→ 用户一次成功后发不起第二次，只能切回书架再进书。原型完成态 footer
   由「完成 + 打开文件夹」改为「再次下载 + 打开文件夹」（后者为主按钮），点击回表单并沿用
   目录/文件名/格式；「完成」不再单独出按钮（X/Esc/遮罩关闭口径不变）。

---

## style-settings.html 粘贴样本修订（c-style-paste-distill，2026-09-18）

蒸馏样本补第三路「直接粘贴文本」：量化空态主入口改为粘贴弹窗，确认卡补落卡基线预览。
本稿在 c-preview-reader 收编稿（style-settings-v2 终态）上做增量修订：

1. **量化空态改双入口**：原「去蒸馏我的文风」单按钮改为「粘贴文本蒸馏」（主，直开
   粘贴弹窗）＋「从文件/章节选样本」（次，进原样本选择页，沿用 `btn-open-distill`
   行为与 id——存量 e2e 按此断言）。粘贴成为第一入口：新书两路样本皆空时原入口是死路。
2. **样本选择页加粘贴入口**：样本框顶部加「直接粘贴文本」text-btn（`btn-open-paste`），
   与勾选两路并存，同一蒸馏管线。
3. **粘贴弹窗层**：词表逐字同 preview.html 弹窗底座（`.modal/.backdrop/.sheet`，宽
   560）；大 textarea＋实时去空白字数＋区间状态提示（不足报还差多少字／超限劝挑代表
   性段落，warn 语气；区间内 ok；区间外禁用提交）；不做硬截断——超限由提示＋禁用兜住。
   **打开态不入 parity 基线场景**；且 style-settings 屏本无像素 parity CASE（parity
   仅 list 屏三场景），门禁影响面＝design-lint 严格名单扫描（禁裸 hex/emoji）。
4. **确认卡补「落卡基线预览」**：作者画像之下、确认按钮之上，展示将要落卡的六行基线
   （行名＋「约 X（±容差%）」，与落卡后 `quant-baseline` 同构只读）；**锁定行如实显示
   将保留的上一版值并带「保留上一版」badge（empty 中性档）**——预览与落卡逐行一致，
   宁如实告知锁定行不更新，不做场景豁免。demo 数据：rhythm 行锁定保留 v2（52/22/16/7/3），
   其余行取新蒸值。
5. **确认卡补「取消，稍后再说」ghost**：原确认卡只有落卡/再学一次两出口，旧画像挂起时
   用户被锁死（粘贴成第一入口后「换样本重来」诉求变多）；新增第三出口＝收起面板保留
   draft，重进蒸馏可恢复确认卡。
6. **右栏蒸馏行 desc 补第三路**：「输入：novel-samples 或已归档章节」→「输入：粘贴文本、
   novel-samples 或已归档章节」（实现侧 `SettingsView.tsx` 同批改）。
7. **弹窗与字数为演示逻辑**：原型内联 JS 只做字数统计（码点口径）与区间提示演示；实现
   走 `Modal` 组件（wbStyle 版式）＋`StylePasteModal.tsx`，后端强校验为权威口径。

---

## storyline.html 卷视图整页落地（c-volume-view-storyline，2026-09-19）

设计源：`docs/design-c/drafts/storyline.html` 卷视图段（`volumeEditorHTML` 头部＋四页签
「卷纲｜本卷章节｜角色关系｜伏笔」、`volOutlineHTML` 两态卷纲、`volChaptersHTML` 本卷章节
台账、卷域投影 `relsHTML(0, order, false)`/`hooksHTML(0, order)`、右栏 `aiVolHTML`），
本稿入库为该屏事实源（同 #27 口径：drafts 目录、不入像素 parity 基线）。逐项偏差：

1. **章数目标编辑态保留可编辑输入**：原型编辑表单无此输入（total 恒承旧值，字段将永为
   「不设」），产品保留输入框；布局沿 c-workbench-outline-fixes ② 口径——标签单行、提示
   「1-9999，留空为不设」移输入框下方小字。
2. **卷域 AI 动作清单暂缺**：原型 `aiVolHTML` 四页签均渲染动作清单，本 change 右栏只落
   引导语＋统计卡，不渲染动作、无「规划中」占位（卷域动作需新端点，另行立项）。**原型该段
   领先于实现，勿按原型补卡**。
3. **装配全空返回空串**：原型 `volOutlineText` 全空返回占位符「（卷纲未填）」；产品返回
   空串以维持 prompt-sources「未填＝chars 0/empty=true」既有断言，占位语义由来源投影的
   未填标注承担。
4. **结构模板字面沿产品单源**：原型「起承转結」vs 产品枚举「起承転結」——沿产品单源不改字面。
5. **章工作台「信息差对齐」块退役**：该块（ChapterWorkspace 顶部只读块）消费本 change 退役的
   `info_gap_start/end` 与 `chapter_plans`，随字段换代整体退役（ADJUSTMENTS #14 的 parity
   gapless 桩同步处置）。
6. **book.html 卷纲面板段过时**：storyline 卷视图为其事实源；book 屏 parity 的 `volume`
   用例与 `book.volume.*.png` 基线下线（事实源转移登记）；如未来重录需先换 book.html 该段。
7. **卷域投影截至本卷末**：按原型 `relsHTML(0, order, false)`/`hooksHTML(0, order)` 截断语义
   实现；**伏笔归类标注（本卷埋下/本卷回收/跨卷悬置）与关系图例「截止本卷末」说明为原型外
   新增**（原型仅右栏统计，无页签内标注）。
8. **本机库首启留档重置＋备份 N-1 读窗/演练豁免**：无用户口径，schema 换代走既有留档
   doctrine（不做旧字段映射/迁移）；format_version 升 4，v0-v3 包卷纲段不承诺恢复；
   破坏性版本 N-1 恢复演练对本版豁免，验收＝留档断言＋新格式自身八层 roundtrip。
9. **待写口径取 frontier**：原型 `pendingInfo` 待写＝首个拟定章＋末端占位；产品取「首个未
   归档章（含草稿）」与排队门禁/写章 409 同源（非 frontier 章不可写，指向拟定章会误导）。
10. **卷名编辑入口移入卷纲编辑表单**：原型 `v-name` 即如此；树上铅笔改名维持（两入口同写
    一列，不冲突）。
11. **标准正文随批登记**：`docs/ux/design-language.html` 的 SubTable 范式示例（卷纲四子表）
    随字段换代失去实体——示例待标准正文下一版更新为「行集（登场人物/剧情节点）＋一行一条」
    口径；本 change 不改标准正文。
12. **右栏统计卡窄列折行修正（上线后实测）**：`.rail-stats` 两列网格在右栏实宽下标签折行
    （「章数目标」折成「章数目／标」，与 QA ② 同款观感；playwright 实测标签高 38.75px＝两行）
    ——`.k/.v` 补 `white-space: nowrap`＋`li` 加 `align-items: baseline`（book.css 业务层；
    该族为章/卷模式共用，章模式同宽度下同样受益）。原型右栏较宽不出现此象，属实现宽度差。
    另实测四页签 centerY 全等（179.5），胶囊「下沉」为底色＋字重视觉错觉，不修。
13. **中栏/右栏视觉语言整体对齐 storyline（用户 09-19 验收指出卷/章布局均不一致）**：初版
    实施错在「映射到 app 现役组件族」（白卡片＋折叠卡＋胶囊页签），与原型编辑器的平面
    编辑语言不符。本次整体换肤（类名保留、视觉替换，e2e 选择器零破坏）：中栏去卡片
    （col-panel/panel 画布化）、头部改 e-head（kicker＋display 大标题＋tag 徽章 meta，章视图
    补 kicker=卷全标签＋状态/字数徽章）、页签改下划线式（.chtab 选中绿字＋2px 底线，计数徽标
    缩为 mono 小字）、分组改 cfgset 语言（＋/－ 标记＋分隔线，.cfg 类名保留）、卷纲查看态
    fro 行式字段/fgrid/ledger 台账（lrow·lname·lstate）/node·stg 节点/pos-line em-b 结构/
    flist 圆点列表；右栏改 aiShell 语言（AI 助手＋PRO 徽章＋当前页签 chip＋白卡 2×2 统计
    ［.rail-stats 类名保留重绘］＋ai-foot 免费版说明；章模式同头）。**app 保留项（原型未画）**：
    editor-toolbar 字号/行距/专注/版本历史/归档控件降为工具条右对齐保留，专注模式隐藏规则
    随 .col-ai 新样式补特异性。editor 皮肤其余页签（OgPane 表单等）经 .cfg 作用域重绘自动对齐。
14. **编辑表单统一（同批续）**：卷纲编辑态初版残留旧 .field/.tpl-row/.sub-row 结构，与章纲
    编辑（olFormHTML）不一致——原型两编辑态本就是同一套语言。统一：卷名/结构模板入
    .fgrid、章数目标独立 fro（提示下移，沿偏差①）、主旨/剧情三字段/伏笔两块改 fro（mono
    标签＋req/em）；登场人物/剧情节点行改 rowx（序号＋cols.c3/.cn＋xbtn）、添加改 edit-bar
    （＋ 加一行人物／＋ 加一个节点）；章纲 OgPane 等 .field 经作用域 CSS 就地获得 fro 语言
    （结构不动）；控件补 aria-label（em 替换 label 后可访问名保持）。

---

## list.html 书架屏换代：四态＋完本链路（c-works-finish-flow，2026-09-19）

设计源：`docs/design-c/drafts/works.html`（2026-09-17）晋级为 `prototypes/list.html` 基线
换代（books/empty/quota 场景数据扩四态、新增 finish 弹窗场景；drafts 原样留存）。原型并入
`.b.ready`（accent 底待完本徽标）、`.foot-acts`（回看＋完本动作组）、`fin-*` 完本清单弹窗
家族、待完本提示条（`#readySlot`）；SEED_BOOKS 与 parity PROTO_BOOKS 同步四态
（写作中/待完本/设定中/已完结）。逐项偏差：

1. **「已归档」标签退役、`done` 语义更名已完结**：全归档未完结＝`ready` 待完本（原型
   works.html 口径）；完结需要完本动作落库（`novels.finished_at`＋finish/reopen 端点）。
2. **「全书收尾后台跑」文案对齐现实**：书级收尾后台任务不建（另行立项）——完结 toast 与
   弹窗③行改为「归档收尾提案可在书的『操作』页逐条确认」（章级 archive-reconcile 既有
   机制）；原型 works.html 的后台叙事不照搬。
3. **伏笔「留白」勾选不落库**：弹窗内 useState 辅助确认（重开重置），SHALL NOT 写伏笔表
   （「故意留白≠弃坑」的持久语义待书级收尾专项定夺）；落库后的行级形态（fin-hook.on）
   原型已备，实现侧后续启用零视觉差。parity finish 场景按空 hooks（第二行 ok 形态）采样。
4. **⋯ 菜单保留＋已完结书补「完本信息 · 撤完本」入口**：原型无卡片菜单也无撤完本入口
   （演示稿程序可达）——产品保留重命名/删除菜单，并为已完结书加弹窗入口（应用侧扩展，
   不入 parity 图，沿本簿既有口径）。
5. **待完本提示条「知道了」＝会话内按书记忆**：不落 localStorage——提示条语义是「当期可
   办的事」，持久关闭会错过后续第二本待完本；完结或关闭后顺延提示下一条（排序最前）。
6. **卡片排序仍按 updated_at 倒排**：原型 SEED 顺序为演示摆位；产品排序不变，parity 注入
   数据按排序结论摆位（写作中 2 小时前→待完本 昨天→设定中 昨天→已完结 3 天前）。
7. **待完本卡本体点击落写作（不落预览）**：预览由页脚「回看/查看」显式进入（一次性
   location state 落点覆盖，认领即清防刷新重放）；与「卡片标签与落点同结论」口径一致。
8. **Banner 群（权益/试用/满额）不入 parity 图**：quota 场景只比额度墙＋锁卡（既有口径
   延续）；待完本提示条**入图**（books/finish 场景，原型已建模）。
9. **更新提示条文案沿 stub 字面**：list.html 的 update-strip 保留「发现新版本 v0.13（当前
   v0.11）·提升章纲 AI 起草的稳定性」（stubUpdateNotice 同文案打桩，既有 #15 口径）；
   works.html 草稿里的 v0.19 文案为演示字面，不采用。
10. **完本弹窗伏笔行数据源**：`hooksApi.list` 过滤 active＋卷章树换算「第 N 章埋下」（原型
    SEED 的 `from: N` 字面量在产品里由 introduced_chapter_id→章号映射得出，映射缺失显示
    「埋下章未定」）。
11. **lint 存量不随批**：`design:lint` 的严格范围违规（preview.html / AcctMenu.tsx 裸 hex）
    为 main 存量（本 change 前已红），不随批处置、不阻断本换代（parity 四场景全绿）。

---

## login.html 登录屏立卷（c-loginless-data-exit，2026-09-19）

**补历史欠账＋新增建模**：登录屏此前从未有原型基线（LoginPage.tsx 无基线直跑），本稿收编
现状 auth-card 形态并新增 UpgradeGate 两场景与免登备份入口（2026-09-19 事故直接对策）。

1. **s1 常规登录**为现状收编（parity 首立以 s1 为界）；新增常驻「不登录也能备份作品」
   text-btn（数据出口不设墙——任何登录态可备份）。
2. **升级卡两场景分档**（s2 需要更新/s3 暂时无法登录）：首答句「你的作品都在这台电脑上」
   ＋可核对计数为情绪主角；主按钮=去下载新版/重试登录，「先备份作品」恒 secondary
   （恐慌由证据化解，不由按钮排序放大）；「版本过旧」全站禁用（challenge 缺失是模糊信号，
   禁止断言客户端版本——事故文案误导根因修正）；s2 空库变体文案行一并立卷。
3. **s4 免登备份弹窗**借 backup-restore 屏 .bk-* 家族口径：无配置开关（服务端强制
   include_config=false，UI 只留静态说明「登录后可一并备份」）；step-tag/zip 预览/
   pick-row 与屏 2 同构，弹窗后三步（进度/完成/失败）复用该屏不另立段。
4. 实现侧 LoginForm 语言不引入工作台 storyline 词汇（e-head/cfgset 等）——登录页非
   工作台语境，防语言越界。

---

## 整书拆纲原型：不走 parity 基线（c-volume-plan-ai，2026-09-20）

`docs/design-c/drafts/ai-novel-c端-整书拆纲.html`（六态可点原型，44 个 data-od-id）为
**交互定稿原型**，本 change 明确**不纳入像素 parity 基线**，理由：

1. 规划台是**弹窗式聚焦页**（Modal 家族），parity 截图工具以整页为界，弹窗态无整页
   基线可比；且生成进度分「弹窗内进度／回填进度」两段，非静态版式。
2. 右栏三态（验证面板／空书规划入口／接着往下规划＋卷的验证）与数据强相关（体检报告、
   分卷依据缺口），stub 数据会双份维护，收益低于组件测试（volumePlan.test.tsx 已盖
   三态与报告渲染）。
3. 原型中栏「起手卡／落点卡」文案在评审中改为作家口径（本书怎么开始？／开始写第一章？），
   实现以 spec 为准、原型不再回改——按「原型=定稿输入，spec=权威字面」口径处理。

设计门禁：`design:lint` 通过（新增 pv-* 类不触严格范围）；本 change 无 parity 场景新增。
5. **（09-21 追加）弹窗壳与按钮类映射**：弹窗用产品 Modal 封装（.mcard.wb-style，680 宽）而非
   原型 .modal/.sheet——C端 弹窗纪律（portal 到 body、防 daisyUI 事故）；内部件类名逐件对齐原型
   （plan-anchor/pa-*、cfgset、dep-row、plan-label、cand 族、genbox/ex-steps、rp-族、plan-foot）。
   原型 `.btn-accent` 映射产品 `.btn-primary`（产品无 accent 档）。portal 弹窗脱离 .wb 作用域，
   表单控件样式在 base.css `.mcard.wb-style` 补一份（与 .wb 同源）。
6. **（09-21 追加）体检报告不带「让 AI 改」按钮**：原型 warn 行带 sc-fix，产品按 spec 口径
   「体检只给判断与定位、不代笔」省略；报告行渲染对齐原型 rp-row（状态点＋结论＋evidence）。
7. **（09-21 追加）卷数行**：原型首卷锚点静态「大约 4 卷」；产品在首次「给我 3 套方案」后才带回
   volume_estimate（明示假设），之前显示引导占位。进场锚点走后端 plan-anchor 单源（事实优先）。

## 版权行加经营主体（© 主体口径统一，2026-09-21）

法定主体「星纬（海口）投资有限公司」进版权行：brand/brand.json 新增 `company` 键
（经营主体单源），两端版权行派生改为「©年 + 主体 + 品牌」——S端 `brandCopyright()`
= ©年+主体+组合名、C端 `copyrightLine` = ©年+主体+name（各自形状不变，仅前置主体）。
Windows 发布者同批对齐（build.spec 读同一 company 键烘版本资源；installer.iss 的
MyAppPublisher 是 Inno 读不了 JSON 的唯一手写字面量副本）。原型同步 6 处 © 行：
list/book/model-config/preview 状态条＋backup-restore pagefoot（旧版式）＋home 落地
页脚；index.html 的「© 爱小说 · 界面重设计 v2」是设计稿 meta 落款、非产品 UI，不改。
对应 e2e 断言同批钉住主体名（statusbar.spec / landing.spec）。

---

## c-volume-antagonist 原型先行（2026-09-21 二稿：五问页重构，旧结构丢弃）

用户审稿指出首版是「旧弹窗＋贴字段」——病根：卷名打头（违背「卷名最后起」）、章数混进创作
问题、五问散在卷纲而非问的时候就在。二稿按「一卷的规划＝回答五个问题」重构：

1. **draft：规划台重做为五问页**（`#plan-desk` 整段重写）——五问依次为 fro 段（序号 qno 高亮）：
   ①讲什么（可空，下挂「没想法？让 AI 给 3 套方案」）②主要冲突 ③这一卷的坎（类型＋一句话，
   新面孔即时提示建卡）④这一卷有哪些角色（cast-row 行集：名字＋作用，可增删、可加新人）
   ⑤卷末收在哪里。底部两动作：**「让 AI 铺完剩下的问题」**（主，PRO——作家答过的它不改，
   只铺空着的；全空＝按设定自由推）与**「直接创建这一卷」**（次，免费——答多少建多少）。
   卷名与章数不在此页（卷名最后起；章数进卷纲）。
2. **draft：入口统一**——手动「＋ 新增一卷」（起手卡/左栏/顶栏三处）与 AI「规划第N卷」打开
   **同一个五问规划台**；独立「添加卷」弹窗（av-modal）**删除**；manual-vol→openPlan。
3. **draft：pick 选方案＝五问全预填**（spine/conflict/ant 拆类型与句/cast/ending）后自动展开；
   生成完成态清单与作家在 Q4 已填行合并去重（AI 只补缺）；genbox 依据文案四态
   （选的方案/你写的那句/你的全书设定）。VOL2 演示数据补 ant/cast（难题型＋两角色）。
4. **book.html：添加卷弹窗按五问序重排**——五问在前（新增第 4 问「这一卷有哪些角色」
   textarea 一行一个），卷名与初始章数降级到底部虚线区（vol-tail 两列；卷名可空兜底
   「第N卷」，label 注「最后起」）；confirm 卷名兜底＋存 cast。原「卷名必填打头＋章数平铺」
   的旧序废弃。
5. 保留项：锚点材料块、分卷依据台账、七条规则、plan-foot（先不规划/关掉/回填）、
   落点卡概要行、回填 11 段序、体检对抗物判据条——均沿用首版已落的形态。
6. **draft：付费＝三选一抽卡弹窗（roguelike 式，用户 09-21 终拍板）**——点右侧「规划第N卷」
   直接弹 **#pick-modal**（940 宽）：**三卡横排**（pick-grid 三列，窄屏纵排），每卡＝五个问题的
   完整答案且三卡互异——只摆对后续章纲/正文生成有帮助的字段：主要冲突／这一卷的坎（类型+是谁）／
   角色（谁登场·作用）／卷末，卡头=侧重轴 pill＋走向大字。点卡选中（描边高亮）→「确认这一套，
   成卷 →」→ 1.2s 铺 → 弹窗关、卷纲直接落库（demo：卷名/章数取 AI 建议、角色进登场人物行集）
   → 落点卡承接。**没有中间编辑步骤**——想改进卷纲再改。底部「↻ 都不满意？换 3 套」重抽
   （PLANS_ALT 首卷备选组，实现侧重调 options 换温度）＋「自己答五个问题」出口（切五问页）。
   免费打开无抽卡、直接五问手写页；规划台内嵌的纵列方案卡退役（plansHTML 置空，三卡前移弹窗）。
7. **draft：卷页布局随字段瘦身重设计（四问一页纸）**——查看态撤全部折叠块（cfgset）：
   进场（只读）→ 四问四行（qno 编号：1 讲什么／2 主要冲突／3 这一位的坎／4 卷末收在哪里，
   与抽卡卡同骨架——卡上选的答案翻开卷就是这四行）→ 两列小区（角色聚合只读｜伏笔与披露
   摘要）→ 留到写的时候 → 进度线 → 排第一章。编辑态同骨架同序（四问编号段标＋卷名/章数＋
   聚合角色＋伏笔）；FORM_BLOCKS 按问序重排。旧「卷基础信息/本卷剧情」分组容器退役。
8. 实现侧（apply 批次）对应：AddVolumeModal 与规划台 VolumePlanModal 合并为四问版式
   （或共用五问区块组件）；付费默认首屏自动调 options（抽卡），免费为空白五问；
   `design:check` 在实现跟上前**预期红**（基线弹窗已五问化）。

复用纪律：新类仅 qno/vol-tail（序号色与两列布局）；五问复用 fro/em/note，行集复用
cast-row，坎行复用 hurdle-row；色彩与组件零新形态。
## c-volume-antagonist 原型先行（2026-09-21，五处新形态）

### 终版落地核对（c-volume-antagonist apply，2026-09-21）

设计与实现逐条对齐（本段是**终态**，与上面二稿条目冲突处以本段为准）：

1. **四问（不是五问）**：`这一卷有哪些角色` 一问**退役**——角色是「写出来的，不是规划出来的」；
   卷页角色改成**聚合只读**（卷下各章章纲 characters 合集＋主角置顶＋坎命中标反派）。
   规划台/抽卡卡/卷页三处同骨架：①讲什么 ②主要冲突 ③这一卷的坎（类型＋一句话）④卷末收在哪里。
2. **抽卡弹窗（付费默认）**：`PickCardsModal` 940 宽三卡横排，卡面＝四问答案＋侧重轴 pill；
   点卡选中 →「确认这一套，成卷 →」→ expand 落库 → 落点卡承接；「↻ 都不满意？换 3 套」重抽；
   「自己答四个问题」切四问页（已答保留）；写请求发出前 Esc/背景＝取消不落库（token 守卫）。
   原型三卡里的「角色」行不渲染（随角色一问退役）。
3. **四问手写页（免费默认）**：`VolumePlanModal` 四问＋「让 AI 铺完剩下的问题」（PRO，答过的不改）
   ＋「直接创建这一卷」（免费，答多少建多少）；卷名兜底「第N卷」、章数不在本页。
4. **卷页四问一页纸**：查看态无折叠块（进场→四问四行→角色聚合→伏笔指引→节点有值才显→留到写
   →进度线）；编辑态同序（四问编号＋卷名/章数＋聚合只读＋节点）。旧「卷基础信息/本卷剧情」
   分组容器、结构模板、整体目标、埋设/揭露 textarea 全部退役。
5. **伏笔归台账**：卷页不再手写伏笔——只留一行指引「住在台账里，切「伏笔」页签看与办」；
   规划台产出的伏笔建议经 `POST /hooks/batch` 入册（服务端 difflib≥0.6 查重，重复给对齐编号）。
6. **AddVolumeModal 退役**：组件已删（`workbench/modals.tsx`）；三处空书入口＋树头「＋」统一接
   规划流（按档分流：付费抽卡／免费四问页）；「初始章数」字段随之退役（落点卡「排第一章」逐章排）。
7. **退役字段**：`template_name/plan_line/goal/volume_cast_members 行集/plants/reveals` 停读停写；
   PUT 带这些键 **422 拒收**；GET 不回；旧卷 `goal` 由服务端并进 `ending` 尾句显示（不丢内容）。
   列/表的物理清理另立项（todo 已登记，属破坏性 schema 变更）。
8. **design:check**：book.html 的添加卷弹窗段与实现同批改到四问版式；parity CASES 不含该弹窗与
   卷纲屏（卷屏事实源早已转 storyline.html），故 parity 不受影响；design:lint 词汇门禁随批次跑。

---

## 三页签回默认主页＋卷页签右栏＋抽卡「上接」（c-write-home-rail-anchor，2026-09-22）

设计源：`drafts/storyline.html` 卷选中态右栏段（`aiVolHTML`）＋ `drafts/ai-novel-c端-整书拆纲.html`
（抽卡卡片 `pickCardsHTML`、默认页段）。两份稿件同属 drafts 目录、**不进像素 parity 基线**（同 #27 口径）。
本 change 同时改实现（`client/frontend`）与这两段原型，逐项：

1. **卷选中态右栏由「四页签统计卡＋卷域动作清单」收窄为「验证面板随页签」**：storyline 稿 `aiVolHTML`
   原四分支渲染统计卡与动作清单（动作无端点、从未落地，见上「卷域 AI 动作清单暂缺」条），本稿按
   `volume-plan-ai` 既有口径收窄——「当前页签」显示真实页签名（卷纲／本卷章节／角色关系／伏笔）、
   引导语随页签、体检报告三组按页签前置、卷纲页签另给「重新规划这一卷（AI）」。**不复活统计卡与动作清单**。
   为收窄所加：`AI_VOL_TAB_NAME`（`outline` 在卷页签叫「卷纲」，章页签才叫「章纲」）＋`aiShell(tab,lead,body,tabName)`
   可选形参＋rp-* 报告类搬入。
2. **抽卡卡片自带上接**：拆纲稿 `pickCardsHTML` 每张 `.pick-card` 卡首插一行 `.pk-row.pk-in`
   （`enterText()` 单源：第二卷起＝上一卷的结尾、首卷＝起点），两行截断（新增 `.pk-in` 截断规则）＋`title` 全文；
   `data-od-id="pick-enter-*"`。实现侧同款落在 `PickCardsModal`（组件内 `useAnchor` 取 `plan-anchor`）。
3. **书主页卡（写作默认页第三态）**：拆纲稿原只有「① 空书起手卡」与「④ 落点卡」，本稿补 `homeCardHTML`
   ＋ demo ⑦；落点卡同批补「＋ 新增一卷」——三态恒有建书入口。实现侧类名角色沿产品既有三态
   （`.be-k` 眉标 / `.be-t` 主句 / `.be-desc` 说明 / `.be-acts` 动作），与原型自有 `.be-mark` 不同名不同层，
   **不为新卡引入未登记类**。
4. **设定与预览的回默认只改落点、不改版式**：设定重复点「设定」拨回默认面板（第一项「简介」）、
   预览定档一律落首章（不再继承写作页当前章）——两处无新版式，故两份原型未改版式段；
   行为口径以 `workbench` / `preview-reader` spec 为准。
5. **基线换基说明（2026-09-22）**：本 change 首版分支切自 c-volume-antagonist（#458）之前；#458 重写规划台后
   本稿把三件事重新落到 origin/main（卡面由 `cand` 族改落 `pick-card` 族、建卷统一走规划流、
   「添加卷」独立弹窗退役）——两段原型与实现同批对齐，`prototypes/book.html` 与全部 parity 基线**不动**。
6. **验证**：两份稿件脚本 `node --check` 通过；Playwright 走查零 JS 报错（卷四页签的「当前页签／组序／动作」
   与抽卡卡片「上接」文本均按预期渲染）。

7. **（09-22 追加）入口分叉：加号＝手填页，抽卡只在右栏**（用户拍板）：各处「＋ 新增一卷」（顶栏空书卡／
   中栏起手卡／中栏落点卡／中栏书主页卡／左栏底部／树头「＋」）SHALL 恒进**四问手写页**，让作家填空、
   **不分档位**；三选一抽卡 SHALL 只从右栏「规划第N卷（AI）」进（该入口仍按档分流：付费＝抽卡、免费＝四问页）。
   原型：拆纲稿 `openPlan(n, manual)` 加 manual 参数、`manual-vol` 传 true；实现：`useVolumePlan.open(volNo, isPro, mode)`，
   `NovelWorkspace` 拆 `openPlanVolumeManual`（加号）与 `openPlanVolume`（右栏 AI）。

8. **（09-22 追加）手动入口的手写页 SHALL NOT 出现 AI 动作**（用户拍板）：加号（各处「＋ 新增一卷」）
   打开的四问手写页只留「直接创建这一卷」，**不出现「让 AI 铺完剩下的问题」**；四问提示文案不承诺
   「答不出的交给 AI」，改为一句指向右栏 AI 入口的说明（「想让 AI 铺空缺：用右侧 AI 助手的『规划第N卷（AI）』」）。
   右栏 AI 入口打开的手写页（免费档）**保留**铺空缺按钮与 PRO 说明（那是 AI 链路的唯一可达页）。
   原型：拆纲稿 `state.manual` ＋ desk 动作条件渲染；实现：`useVolumePlan.state.openMode` ＋
   `VolumePlanModal` 的 `manual` 分支。
