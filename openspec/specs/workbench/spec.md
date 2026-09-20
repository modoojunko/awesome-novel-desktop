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

写作页空态 SHALL NOT 设设定完备门控：零卷零章的书切到「写作」即呈现起手态，不弹「先去设定」、
不拦操作（空书默认落「设定」是打开书的落点，不是门控）。

- 中栏 SHALL 呈现起手卡（`.e-empty`）：「这本书还没有开始」＋说明句（先建第一卷、写清卷名与
  卷主旨；也可直接排第一章，系统会先垫好第一卷）＋双入口「＋ 新增一卷」（主）／「＋ 新增一章」。
- 有卷但未选中任何节点时（含章节删空后未选中），中栏 SHALL 呈现同一容器的一句选章引导
  （「在左侧目录里选一章，上面一行页签会展开它的章纲、正文、提示词、设定与关系伏笔，重写与
  回退收在「操作」页签里」），SHALL NOT 再出现起手卡双入口。
- 左栏空书态 SHALL 呈现提示文案与底部两个入口「＋ 新增一章」「＋ 新增一卷」（虚线按钮，贴列底）；
  空书态 SHALL NOT 呈现「确认全部已填章节」（无章可确认）；非空书态左栏结构 SHALL 保持不变。
- 空书「＋ 新增一章」SHALL 先垫第一卷（程序默认序号形态「第一卷」，用户可改名）再排「第一章」，
  新章 SHALL 直接落在章纲页签，并在垫卷时提示已垫好第一卷。
- 三处「＋ 新增一卷」（顶栏空书卡／中栏起手卡／左栏底部）SHALL 打开同一个「添加卷」弹窗
  （卷名必填＋卷摘要＋初始章数），SHALL NOT 各自实现建卷路径。

#### Scenario: New book reaches writing without settings
- Given 新建的书（0 卷 0 章）
- When 作者切到「写作」
- Then 中栏呈现起手卡与双入口，无「先去设定」拦截；左栏呈现空态提示与底部两入口

#### Scenario: 直接排第一章先垫卷
- Given 书里还没有任何卷
- When 作者点「＋ 新增一章」
- Then 先创建「第一卷」再排「第一章」，并直接打开该章章纲；左栏树上「第一卷」「第一章」可见

#### Scenario: 有卷未选中只给选章引导
- Given 书里已有卷（哪怕章节已删空）
- When 写作页没有任何选中节点
- Then 中栏只给一句选章引导，不出现起手卡双入口

### Requirement: 章纲面板 AI 起草入口

右栏「AI 助手」的章纲页签动作区 SHALL 提供「AI 起草」入口（需 AI 访问门通过；免费态置灰禁点，与右栏 AI 动作组同口径）；章纲页签 body 内 SHALL NOT 再设 AI 按钮（2026-09-20 AI 入口唯一化右栏）。

已有内容需二次确认的判定覆盖**全部章纲格子**：核心任务/概要/主情绪/读者预期/必须变化/段落规划之外，场景卡（任一行任一字段有内容）、读者获得（任一条有描述）、章末落点、本章目标字数任一非空即视为「已有内容」，必须经确认后才发起起草。

#### Scenario: 空章纲一键起草
- **WHEN** 作者在章纲尚为空的章节点击右栏「AI 起草」
- **THEN** 发起起草请求，成功后将返回的结构化草稿回填进章纲表单（不落库），作者可直接修改后保存

#### Scenario: 已有内容需二次确认
- **WHEN** 章纲表单已有内容时点击右栏「AI 起草」
- **THEN** 弹出确认（说明将覆盖当前表单内容），确认后才发起；取消不发请求

#### Scenario: 只填了场景卡也要确认
- **WHEN** 作者仅在场景卡行填了场景名（其余格子全空）时点击右栏「AI 起草」
- **THEN** 弹出覆盖确认；取消不发请求，表单内容保留

