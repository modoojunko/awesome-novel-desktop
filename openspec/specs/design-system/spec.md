# design-system Specification

## Purpose

Single source of truth for product-wide visual vocabulary across both frontends (C-end React SPA in `client/frontend`, S-end Vue console in `server/frontend`), so every UI-touching change reuses the same tokens, status language, component roles and destructive-action rules instead of inventing local variants. Authoritative detail lives in `docs/ux/design-language.html` (state language, terminology) and `docs/ux/cross-end.html` (three-layer contract, drift rulings, migration map); this spec holds the enforceable requirements.

## Requirements

### Requirement: One shared token palette and theme
- Both frontends SHALL use one light theme built on identical oklch tokens (`--bg`, `--surface`, `--fg`, `--muted`, `--border`, `--accent`, `--accent-strong`, `--accent-soft`, `--ok`/`--ok-soft`, `--warn`/`--warn-soft`, `--err`/`--err-soft`, `--fg-soft`) declared in each end's `src/design/base.css`; token drift between ends is a defect.
- The default accent SHALL remain teal (`--accent: oklch(48% 0.11 170)`, `--accent-strong: oklch(41% 0.10 170)`); user-selectable accent themes (catalog defined in the `theme-preferences` capability) SHALL be expressed only through a shared `:root[data-theme="<key>"]` override layer that redefines `--accent`/`--accent-strong` (soft variants keep deriving via `color-mix`), located inside the `@cross` shared segment in both frontends.
- Text on accent or dark surfaces SHALL use an explicit foreground token, never a borrowed surface or background token.
- Derived soft variants SHALL be produced with `color-mix(in oklch, …, transparent)`; raw hex/rgb literals are forbidden in either end's source.
- Status colors follow N6: red (`--err`) means irreversible-or-immediate actions only; cautionary-but-safe content uses `--warn` or accent.
- Introducing or retiring an accent hue — default or theme — SHALL be registered in the ux standard doc (`docs/ux/cross-end.html`) 色相登记簿 in the same batch as the token change; the registry tracks the theme catalog as a set, not a single brand hue.

#### Scenario: Same warning surface in either console
- Given a screen needs a persistent cautionary notice
- When it is styled
- Then it uses the warn soft background through the notice family and not red

#### Scenario: Accent renders as ink on both ends
- Given any screen on either frontend renders an accent element (primary button, logo mark, accent pill, breathing dot) under `data-theme="ink"`
- When its computed accent color is read
- Then it resolves to the ink hue oklch(37% 0.01 250) on both ends, and no theme override exists outside the shared `@cross` segment

#### Scenario: Default teal is untouched
- Given both frontends render without a `data-theme` attribute
- When accent color is computed
- Then it resolves to oklch(48% 0.11 170), identical to the pre-theme-system baseline
### Requirement: Shared status language and tone words
- Progress-bearing objects SHALL express state through the three-state dot classes (`dot-empty`, `dot-warn`, `dot-ok`) plus a title attribute wherever progress semantics exist.
- Evidence-bearing chapter rows in the reading preview (目录行) SHALL NOT use the three-state dot; they SHALL express 成稿状态 through the `.pill` status family with the labels 拟定 / 草稿 / 已归档, plus a word-count number in the mono/tabular style. 章纲 gap detail stays in the writing view.
- Badges SHALL use the `.pill` family (roles tag/status/count x tones); callout bars SHALL use the `.notice` family with explicit modifiers; toast severity may add `warn`.
- The cross-end tone vocabulary is fixed at info / ok / warn / err. Retired synonyms (success/danger as notice or badge tones, the `.b` badge names, `.strip`) MUST NOT reappear. The save-state ladder remains autosaving, unsaved, failed-with-retry, saved.
- Streaming/AI activity SHALL be expressed by a breathing accent dot; prose layout MUST NOT animate during streaming.

#### Scenario: Same object viewed twice
- Given a chapter with a fixed 成稿状态 (无正文 / 有正文未归档 / 已归档)
- When the preview view lists that chapter
- Then the 目录行 shows the matching `.pill` status label (拟定 / 草稿 / 已归档) derived from the same chapter data, with the word count in mono/tabular style — never a three-state dot

