# workbench Specification

## Purpose

写作工作台的行为契约：骨架层（卷/章树、两栏布局与专注模式、底栏状态）承接 free-workspace 归档；章纲面板的 AI 起草入口行为契约——入口可见性、覆盖确认与失败语义。

## Requirements

### Requirement: useWorkbench hook

- The system SHALL provide `hooks/useWorkbench.ts` assembling: project metadata (from `useProject`), the volume/chapter tree, current selection (`selectedId` / `selectedRef`), the four-state view + `setView(view, payload)`, `expandedIds` / `onToggle`, `onSelectNode`, tree CRUD (`createVolume` / `createChapter` / `renameNode` / `deleteNode`), `refresh`, and `focusNode(ref)`.
- The tree SHALL be sourced from the backend; while the DB-backed `/volumes` full-tree contract (change 005) is not yet available, the hook SHALL degrade to the current legacy shape: `GET /volumes` (list) then per-volume `GET /volumes/{filename}` to assemble `chapters`.
- The tree and selection state SHALL be shared across views (workbench and advanced-outline consume the same `volumes` array), so switching views does not split state (C3/R3).
- `VolumeEntry` (exported by `hooks/useOutline.ts`) SHALL gain optional `has_prose?: boolean` and `archived?: boolean` fields, defaulting via `??` fallback for backward compatibility (N1).
- `focusNode(ref)` SHALL locate the tree node with the given chapter ref and select it.

#### Scenario: Tree loads from legacy volumes shape
- Given a project with volumes and chapters on the current backend
- When `useWorkbench` initializes
- Then it assembles a tree with volume and chapter nodes including per-chapter `word_count`/`status`, and `has_prose` falls back to a local heuristic when the field is absent

#### Scenario: Selection persists across view switches
- Given a chapter selected in the workbench tree
- When the user switches to advanced-outline and back
- Then the same chapter remains selected

### Requirement: WritingTree with persistent create actions (N1/N2)

- The system SHALL provide `components/novel/WritingTree.tsx` wrapping `StructureTree`.
- The tree SHALL render persistent 「+ 新建卷」 and 「+ 新建章」 action buttons at its top (N1).
- Clicking 「+ 新建章」 SHALL create a volume first if none exists, create the next chapter (`第N章`), refresh the tree, and immediately focus the new chapter in the editor (N1 "建章即达编辑器").
- Empty chapters (`!has_prose && !isSelected && not newly created this session`) SHALL be displayed with a de-emphasized 「未写」 marker; they SHALL NOT be hard-filtered out (N1). When `has_prose` is absent, the current/selected volume/chapter SHALL always display.
- Hovering a volume or chapter SHALL reveal config / rename / delete affordances (N2); rename and delete SHALL call the corresponding CRUD endpoints and refresh the tree.
- Chapter nodes SHALL show a word-count badge when prose exists and an archive 📦 badge when archived.
- `StructureTree` SHALL gain a minimal `onAddChild?` row-insert slot rendered on volume hover, without changing its core structure.

#### Scenario: New chapter reaches editor immediately
- Given an empty project (no volumes)
- When the user clicks 「+ 新建章」
- Then a volume is auto-created, `第1章` is created under it, and the editor for that chapter opens and is ready to type

#### Scenario: Empty chapters are softened, not filtered
- Given a chapter with no prose that is not selected
- When the tree renders
- Then the chapter appears with a 「未写」 de-emphasized marker instead of being hidden

### Requirement: Breadcrumb navigation (N17)

- The system SHALL provide `components/novel/Breadcrumb.tsx` rendering `作品名 / 第N卷 / 第N章` with `h-9` lightweight styling, shown only in the writing workbench.
- Volume and chapter segments SHALL be clickable buttons that select the corresponding node (`onSelectNode` / `focusNode`); the current node SHALL be highlighted.
- Breadcrumb SHALL remain visible in focus mode.

#### Scenario: Breadcrumb navigates to volume
- Given the breadcrumb showing a volume segment
- When the user clicks the volume segment
- Then that volume is selected in the tree

### Requirement: Workbench two-column layout with focus mode

- The system SHALL provide `components/novel/Workbench.tsx` with a left `WritingTree` column, a right editor region, and `BottomStatusBar`, and SHALL own the `focusMode` state.
- Focus mode SHALL hide the left tree and editor toolbar, retain the breadcrumb and bottom status bar, center the prose area (`max-w-3xl mx-auto`), and exit on `Esc` (global listener).
- When no chapter is selected, the editor region SHALL render the refactored `EmptyState`.