#### Scenario: 整表仍空不弹确认
- **WHEN** 全部章纲格子为空时点击右栏「AI 起草」
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
- bar-here 的目标章 SHALL 取**主线端点（frontier）＝全书首个未归档章**；全书已归档时 SHALL 显示待写占位（下一章号）。目标章有正文且未归档时的「草稿」标签、卷面进度（`第X卷 · 已归档/总章`＋进度条）与「续写」按钮。
- bar-here SHALL 显示：「当前主线」引导词、`第 N 章` 与章节题（题名为默认序号名时 SHALL 省略题名，避免「第 1 章第一章」重复序号）。
- bar-here SHALL 在全书零卷零章时切换为「空书」态（「当前主线」态让位）：`空书` 引导词＋`第 1 章` 待写＋`未开始` 徽＋`还没有卷与章节`＋「＋ 新增一卷」按钮；该按钮 SHALL 打开「添加卷」弹窗。
- 程序序号 SHALL 由中文数字表给出，**四位及以上回退阿拉伯数字**（`1000` → `第1000章`，中文表只排到百位）；默认序号判定 SHALL 同时认中文千位形态（如「第一千零一章」，故该章也不重复拼题名）。该口径前后端 SHALL 逐字一致（`lib/nodeTitle.ts::cnNum/_DEFAULT_TITLE_RE` ↔ `manuscript/render.py::cn_num/_DEFAULT_TITLE_RE`），parity 测试为唯一判定依据（P3，2026-09-18：修复前 ≥1000 会渲染成「第undefined百…章」且成稿整单硬失败）。
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

#### Scenario: 主线端点跟随未归档章
- **WHEN** 第 1 章已归档、第 2 章存在且未归档
- **THEN** bar-here 定位到第 2 章（而非最近归档的第 1 章）

#### Scenario: 全书归档后的待写占位
- **WHEN** 全书所有章节均已归档
- **THEN** bar-here 显示待写占位（下一章号），不报错

#### Scenario: 空书顶栏起手卡
- **WHEN** 打开一本还没有任何卷与章节的书的写作页
- **THEN** bar-here 显示「空书 · 第 1 章待写 · 未开始 · 还没有卷与章节」与「＋ 新增一卷」按钮；点该按钮打开添加卷弹窗

#### Scenario: 免费态档位告知
- **WHEN** 免费档用户打开工作台
- **THEN** 账户胶囊显示「免费版」档位徽，且升级入口在右栏 locked 卡与本书偏好弹窗可达

### Requirement: 续写＝上次写作会话恢复

- 工作台 SHALL 按书、按设备（localStorage）持久化「上次写作会话」：章节 ref 与正文编辑器滚动比例，在作者于正文页输入或滚动时节流更新。
- bar-here 的目标章 SHALL 优先取该会话指向的章节；会话缺失或其章节已不存在时 SHALL 回落**主线端点（frontier）**，再回落「首章」。
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
- **THEN** bar-here 与「续写」回落主线端点（全书归档则待写占位），且不报错

### Requirement: 章节状态机排队门禁（frontier）

- 系统 SHALL 提供 `GET /api/novels/{novel_id}/frontier` 返回主线端点信息：首个未归档章的章号/ref/标题与状态；全书归档时返回待写占位（含下一章号）。
- 正文保存（PUT prose）与 AI 写章端点 SHALL 对**非主线端点**章节返回 409（reason 文案为「还不能写这一章——先完成前面的章节」类，前端就地只读呈现）；旧稿支线（ghost）章节 SHALL 一律只读（409 reason「旧稿支线只读」）。
- 归档 SHALL NOT 受排队门禁限制（作者可归档任意已就绪章）。
- 前端正文页在锁定时 SHALL 呈现只读态（编辑器不可编辑 + 顶部提示），不弹全局错误。

#### Scenario: 未来章不可写
- **WHEN** 第 1 章未归档（存在且未归档），对第 2 章发起正文保存
- **THEN** 返回 409 且正文未被写入

#### Scenario: 主线端点可写
- **WHEN** 第 1 章已归档、第 2 章成为主线端点
- **THEN** 对第 2 章的正文保存成功

#### Scenario: 支线章只读
- **WHEN** 对旧稿支线章节发起正文保存
- **THEN** 返回 409（旧稿支线只读）

### Requirement: 回退与旧稿支线

- 系统 SHALL 提供 `POST /api/novels/{novel_id}/chapters/{chapter_ref}/revert`：把主线截断到目标章，其**后**所有主线章转入旧稿支线——`chapters.ghost_of` 记录回退目标章号，章数据只读保留（不删除）。
- 回退 SHALL 清除被转支线章节按章序派生的数据：出场引用的本章状态变化、来源章指向这些章的关系记录、这些章的伏笔留痕、其收尾提案行与版本快照；更早章节的派生数据 SHALL NOT 受影响。
- 系统 SHALL 提供 `GET /api/novels/{novel_id}/ghosts` 列出旧稿支线章（按章序）。
- 工作台「操作」页签 SHALL 提供回退卡（不可逆二次确认）；支线章正文页 SHALL 显示只读横幅且 SHALL NOT 提供恢复编辑。

