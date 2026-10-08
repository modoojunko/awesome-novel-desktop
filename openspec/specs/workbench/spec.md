# workbench Specification

## Purpose

写作工作台的行为契约：骨架层（卷/章树、两栏布局与专注模式、底栏状态）承接 free-workspace 归档；章纲面板的右栏动作行为契约——入口可见性、动作行排序与失败语义（原「AI 起草」入口随 c-og-ai-draft-retire 退役）。

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

- 中栏 SHALL 呈现起手卡（`.e-empty`）：眉标（设定 N/7 已确认）＋「这本书怎么开始？」＋说明句（自己动手：
  先建一卷、排上第一章就能开写；想让 AI 按主线拆分卷，用右侧的 AI 助手）＋双入口「＋ 新增一卷」（主）／
  「＋ 新增一章」；中栏 SHALL NOT 出现 AI 动作按钮（AI 入口统一在右栏，见 `volume-plan-ai`）。
- 有卷、且本书**从未排过章**（章节总数为 0）时，中栏 SHALL 呈现**落点卡**：眉标「第N卷 · 名字 已就绪」
  ＋标题「开始写第一章？」＋说明（点左栏的卷排第一章；卷纲随时能回来改）＋「＋ 在本卷排第一章」（主）／
  「看第N卷的卷纲」／「＋ 新增一卷」；规划完卷（无论第几卷）SHALL 落在这里，SHALL NOT 停留在卷纲页。
- 其余未选中态（章节总数 > 0，或全部删空后曾经排过章）SHALL 呈现**书主页卡**：眉标为本书进度
  （卷数 · 章数 · 已归档 · 全书总字数）＋主入口「续写」（主线端点章：草稿回上次退出位置、拟定开该章章纲、
  待写先建再写，判据与文案同顶栏「续写」）＋「＋ 新增一卷」「＋ 新增一章」＋一句选章引导
  （「在左侧目录里选一章，上面一行页签会展开它的章纲、正文、提示词、设定与关系伏笔，重写与回退收在
  「操作」页签里」）。书主页卡 SHALL 是默认页——点「写作」、采纳保存回填落点、以及没有选中节点时都落这里；
  判据 SHALL 取「章节总数是否为 0」，SHALL NOT 只按「当前有没有选中节点」判——既有 e2e 口径随之改为
  「删掉最后一章仍见书主页卡与建书入口」。
- 左栏空书态 SHALL 呈现提示文案与底部两个入口「＋ 新增一章」「＋ 新增一卷」（虚线按钮，贴列底）；
  空书态 SHALL NOT 呈现「确认全部已填章节」（无章可确认）；非空书态左栏结构 SHALL 保持不变。
- 空书「＋ 新增一章」SHALL 先垫第一卷（程序默认序号形态「第一卷」，用户可改名）再排「第一章」，
  新章 SHALL 直接落在章纲页签，并在垫卷时提示已垫好第一卷。
- 各处「＋ 新增一卷」（顶栏空书卡／中栏起手卡／中栏落点卡／中栏书主页卡／左栏底部／树头「＋」）SHALL 打开
  **四问手写页**——让作家自己填空，**不分档位**（用户 2026-09-22 拍板）；该页 SHALL NOT 出现任何 AI 动作
  （不出现「让 AI 铺完剩下的问题」，四问提示文案 SHALL NOT 承诺「答不出的交给 AI」），缺失项的铺填 SHALL
  只经右栏 AI 入口（该页 SHALL 给出一句指向右栏「规划第N卷（AI）」的说明）。三选一抽卡 SHALL 只从右栏
  「规划第N卷（AI）」进（见 `volume-plan-ai`）。各入口 SHALL NOT 各自实现建卷路径；「添加卷」独立弹窗与
  「初始章数」字段 SHALL 退役（创建卷不问章数，落点卡「排第一章」逐章排）。

#### Scenario: New book reaches writing without settings
- Given 新建的书（0 卷 0 章）
- When 作者切到「写作」
- Then 中栏呈现起手卡与双入口（AI 入口在右栏），无「先去设定」拦截；左栏呈现空态提示与底部两入口

#### Scenario: 新增一卷按档分流

- **WHEN** 付费作家从起手卡点「＋ 新增一卷」，另一时刻免费作家点同一入口
- **THEN** 两者都直接进**四问手写页**（加号＝手动建卷，不分档位）；按档分流只发生在右栏
  「规划第N卷（AI）」：付费＝三选一抽卡弹窗、免费＝四问手写页——无独立添加卷弹窗

#### Scenario: 直接排第一章先垫卷
- Given 书里还没有任何卷
- When 作者点「＋ 新增一章」
- Then 先创建「第一卷」再排「第一章」，并直接打开该章章纲；左栏树上「第一卷」「第一章」可见

#### Scenario: 规划完卷落写作默认页
- Given 书里已有卷但没有章节
- When 作者保存一卷卷纲（或写作页没有任何选中节点）
- Then 中栏呈现落点卡（第N卷已就绪 / 开始写第一章？/ ＋在本卷排第一章 / 看第N卷的卷纲 / ＋新增一卷），不停留在卷纲页

#### Scenario: 有卷未选中只给选章引导
- Given 书里已有卷且曾经排过章
- When 写作页没有任何选中节点
- Then 中栏呈书主页卡：进度眉标＋「续写」＋「＋ 新增一卷」「＋ 新增一章」，并保留选章引导句；
  不出现起手卡，也不出现卷域 AI 动作

#### Scenario: 删空最后一章仍见书主页卡

- Given 书里已有卷且曾经排过章，现在章节被全部删掉
- When 写作页没有任何选中节点
- Then 仍呈书主页卡（判据＝章节总数是否为 0 与「曾排过章」标记双判），建书入口照常在

### Requirement: 页签回默认主页（写作／设定／预览）

书内模块导航的三个页签 SHALL 都是**回默认主页**的动作：不论当前停在哪个页签、该页内停在哪一步，
点该页签 SHALL 落到该页的默认落点——不是无操作、不是留在原处。三个默认落点：

- **写作** SHALL 落书主页：清空当前选中节点后呈现中栏默认页（内容见 `EmptyState without settings gating (N4)`），
  SHALL NOT 保留上次选中的章/卷。
- **设定** SHALL 落默认面板（第一项「简介」；面板顺序口径见 `intro-genre-settings`）。从别处进入设定本就从默认面板开始，
  本需求要的是**已在设定时重复点「设定」也把面板拨回默认**。
- **预览** SHALL 落全书首章（定档口径见 `preview-reader`）。

「任何入口」都成立：顶栏页签、设定左栏完成卡的「去写作」、预览空书出口的「去写作」都回它们各自的默认主页。

- 回默认前 SHALL 守卫未保存现场：卷纲表单有未保存修改时 SHALL 先确认（复用既有卷脏守卫文案与出口）；
  设定表单有未保存修改时 SHALL 先确认（复用既有设定脏守卫）；正文 AI 正在流式生成时 SHALL 先确认
  （明确告知会中断本次生成）——任一守卫被取消，SHALL 留在原位、不重置、不清选中。
- 回默认 SHALL NOT 改动其它入口的落点：左树点章/点卷、右栏「卷的验证」点行、「续写」、落点卡与书主页卡上的动作、
  预览内的目录点章与上一章/下一章，仍各自落它们的目标；打开书的默认落点（无章→设定／待完本→写作／已完结→预览，
  写作落点自动聚焦主线首章）SHALL NOT 被本需求改变——「打开书」与「点页签」是两件事。
- 书主页 SHALL 是**建书入口的唯一常驻处**：三态（零卷零章／有卷未排章／其余）
  SHALL 都给出「＋ 新增一卷」与「＋ 新增一章」两个入口，作者无需先选节点才能建卷建章。
- 各处「＋ 新增一卷」SHALL 打开与顶栏空书卡、左栏底部同一个**四问手写页**（作家填空，不分档位；
  见 N4 与 `volume-plan-ai`）；三选一抽卡 SHALL 只从右栏 AI 入口进，SHALL NOT 新增第二条建卷路径。

#### Scenario: 从章页点「写作」回主页

- **WHEN** 正停在第 3 章的正文页签时点「写作」
- **THEN** 中栏切到书主页（不再显示第 3 章的正文），左树保持展开与位置不变，章页的未保存内容按既有自动保存口径落库

#### Scenario: 从设定切回「写作」也落主页

- **WHEN** 在设定页点「写作」
- **THEN** 落书主页（不回到进入设定之前的那一章），且设定页的脏守卫口径不变

#### Scenario: 重复点当前页签也回默认

- **WHEN** 已在写作页（停在某章）、已在设定页（停在「世界」面板）、已在预览页（停在第十章）时，各自再点一次所在页签
- **THEN** 写作回书主页、设定回「简介」面板、预览回首章——三处都不是无操作、不是留在原处

#### Scenario: 预览不继承写作页当前章

- **WHEN** 在写作页停在第 5 章时点「预览」
- **THEN** 预览从中栏首章开始，而不是第 5 章；预览内的目录点章与「上一章／下一章」照常可用

#### Scenario: 卷纲未保存时先确认