#### Scenario: Focus mode leaves only writing essentials
- Given focus mode is active
- When the user looks at the workbench
- Then only the breadcrumb, centered prose area, and bottom status bar are visible

### Requirement: BottomStatusBar with save states and progress (N5/N13)

- The system SHALL provide `components/novel/BottomStatusBar.tsx` showing: live word count, the save four-state (autosaving / saved / unsaved / failed-with-retry), and an embedded progress bar (`progress progress-primary h-1.5`) of `wordCount / targetWords` in the same row.
- The target word count SHALL be editable in place (click target → input → change writes back via `useChapterData.setTargetWords`), updating the bar immediately (N5).
- The archived state SHALL freeze the progress display.

#### Scenario: Target words adjust progress immediately
- Given a chapter with 500 words and target 1000
- When the user edits the target to 2000
- Then the progress bar recomputes to 25% immediately

### Requirement: EmptyState without settings gating (N4)

- The system SHALL refactor `components/novel/EmptyState.tsx` to remove the `settingsComplete`/`bypass` gate branches.
- The empty state SHALL present 「添加卷」 / 「添加章」 primary actions, an advanced-config secondary link (marked 「可选」), and a 「先写正文」 hint.
- The empty state SHALL NOT block or prompt "先去设定".

#### Scenario: New book reaches writing without settings
- Given a newly created book with no volumes or chapters
- When the workbench empty state renders
- Then it offers add-volume / add-chapter actions directly, with no settings-completeness gate and no "先去设定" blocker

### Requirement: 章纲面板 AI 起草入口

章纲面板 SHALL 提供「AI 起草」入口（需 AI 访问门通过；免费态隐藏或禁用，与提示词子面板同口径）。

已有内容需二次确认的判定覆盖**全部章纲格子**：核心任务/概要/主情绪/读者预期/必须变化/段落规划之外，场景卡（任一行任一字段有内容）、读者获得（任一条有描述）、章末落点、本章目标字数任一非空即视为「已有内容」，必须经确认后才发起起草。

#### Scenario: 空章纲一键起草
- **WHEN** 作者在章纲尚为空的章节点击 AI 起草
- **THEN** 发起起草请求，成功后将返回的结构化草稿回填进章纲表单（不落库），作者可直接修改后保存

#### Scenario: 已有内容需二次确认
- **WHEN** 章纲表单已有内容时点击 AI 起草
- **THEN** 弹出确认（说明将覆盖当前表单内容），确认后才发起；取消不发请求

#### Scenario: 只填了场景卡也要确认
- **WHEN** 作者仅在场景卡行填了场景名（其余格子全空）时点击 AI 起草
- **THEN** 弹出覆盖确认；取消不发请求，表单内容保留

#### Scenario: 整表仍空不弹确认
- **WHEN** 全部章纲格子为空时点击 AI 起草
- **THEN** 不弹确认，直接发起

#### Scenario: 起草失败可重试
- **WHEN** 起草请求返回错误（校验失败/模型错误/无主线卡）
- **THEN** toast 显示后端错误消息，表单内容保持不变

#### Scenario: 回填内容过既有校验
- **WHEN** 草稿回填表单后作者直接保存
- **THEN** 与手填完全同一条链路：ogFormIssues 拦截（场景名门槛/字数区间）、ogGaps 缺项提示、确认门照常生效

### Requirement: 本书偏好弹窗归档 AI 摘要开关（既有能力规格化确认）

工作台本书偏好弹窗 SHALL 提供「归档 AI 摘要」per-book 开关（开/关，按书独立存储）——此为既有实现（含原型），本 change 对其规格化确认：全局设置弹窗退役移除全局归档开关入口后，该开关 MUST 保持可达且行为不回归。该书归档时 SHALL 按书级取值决定是否生成 AI 摘要；书级未设置时 SHALL 回退全局存量值（无全局存量值时默认开）——回退链既有语义 MUST NOT 改动，既有用户已存的书级/全局偏好值 MUST NOT 丢失或被重置（历史关闭过全局开关的用户，书级未设置时归档仍不出 AI 摘要）。

#### Scenario: 按书关闭归档 AI 摘要

- **WHEN** 用户在某本书的本书偏好中关闭「归档 AI 摘要」后归档该书章节
- **THEN** 该书归档不生成 AI 摘要，其他书不受影响