#### Scenario: 回退截断主线
- **WHEN** 在第 1 章（共 3 章）发起回退
- **THEN** 第 2、3 章转为旧稿支线（只读、ghost_of=1），主线端点回到第 1 章之后的新写作位

#### Scenario: 派生数据按章序清除
- **WHEN** 第 2 章曾被记录某角色状态变化后发生回退
- **THEN** 该状态变化被清除，且第 1 章的既有数据不变

### Requirement: 角色关系页签（全书关系图）

- 系统 SHALL 提供 `GET /api/novels/{novel_id}/characters/graph` 返回全书关系图数据（节点＝角色/势力、边含关系类型与立场、孤立点清单）。
- 工作台 SHALL 提供「角色关系」页签：以确定性定距圆布图（SVG）渲染关系图，边标签为 `关系类型 · 立场`；SHALL 附文本清单作为兜底视图。
- 关系图为全书统一视图（不按章过滤）；无关系时 SHALL 呈现空态文案而非空白画布。

#### Scenario: 关系图渲染
- **WHEN** 打开有角色关系的书的「角色关系」页签
- **THEN** 节点与边按确定性布局渲染，边标签显示关系类型与立场

### Requirement: 章纲页签剧情推演入口

- 右栏「AI 助手」的章纲页签动作区 SHALL 提供「剧情推演」入口（PRO 可用；归档章禁用；免费态置灰禁点）；章纲页签 body 内 SHALL NOT 再设入口按钮。
- 弹窗 SHALL 按回合逐步展开：未走到的回合显示占位；当前回合 SHALL 先定走法（顺/拗）才能「推演下一个回合」；走法选定后 SHALL 就地回显走法结果句。
- 弹窗 SHALL 提供「重新推演」（重置回合与走法选择，重新取数）与「按这条走法收进章纲」（展开到末回合后出现）。
- 「收进章纲」SHALL 把走法行写入本章「预期策略」：任一回合一「拗」→「推演走法 · 中途先接一次意外，再拉回主线」；全「顺」→「推演走法 · 顺着章纲节奏推进，不多加波折」；保存失败 SHALL 提示且弹窗不关闭。走法只作参考，SHALL NOT 自动改动章纲其它字段。

#### Scenario: 未定走法不能推进
- **WHEN** 当前回合未选择走法时点击「推演下一个回合」
- **THEN** 回合不展开并就地提示先选走法

#### Scenario: 收进章纲写预期策略
- **WHEN** 回合走完且任一回合一选择「拗」后点击「按这条走法收进章纲」
- **THEN** 本章「预期策略」更新为「推演走法 · 中途先接一次意外，再拉回主线」并提示成功

#### Scenario: 免费档入口置灰
- **WHEN** 免费档用户停留在章纲页签
- **THEN** 右栏「剧情推演」入口呈 rail-locked 置灰禁点（不隐藏）；章纲页签 body 无入口按钮

### Requirement: 文风页签（全档位：手工影子＋PRO 建议）

- 工作台 SHALL 提供「文风」页签（全档位可达）：承接全书文风基线（只读）＋本章覆盖行的**手工编辑**（增/改/还原）；「AI 建议本章调整」的触发入口 SHALL 在右栏「AI 助手」的文风页签动作区（PRO；归档章禁用；免费态置灰禁点），页签 body 内 SHALL NOT 再设触发按钮。
- 手工编辑 SHALL 包含：已有行行内直改「取值/理由」（失焦保存）、「添加覆盖行」（选择参数行＋取值，取值非空才可添加）、逐行「还原」；产出 SHALL 经既有 PUT 影子端点落库（形状清洗口径不变）。
- 右栏触发后，建议列表与逐条「采纳」SHALL 呈现在文风页签内；采纳 SHALL 写影子并可在列表继续手工修改。免费档页签内 SHALL NOT 呈现锁定占位说明（门控在右栏动作上）。
- 归档章 SHALL 只读呈现：行输入、添加与还原 SHALL 禁用，右栏建议动作 SHALL 禁用。

#### Scenario: 免费档手工编辑影子
- **WHEN** 免费档用户打开「文风」页签
- **THEN** 基线只读可见、影子行可增/改/还原（请求走 PUT 影子端点）；右栏建议动作置灰、页签内无触发按钮与占位拦截

#### Scenario: 添加覆盖行的取值门槛
- **WHEN** 未选择参数行或取值为空时点击「添加」
- **THEN** 添加按钮保持禁用，不发起请求