- **WHEN** 卷纲表单有未保存修改时点「写作」
- **THEN** 先弹出离开确认；取消则留在卷纲页、修改保留；确认则回书主页并丢弃该表单修改（库中卷纲不变）

#### Scenario: 设定未保存时先确认

- **WHEN** 设定某面板有未保存修改时重复点「设定」
- **THEN** 先弹出确认；取消则留在原面板、修改保留；确认则拨回默认面板

#### Scenario: AI 生成中回主页先确认

- **WHEN** 右栏「生成正文」正在流式写入时点「写作」
- **THEN** 先确认会中断本次生成；取消则留在原章、生成继续

#### Scenario: 主页上能直接建卷建章

- **WHEN** 书里已有三卷十二章且没有任何选中节点
- **THEN** 书主页同时呈现「续写」（主线端点章）与「＋ 新增一卷」「＋ 新增一章」；点「＋ 新增一卷」打开四问手写页（作家填空）

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
- bar-here SHALL 在全书零卷零章时切换为「空书」态（「当前主线」态让位）：`空书` 引导词＋`第 1 章` 待写＋`未开始` 徽＋`还没有卷与章节`＋「＋ 新增一卷」按钮；该按钮 SHALL 打开**四问手写页**（作家填空，不分档位；三选一抽卡只从右栏 AI 入口进；c-volume-antagonist 起「添加卷」独立弹窗退役）。
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
- **THEN** bar-here 显示「空书 · 第 1 章待写 · 未开始 · 还没有卷与章节」与「＋ 新增一卷」按钮；点该按钮打开四问手写页（作家填空）

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

### Requirement: 角色关系页签（关系图为主表达）

- 系统 SHALL 提供 `GET /api/novels/{novel_id}/characters/graph` 返回全书关系图数据（节点＝角色/势力、边含关系类型与立场、孤立点清单）。
- 工作台 SHALL 提供「角色关系」页签：以确定性定距圆布图（SVG）渲染关系图，边标签为 `关系类型 · 立场`；SHALL 附文本清单作为兜底视图。
- 关系图为全书统一视图（不按章过滤）；无关系时 SHALL 呈现空态文案而非空白画布。
- **章打开态（c-chapter-relations-graph）**：页签以关系图为主表达（图在前），「本章关系变化」确认工作流区在后。图 SHALL 并入**截至本章**的剧情关系边，双源：往章演变边取 `GET /api/novels/{novel_id}/dossier/preview?up_to_ref={章ref}` 的 relations 域（与写章消费同一折叠单源：已采纳∧已归档∧非 stale，按 (owner,other) 后章覆盖）；本章边（已采纳＋待确认）取章档端点的本章关系行（与「本章关系变化」工作流区同源同态，SHALL NOT 要求本章已归档）。同向剧情边 SHALL 覆盖开书设定边；本章采纳边高亮、待确认行画虚线提案边，未登记名 SHALL 以虚线占位节点上图。本章边（采纳＋待确认）SHALL 由「本章关系变化」工作流区呈现（证据＋逐条/批量动作），文本清单兜底只列开书设定与往章演变边；行动作提交后图 SHALL 即时刷新剧情边。
- 关系图 SHALL 支持缩放与平移：默认整图适配视区（viewBox 全见）；滚轮以光标为锚缩放、拖拽平移，并提供 ＋/−/复位按钮（放大上限 4×，缩放下限＝整图适配）。
- 边 SHALL 带方向箭头（owner→other，落点在节点圆周外缘）；边色 SHALL 按关系极性着色——敌对红、友好绿、中性灰（按 rel_type 字面关键词归类，敌对优先），线宽/虚实/深浅只承载状态（开书设定淡、往章演变中、本章加重、待确认虚线）；图例 SHALL 附极性色键，行清单每行 SHALL 带极性色签。
- 节点 SHALL 按角色类型着色：主角实心品牌色（字用 on-accent 对比色）、反派红软底、配角默认白底、路人虚线圈（词表外历史值回落配角）；图例 SHALL 附四类节点色键。
- **卷选中态（c-volume-rels-live）**：页签呈**截至该卷末**的剧情投影（只读，无章高亮、无工作流区）。图 SHALL 并入截至本卷末章的剧情关系边：已归档部分取 `GET /api/novels/{novel_id}/dossier/preview?up_to_ref={本卷末章 ref}` 的 relations 域（折叠单源同章态：已采纳∧已归档∧非 stale，按 (owner,other) 后章覆盖）；投影范围内**未归档章**的已采纳关系行 SHALL 取章档端点并入投影（SHALL NOT 要求已归档）——卷页随时对齐本卷剧情最新的已确认关系。同向剧情边 SHALL 覆盖开书设定边；来源章卷号大于该卷的边（开书设定与剧情边同规则）SHALL 不显示；待确认提案行 SHALL NOT 上图（提案在章工作台确认）；未登记名 SHALL 以虚线占位节点上图。剧情边数据就位前页签 SHALL 呈加载态（SHALL NOT 先闪开书设定半成品图）；投影数据拉取失败 SHALL 静默退回开书设定边（不阻断图）。

#### Scenario: 关系图渲染
- **WHEN** 打开有角色关系的书的「角色关系」页签
- **THEN** 节点与边按确定性布局渲染，边标签显示关系类型与立场

#### Scenario: 章打开态剧情边上图

- **WHEN** 打开一章的「角色关系」页签，本章及往章已有已采纳的关系变化
- **THEN** 关系图在前：截至本章的剧情关系以实线边呈现（本章来源加重高亮、往章来源中间色，同向覆盖开书设定边），待确认变化以虚线提案边呈现；图下列出「本章关系变化」确认工作流；文本清单只列开书设定与往章演变边

#### Scenario: 行动作后图即时翻面

- **WHEN** 作者在「本章关系变化」采纳或驳回一条待确认关系
- **THEN** 关系图即时刷新：被采纳边由虚线转为高亮实线，被驳回边移除

#### Scenario: 卷态剧情边投影（c-volume-rels-live）

- **WHEN** 打开第 1 卷的「角色关系」页签，本卷某章已有已采纳的关系变化（含未归档章的已采纳行）
- **THEN** 图并入截至本卷末的剧情边（同向覆盖开书设定边，复用「随剧情演变」档），待确认提案不上图；图例标「截至第 1 卷末（只读投影）」并附剧情演变条数
- **WHEN** 来源章属于第 2 卷及以后
- **THEN** 该来源的剧情边与设定边都不进第 1 卷的投影

### Requirement: 章纲页签剧情推演入口

- 右栏「AI 助手」的章纲页签动作区 SHALL 提供「剧情推演」入口（归 `ai-plot`，仅 MAX 可用；归档章禁用；无该 key 的档位置灰禁点＋档位感知锁文案）；章纲页签 body 内 SHALL NOT 再设入口按钮。
- 弹窗 SHALL 按回合逐步展开：未走到的回合显示占位；当前回合 SHALL 先定走法（顺/拗）才能「推演下一个回合」；走法选定后 SHALL 就地回显走法结果句。
- 弹窗 SHALL 提供「重新推演」（重置回合与走法选择，重新取数）与「按这条走法收进章纲」（展开到末回合后出现）。
- **「收进章纲」的落点（c-og-slim-v2）**：走法行 SHALL **追加**为本章「剧情」区的一条剧情条目（`plot_items`），SHALL NOT 覆盖或清空既有条目；任一回合一「拗」→「推演走法 · 中途先接一次意外，再拉回主线」；全「顺」→「推演走法 · 顺着章纲节奏推进，不多加波折」；写入走章纲既有保存链（自动保存/手动保存同链），保存失败 SHALL 提示且弹窗不关闭。走法只作参考，SHALL NOT 自动改动章纲其它字段。**原「写入预期策略」的落点随该字段退役，SHALL NOT 复活。**

#### Scenario: 未定走法不能推进
- **WHEN** 当前回合未选择走法时点击「推演下一个回合」
- **THEN** 回合不展开并就地提示先选走法

#### Scenario: 收进章纲写预期策略
- **WHEN** 回合走完且任一回合一选择「拗」后点击「按这条走法收进章纲」
- **THEN** 本章剧情区新增一条「推演走法 · 中途先接一次意外，再拉回主线」并提示成功（原落点「预期策略」已随 c-og-slim-v2 退役，改追加为剧情条目，既有条目不变）

#### Scenario: 收进失败不丢内容
- **WHEN** 收进保存失败（网络或校验错误）
- **THEN** 提示失败、弹窗不关闭，剧情区既有条目保持不变

#### Scenario: 免费档入口置灰
- **WHEN** 免费档用户停留在章纲页签
- **THEN** 右栏「剧情推演」入口呈 rail-locked 置灰禁点（不隐藏）；章纲页签 body 无入口按钮

### Requirement: 文风页签（全档位：手工影子＋PRO 建议）