#### Scenario: S端 console uses unified badge and notice vocabulary
- Given any S端 console, auth or landing screen needs a badge or a callout bar
- When the page renders
- Then badges use `.pill` role × tone classes and callout bars use `.notice` with an explicit tone, and no `.b` or `.strip` class remains in S端 source or rendered DOM
### Requirement: Prototype-first flow with per-end gates
- Any user-visible C-end change SHALL update `docs/design-c/prototypes/<screen>.html` and record deviations in `docs/design-c/prototypes/ADJUSTMENTS.md` before implementation, and SHALL pass `npm run design:check` under 0.2% pixel difference per baseline scenario.
- S-end changes have no prototype baseline; they SHALL provide before/after screenshot pairs inside the change folder as consistency evidence.
- Vocabulary edits SHALL land in both ends' `scripts/design-vocab.mjs` in the same batch, derived from the standard doc (`docs/ux/design-language.html`), so the doc and the whitelists never diverge.

#### Scenario: Deviating spacing needs registration
- Given an implementation keeps a denser rhythm than the default spacing scale
- When reviewed
- Then ADJUSTMENTS.md documents the deviation and its reason, or the change is rejected
### Requirement: Component vocabulary reuse before invention
- Buttons SHALL map to the existing `.btn` size/variant ladder; C-end wrappers around it MUST NOT be introduced, and S-end shell components SHALL compile down to those same classes.
- Static capsules belong to pill roles (tag/status/count); clickable capsule-like controls belong to the chip family.
- File-format checkbox rows in the download overlay (`.ex-fmt`) SHALL be a single reusable control (role=checkbox semantics, visible selected state) rather than ad-hoc toggle markup, and its selected state SHALL use token-derived color-mix values only.
- Progress lists in task overlays (`.ex-steps`) SHALL express per-item state as text (等待 / 下载中 / 完成) with the ok tone reserved for the completed state; they MUST NOT animate prose or the reading area.
- Destructive confirmations SHALL render through an in-app modal confirm (no native `window.confirm`), listing affected items as inventory when deletion cascades.
- Empty states SHALL offer at least one actionable exit alongside the descriptive line.

#### Scenario: Delete affecting linked content
- Given deleting a config that books depend on
- When the user confirms
- Then an in-app dialog lists the affected items as inventory chips before deletion executes

#### Scenario: 格式勾选行即统一控件
- Given 下载成稿弹层渲染三种格式
- When 用户点选其中一行
- Then 该行呈现选中态（token 派生配色）且可键盘操作，另两行保持未选态
### Requirement: Cross-end shared-class synchronization
- Classes that must render identically — tokens block (including `--on-accent`), `.btn` ladder, modal family, form base and error states, toast (including the `warn` tone), notices (`.notice` with explicit `info/ok/warn/err` tones), pills (`.pill` role × tone family), skeleton atoms (`.sk` + `sk-pulse`), panel cards (`.panel` + `hoverable/hl/compact`), empty-state slots — SHALL exist under the same name with the same declarations in both ends' `src/design/base.css`, inside a `@cross-begin/@cross-end` marked segment.
- The `@cross-begin/@cross-end` markers and the validation script `scripts/design-cross.mjs` (repo root) SHALL exist; both ends' `package.json` SHALL expose it as `design:cross`.
- When legal values diverge between ends, the parity-gated C-end value wins unless the change registers a reasoned deviation.
- The validation script SHALL fail on single-side drift of the shared segment, and icon registries' common keys SHALL have identical path data.

#### Scenario: One snippet, two apps
- Given an HTML fragment using shared classes
- When pasted into a C-end screen and an S-end screen
- Then the rendered results match apart from font fallbacks

#### Scenario: Single-side drift fails validation
- Given one end edits a shared-class declaration alone
- When the cross check runs
- Then it exits non-zero naming the divergent selector

#### Scenario: Shared segment baseline is zero-diff
- Given the change that establishes the markers has landed
- When `design:cross` runs on both ends
- Then the marked segments are byte-identical after whitespace normalization
### Requirement: Free vs PRO gating stays visible
- PRO-only capabilities SHALL keep their entry points visible to free users in locked form with one sentence describing what unlocking provides; hiding entries is the documented exception requiring compensating notice.
- Gating vocabulary in UI text SHALL avoid internal terms (gate/readiness/license errors); it describes what is missing and how to proceed.