#### Scenario: PRO 右栏触发并采纳 AI 建议
- **WHEN** PRO 用户在文风页签点击右栏「AI 建议本章调整」，建议列表出现后对某行点「采纳」
- **THEN** 该行写入影子（PUT）并在列表中可继续手工修改

#### Scenario: 归档章只读
- **WHEN** 打开已归档章的「文风」页签
- **THEN** 行输入、添加与还原按钮均禁用，右栏「AI 建议本章调整」动作禁用

### Requirement: 中栏「伏笔」页签（章内台账投影）

- 章工作台中栏 SHALL 提供「伏笔」页签（全档位可达），位于「角色关系」与「操作」之间；内容为全书伏笔台账的**章内只读投影**：
  - 汇总行 SHALL 显示「N 条 · M 条悬置」，并在本章有埋下/回收时追加「本章埋下 N / 本章回收 N」；
  - 台账行 SHALL 显示编号、描述、埋点章（`第 N 章 · 题名`，无埋点章显示「开书」）与状态（悬置 / 已收 · 第 N 章 / 已弃）；
  - **本章埋下或本章回收的条目 SHALL 高亮**；
  - 空台账 SHALL 呈现引导文案（去「设定 · 伏笔」登记）。
- 页签 SHALL NOT 提供编辑入口（台账在设定页维护；AI 登记提案在「操作」页签确认）。

#### Scenario: 本章条目高亮
- **WHEN** 打开某章「伏笔」页签，且存在埋于本章与收于本章的伏笔
- **THEN** 这两类条目高亮显示，其余条目常态；汇总行含「本章埋下」与「本章回收」计数

#### Scenario: 空台账引导
- **WHEN** 本书还没有伏笔条目
- **THEN** 显示「还没有伏笔条目」引导且不报错

### Requirement: 设定投影含书级设定条目

- 章工作台「设定」页签的「截至本章」投影 SHALL 包含书级设定条目（world 的 factions/history/extra）：条目标注来源章（`第 N 章`；无 origin 标注「开书」），**来源章晚于当前章的条目 SHALL 被排除**；origin 无法解析时保守显示（不隐藏）。
- 该投影 SHALL NOT 含世界铁律（constraints，属硬边界不进按章投影）。

#### Scenario: 未来章条目被排除
- **WHEN** 某设定条目的 origin 指向第 3 章，而当前查看第 1 章
- **THEN** 该条目不显示；第 1 章与开书条目显示

#### Scenario: 开书条目恒显示
- **WHEN** 设定条目无 origin（开书期写入）
- **THEN** 任意章的投影都显示该条目并标注「开书」

### Requirement: 重写这一章（旧稿转支线＋下游旧设定角标）

- 「操作」页签 SHALL 提供「重写这一章」卡（对有正文且非支线的章渲染）；点击 SHALL 先弹影响面确认（wbStyle 小弹窗）：
  - **旧稿**：本章当前正文将转入旧稿支线（可随时点开查看）；
  - **后续**：其后章节原样保留，但挂「基于旧设定」角标；
  - **设定**：归档时确认本章变化；开书设定永不改写，之后累积的条目跟着重算。
- 确认前 SHALL 先落盘未保存正文（flush）；确认后经**一次事务**完成：本章当前正文快照为旧稿支线章（`ghost_of` 指向本章 ref，ref=`{ref}-r{sha256(正文)[:8]}` 内容寻址——同内容重放幂等）＋归档章解锁回可写；作者落正文页签在原文基础上改写。
- 重写后的再次归档 SHALL 与既有归档链完全一致（收尾提案照常产生）；归档提示在存在下游「基于旧设定」章时 SHALL 追加点名说明。
- **「基于旧设定」＝章自身状态（零时间戳派生）**：重写事务 SHALL 把源章之后的主线章（有正文者）置 stale；本章自身经单写入口保存/归档 SHALL 清除自身 stale。该角标 SHALL 呈现于：章节树行（中性虚线标签）、「设定」页签投影（顶部提示）、右栏「操作」统计（`下游挂着旧设定 N 章`）；本章保存成功后 SHALL 刷新树使角标消失。
- 旧稿支线章 SHALL 可点开只读查看（正文页签 contenteditable=false，只读横幅）。
- 重写 SHALL NOT 破坏排队门禁与支线只读口径：支线旧稿只读；主线仅端点章可写；旧稿快照 SHALL NOT 参与主线端点（frontier）推导。

#### Scenario: 确认弹窗与旧稿留存
- **WHEN** 在已归档的第 2 章点「重写这一章」并确认
- **THEN** 弹出影响面说明后进入可编辑态；旧稿支线出现本章快照（可点开只读查看），主线正文可继续编辑