- 工作台 SHALL 提供「文风」页签（全档位可达）：承接全书文风基线（只读）＋本章覆盖行；本章影子行 SHALL 以**查看/编辑两态**呈现（c-ch-og-readonly）：默认只读文本行，「编辑影子」解锁行内编辑，「完成」退回查看态。
- 编辑态（「编辑影子」解锁后）SHALL 包含：已有行行内直改「取值/理由」（失焦保存）、「添加覆盖行」（选择参数行＋取值，取值非空才可添加）、逐行「还原」；产出 SHALL 经既有 PUT 影子端点落库（形状清洗口径不变）。
- 右栏触发后，建议列表与逐条「采纳」SHALL 呈现在文风页签内（两态皆可用）；采纳 SHALL 写影子并可在列表继续手工修改。文风建议（右栏「AI 建议本章调整」）SHALL 归 feature key `style-suggest`（标准档起发放；文风蒸馏 style-quant 仅 MAX——拆 key 口径见 tier-gating 词汇表，2026-10-05 终拍）。免费档页签内 SHALL NOT 呈现锁定占位说明（门控在右栏动作上）。
- 归档章 SHALL 不开放影子编辑：「编辑影子」入口禁用，行保持只读呈现；右栏建议动作 SHALL 禁用。

#### Scenario: 免费档手工编辑影子

- **WHEN** 免费档用户在「文风」页签点「编辑影子」
- **THEN** 影子行可增/改/还原（请求走 PUT 影子端点）；右栏建议动作置灰、页签内无触发按钮与占位拦截

#### Scenario: 默认查看态只读行

- **WHEN** 打开「文风」页签
- **THEN** 影子行以只读文本呈现（无输入框、无添加行、无还原按钮），「编辑影子」在场

#### Scenario: 添加覆盖行的取值门槛

- **WHEN** 编辑态下未选择参数行或取值为空时点击「添加」
- **THEN** 添加按钮保持禁用，不发起请求

#### Scenario: PRO 右栏触发并采纳 AI 建议

- **WHEN** PRO 用户在文风页签点击右栏「AI 建议本章调整」，建议列表出现后对某行点「采纳」
- **THEN** 该行写入影子（PUT）并在列表中可继续手工修改

#### Scenario: 归档章只读

- **WHEN** 打开已归档章的「文风」页签
- **THEN** 「编辑影子」禁用、影子行保持只读呈现，右栏「AI 建议本章调整」动作禁用

### Requirement: 中栏「伏笔」页签（章内台账投影）

- 章工作台中栏 SHALL 提供「伏笔」页签（全档位可达），位于「角色关系」与「操作」之间；内容为全书伏笔台账的**章内只读投影**：
  - 汇总行 SHALL 显示「N 条 · M 条悬置」，并在本章有埋下/回收时追加「本章埋下 N / 本章回收 N」；
  - 台账行 SHALL 显示编号、描述、埋点章（`第 N 章 · 题名`，无埋点章显示「开书」）与状态（悬置 / 已收 · 第 N 章 / 已弃）；
  - **本章埋下或本章回收的条目 SHALL 高亮**；
  - 空台账 SHALL 呈现引导文案（去「设定 · 伏笔」登记）。
- 废弃条目不进投影（c-hooks-abandoned-hidden）：页签 SHALL NOT 显示 status=abandoned 的条目（汇总行计数、本章埋下/回收计数、台账行、卷域投影同口径；恢复入口在设定页「显示已废弃」开关后）。
- 推进与该收了进投影（c-hooks-advance-ledger）：台账行 SHALL 附「最近推进 · 第 N 章」（`mentioned_chapter_id` 且晚于埋点章时显示）；`planned_chapter_id` 非空 ∧ 活跃 ∧ 计划章号 ≤ 当前章号 → 该行 SHALL 标「该收了」（卷域投影按该卷末章号同口径）。
- 页签 SHALL NOT 提供编辑入口（台账在设定页维护；AI 登记的伏笔登记提案在本页签顶部确认，见 archive-reconcile）。

#### Scenario: 本章条目高亮
- **WHEN** 打开某章「伏笔」页签，且存在埋于本章与收于本章的伏笔
- **THEN** 这两类条目高亮显示，其余条目常态；汇总行含「本章埋下」与「本章回收」计数

#### Scenario: 空台账引导
- **WHEN** 本书还没有伏笔条目
- **THEN** 显示「还没有伏笔条目」引导且不报错

#### Scenario: 废弃条目不出现在投影
- **WHEN** 台账 18 条活跃、15 条废弃，作者打开任一章「伏笔」页签
- **THEN** 台账只列 18 条（汇总行同值），无「已弃」行

#### Scenario: 推进与该收了在投影行可见
- **WHEN** 打开第 4 章的伏笔页签：一条活跃伏笔埋于第 1 章、最近推进于第 3 章、计划收束第 2 章
- **THEN** 该行显示「最近推进 · 第 3 章」并标「该收了」

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

- 章工作台中栏「操作」页签 SHALL 只承载生命周期卡（归档本章／重写这一章／回退到这里）与归档进度：归档卡 SHALL 以三段进度条呈现归档进度（c-ops-archive-stages）——**提取**（受理后 active 并随秒走针显示已运行时长；失败 fail；跳过/未提取 skip；已提取 done）、**确认**（有待确认提案时 active 并显示「待确认 N 条」，提案全处理完转 done，未归档不点亮）、**完成**（已归档点亮）；提取中锁定提示、失败重试、未提取补提取、重新归档入口不变（归档语义见 chapter-dossier）。
- 收尾提案区 SHALL NOT 出现在「操作」页签：伏笔登记提案在「伏笔」页签顶部、世界要素提案在「设定」页签（展示与采纳见 archive-reconcile）；收尾进度由收尾行聚合派生并轮询刷新（提案所在页签内推进可见）。
- 生命周期卡操作 SHALL 即时反馈且不阻塞作者切换到其他章节继续写作；免费档 SHALL NOT 渲染收尾区（无占位）。

#### Scenario: 归档后提案落在对应页签
- **WHEN** PRO 作者归档一章且收尾完成
- **THEN** 「操作」页签只有生命周期卡与归档进度，无提案行；伏笔/世界要素提案分别出现在「伏笔」「设定」页签

#### Scenario: 归档进度仍在操作页签
- **WHEN** 归档提取失败
- **THEN** 「操作」页签归档卡出现「重试提取」与（未归档章的）「跳过提取，仍要归档」入口，进度条提取段标失败

#### Scenario: 提取中进度条随秒推进

- **WHEN** 作者确认归档弹窗、后台提取受理
- **THEN** 归档卡进度条提取段点亮并显示已运行秒数，确认/完成两段不点亮

#### Scenario: 提取完成后待确认计数在卡上可见

- **WHEN** 提取完成、本章归档且产出 N 条待确认提案
- **THEN** 归档卡进度条提取段转完成态，确认段显示「待确认 N 条」，作者逐条确认后计数清零、确认段转「提案已处理」

### Requirement: 归档确认含收尾计划预览

- 归档确认弹窗 SHALL 含「归档收尾」预览区：说明**未确认的提案不参与后续章节的提示词**；全档 SHALL 列出后台两件事——登记伏笔（产出在「伏笔」页签确认）/ 识别世界要素（产出在「设定」页签确认），并说明设定变化／角色关系／物品／角色认知随归档自动提取、全档可用（归档 AI 全家免费，2026-09-30 拍板）；SHALL NOT 出现「提案为 PRO 能力」类文案。
- 已归档章的「重新归档」弹窗 SHALL 为重归档变体：说明以当前正文重提本章变化、**已采纳条目保留**（决策留给作家）、提取期间锁定、收尾提案不重跑；有既有章档行时 SHALL 说明「已确认 M 条将保留，其余 N−M 条由重提替换」，且收尾计划预览区 SHALL NOT 出现。

#### Scenario: PRO 归档前预览
- **WHEN** PRO 用户点「归档本章」打开确认弹窗
- **THEN** 预览区列出两件收尾及其页签去向、四域全档可用说明与「未确认不参与提示词」

#### Scenario: 免费档说明无提案
- **WHEN** 免费用户打开归档确认
- **THEN** 预览区照全档口径列出两件收尾及其页签去向与四域全档可用说明（归档 AI 全家免费），SHALL NOT 出现「提案为 PRO 能力」类文案

#### Scenario: 重新归档弹窗不含收尾计划
- **WHEN** 已归档章作者点「重新归档 · 重提本章变化」
- **THEN** 弹窗为重归档变体（警示覆盖 N 条含已采纳 M 条），收尾计划预览区不出现

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

- 章工作台右栏（章选中态）SHALL 提供「AI 助手」卡，内容随中栏当前页签切换。**布局全局统一（c-ai-rail-shared：公共前端布局，内容各域不同、造型三域一致；模版＝设定域）**：
  · 头部（`ra-head`）＝档位角标（`.plan-badge`，**随套餐**：免费版／标准会员／PRO 会员／MAX 会员／试用剩 N 天，文案单源＝账号菜单同源投影；档位未知时不标）＋标题（「AI 助手 · 页签名」）＋**可选**状态副行（只承载功能性状态：无 Key／缺模型／模型失效／能力包未就绪；SHALL NOT 出套餐营销文案——各档差异由角标＋能力行可用性体现：能用几行、其余行 ra-off＋行内 hint「需开通（标准档起）／PRO 专属／MAX 专属」（hint 单源 helper `upgradeHintOf(featureKey)`，SHALL NOT 硬编码字面量））；
  · 作用域行（`ai-target`，一行）＝本页签数据口径（正文字数/完成度、本章提示词状态与组装来源、悬置台账、全书基线等；章纲页签＝「还缺」缺口，与其同源「归档门槛」徽章口径一致）；
  · 能力行清单（`ra-step`）＝整行可点：名称（粗体）＋描述（会读什么、落到哪）＋`›` 箭头；运行中 SHALL 显示「生成中…」并经在途互斥（busyRef）串行；前置未满足（未归档/未选中/无缺项）SHALL `disabled`＋内联 hint；
  · 底部声明（`ra-foot`）＝本页签的来源/去向说明。
  ra-* 布局类 SHALL 为全局公共样式（`.rail-assist` 卡壳 + ra-head/ra-step/ra-body/ra-arrow/ra-foot/.locked），三域（设定/卷/章）共用；面板动作 SHALL 全部为真实链路（无「规划中」占位）。