#### Scenario: Free hits project limit
- Given a free account already has the maximum number of projects
- When they view the shelf
- Then create/import appear locked with an upgrade path rather than being hidden
### Requirement: AI 写作助手卡片与结果区组件词汇
- 「AI 写作助手」卡片组件（C端设定视图右栏）保持不变：PRO 徽标并入卡片头部＋标题＋一行套餐归属/只加工不代写；内部为**并列能力行**（每行＝名称上＋描述下从属＋右侧箭头，整行可点）；底部一条来源/去向声明。命名 `.rail-assist` + `.ra-*`。
- AI 结果呈现 SHALL 统一为**「AI 出卡确认弹窗」**：复用全局弹窗壳（`design/Modal`）与写作域既有弹窗词汇，右栏能力行点击后结果进弹窗、弹窗内确认才写回、关闭即弃。**`.ai-sink` / `.aiz-*` 内嵌结果区词汇自本 change 起退役**，SHALL NOT 再作为设定域 AI 结果的渲染面；体检检查行沿各域既有 `chk-*`（角色页 `chk-row`）词汇**重挂**到弹窗卡体容器（Modal portal 到 body，`.settings-v .ai-sink` 前缀不再命中，词汇定义本身不变、只换挂载作用域）。
- 弹窗四种卡形（不新增视觉词汇定义，逐一对齐写作域既有实现）：**文本卡**（内容＋「换一个」＋按域确认键）／**体检报告卡**（检查行列表＋「关闭」「重新检查」，无采纳键）／**候选勾选卡**（候选行可勾选＋「采纳」）／**结构化卡**（kv 行/势力行/逐格 diff 沿各域既有行词汇）。四卡形 footer 骨架统一＝次级「关闭」＋主行动键（按域文案）＋可选「换一个」；生成中 footer 隐藏主行动、占位常显。
- **生成中关闭的保护口径**：生成中（running 态）允许关闭弹窗，最近一次生成结果 SHALL 缓存在面板 state；重开同一能力行 SHALL 直接展示缓存结果、不再发请求、不重复计 usage；「换一个」才重新生成。生成尚未返回即关闭＝放弃该次结果（请求在途自然丢弃），不弹挽留。
- **版数计数**：文本卡 SHALL 显示已生成版数（「第 N 版」，从 1 起、每次「换一个」递增）；「换一个」在途期间旧版 SHALL 保持可读可采纳，新版到达后替换。
- 生成中弹窗 SHALL 有进行中占位（prog 语气、aria-busy），占位 SHALL 附「AI 创作中，请勿关闭弹窗」提示行（c-ai-modal-no-close-tip：全 AI 弹窗统一、创作类用「AI 创作中」，盘点/检查/推演等非创作类按实义动词；只作文案提醒，不改变上方可关闭口径）；失败 SHALL 给可读提示＋可点击出口，动词单源：生成类失败＝「重试」、体检类＝「重新检查」；确认写回后 SHALL 沿既有回执一步撤销（ChangeReceipt）词汇。
- 这些是 **C端局部组件**（不在两端共享 `base.css` 共享段），归 C端工作台设定视图作用域（`book.css` 或设定视图局部样式）；只复用共享令牌，不新增全局 token、不新增状态档位/胶囊形态/字号档位。
- 能力行在无套餐时 SHALL 复用既有「可见 + 锁定」门控（见 Requirement: Free vs PRO gating stays visible）：整卡降透明、徽标转灰、行降透明 + cursor:not-allowed，点击给统一升级提示，不各自弹窗；锁定态卡片名 `.rail-assist.locked`。门控 key 用已登记的 `settings-ai-fields`（memberOnly），而非未登记的新 key。

#### Scenario: 结果区不用可编辑底色
- Given 简介/题材 AI 反馈已产出（弹窗卡内呈现）
- When 查看弹窗卡内容区样式
- Then 内容为 fg-soft 只读底、无输入控件（不误判可编辑）；写回只经弹窗确认键，与可编辑表单区（surface）可区分

#### Scenario: 结果在弹窗确认后才写回
- Given 简介 AI 补缺失已出候选
- When 弹窗内点确认
- Then 建议写回对应控件；未点确认直接关闭弹窗则不写回任何内容

#### Scenario: 体检报告卡无采纳
- Given 任一设定域体检已出报告
- When 查看体检报告卡
- Then 卡内为只读检查行列表＋「关闭」「重新检查」，无写回控件

#### Scenario: 弹窗内换一个重新生成
- Given 文本卡已出一版结果（显示「第 1 版」）
- When 点「换一个」
- Then 弹窗内就地重新生成并替换当前内容（版数递增为「第 2 版」），无历史条切换 UI；「换一个」在途期间旧版保持可读、可采纳