#### Scenario: 未设置回退全局存量值

- **WHEN** 某本书从未设置书级归档开关，且历史上通过全局设置写入过全局值
- **THEN** 归档该书的 AI 摘要行为与该全局存量值一致（新用户无存量值时默认开）

#### Scenario: 入口在全局设置退役后保持可达

- **WHEN** 全局设置弹窗退役后用户进入工作台打开本书偏好弹窗
- **THEN** 「归档 AI 摘要」开关可见可用，取值不受入口迁移影响

### Requirement: 书内顶栏（行头归一：单行 appbar）

- 书内页顶栏 SHALL 为**单行 48px**，自左向右依次为：品牌 logo（唯一「返回书架」入口；原「← 我的小说」链接退役）｜书名（双击就地改名，Enter 保存 / Esc 取消，SHALL 保证只保存一次）｜题材胶囊｜当前主线定位（bar-here）｜账户胶囊（档位徽）。
- 全局顶栏组件 SHALL NOT 在 `/novel/*` 渲染书内变体——书内顶栏的唯一事实源是工作台。
- 免费档的档位告知 SHALL 由账户胶囊的档位徽承担（原顶栏 free-hint 与「升级 PRO」按钮退役）；升级入口 SHALL 仍在右栏 locked 卡与本书偏好弹窗可达。
- bar-here SHALL 显示：「当前主线」引导词、`第 N 章` 与章节题（题名为默认序号名时 SHALL 省略题名，避免「第 1 章第一章」重复序号）、目标章有正文且未归档时的「草稿」标签、卷面进度（`第X卷 · 已归档/总章`＋进度条）与「续写」按钮。
- bar-here SHALL 按原型三档响应式降级：≤1320px 隐藏题材胶囊、≤1180px 隐藏卷面进度、≤920px bar-here 换行为独立一行。
- 书内顶栏 SHALL NOT 引入第二条导航行；modnav（设定/写作/预览）保持原样位于其下。

#### Scenario: 单行头
- **WHEN** 打开任意一本书的工作台
- **THEN** 顶栏只有一行：logo｜书名｜题材｜当前主线定位｜账户胶囊，且没有「我的小说」返回链接、免费提示条与顶栏升级按钮

#### Scenario: 就地改名只保存一次
- **WHEN** 作者双击顶栏书名、输入新名后先按 Enter 再触发失焦
- **THEN** 书名恰好保存一次

#### Scenario: 默认名不重复序号
- **WHEN** 主线章标题为默认序号名（如「第一章」）
- **THEN** bar-here 渲染为「第 1 章」，不拼接章节名

#### Scenario: 免费态档位告知
- **WHEN** 免费档用户打开工作台
- **THEN** 账户胶囊显示「免费版」档位徽，且升级入口在右栏 locked 卡与本书偏好弹窗可达

### Requirement: 续写＝上次写作会话恢复

- 工作台 SHALL 按书、按设备（localStorage）持久化「上次写作会话」：章节 ref 与正文编辑器滚动比例，在作者于正文页输入或滚动时节流更新。
- bar-here 的目标章 SHALL 优先取该会话指向的章节；会话缺失或其章节已不存在时 SHALL 回落「最新归档章」，再回落「首章」。
- 「续写」SHALL 选中目标章、切到正文页签，并在章节内容就绪后恢复记录的滚动比例（加载期间允许短暂轮询重试；空章/内容不足一屏时 SHALL 为无操作）。
- 恢复 SHALL 每个信号至多应用一次：其后作者的输入与滚动 SHALL NOT 被覆盖（编辑器 SHALL NOT 弹回恢复位置）。
- 若会话记录的章节其后已归档，续写 SHALL 落在该章的既有只读态，不引入新的解锁行为。

#### Scenario: 续写回到上次位置
- **WHEN** 作者在第 1 章滚动到内容后部，切到第 2 章后点击顶栏「续写」
- **THEN** 选中章回到第 1 章、正文页签激活，且编辑器滚动位置恢复到上次记录的比例

#### Scenario: 恢复只发生一次
- **WHEN** 续写恢复完成后，作者把编辑器滚回顶部并继续输入
- **THEN** 编辑器保持作者自己的滚动与输入结果，不再被拽回恢复点

#### Scenario: 会话章已删除
- **WHEN** 上次写作会话指向的章节已被删除
- **THEN** bar-here 与「续写」回落到最新归档章（无归档则首章），且不报错