- 卷选中态右栏 SHALL 呈现**验证面板**（同 ra-* 统一布局）：作用域行＝「当前页签 · 卷纲/本卷章节/…」＋能力行「体检这一卷」（归 `ai-plan`，标准档起；可重复）＋体检报告（对主线／对设定／对已写内容，口径见 `volume-plan-ai`）作为内容区保留在能力行与声明之间；SHALL NOT 复述本卷方向。原「卷选中态四页签统计卡」与原「卷域 AI 动作另行立项、不渲染动作清单」的占位由 `volume-plan-ai` 兑现并退役。
- 卷选中态右栏 SHALL **随卷页签重排**（与章页签同一「跟随当前页面」口径）：「当前页签」SHALL 显示真实页签名（卷纲／本卷章节／角色关系／伏笔，SHALL NOT 显示「卷的验证」这类动作名）；引导语 SHALL 按页签换焦（卷纲＝走向与结构；本卷章节＝已写内容与卷纲的出入；角色关系与伏笔＝本卷人物、伏笔在全书口径下是否成立）；体检报告三组 SHALL 按页签把相关一组前置（卷纲→对主线，本卷章节→对已写内容，角色关系与伏笔→对设定；组名按规范前缀归一，重名/顺序表外的组一组都不丢）。未体检时 SHALL 只呈现引导语与动作，SHALL NOT 预置空报告或假结论。
- 卷纲页签 SHALL 另提供「重新规划这一卷（AI）」入口（打开规划流、卷号＝本卷；生成类归 PRO），这是验证面板之外唯一的卷域动作；其余页签 SHALL NOT 出现与验证无关的辅助动作（统计卡与卷域动作清单不得复活）。
- 未选中态 SHALL 分两态：**零卷（空书）**＝「规划第一卷（AI）」入口卡＋「分卷依据 · 来自你的设定」（主线全景／结局三问／题材阶段／主要角色／目标篇幅；缺口标出、不拦）＋免费档脚注；**有卷未选中（书主页）**＝「接着往下规划」（「规划第N卷（AI）」）＋「卷的验证」（已有各卷一行：卷号 · 名字 · 章数目标，点一行＝选中该卷并立刻体检）＋免费档脚注。两态 SHALL NOT 出现卷域统计卡；原「未选中态四格全书统计（当前主线／悬置伏笔／全书章节／基于旧设定）」退役。
- 已在中栏页签内提供的动作 SHALL NOT 在右栏重复。据此，以下三个动作 SHALL NOT 出现：提示词「重新组装提示词」（＝生成正文弹窗内 刷新组装/存稿，且本次组装每次重算）、关系「本章关系变化检测」（＝「操作」页签收尾提案的关系类）、伏笔「建议本章回收」（＝收尾提案的伏笔收束项）。
- 章纲页签 SHALL 在动作清单上方展示「还缺」清单（当前必填缺口标签），且与中栏头部 meta 行「归档门槛」徽章同源（同一必填缺口口径）——**必填为两项（必须完成的变化、主情绪），门槛分母 SHALL 由必填项数派生（`N/2`），SHALL NOT 硬编码数字**（c-og-slim-v2 修正「六改四」遗留的 `N/6` 错值；c-og-rail-declutter 起该门槛的展示位在中栏头部 meta 行）。
- 正文页签动作清单 SHALL 为：生成正文（首项；点击打开 AiModal 提示词预览；归档章 `disabled`＋内联 hint「已归档 · 恢复编辑后可用」——「解除只读」页面级解锁链保持退役（c-archived-readonly：小改走横幅「恢复编辑」、整体重写走「重写这一章」）；`testid=ai-write-btn`）→ **去AI味（单张动作卡，`testid=ai-polish`；未选中段落时置灰并带「先在正文选中一段」hint；无 MAX 权益时 hint「MAX 专属」、进行中「生成中」）** → 朱雀 AI 检测行（见 zhuque-workbench）。原全页签常驻的「AI 生成正文」工具卡与逐张 `.ai-tool` 卡 SHALL 退役（c-prose-write-entry/c-ai-rail-shared）：这些动作 SHALL NOT 以旧卡片形态出现在右栏；「补全负向约束／精简提示词」精修两行 SHALL NOT 出现在动作清单（正文 tab 收编后随功能整体退役）；续写建议行与「段落加工」三卡组（场景扩写、压缩啰嗦段落）SHALL NOT 出现（c-retire-continue-writing／c-retire-selection-transforms：段落加工由去AI味单卡承接）。
- 无对应 feature key 的档位 SHALL 以整卡锁定呈现（`.rail-assist.locked`：行降透明、角标转灰）；能力行 SHALL 保持可点，点击经统一门控 `onBlocked` 收口到升级弹窗（`UpgradeModal`），SHALL NOT 各自弹不同提示；「体检这一卷」与规划入口（卷域）归 `ai-plan`（标准档起），对无该 key 的档位随卡锁定。
- **升级弹窗目标档 SHALL 按被触发能力所需档（`tier_required`）**：能定位到被点那一行的出口（如卷页签拆章行/规划台铺空缺 → `ai-plan`、朱雀检测行 → `ai-detect`）SHALL 把该行 feature key 传进弹窗，弹窗出**该档**口径与权益（标准/PRO/MAX 三套）；全局入口（本书偏好/账号区）不带 key 时 SHALL 回退——**已有 PRO（含试用）者出 MAX，否则出 PRO**（免费也出 PRO：全局入口不指具体件，PRO 是正文 AI 的起点）。SHALL NOT 对已含该能力的档位重复喊同一档。
- **章纲页签行级出口**：未到 `ai-generate`（免费/标准）SHALL 在能力行下方给一枚「升级套餐」按钮（SHALL NOT 附说明文案——锁定行自带行级 hint）；已含 `ai-generate` 的档位 SHALL NOT 出现该出口（其剩余锁定行属 MAX，由行内 hint 承载）。
- 作用域行与能力行所需数据 SHALL 来自与中栏页签相同的端点（按激活页签懒取；取数失败 SHALL 静默降级为「—/…」，不阻断面板）；章纲页签 SHALL NOT 渲染统计卡（其数值以中栏头部徽章承载）。

#### Scenario: 面板随页签切换

- **WHEN** 在「章纲」与「正文」页签之间切换
- **THEN** 右栏卡标题随之切换（AI 助手 · 章纲 ⇄ AI 助手 · 正文），作用域行数值对应各页签口径；章纲页签不出现统计卡（其数值以中栏头部徽章承载）

#### Scenario: 动作清单无占位

- **WHEN** 查看任一页签的动作清单
- **THEN** 每个按钮都有真实链路，不出现「规划中」标签；不可用的动作呈禁用态

#### Scenario: 章纲还缺清单
- **WHEN** 章纲必填项（必须完成的变化、主情绪）有缺口时查看章纲页签面板
- **THEN** 作用域行列出缺口标签（与中栏头部「归档门槛 N/2」徽章一致）；缺口清零后显示「必填已齐」

#### Scenario: 门槛分母随必填项派生
- **WHEN** 某章两项必填都已填、其余留存格子为空
- **THEN** 中栏头部 meta 行「归档门槛」徽章显示 `2/2`，SHALL NOT 显示 `6/6`、`6/4` 一类与必填项数不符的分母

#### Scenario: 卷选中态语境面板

- **WHEN** 选中一卷
- **THEN** 右栏显示这一卷的验证引导语与「体检这一卷」动作（归 `ai-plan`，标准档起；无该 key 的档位随卡锁定），不出现本卷方向复述、
  不出现与验证无关的辅助动作、不出现四页签统计卡

#### Scenario: 卷页签右栏跟随

- **WHEN** 在卷页签「卷纲」与「本卷章节」之间切换
- **THEN** 右栏「当前页签」随之显示「卷纲」／「本卷章节」，引导语随之切换；已体检时报告把「对主线」／「对已写内容」分别前置

#### Scenario: 从卷纲页签重新规划这一卷

- **WHEN** 在卷页签「卷纲」点「重新规划这一卷（AI）」
- **THEN** 打开规划流、卷号为本卷；确认后更新这一卷的卷纲，不新建卷

#### Scenario: 空书态右栏是规划入口

- **WHEN** 零卷零章的书切到「写作」
- **THEN** 右栏显示「规划第一卷（AI）」入口与「分卷依据 · 来自你的设定」，不出现四格全书统计

#### Scenario: 未选中态通用面板