#### Scenario: 生成中关闭后重开不重复计费
- Given 主线起草这类长文生成进行中（30 秒级）
- When 作者误按 Esc 关闭弹窗，随后再点同一能力行
- Then 弹窗直接展示已缓存的那次结果（不再发请求、不重复计 usage）；点「换一个」才重新生成

#### Scenario: 生成未返回即关闭＝放弃
- Given 生成请求在途且尚未返回
- When 作者关闭弹窗
- Then 不弹挽留；该次结果放弃（在途响应被丢弃），面板与表单无残留

#### Scenario: 能力行锁定态可见且不可点
- Given 无套餐用户
- When 查看 AI 写作助手卡片
- Then 能力行名称/描述可见、整体降透明、点击给升级提示且不产出结果

### Requirement: 角色页的状态与体检行词汇

角色设定页 SHALL 只使用既有状态语言与组件词汇，新增的状态与行型 SHALL 按下述口径登记：

- 角色类型（主角 / 配角 / 反派 / 路人）SHALL 作为可点击胶囊复用既有 chip 家族（`.chip` + `.chip.on`），SHALL NOT 另造胶囊类名。
- 人物关系的类型标签 SHALL 复用既有状态胶囊（`.pill` + 既有语气档），SHALL NOT 另造胶囊类名。
- 徽标 SHALL 只用既有档位 `ok / warn / prog / empty`；「已确认」SHALL 用 `ok`（绿）且其文案 SHALL NOT 与其他状态混用。
- 保存态 SHALL 复用既有四态（saving / saved / dirty / failed），失败态 SHALL 给可点击的重试出口。
- 体检（一致性检查）逐项行在角色页 SHALL 使用独立类名（`.chk-row`：名称与结论一行、依据一行），SHALL NOT 覆盖既有 `.chk-line` 的样式作用域；体检结果 SHALL 落在「AI 出卡确认弹窗」的体检报告卡内（`.ai-sink` 已退役）。
- 体检结论的第四个取值 SHALL 命名为 `conflict`（矛盾），渲染走 err 色；该取值 SHALL NOT 加入既有世界页的结论白名单（避免把「矛盾」在世界页显示成「缺失」）。
- 「内容有变 · 待重新确认」这一状态的文案 SHALL NOT 含「已确认」字样（依据 §5 状态语言 S-R2 与「已确认 → ok 软底徽标」条目；状态措辞以标准正文为准，不在 spec 里另行转述）。
- 「草稿」这类**常态化**状态 SHALL NOT 用 warn 徽标（依据 §5 的 S-R3：警示性徽标不得常态化）；未确认只是常态属性，SHALL 用中性档位表达。

#### Scenario: 角色体检落弹窗报告卡
- **WHEN** 作者对当前角色跑一致性体检
- **THEN** 结果呈现在 AI 出卡弹窗的体检报告卡内（逐项 `.chk-row` 行、四态结论＋依据），弹窗关闭后不残留面板内结果区

#### Scenario: 只复用既有胶囊与徽标
- **WHEN** 查看角色页的类型胶囊、关系标签与徽标
- **THEN** 它们分别来自既有 chip / pill / badge 档位，页面样式表内不出现新的胶囊类名

#### Scenario: 体检行与既有体检互不影响
- **WHEN** 角色页渲染体检逐项，且世界页/主线页的体检行也存在于同一应用
- **THEN** 角色页的逐项样式只作用于 `.chk-row`，既有 `.chk-line` 的显示不变

#### Scenario: 第四态不污染世界页
- **WHEN** 角色页体检返回 `conflict`
- **THEN** 世界页体检的取值集合仍只含既有三态（不出现 `conflict`）

#### Scenario: 第三态文案合规
- **WHEN** 角色项因内容变动退回未完成
- **THEN** 徽标文案为「内容有变 · 待重新确认」，不含「已确认」字样
### Requirement: 认知六层的理解层次标记

角色认知六层区块 SHALL 在层头补一句大白话 hint（给作家看的，不出现「理解层次/NLP/上三层下三层/精神层」等术语）：
- 世界观：「他眼里的世界是什么样的？」
- 自我观：「他把自己当成谁？」
- 价值观：「他在乎什么？为什么做这些事？」
- 能力：「他能做什么？怎么做到的？」
- 行为：「遇到事，他会怎么做？」
- 环境：「他身边有什么人、什么事？」
s5 的展示口径 SHALL 为「宿命认知观」＋hint「他和这个世界到底是怎么回事？这条路走到头，他注定要面对什么？」。层名 SHALL 保留既有叫法不改写。hint 与分组标记 SHALL 复用既有 `.cog-layer-tag` 档位（或同档位等价类），SHALL NOT 新增胶囊形态。