#### Scenario: 重写后下游挂角标
- **WHEN** 第 2 章重写（第 3 章有正文且未改动）
- **THEN** 第 3 章在树行/设定投影/右栏统计中呈现「基于旧设定」

#### Scenario: 下游自身改写后角标消失
- **WHEN** 之后作者改写（正常保存）第 3 章
- **THEN** 第 3 章的「基于旧设定」角标不再呈现

#### Scenario: 旧稿只读可查看
- **WHEN** 点击旧稿支线条目并切到正文页签
- **THEN** 呈现只读正文（不可编辑）与只读横幅

#### Scenario: 无正文章不提供重写
- **WHEN** 某章尚无正文
- **THEN** 「重写这一章」卡不渲染（沿用「去写正文」路径）

### Requirement: 中栏「设定」页签（本章变化 / 截至本章）

- 章工作台中栏 SHALL 新增「设定」页签，含两个子视图：「本章变化」（本章写下的设定变化，含收尾提案采纳落地的条目，作者可编辑）与「截至本章」（开书设定＋按章序累积的既有设定，只读，条目标注来源章）。
- 「本章变化」的编辑 SHALL 保存回该章的数据来源（不新建账本对象）；「截至本章」SHALL 为派生投影（按各对象的来源章/章序过滤组合），SHALL NOT 引入第二份设定存储。

#### Scenario: 截至本章的投影
- **WHEN** 查看第 5 章的「截至本章」
- **THEN** 显示开书设定＋来源章不晚于第 5 章的设定变化，每条标注来源章

#### Scenario: 本章变化可编辑
- **WHEN** 作者在「本章变化」修改一条文字并保存
- **THEN** 保存写回该章的数据来源，刷新后仍在

### Requirement: 中栏「操作」页签与收尾进度

- 章工作台中栏 SHALL 新增「操作」页签：归档入口（沿用既有确认流）＋归档收尾进度区（按收尾行聚合：进行中/待确认/失败，可展开明细）。
- 每条待确认提案 SHALL 提供采纳/驳回操作；失败行 SHALL 提供重试；确认/驳回/重试 SHALL 即时反馈且不阻塞作者切换到其他章节继续写作。
- 收尾进度 SHALL 由收尾行聚合派生并轮询刷新（后台产出时前端可见推进）；免费档 SHALL 不渲染收尾进度区（以「PRO 可用」占位提示）。

#### Scenario: 归档后出现收尾进度
- **WHEN** PRO 作者归档一章
- **THEN** 「操作」页签出现收尾进度区，随后台完成从「进行中」转为「待确认 N」

#### Scenario: 逐条确认
- **WHEN** 作者采纳一条伏笔登记提案、驳回一条关系提案
- **THEN** 前者写回伏笔账本并标记已采纳，后者标记已驳回；两者都不阻塞作者继续写作

### Requirement: 归档确认含收尾计划预览

- 归档确认弹窗 SHALL 含「归档收尾」预览区：说明归档即刻生效、后台 AI 收尾的产出都进入「操作」页签待确认、**未确认的提案不参与后续章节的提示词**。
- PRO 档 SHALL 列出后台五件事：提取本章设定变化 / 更新角色关系 / 登记伏笔 / 识别世界要素 / 概括角色状态变化；免费档 SHALL 说明「归档即刻生效，不产生收尾提案」，SHALL NOT 列后台事项。

#### Scenario: PRO 归档前预览
- **WHEN** PRO 用户点「归档本章」打开确认弹窗
- **THEN** 预览区列出上述五件事与「未确认不参与提示词」说明

#### Scenario: 免费档说明无提案
- **WHEN** 免费用户打开归档确认
- **THEN** 预览区说明不产生收尾提案，且不列出后台事项

### Requirement: 角色关系页签按章投影

- 「角色关系」页签 SHALL 在全图之上叠加当前章投影：
  - 边中 `origin_chapter` 等于当前章的（本章新建/变化）SHALL 在图上高亮（线加粗着色）并在列表行标注「本章」；
  - 边行 SHALL 显示来源（`第 N 章 · 题名`；无来源＝「开书设定 · 全书统一」）与状态列（无来源＝开书设定；来源章带「基于旧设定」角标＝基于旧设定；否则＝随剧情演变）；
  - 图下 SHALL 列出孤立角色（无边节点）为「还没连线：A · B」行；无孤立时不渲染该行。
- 题名/角标取数失败 SHALL 静默降级（章号仍显示），不阻断关系图。

