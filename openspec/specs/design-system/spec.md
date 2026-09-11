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