#### Scenario: 层头带大白话 hint
- **WHEN** 作者展开认知六层的「自我观」层
- **THEN** 层头可见 hint「他把自己当成谁？」；s5 格位 hint 为「他和这个世界到底是怎么回事？这条路走到头，他注定要面对什么？」

#### Scenario: 词表双源一致
- **WHEN** 后端 character_model 与前端 characterModel 的 label/口径变更
- **THEN** 两端同批修改且 parity 测试通过（镜像个数为零）
### Requirement: 伏笔面板的词表与状态词汇

- 伏笔台账与伏笔卡 SHALL 使用 settings-v 作用域的 hk-* 词表（台账两行条目、分组头、伏笔卡档案表）， SHALL NOT 复用世界面板现役 `.kv-row` 等同名异义类——落地时以 ADJUSTMENTS 登记的类名映射表为准（`.kv` 家族作用域化或改名 `.hk-kv`）。
- 伏笔对象的状态语言 SHALL 全链同源（N5）：活跃＝实心 warn、已收束＝实心 ok、废弃＝muted 描边；台账点、分组头点、卡面状态徽标、状态切换控件共用同一套语义色，禁止为单屏发明第四种组合。
- 面板徽标口径：还没有伏笔=empty、N 条待收束=warn、已确认 · N 条待收束=done、全部收束=ok、内容有变 · 待重新确认=warn（优先级最高）。
- 回执 SHALL 面板内自管（不经 SettingsView 回执通道），语义沿用回执语言：最近一条、8 秒自清窗口、撤销按钮。
- 面板脚 SHALL 呈现保存态（保存中…/已自动保存，mono 小字），「存草稿」按钮对伏笔隐藏。

#### Scenario: 状态点与卡面徽标同色

- **WHEN** 一条伏笔处于「已收束」状态
- **THEN** 台账状态点、分组头计数点与卡面状态徽标均为 ok 语义色，三者由同一 status 派生

#### Scenario: 类名不撞世界面板

- **WHEN** 伏笔面板与世界面板同处于设定视图
- **THEN** 伏笔卡的档案表样式不改变世界面板 `.kv-row` 的布局（类名经映射表隔离）
### Requirement: 设定页内页签与文风量化词表

- 设定面板内层级 SHALL 允许页签（`.settings-v .ptabs/.ptab`），并在 ADJUSTMENTS 登记页签回归例外（仅面板内层级，面板间导航仍走左树）；页签激活态沿 modnav 口径（accent 下划线）。
- 文风面板 SHALL 收编以下 settings-v 作用域词表（book.css 本地段，随 ADJUSTMENTS 登记映射）：锚定块 `.fblock/.fb-head/.fb-no/.hint` 与锚定链 `.anchor-chain/.ac-node/.ac-arrow/.ac-note`；基线 `.dims/.dims-meta/.bx-row/.bx-head/.bx-name/.bx-dims/.bx-vals/.bx-note/.lock-btn/.five-bar/.fb-legend/.det-row`；蒸馏 `.sample-box/.sample-row/.s-name/.s-cnt/.s-check/.sample-total/.dist-step/.ds-no/.ds-b/.ds-ok/.portrait/.pz-head/.pz-note/.pz-ask/.pz-act`。
- `Cfg` 折叠组件 SHALL 加可选 `sum` 摘要位（组头一行灰字，收起态也传达信息）；`ListEditor` SHALL 加可选上移与 `x/y` 计数（`maxItems` 到量隐藏添加钮已有）；均 SHALL 以可选 prop 扩展，SHALL NOT 新造平行词表。
- `.hk-sec-label/.hk-sl-tag` SHALL 提升为 `.settings-v .sec-label/.sl-tag` 共享类（hk-* 保留别名或机械改名，映射表随 ADJUSTMENTS 登记），SHALL NOT 长期两套。
- 已撤并入口的遗留词表（src-card 家族、genre-grid/g-chip、badge.done）SHALL NOT 入库。
- 基线锁定按钮 SHALL 带 `aria-pressed`；五层占比条为纯装饰 SHALL 带 `aria-hidden`。