#### Scenario: 本章关系高亮
- **WHEN** 打开某章「角色关系」页签，且图中存在来源为该章的关系边
- **THEN** 该边在图上高亮、列表行标「本章」，其余边常态

#### Scenario: 状态与来源列
- **WHEN** 边来源章钩「基于旧设定」/无来源/普通来源
- **THEN** 状态列分别显示 基于旧设定 / 开书设定 / 随剧情演变，来源列显示对应章题或「开书设定 · 全书统一」

#### Scenario: 孤立角色提示
- **WHEN** 存在没有任何边的角色
- **THEN** 图下显示「还没连线：角色名 · …」

### Requirement: 右栏「AI 辅助」面板（随页签切换，动作全部落地）

- 章工作台右栏（章选中态）SHALL 提供「AI 辅助」面板，内容随中栏当前页签切换：每页签含一条引导语、一组统计卡（2-4 项）与动作清单；面板动作 SHALL 全部为真实链路按钮（无「规划中」占位）；动作不可用（未归档/未选中/无缺项/免费档）SHALL 以 `disabled` 表达，并带说明性 title。
- 卷选中态右栏 SHALL 提供随卷页签切换的语境面板：每页签含一条引导语与一组统计卡（2-4 项，口径如下）——卷纲页签（章数目标、已写章数、关键节点数、登场人物数）、本卷章节页签（章节总数、已归档、草稿/拟定、缺章纲章数）、角色关系页签（本卷关系边数、涉及实体数、全书关系边数）、伏笔页签（本卷埋下、本卷悬置、本卷回收、全书悬置）；卷选中态 SHALL NOT 渲染动作清单（卷域 AI 动作另行立项），也不得出现「规划中」占位卡。
- 未选中（含空书）时右栏 SHALL 呈现原型无语境 aiShell：`当前页签 / 未选` 行＋通用引导语（在左侧目录里选中一章或一卷…章纲检查、正文续写、提示词组装、设定与关系伏笔的检测）＋四格**全书**统计（当前主线／悬置伏笔／全书章节／基于旧设定）＋免费档脚注；SHALL NOT 出现卷域统计卡。悬置伏笔 SHALL 按需取 `GET /hooks` 计 active 条数，取数失败 SHALL 降级为「—」（与卷域统计同口径）。
- 已在中栏页签内提供的动作 SHALL NOT 在右栏重复。据此，以下三个动作 SHALL NOT 出现：提示词「重新组装提示词」（＝提示词页签内 AI 润色，且粗组稿每次重算）、关系「本章关系变化检测」（＝「操作」页签收尾提案的关系类）、伏笔「建议本章回收」（＝收尾提案的伏笔收束项）。
- 章纲页签 SHALL 在动作清单上方展示「还缺」清单（当前必填缺口标签），且与统计卡「归档门槛」同源。
- 免费档 SHALL 以既有 locked 口径呈现（`.rail-locked` 置灰禁点）。
- 统计卡数据 SHALL 来自与中栏页签相同的端点（按激活页签懒取；取数失败 SHALL 静默降级为「—」，不阻断面板）。
- 建表类动作（提取本章变化 / 识别角色与物品变化 / 登记新伏笔）SHALL 仅在章已归档时可用；检测族与精修族动作 SHALL 不受归档态限制（只读检查）。

#### Scenario: 面板随页签切换

- **WHEN** 在「章纲」与「正文」页签之间切换
- **THEN** 右栏面板标题与引导语随之切换（AI 辅助 · 章纲 ⇄ AI 辅助 · 正文），统计卡数值对应各页签口径

#### Scenario: 动作清单无占位

- **WHEN** 查看任一页签的动作清单
- **THEN** 每个按钮都有真实链路，不出现「规划中」标签；不可用的动作呈禁用态

#### Scenario: 卷选中态语境面板

- **WHEN** 选中一卷并切到「卷纲」页签
- **THEN** 右栏显示卷纲语境引导语与统计卡（章数目标/已写章数/关键节点/登场人物），无动作清单、无「规划中」卡

#### Scenario: 未选中态通用面板

- **WHEN** 写作页没有任何选中节点（空书，或删完章后未选中）
- **THEN** 右栏显示「当前页签：未选」、通用引导语与四格全书统计（当前主线／悬置伏笔／全书章节／基于旧设定），不出现卷域统计卡

#### Scenario: 章纲还缺清单

- **WHEN** 章纲必填项有缺口时查看章纲页签面板
- **THEN** 「还缺」清单列出缺口标签（与「归档门槛 N/6」一致）；缺口清零后清单消失

