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
- Badges SHALL use the `.pill` family (roles tag/status/count x tones); callout bars SHALL use the `.notice` family with explicit modifiers; toast severity may add `warn`.
- The cross-end tone vocabulary is fixed at info / ok / warn / err. Retired synonyms (success/danger as notice or badge tones, the `.b` badge names, `.strip`) MUST NOT reappear. The save-state ladder remains autosaving, unsaved, failed-with-retry, saved.
- Streaming/AI activity SHALL be expressed by a breathing accent dot; prose layout MUST NOT animate during streaming.

#### Scenario: Same object viewed twice
- Given a chapter confirmed in the workbench tree
- When the preview view lists that chapter
- Then it shows the same dot-ok semantics derived from the same data

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
- Destructive confirmations SHALL render through an in-app modal confirm (no native `window.confirm`), listing affected items as inventory when deletion cascades.
- Empty states SHALL offer at least one actionable exit alongside the descriptive line.

#### Scenario: Delete affecting linked content
- Given deleting a config that books depend on
- When the user confirms
- Then an in-app dialog lists the affected items as inventory chips before deletion executes

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
- 新增「AI 写作助手」卡片组件（C端设定视图右栏）：PRO 徽标并入卡片头部＋标题＋一行套餐归属/只加工不代写；内部为**并列能力行**（每行＝名称上＋描述下从属＋右侧箭头，整行可点）；底部一条来源/去向声明。命名 `.rail-assist` + `.ra-*`。
- 新增「AI 结果区」组件 `.ai-sink`：`TintPanel`（fg-soft 平底）只读说明，置于左侧对应输入框/字段**正下方**；顶部操作名标签（`.aiz-head`）＋候选文本＋采纳/重试按钮。必须用 fg-soft，不得用 `--surface`（surface 是可编辑/可操作容器底色，与输入框撞色会误判结果区可编辑）。
- 这些是 **C端局部组件类**（不在两端共享 `base.css` 共享段），归 C端工作台设定视图作用域（`book.css` 或设定视图局部样式）；只复用共享令牌（`--fg-soft`/`--surface`/`--border`），不新增全局 token。
- 能力行在无套餐时 SHALL 复用既有「可见 + 锁定」门控（见 Requirement: Free vs PRO gating stays visible）：整卡降透明、徽标转灰、行降透明 + cursor:not-allowed，点击给统一升级提示，不各自弹窗；锁定态卡片名 `.rail-assist.locked`。门控 key 用已登记的 `settings-ai-fields`（memberOnly），而非未登记的新 key。

#### Scenario: 结果区不用可编辑底色
- Given 简介/题材 AI 反馈已产出
- When 查看结果区样式
- Then 结果为 fg-soft 只读底（TintPanel），与输入框（surface）可区分，误判不可编辑

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
- 体检（一致性检查）逐项行在角色页 SHALL 使用独立类名（`.chk-row`：名称与结论一行、依据一行），SHALL NOT 覆盖既有 `.chk-line` 的样式作用域；结果区 SHALL 落在 `.ai-sink` 内。
- 体检结论的第四个取值 SHALL 命名为 `conflict`（矛盾），渲染走 err 色；该取值 SHALL NOT 加入既有世界页的结论白名单（避免把「矛盾」在世界页显示成「缺失」）。
- 「内容有变 · 待重新确认」这一状态的文案 SHALL NOT 含「已确认」字样（依据 §5 状态语言 S-R2 与「已确认 → ok 软底徽标」条目；状态措辞以标准正文为准，不在 spec 里另行转述）。
- 「草稿」这类**常态化**状态 SHALL NOT 用 warn 徽标（依据 §5 的 S-R3：警示性徽标不得常态化）；未确认只是常态属性，SHALL 用中性档位表达。

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