#### Scenario: 页签例外已登记

- **WHEN** design:lint 检查 settings-v 作用域新类
- **THEN** ptabs/ptab 在 ADJUSTMENTS 例外清单内放行；面板间导航未出现第二套页签

#### Scenario: 锁定状态可被辅助技术读出

- **WHEN** 基线行「篇幅配比」处于锁定态
- **THEN** 锁定按钮带 aria-pressed=true，五层条 aria-hidden=true
### Requirement: C端 书架阶段徽标四态档位

- C端 书架卡片的阶段徽标（`.b` 家族，C端 业务层专属，与 S端「`.b` 退役」口径无关）SHALL 呈现四态档位，档位-语气映射固定：
  - `setting` 设定中——中性底（fg-soft/muted）；
  - `writing` 写作中——warn 底（进行中的提醒语气）；
  - `ready` 待完本——**accent 底**（可行动召唤：全书已归档、就差完本这个动作）；
  - `done` 已完结——ok 底（完成语气；本 change 前该档语义为「已归档」，语义更名、底色不变）。
- SHALL NOT 新增第四种胶囊形态、SHALL NOT 引入 info/ok/warn/err 之外的新语气词；`ready` 档复用 accent 语义色，SHALL NOT 新造令牌。
- docs/ux/design-language.html §5 状态语言总表 SHALL 同批补「待完本（accent）」「已完结（ok）」两行；两端 `design-vocab.mjs` 若将 `.b` 档位纳入白名单 SHALL 两端同批登记（S端 无此形态，仅登记不生效）。

#### Scenario: 书架徽标四态渲染

- **WHEN** 书架上同时存在设定中/写作中/待完本/已完结四本书
- **THEN** 四张卡片的徽标分别命中 setting（中性）/writing（warn）/ready（accent）/done（ok）四档，无其它形态
### Requirement: 中栏空态卡的四档词汇（`.e-empty` 家族）

中栏默认页的空态卡 SHALL 用四档版式层级表达「这一屏在问你什么」，档位与命名固定为：

- **眉标** `.e-empty .be-mark`：小号等宽强调字（mono 10px／字距 .14em／`--accent` 色），放状态类信息
  （设定 N/7 已确认／第N卷 · 名字 已就绪／卷数·章数·字数进度），SHALL NOT 承载提问。
- **主句** `.e-empty .be-k`：19px 展示体＋墨色，放这一屏的提问或主行动语
  （这本书怎么开始？／开始写第一章？／接着写第 N 章？），SHALL 是全卡视觉最重的一行文字。
- **说明** `.e-empty .be-t`：13.5px muted（380 字宽内居中），放一句操作说明。
- **动作** `.e-empty .be-acts`：按钮行（保持既有按钮语言，不新增按钮档位）。

- 四档 SHALL 按「眉标 → 主句 → 说明 → 动作」自上而下排列；三张卡（起手卡／落点卡／书主页卡）SHALL 同批同档。
- `.be-desc` SHALL NOT 使用（该类在共享/业务层均无定义；说明句一律走 `.be-t`）。
- 四档 SHALL 只复用既有共享令牌与字体族（`--accent`／`--fg`／`--muted`／`--font-mono`／`--font-display`），
  SHALL NOT 新增 token、SHALL NOT 触碰两端共享段。

#### Scenario: 三张卡同档

- **WHEN** 依次看到起手卡（0 卷）、落点卡（有卷未排章）、书主页卡（有卷有章）
- **THEN** 三张卡呈现的档位顺序都是 `be-mark → be-k → be-t → be-acts`，提问落在 `.be-k` 上

#### Scenario: 提问是这一屏最重的字

- **WHEN** 起手卡显示「设定 0/7 已确认」与「这本书怎么开始？」
- **THEN** 「这本书怎么开始？」是 19px 主句（`.be-k`），「设定 0/7 已确认」是眉标（`.be-mark`）——
  程序计数 SHALL NOT 成为全卡最大的字

### Requirement: 朱雀检测的组件词汇与结果呈现