#### Scenario: 已实现动作可用

- **WHEN** PRO 用户在章纲页签点击「剧情推演」
- **THEN** 打开剧情推演弹窗（与中栏入口同链路）

#### Scenario: 重复动作不出现

- **WHEN** 查看提示词/关系/伏笔页签的动作清单
- **THEN** 不出现「重新组装提示词」「本章关系变化检测」「建议本章回收」

#### Scenario: 统计懒取与降级

- **WHEN** 切到提示词页签且来源接口正常
- **THEN** 统计卡显示组装来源处数与来源字数；接口失败时显示「—」且面板其余内容照常

### Requirement: 六类案头检查（ai-check）

- 章工作台 SHALL 提供六类只读案头检查：卷纲冲突、关系冲突、伏笔冲突、文风一致性、标记偏离段落、建议补边；检查类别由请求参数指定，未知类别 SHALL 返回 400。
- 检查 SHALL 读取本章章纲与正文，并按类别附加素材：卷纲类附本卷卷纲（含全书主线）、关系类附全书角色关系（取自角色与关系数据）、伏笔类附活跃伏笔台账、文风两类附全书文风基线（含本章影子调整）。
- 产出 SHALL 为 finding 列表（每条含对象/位置与问题依据），上限 8 条；没有发现问题 SHALL 返回空数组（不得为凑数编造）。
- 检查 SHALL 受 AI 访问与本书模型双门控（免费档 403，且不触达模型）。
- 产物 SHALL NOT 落库（就地弹窗消费）；用量 SHALL 按 `ai_check_{kind}` 记账，失败留 `_fail` 记录。

#### Scenario: 检查产出条目
- **WHEN** PRO 用户在文风页签点击「文风一致性检查」
- **THEN** 打开检测弹窗，逐条列出 finding（涉及对象/位置＋问题与依据）

#### Scenario: 没有发现问题
- **WHEN** 检查返回空数组
- **THEN** 弹窗显示「没有发现明显问题。」，不显示空列表

#### Scenario: 失败可就地重试
- **WHEN** 检查调用失败（超时/模型错误）
- **THEN** 弹窗就地显示错误消息，并提供「重新检查」再次发起

#### Scenario: 未知类别拒绝
- **WHEN** 请求携带未定义的检查类别
- **THEN** 返回 400，不触达模型

#### Scenario: 免费档不可用
- **WHEN** 免费档用户在任一页签查看检测动作
- **THEN** 动作呈禁用（`.rail-locked`），不发起任何检查请求

### Requirement: 提示词精修（提案制写回）

- 章工作台 SHALL 提供两种整章提示词精修：补全负向约束、精简提示词；未知模式 SHALL 返回 400。
- 精修 SHALL 以「当前提示词」为基底；未传时（未润色过的章）SHALL 以服务端组装稿为基底。
- 产物 SHALL NOT 落库：精修结果只在弹窗中只读展示，作者确认「采纳并保存」后 SHALL 走既有提示词保存链写回本章；「放弃」SHALL NOT 改动已存提示词。
- 精修结果为空 SHALL 返回 502 并可重试（不写入提示词存储）。
- 精修 SHALL 受 AI 访问与本书模型双门控；用量按 `prompt_refine_{mode}` 记账，失败留 `_fail` 记录。

#### Scenario: 精修预览不落库
- **WHEN** 作者点击「精简提示词」且模型返回结果
- **THEN** 弹窗只读展示修订稿；在点击「采纳并保存」之前，本章已存提示词保持不变

#### Scenario: 采纳并保存
- **WHEN** 作者在精修弹窗点击「采纳并保存」
- **THEN** 修订稿经既有提示词保存链写回本章，提示词页签随之刷新（`polished=true`），并提示已保存

#### Scenario: 放弃不改动
- **WHEN** 作者在精修弹窗点击「放弃」
- **THEN** 已存提示词与提示词页签内容均无变化

#### Scenario: 未润色章以组装稿为基底
- **WHEN** 本章尚无已存提示词时发起精修
- **THEN** 以服务端组装稿为输入（组装链六处来源照常），产出精修稿供确认

#### Scenario: 模式非法拒绝
- **WHEN** 请求携带未定义的精修模式
- **THEN** 返回 400，不触达模型

### Requirement: 卷/章页签结构同位（storyline 对齐）