- **WHEN** 书里已有卷、写作页没有任何选中节点
- **THEN** 右栏显示「接着往下规划」（规划第N卷）与「卷的验证」（已有各卷一行），点其中一行即选中该卷并体检

#### Scenario: 已实现动作可用

- **WHEN** MAX 用户在章纲页签点击「剧情推演」
- **THEN** 打开剧情推演弹窗（与中栏入口同链路）

#### Scenario: 重复动作不出现

- **WHEN** 查看关系/伏笔页签的动作清单
- **THEN** 不出现「本章关系变化检测」「建议本章回收」；提示词调整只发生在生成正文弹窗内（刷新组装/编辑/存稿——原「AI 润色」入口随 c-retire-prompt-polish 退役，提示词不再有 AI 改写入口），右栏不再设「重新组装提示词」

#### Scenario: 统计懒取与降级

- **WHEN** 切到某页签且其数据接口正常/失败
- **THEN** 作用域行显示该页签口径（伏笔页签悬置与台账总数、正文页签本章提示词状态与组装来源字数）；接口失败时显示「—/…」且面板其余内容照常

#### Scenario: 生成正文入口在正文页签面板

- **WHEN** 在章纲页签查看右栏，再切到正文页签
- **THEN** 章纲页签右栏无「生成正文」按钮；正文页签动作清单首项为「生成正文」，点击走解锁链/AiModal，确认生成后编辑器可见

#### Scenario: 三域同构（设定/卷/章同一卡）

- **WHEN** 分别在设定页、卷选中态、章选中态查看右栏
- **THEN** 三处均为同一张 AI 助手卡（ra-head 头部＋作用域行＋能力行＋底部声明），仅标题、作用域行数值与能力行内容不同

#### Scenario: 免费档统一升级出口

- **WHEN** 免费档点击任一 AI 能力行
- **THEN** 动作不执行，弹出统一升级弹窗（不出现各自文案的独立提示）；弹窗目标档＝PRO

#### Scenario: 卡头角标随套餐（不出套餐文案）

- **WHEN** PRO 会员查看章纲页签右栏
- **THEN** 卡头角标显示「PRO 会员」、副行不出现任何套餐文案；「剧情推演」行呈置灰并标「MAX 专属」，其余行可用——档位差异只由角标与能力行可用性体现

#### Scenario: 已含 ai-generate 的档位不再被推升级

- **WHEN** PRO 会员查看章纲页签右栏
- **THEN** 能力行下方不出现「升级套餐」按钮（无行级出口）

#### Scenario: 弹窗目标档按被点那行（tier_required）

- **WHEN** 免费用户点章纲页签行内出口（其锁定行所需最低档＝`ai-plan`）、或标准用户点朱雀检测行（`ai-detect`）
- **THEN** 弹窗标题与权益分别为「升级标准 · 解锁 AI 能力」与「升级 PRO · 解锁 AI 能力」；不带 key 的全局入口回退为「已有 PRO 出 MAX、否则出 PRO」

#### Scenario: 未选段时段落动作折叠为分组行

- **WHEN** 正文页签未选中任何段落时查看动作清单
- **THEN** 「去AI味」为单张动作卡（`testid=ai-polish`），未选中段落时置灰并带「先在正文选中一段」提示；选中段落后卡片可用，生成正文一行不受影响。扩写与压缩两动作已随 c-retire-selection-transforms 退役，SHALL NOT 出现

### Requirement: 右栏纯 AI 助手（本章进度卡退役）

- 章选中态右栏 SHALL 只承载 AI 相关功能（生成正文入口、随页签的「AI 辅助」面板、免费态 PRO 升级卡）；原「本章进度」块（大百分数/进度条/目标字数就地编辑/进度提示语/「本章已归档 · 只读查看」卡/本书总字数等 mini 统计）SHALL 退役（c-rail-ai-only）。
- 与头部徽章重复的项（本章字数/计划字数）SHALL NOT 在右栏重复展示；非重复两项收编中栏头部 meta 行（承载见「卷/章页签结构同位」）：完成度 `N%` 与本书总字数。
- 目标字数就地编辑 SHALL 退役：改值 SHALL 走章纲「本章目标字数」格（同一 `word_target`，既有 500-6000 区间校验照常生效）。
- `RailChapterData` 数据通道 SHALL 全量保留（字数/目标/归档态/动作回调随通道上抛，右栏仅不再渲染进度块）。

#### Scenario: 头部徽章收编进度信息

- **WHEN** 查看章视图头部 meta 行
- **THEN** 含「完成度 N%」与「本书总字数 N」徽章，随正文保存即时更新；右栏不再出现进度块

#### Scenario: 右栏无进度块

- **WHEN** 停在章的任一页签查看右栏
- **THEN** 右栏只有 AI 相关功能，不出现「本章进度」标题、目标字数编辑或 mini 统计

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

### Requirement: 章提示词查看与存稿（生成正文弹窗承载）
「提示词」页签退役后（c-prompt-tab-retire），本章提示词的查看/编辑/落库三层 SHALL 落位如下：

- **状态（常驻）**：正文页签 AI 助手卡作用域行 SHALL 显示「本章提示词 自动组装/已自定义」与组装来源字数（懒取，失败降级「…」）。
- **全文（查看/编辑）**：「生成正文」弹窗打开时 SHALL 展示当前最新提示词（每次打开重新拉取/组装，含截至上一章的动态内容）；作者 SHALL 可直接编辑。只查看不生成 SHALL 通过关闭弹窗完成，SHALL NOT 有副作用（不组装不落库不烧 token）。
- **存稿（落库）**：弹窗 SHALL 提供「存为本章提示词」：经 `PUT /novels/{id}/chapters/{ref}/prompts/write` 落库，此后每次生成 SHALL 沿用该稿（`polished=true`）；**生成即落库**：点「生成正文」后本次实际使用的提示词稿 SHALL 落库为本章提示词行（`POST /write` 既有行为）——原「不点存稿的编辑 SHALL 仅用于本次生成，SHALL NOT 改动已存提示词」表述与实现相悖，随本 change 更正；「存为本章提示词」提供不生成、只落库的入口。
- 存稿成功后 SHALL 通知页面刷新状态行（`promptSavedSignal` 链路；原「弹窗内 AI 润色成功」触发方随 c-retire-prompt-polish 退役）；原「提示词」中栏页签、页签徽标「已自定义/自动组装」与整章提示词管理页 SHALL 退役。

#### Scenario: 状态行随存稿刷新

- **WHEN** 在弹窗编辑提示词并点「存为本章提示词」
- **THEN** toast 提示已保存；关闭弹窗后正文页签作用域行显示「本章提示词 已自定义」

#### Scenario: 只查看不生成零副作用

- **WHEN** 打开「生成正文」弹窗仅阅读/核对提示词后点「取消」
- **THEN** 不发起生成、不落库，提示词存储与状态行不变

#### Scenario: 不存稿的编辑仅用于本次

- **WHEN** 编辑提示词后直接点「生成正文」（不点存稿）
- **THEN** 本次生成使用编辑稿；重开弹窗仍显示已存稿（未落库的编辑不保留）

### Requirement: 卷/章页签结构同位（storyline 对齐）
- 章/卷编辑页中栏 SHALL 采用两段式结构：`e-head`（kicker＋标题＋徽章行）→ 页签条（紧贴头部下缘）→ 滚动内容区；两视图页签条位置 SHALL 一致（原型 e-head→e-toolbar 口径）。章视图徽章行 SHALL 为八枚：状态（拟定/草稿/已归档）、正文字数、归档门槛 `N/2`、计划字数、完成度 `N%`、剧情条数、出场角色数、本书总字数——归档门槛/计划字数/剧情/出场角色为章纲统计（c-og-rail-declutter 自右栏 AI 助手章纲页签统计卡上移，口径与右栏数据通道同源：分母按必填项数派生、计划字数按本章目标字数兜底）；完成度＝正文字数/计划字数（计划字数未定 SHALL NOT 渲染该徽章）与本书总字数自右栏「本章进度」卡收编（c-rail-ai-only，见「右栏纯 AI 助手」）；卷视图徽章行维持状态类徽章，SHALL NOT 出现章纲统计。
- 章页签顺序 SHALL 为：章纲→正文→设定→文风→角色关系→伏笔→操作（七项，全档一致；「提示词」页签自 c-prompt-tab-retire 退役——提示词的查看/编辑/存稿由「生成正文」弹窗承载，见「章提示词查看与存稿」）。
- 章编辑器控件布局（c-og-rail-declutter 收敛）：字号/行距切换 seg SHALL 退役（改值唯一入口＝账号菜单「本书偏好」，工作台对既有书级偏好只读回显，`ProsePane` 排版数据流不变）；专注按钮 SHALL 收在 e-head 右侧；版本历史入口 SHALL 在页签条右端（`.ch-history`，右对齐、弹窗不变）；「归档本章」SHALL 在「操作」页签首卡（`ArchiveModal` 确认弹窗与守卫不变：已归档/空章置灰并带说明 title；旧稿支线章 SHALL NOT 渲染归档卡，与重写/回退卡同口径）。头部右侧 SHALL NOT 再设归档/版本历史/排版 seg；章 body SHALL NOT 出现独立工具行。
- 卷视图内容区 SHALL 采用原型 `.e-pad` 衬垫（18px 22px 24px），卷纲六个分节（卷基础信息/本卷剧情/本卷登场人物/本卷关键剧情节点/伏笔与信息披露/章节拆分）SHALL 默认展开。
- AI 入口唯一化：章/卷页面 body SHALL NOT 设任何 AI 按钮；AI 生成正文、去AI味、起草/推演/补缺/检测/文风建议 SHALL 全部由右栏「AI 助手」承载。