- 模型配置页页签行 SHALL 使用 `.cfg-tabs/.cfg-tab` 词汇（C端 model-config 作用域，business 层），页签激活态沿 seg 口径（surface 提亮＋fg）；「添加 API Key」按钮的页签级显隐归 zhuque-config 域约束。
- 朱雀检测结果在章标题行的呈现 SHALL 裸排（`.zq-hd` 及 `.hd-top/.hd-bar/.hd-ratio/.hd-act/.hd-errline/.hd-run` 行内词），SHALL NOT 套卡片壳；正文段落标注 SHALL 使用 `.zq-warn/.zq-err/.zq-mark`（m-ok/m-warn/m-err 三语气档＋`.zq-mark.stale` 过期置灰档），挂编辑器作用域（`.editor`），SHALL NOT 挂通用 `.prose` 名。
- 右栏检测行的引导态 SHALL 用 `.ra-step.zq-guide`（虚线变体）、锁定态 SHALL 用 `.ra-step.zq-maxlk`（复用既有锁定视觉：降透明＋cursor not-allowed＋MAX 专属 warn 徽章），SHALL NOT 新发明第四种行形态；徽章 SHALL 用既有 `.pill` warn 语气档。配置面板的 Key 行/统计行/步骤条 SHALL 使用 `.zg-keyrow/.zg-stats/.zg-flow`，显示开关行 SHALL 使用 `.zq-toggle-row`（开关本体复用现役 `.switch-btn` 家族）。
- 「AI 结果统一出卡确认弹窗」条款（见 Requirement: AI 写作助手卡片与结果区组件词汇）的适用域 SHALL 为**有写回语义的 AI 产物**（生成文本、候选、补缺建议等确认后才落库的结果）；朱雀检测是只读测量、无写回动作，其结果 SHALL 就地呈现（章标题区结果条＋正文装饰层），SHALL NOT 强制走出卡弹窗，清除即弃（无确认语义）。本条为该条款适用域的裁定：只读测量类结果与「结果进弹窗」字面冲突时，以本条为准。
- 本条新增词全部为 C端 business 层（book.css / model-config.css 本地段），SHALL 只复用共享令牌，不新增全局 token、不新增状态档位/胶囊形态/字号档位；开关 SHALL 复用现役 `.switch-btn/.sw-track/.sw-knob`，SHALL NOT 另造 `.switch` 样式。

#### Scenario: 检测结果不走卡弹窗

- Given MAX 作者点击右栏检测行且检测成功
- When 查看结果呈现位置
- Then 结果在章标题行右侧与正文标注中就地展示，无弹窗、无确认键；「清除标注」即弃

#### Scenario: 新词通过设计门禁

- Given zhuque 域新词已登记入 book.css / model-config.css 本地段
- When 跑 npm run design:lint 与 design:check
- Then 无禁令违规、基线场景像素差 <0.2%

### Requirement: C端 写作能力弹窗与菜单项词汇

- 「写作能力」引导弹窗 SHALL 复用既有设计系统弹窗骨架（`Modal`/`mcard` 形态与进出场、
  Esc/遮罩关闭、焦点圈行为），SHALL NOT 新造弹窗骨架；进度呈现为分步行（检查版本 →
  下载 → 校验安装）而非百分比环形。
- 弹窗三模式（首装自动／更新确认／手动检查）的标题、进度行、完成行与失败行文案
  SHALL 在 design-language 状态总表登记新行；状态语气沿用既有 info/warn/err 档，
  不新增语气档。（design-vocab.mjs 无新登记项——其机制只辖任意值/opacity 档/禁用
  色板，类名与文案不入其白名单；review-agent 轮 P3 对齐。）
- 账号面板「数据」组「写作能力」菜单项 SHALL 复用 `am-item` 组件词汇与图标位规格
  （与「模型配置 · API Key」同行规），状态随行文案三态：`已就绪 vX`／`未就绪`／
  `有新版本`；面板 foot 的 `am-pack` 小字行词汇与样式 SHALL 随本批退役。
- 用户可见名词延续既有口径：统一「写作能力」，提示词包/pack/manifest/验签/换钥等
  内部词 SHALL NOT 出现在弹窗与菜单项任何文案中。

#### Scenario: 原型先行登记
- **WHEN** 实现写作能力弹窗与菜单项
- **THEN** 书架原型先行登记弹窗三模式变体（含进度行/完成行/失败行）并在 ADJUSTMENTS.md
  留档，design-language 状态总表登记后才落实现（design-vocab.mjs 无涉，机制见上）

#### Scenario: 内部词不进文案
- **WHEN** 检查弹窗三模式与菜单项全部用户可见文案
- **THEN** 仅出现「写作能力」及既有状态词汇；无「提示词包/manifest/验签」等内部词