- 章/卷编辑页中栏 SHALL 采用两段式结构：`e-head`（kicker＋标题＋状态徽章）→ 页签条（紧贴头部下缘）→ 滚动内容区；两视图页签条位置 SHALL 一致（原型 e-head→e-toolbar 口径）。
- 章页签顺序 SHALL 为：章纲→正文→提示词→设定→文风→角色关系→伏笔→操作（提示词 PRO-only；免费态七项）。
- 章编辑器排版控件（字号/行距/专注/版本历史/归档本章）SHALL 收在 e-head 右侧；章 body SHALL NOT 出现独立工具行。
- 卷视图内容区 SHALL 采用原型 `.e-pad` 衬垫（18px 22px 24px），卷纲六个分节（卷基础信息/本卷剧情/本卷登场人物/本卷关键剧情节点/伏笔与信息披露/章节拆分）SHALL 默认展开。
- AI 入口唯一化：章/卷页面 body SHALL NOT 设任何 AI 按钮；AI 生成正文、续写/润色/扩写、起草/推演/补缺/检测/精修/文风建议 SHALL 全部由右栏「AI 助手」承载。

#### Scenario: 章/卷页签条同位
- **WHEN** 分别选中一个卷与一个章（同一视口）
- **THEN** 两视图 `.ch-tabs` 页签条顶边 Y 坐标一致，头部与页签条之间无独立工具行或空行

#### Scenario: 章页签顺序
- **WHEN** PRO 用户选中一章
- **THEN** 页签条依次为 章纲/正文/提示词/设定/文风/角色关系/伏笔/操作；免费用户无提示词页签

#### Scenario: 卷视图衬垫与分节展开
- **WHEN** 打开卷视图「卷纲」页签
- **THEN** 内容区与页签条、左右缘之间有 18/22/24 衬垫，六个分节默认展开

#### Scenario: 章 body 零 AI 按钮
- **WHEN** 任意档位用户停在章的任一页签
- **THEN** 中栏 body 无 AI 按钮；AI 动作全部在右栏「AI 助手」（免费态置灰）

### Requirement: 中栏节奏单源（内容衬垫与版心）

书内三栏页的中栏内容节奏 SHALL 以单源变量定义一次（`.wb .view.on.three-col` 作用域）：内容衬垫 `--col-pad-t/-x/-b`（26px / clamp(20px,4vw,48px) / 60px，book.html 口径）与表单版心 `--col-measure`（76ch）；卷/章编辑区节奏 SHALL 以 `--col-pad-editor`（18px 22px 24px，storyline `.e-pad` 口径）单列。全部**内容型面板** SHALL 继承单源衬垫而非各自声明：

- 章页签：`.og-pane`/`.prompt-pane`/`.settings-pane`/`.style-pane`/`.relations-pane`/`.actions-pane`/`.hooks-wrap` 左右内容衬垫 SHALL 一致（同值同源）；
- 设定视图（settings-v）各面板 SHALL 具备列级内容衬垫；行级内容（文风表单行/操作卡等）SHALL 不超过 `--col-measure`；（写作空态由并行 change `c-0vol0ch-empty-state` 按新原型处理，不在本条范围）
- **通栏构件**（e-head／页签条／设定页 panel-head 与 panel-foot）SHALL 保持左右出血（不因内容衬垫而缩进），文字与内容对齐；
- **版心**：面板默认版心 660px（book.html `.panel`）；豁免清单 SHALL 显式声明且仅此三处——设定页 1180 上限（贴 AI 栏的既有决策）、`sub-fill` 双栏（角色/伏笔满栏）、卷壳面板（其字段自带 76ch 约束）。
- 实现 SHALL NOT 再以「先整列归零 `.col-panel`/`.panel`、再逐面板补衬垫」的模式维护节奏；新增面板 SHALL 自动继承单源。

#### Scenario: 设定页不再贴边

- **WHEN** 打开设定视图任一面板（简介/题材/世界/角色/主线/文风/伏笔）
- **THEN** 中栏内容左右具备列级衬垫（1440 视口下 48px），面板版心不超过声明上限（设定域 1180 / 其余 660），底部保存条保持通栏

#### Scenario: 章页签节奏一致

- **WHEN** 在章视图依次切换章纲/正文/提示词/设定/文风/角色关系/伏笔/操作页签
- **THEN** 各页签内容左右衬垫一致（同源变量），表单内容宽度不超过版心；正文阅读区（独立排版 680 居中）与卷视图（e-pad 18/22/24）节奏不回归

#### Scenario: 通栏条保持出血

- **WHEN** 查看章头部（e-head）、页签条（ch-tabs）或设定页底部保存条
- **THEN** 其底边线/顶边线仍横跨整栏（不因面板衬垫而缩进），条内文字与内容区左对齐