#### Scenario: 章/卷页签条同位
- **WHEN** 分别选中一个卷与一个章（同一视口）
- **THEN** 两视图 `.ch-tabs` 页签条顶边 Y 坐标一致，头部与页签条之间无独立工具行或空行

#### Scenario: 章页签顺序
- **WHEN** 任意档位用户选中一章
- **THEN** 页签条依次为 章纲/正文/设定/文风/角色关系/伏笔/操作（七项，免费与 PRO 一致；不出现「提示词」页签）

#### Scenario: 头部徽章行随章纲即时更新
- **WHEN** 某章两项必填已填、剧情已写两条，查看章视图头部
- **THEN** 徽章行显示 归档门槛 `2/2`、剧情 `2 条`、出场角色数与计划字数，且随章纲表单编辑即时更新；右栏章纲页签不再重复展示这四项，完成度与本书总字数随正文保存即时更新

#### Scenario: 版本历史与归档的新落位
- **WHEN** 已写正文的章停在任一页签
- **THEN** 版本历史按钮在页签条右端、点击打开历史弹窗；「归档本章」只出现在「操作」页签首卡且头部无归档按钮；已归档或空章时该卡按钮置灰并带说明 title；旧稿支线章不渲染归档卡

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
- **列内滚动**：五个内容页签容器（`.settings-pane`/`.style-pane`/`.relations-pane`/`.actions-pane`/`.hooks-wrap`）SHALL 自带列内滚动契约（`flex:1; min-height:0; overflow-y:auto`，同 `.og-pane` 口径）——`.wb` 封顶视口且 `overflow:hidden`，页签内容超过视口高 MUST 在本页签内滚动可达，页面整体 MUST NOT 出现滚动（#586 实锤：长伏笔台账被裁不可达）。
- 实现 SHALL NOT 再以「先整列归零 `.col-panel`/`.panel`、再逐面板补衬垫」的模式维护节奏；新增面板 SHALL 自动继承单源。

#### Scenario: 超高页签内容可滚动到达

- **WHEN** 任一内容页签（设定/文风/角色关系/伏笔/操作）的内容超过视口高（如伏笔台账数十条、归档提案多行）
- **THEN** 超出部分在该页签容器内滚动可达（`overflow-y:auto`），页面整体不出现滚动条；章纲/正文仍由各自滚动容器（`.og-pane`/`.editor-wrap`）承载，通栏头部与页签条保持常驻

#### Scenario: 设定页不再贴边

- **WHEN** 打开设定视图任一面板（简介/题材/世界/角色/主线/文风/伏笔）
- **THEN** 中栏内容左右具备列级衬垫（1440 视口下 48px），面板版心不超过声明上限（设定域 1180 / 其余 660），底部保存条保持通栏

#### Scenario: 章页签节奏一致

- **WHEN** 在章视图依次切换章纲/正文/提示词/设定/文风/角色关系/伏笔/操作页签
- **THEN** 各页签内容左右衬垫一致（同源变量），表单内容宽度不超过版心；正文阅读区（独立排版 680 居中）与卷视图（e-pad 18/22/24）节奏不回归

#### Scenario: 通栏条保持出血

- **WHEN** 查看章头部（e-head）、页签条（ch-tabs）或设定页底部保存条
- **THEN** 其底边线/顶边线仍横跨整栏（不因面板衬垫而缩进），条内文字与内容区左对齐

### Requirement: 建卷建章入口防重复提交

所有建卷/建章入口（空书架卡、空书落点卡、左栏加号、卷页签与章页签内的新增入口等）SHALL 在提交进行中禁用并置忙；重复触发 MUST NOT 产生第二次创建请求，或由服务端幂等吸收（同签名请求返回同一结果）。失败时入口 SHALL 恢复可点并给出可读原因（err 语气 + 可点击出口）。

#### Scenario: 双击只建一卷

- **WHEN** 用户在空书架卡上快速双击「新增一卷」
- **THEN** 只产生一卷；不出现 UNIQUE 冲突错误，也不出现两卷

#### Scenario: 提交中入口禁用

- **WHEN** 建章请求进行中
- **THEN** 该入口呈置忙禁用态，无法再次触发

#### Scenario: 失败可重试

- **WHEN** 建卷请求失败（网络/服务端拒绝）
- **THEN** 入口恢复可点，界面给出可读原因与重试出口

### Requirement: 章纲页签查看/编辑两态

- 章纲页签 SHALL 默认呈现**查看态**：留存格子（概要/出场角色/挑战/阶段/兑现与约束四格/主情绪/读者获得/章末落点/目标字数/剧情条目）以只读一页纸呈现，未填格 SHALL 给出未填占位（不隐藏）——**回收/悬念两格除外**：空置时按「章纲回收/悬念两格接伏笔台账」呈现台账投影或理由句，SHALL NOT 显示「（未填）」占位；必填缺口 SHALL 以 chip 呈现；查看态 SHALL 提供「编辑章纲」入口（章纲载入中 SHALL 以载入占位替代内容，入口禁用）。
- 查看态 SHALL 保留「确认章纲」（缺口清零才可点）与「去写正文」两个动作；已确认态 SHALL 另提供**「撤回确认」**（c-og-draft-no-autconfirm）：确认弹窗告知后果（章纲回到草稿态，确认按钮恢复可点）后把本章章纲退回草稿态，「确认章纲」按钮恢复可点，树上确认计数随批回落；撤回 SHALL NOT 动正文、归档态与章档数据。
- 「编辑章纲」SHALL 进入编辑态：既有章纲格子表单、剧情区编辑与保存链（保存草稿/确认章纲/3s 静默自动保存）不变；编辑态 SHALL 提供「取消」——按最近一次落库值（含自动保存）回退表单并退出编辑态。
- **「保存草稿」只保存（c-og-draft-no-autconfirm）**：保存链落库成功后呈「草稿已保存」，SHALL NOT 改变本章确认状态——无必填缺口时也 SHALL NOT 自动确认（旧「无缺项自动确认」行为退役）；确认 SHALL 只由「确认章纲」显式触发。
- 查看态缺口 chip 点击 SHALL 进入编辑态并滚动聚焦对应格子；右栏「补全缺失字段」成功回填后 SHALL 直接进入编辑态（产物须过目）。
- 切换章节 SHALL 回落查看态；正文/提示词/设定/文风关系投影/伏笔/操作各页签 SHALL NOT 受本条两态约束（正文有自己的只读语义，提示词内部自带查看/编辑两态）。

#### Scenario: 默认查看态

- **WHEN** 选中一个章纲未确认的章并停在「章纲」页签
- **THEN** 呈只读一页纸＋必填缺口 chip，「编辑章纲」可点，「确认章纲」缺口清零才可点

#### Scenario: 保存草稿不再自动确认（c-og-draft-no-autconfirm）

- **WHEN** 在编辑态点「保存草稿」且本章必填两项已齐、此前未确认
- **THEN** 落库成功呈「草稿已保存」，章保持草稿态（无「已确认」徽标、树上确认计数不变）；「确认章纲」按钮仍可点

#### Scenario: 撤回确认（c-og-draft-no-autconfirm）

- **WHEN** 已确认章的查看态点「撤回确认」并在确认弹窗选「撤回」
- **THEN** 章退回草稿态：「已确认」徽标消失、「确认章纲」恢复可点、树上确认计数回落；正文与归档态不变；弹窗选「保留确认」则章保持已确认

#### Scenario: 进编辑态与取消

- **WHEN** 点「编辑章纲」修改任一格子后点「取消」
- **THEN** 表单回退到最近一次落库值并回到查看态（3s 自动保存已落盘的改动不在回退之列）

#### Scenario: 查看态缺口 chip 直达编辑

- **WHEN** 查看态点击缺口 chip（如「必须完成的变化」）
- **THEN** 进入编辑态并滚动聚焦该格子

#### Scenario: AI 起草产物落在编辑态

- **WHEN** 右栏「补全缺失字段」成功回填（原口径为「AI 起草」产物——该入口已随 c-og-ai-draft-retire 退役，本条按留存同族口径执行）
- **THEN** 页签直接处于编辑态，产物在表单中可见可改

#### Scenario: 归档章章纲只读（c-archived-readonly）

- **WHEN** 打开已归档章的「章纲」页签（含归档前正停在编辑态的情形）
- **THEN** 恒呈只读一页纸＋归档横幅（「恢复编辑」出口在场；整体重写指路「重写本章」），「确认章纲」「去写正文」「编辑章纲」「撤回确认」均不在场；点缺口 chip 不进编辑态；章纲状态徽呈终态「已归档」

### Requirement: 章纲回收/悬念两格接伏笔台账

章纲查看态的「必须在本章回收」「必须维持悬念」两格 SHALL 接伏笔台账投影（c-og-hooks-projection）：

