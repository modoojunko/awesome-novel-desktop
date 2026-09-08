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