- 两格为空时 SHALL NOT 显示「（未填）」：回收格显示**计划收 ≤ 本章**的悬置伏笔投影（「该收了」判定与伏笔页签同口径），维持格显示**埋点 ≠ 本章**的悬置伏笔投影（与写作注入「排除本章引入」同口径，无埋点的开书条目计入）；每条带 `[编号] 描述` 与来源标注（计划收 第 N 章/埋于 第 N 章/开书），投影区 SHALL 注明「来自伏笔台账 · 可在编辑章纲勾选为正式条目」。
- 投影为空时 SHALL 给出理由句：台账无悬置伏笔／悬置伏笔的计划收均不在本章或未设计划收／悬置伏笔均由本章埋设。
- 两格非空时 SHALL 只呈现格内内容，SHALL NOT 并列投影。
- 编辑态两格文本域下方 SHALL 挂台账候选 chips（本格已含编号的不再列；回收格按该收了优先排序并带标）；点选 SHALL 把 `[编号] 描述` 追加为一行并走既有保存链（3s 自动保存/手动保存），SHALL NOT 清空既有行。
- 投影 SHALL 为纯派生展示，SHALL NOT 落库；台账「计划收」SHALL NOT 被本能力自动赋值。

#### Scenario: 空格显示台账投影

- **WHEN** 某章「必须在本章回收」为空且台账存在计划收 ≤ 本章的悬置伏笔
- **THEN** 回收格显示这些伏笔的 `[编号] 描述（计划收 第 N 章 · 该收了）` 投影与来源注脚，不显示「（未填）」

#### Scenario: 投影空时给理由

- **WHEN** 某章两格为空且台账悬置伏笔均未设计划收章
- **THEN** 回收格显示理由句（计划收均不在本章或未设），维持格按埋点口径投影或给对应理由

#### Scenario: 编辑态勾选落格

- **WHEN** 编辑态点回收格候选 chip `[H-0009] 猎血短刃的异常威力`
- **THEN** 文本域追加一行 `[H-0009] 猎血短刃的异常威力`，既有行不动，走自动保存落库；该 chip 从候选中消失

#### Scenario: 格非空不并列投影

- **WHEN** 两格任一已有作者填写的条目
- **THEN** 该格只显示格内内容，不渲染台账投影

### Requirement: 正文页签查看/编辑两态

- 正文页签 SHALL 默认呈现**查看态**：编辑器不可编辑（contenteditable=false），顶部一行呈现「正文 · 已写字数（空章标注）」与「编辑正文」入口；切章 SHALL 回落查看态。
- 「编辑正文」SHALL 进入编辑态：段落化输入、自动保存三态、AI 流式写入等既有写作能力不变；编辑态 SHALL NOT 提供「取消/还原」入口（正文无未保存回退语义；退出编辑态＝切页签/切章，或点编辑态顶条「完成」回查看态）。
- 进入编辑态 SHALL 有明确可见反馈：编辑态呈现一个**成形编辑框**——顶条（「正在编辑正文 · N 字」＋「写完自动保存」＋「完成」）与正文区以同底色、连体外框（上圆角条＋下圆角内容区）合成一个控件，正文区取可编辑容器样式（`--surface`/`--border` 语义）；查看态与编辑态 SHALL 一眼可辨。编辑框正文列（含生成中呼吸灯）SHALL **撑满中栏滚动区剩余高度**（c-prose-edit-fill-height）：内容不足一屏时框沿直通状态栏上方、底部留白与顶部对称，框内空白为可点击聚焦的书写面；内容超出一屏时照常滚动（c-prose-edit-affordance / c-prose-edit-fill-height）。
- 编辑框顶条 SHALL 提供**撤销／重做**图标按钮（真实历史链路；无步可撤／可重时置灰）。SHALL NOT 提供加粗/斜体/标题等格式按钮（纯文本存储下无法持久化）；真格式能力另立富文本存储立项。
- 点「编辑正文」进编辑态后 SHALL 聚焦编辑器且光标落文末（继续写作的自然位置）。
- 写/生成意图 SHALL 自动进入编辑态：右栏「生成正文」确认（含解锁链后的生成）、顶栏「续写」恢复、「重写这一章」确认、章纲「去写正文」。进入编辑态后既有聚焦/滚动恢复行为不变。
- 归档、排队门禁（frontier）、旧稿支线三套锁定语义 SHALL 优先于编辑态：锁定期 SHALL NOT 出现「编辑正文」入口，编辑器保持不可编辑，既有锁定横幅照旧；归档章「恢复编辑」（unarchive）后 SHALL 落查看态，作者点「编辑正文」进入编辑态。
- 右栏 AI 动作（去AI味）与「生成正文」为显式动作，SHALL NOT 强制编辑态：两态下产物/流式照常写入编辑器。

#### Scenario: 默认查看态

- **WHEN** 打开某章的正文页签
- **THEN** 编辑器 contenteditable=false，顶行有「正文 · 字数/空章」与「编辑正文」；可直接阅读与滚动

#### Scenario: 进编辑态可见框

- **WHEN** 点「编辑正文」
- **THEN** 顶条变为「正在编辑正文 · N 字」＋「完成」，正文区呈现可编辑容器样式（底色＋细边），光标落文末；编辑列撑满中栏剩余高度（短内容时框沿直通状态栏上方，下方无死空白）

#### Scenario: 短内容编辑列撑满

- **WHEN** 编辑态正文内容不足一屏（如空章或少量段落，含生成中呼吸灯态）
- **THEN** 编辑框直通状态栏上方、底部留白与顶部对称；框内空白可点击聚焦书写，生成中呼吸灯同步满高；内容写超一屏后恢复照常滚动

#### Scenario: 完成回查看态

- **WHEN** 编辑态点顶条「完成」
- **THEN** 回查看态（顶条恢复「编辑正文」，正文区恢复无框阅读样式），内容不回退、未保存修改照常自动保存

#### Scenario: 进编辑态写作

- **WHEN** 点「编辑正文」后输入
- **THEN** 编辑器可写，实时字数与自动保存三态照旧；切走再切回本章仍保持编辑态

#### Scenario: 生成正文自动进编辑态

- **WHEN** 在 AiModal 确认「生成正文」或点顶栏「续写」
- **THEN** 直接进入编辑态并聚焦/恢复滚动，无需再点「编辑正文」

#### Scenario: 锁定期不出编辑入口

- **WHEN** 打开已归档章、排队未到的章或旧稿支线章的正文页签
- **THEN** 不出现「编辑正文」入口，编辑器不可编辑，各自只读横幅照旧

#### Scenario: 恢复编辑后落查看态

- **WHEN** 在归档章点「恢复编辑」（unarchive 成功）
- **THEN** 只读横幅撤下，正文处于查看态；点「编辑正文」后可写

#### Scenario: 归档章写入锁死（c-archived-readonly）

- **WHEN** 打开已归档章的正文页签
- **THEN** 编辑器不可编辑、无「编辑正文」入口；只读横幅＝「恢复编辑」出口＋指路「重写本章」（旧稿自动转存支线）；右栏「生成正文」禁用＋hint「已归档 · 恢复编辑后可用」；「解除只读」弹窗不再出现

### Requirement: 正文编辑器核心契约

- 正文编辑器 SHALL 以「仅段落」的文档模型承载正文：文档 = 段落序列，SHALL NOT 提供标题、加粗等其它节点或标记类型。
- 编辑器内容与 `chapter.prose`（`\n` 分段纯文本）SHALL 保持无损往返：加载、输入自动保存、AI 写入、去AI味/扩写/压缩采纳后的持久化内容 SHALL 与既有纯文本语义一致（后端契约、AI 提示词链、预览阅读器、成稿下载 SHALL NOT 感知编辑器实现）；空正文 SHALL 与空串互转（空态占位提示照旧）。
- 编辑器 SHALL 保证中文输入法组合期不被程序性渲染打断：作者正在组合（拼音组词）时，编辑器 SHALL 挂起外部内容替换，组合提交后再行同步。
- 撤销/重做 SHALL 覆盖作者输入与 AI 流式写入：AI 流式写入 SHALL 作为一个可整体撤销的历史单元，生成完成后作者执行一次撤销 SHALL 回到本次生成前的正文；「停止」已落盘的部分照既有收尾语义处理。
- 粘贴 SHALL 归一为纯文本段落：剪贴板中的格式标记（加粗、标题、链接、图片等）SHALL 被剥离，多段落结构保留。
- 既有只读判定与语义 SHALL 保持：c-prose-edit-gate 查看/编辑两态（`contenteditable=false` 判定、「编辑正文」入口）、归档/frontier/旧稿三套锁定优先、流式期间编辑器不可编辑。
- 段落版式 SHALL 保持：宋体、680 版心、段首缩进、per-book 字号/行距偏好类照常生效；`.editor` 宿主类与 `contenteditable` 属性（e2e 与 a11y 判定口）SHALL 保留。

#### Scenario: 纯文本无损往返

- **WHEN** 打开含多段正文的章节，输入若干段后触发自动保存
- **THEN** 持久化的 `chapter.prose` 为 `\n` 分段纯文本，与作者所见段落一一对应，无 HTML 残留

#### Scenario: 中文输入不被打断

- **WHEN** 作者在编辑器中用拼音输入法组词（组合进行中）
- **THEN** 组合期不发生外部内容替换导致的渲染重置，候选与确认文本完整落入所在段落

#### Scenario: AI 生成可整体撤销

- **WHEN** AI 生成正文完成落盘后，作者立即执行一次撤销
- **THEN** 正文回到本次生成前的内容；重做可恢复生成结果

#### Scenario: 富文本粘贴降级

- **WHEN** 作者从网页复制含加粗、标题、图片的内容粘贴进编辑器
- **THEN** 仅保留纯文本与段落结构，格式标记与图片被剥离

#### Scenario: 只读与两态判定保持

- **WHEN** 打开归档章、排队未到章、旧稿支线章或处于正文查看态
- **THEN** 编辑器 `contenteditable=false`、「编辑正文」入口与各只读横幅按 c-prose-edit-gate 既有口径呈现

#### Scenario: 版式与偏好保持

- **WHEN** 作者调整本书字号/行距偏好后在正文页签写作
- **THEN** 版心宽度、宋体、段首缩进与字号/行距按既有偏好生效

### Requirement: 正文生成中的现场保护

正文 AI 流式生成期间，工作台 SHALL 保证生成现场可见、危险导航被拦、已生成内容不丢：

- **生成状态可视**：正文编辑区在流式写入期间 SHALL 呈现呼吸灯边框动效（accent 色；流式开始即起、收尾即止）；「AI 正在生成…」徽章与「停止」按钮 SHALL 在流式期间于正文页签之外的章纲/操作页签同样可见。
- **左栏树锁定**：流式写入期间，左栏卷/章树的切换入口（点章、点卷）SHALL 置灰不可点，并以带可点击出口的提示指路「停止」；「停止」被点或生成收尾后 SHALL 立即恢复可点。顶栏「写作」回书主页的确认弹窗口径不变（见「页签回默认主页」）；页签切换（正文/章纲/操作）与切设定/预览不受影响、生成照常继续。
- **半截内容落库**：流式写入期间发生切章或编辑器卸载，已接收的生成内容 SHALL 按「停止」的既有收尾语义落库（半截正文并入该章正文并走自动保存），SHALL NOT 静默丢弃。
- **流式态复位**：切章或卸载收尾后，编辑器 SHALL 恢复既有可编辑判定，生成中徽章与呼吸灯动效 SHALL 消失，SHALL NOT 残留锁定或「生成中」UI 态。

#### Scenario: 生成中编辑区呼吸灯可见

- **WHEN** 正文 AI 流式写入进行中，作者停在正文页签
- **THEN** 编辑区呈呼吸灯边框动效，底部状态条显示「AI 正在生成…」与「停止」；生成收尾后动效与徽章消失

#### Scenario: 非正文页签仍可见生成徽章

- **WHEN** 流式写入进行中，作者切到章纲页签
- **THEN** 「AI 正在生成…」徽章与「停止」按钮仍可见可用，生成持续写入不中断，切回正文页签可见新增内容

#### Scenario: 生成中左栏树不可切换

- **WHEN** 流式写入进行中，作者点击左栏另一章或另一卷
- **THEN** 该入口置灰不可点并提示先点「停止」；现场保持在当前章、生成继续；点「停止」后入口恢复可点

#### Scenario: 切章保留半截内容

- **WHEN** 流式写入进行中，作者经未锁定的中断路径（如点「写作」回主页并确认中断）离开本章
- **THEN** 已接收的半截生成内容并入该章正文并按自动保存落库，重新打开该章可见；编辑器无残留锁定，生成中徽章与呼吸灯动效消失

### Requirement: 正文页签密度重排

章工作台正文页签 SHALL 按「演示页基准」（2026-10-04 用户拍板）压缩头部层级：

- **徽章行收敛**：头部徽章行 SHALL 只保留 草稿（状态）/ 字数 / 归档门槛 / 剧情 / 出场角色，SHALL NOT 重复渲染 计划字数、完成度、本书总字数（该三项唯一承载位见下）；卷名 kicker SHALL NOT 在章工作台头部重复渲染（卷归属由左树承载）。
- **页签行进度**：页签行右端（版本历史左侧）SHALL 常驻显示「完成度 X% · 总字数 X」compact 进度。
- **完工检查并入工具行**：编辑态下，完工检查（字数未达标＋叙事自查）SHALL 呈现为编辑工具行左侧的警示胶囊，点击 SHALL 展开/收起叙事自查明细；查看态 SHALL NOT 渲染该胶囊（查看态无工具行）。既有 qc 字数/自查数据源与口径不变。

#### Scenario: 头部只剩一枚信息源

- **WHEN** 打开有正文的章（实写 1930 / 目标 2500）
- **THEN** 头部徽章行恰含 草稿/字数/归档门槛/剧情/出场角色 五类，无「计划字数」「完成度」「本书总字数」徽章；「完成度 77% · 总字数 7,738」出现在页签行右端

#### Scenario: 编辑态完工检查为一枚胶囊

- **WHEN** 编辑态且上次生成字数未达标
- **THEN** 工具行左侧出现「⚠ 字数未达标 · 实写/目标」警示胶囊；点胶囊展开叙事自查明细，再点收起；无整条横幅压在正文上方

### Requirement: 章纲页签剧情区

- 章纲页签 SHALL 在既有格子之后提供「剧情」区（条目列表编辑，契约见 `chapter-plot-items`），全档可编辑（免费手写不锁）；**编辑态下**空态 SHALL 直接呈现输入框＋引导 placeholder（无引导卡、无「写第一条」按钮）；查看态下剧情条目 SHALL 以只读行呈现（空态给出「不填也能写」占位）。
- 剧情条目 SHALL NOT 参与 AI 产物对章纲格子的覆盖（原「AI 起草」覆盖判定只回填章纲格子、不改剧情条目——该入口已随 c-og-ai-draft-retire 退役，条目不受任何生成类覆盖）；剧情区 SHALL NOT 出现任何 AI 按钮（AI 入口唯一化右栏，与既有口径同）。
- **推演走法行入口（c-og-slim-v2）**：剧情区 SHALL 接受来自剧情推演「收进章纲」的**追加**写入（追加一条、既有条目不变）；该写入 SHALL NOT 在剧情区内新增按钮（入口仍在右栏推演弹窗），写入后 SHALL 走章纲既有保存链并刷新剧情区显示。
- 章纲页签 SHALL NOT 再呈现已退役的 11 个格子及其折叠组（关键事件/地点/时间/叙事视角/视角指导/预期策略/预期细节/可部分推进/段落规划/本章行动/场景卡）；留存格子 SHALL 只呈现页面文案与控件。

#### Scenario: 剧情区随章纲页签呈现

- **WHEN** 在章纲页签点「编辑章纲」
- **THEN** 剧情区可见且可直接编辑（空态为直接输入框＋引导 placeholder），区内无 AI 按钮

#### Scenario: 查看态剧情只读

- **WHEN** 打开某章章纲页签（查看态）
- **THEN** 剧情条目以只读行呈现，无输入框；空态给「不填也能写」占位

#### Scenario: AI 起草不动剧情

- **WHEN** 章纲格子全空但已有剧情条目时发起 AI 产物回填（原「发起 AI 起草」入口已随 c-og-ai-draft-retire 退役，本条按留存同族口径执行——现役回填面为「补全缺失字段」）
- **THEN** 不弹覆盖确认（判定只看章纲格子），回填只落章纲格子，剧情条目保持不变

#### Scenario: 推演走法行落进剧情区

- **WHEN** 从推演弹窗执行「收进章纲」
- **THEN** 剧情区新增该走法行且既有条目不变，保存状态与章纲其它格子同链

### Requirement: 右栏「剧情抽卡」动作

- 右栏「AI 辅助」面板章纲页签动作区 SHALL 提供「剧情抽卡」动作（生成类归 `ai-plan`，标准档起；无该 key 的档位以档位感知 locked 口径置灰禁点、不隐藏；归档章禁用），点击打开三版选一弹层（口径见 `chapter-plot-items`）；动作 SHALL 为真实链路按钮（无占位）。
- 章纲页签动作行排序（c-plot-draw-rename-lead）：「剧情抽卡」 SHALL 为第 1 行、「盘点出场人物」 SHALL 为第 2 行；其余动作行（剧情推演/补全缺失字段/与卷纲冲突检测）排于两者之后。
- 中栏剧情区 SHALL NOT 出现与「剧情抽卡」同链路的第二入口。

#### Scenario: 免费态锁定卡

- **WHEN** 免费档用户查看章纲页签右栏
- **THEN** 「剧情抽卡」以 locked 口径呈现（置灰禁点、不隐藏），带升级出口

#### Scenario: PRO 打开三版弹层

- **WHEN** PRO 用户在右栏点「剧情抽卡」
- **THEN** 打开三版选一弹层（口径见 chapter-plot-items），中栏无第二入口

#### Scenario: 动作行排序

- **WHEN** 选中一章停在章纲页签查看右栏动作区
- **THEN** 第 1 行为「剧情抽卡」、第 2 行为「盘点出场人物」，其余行为剧情推演/补全缺失字段/与卷纲冲突检测
