# creation-flow Specification

## Purpose
TBD - created by archiving change creation-simplify. Update Purpose after archive.

## Requirements

### Requirement: Name-only creation
- The create modal SHALL collect only a book name (single-stage).
- The modal SHALL have no import entry, no AI naming, and no synopsis/genre collection.
- An empty name SHALL disable the create button.
- Submitting (in-flight) SHALL lock all close paths (backdrop, X, Esc).
- The create endpoint SHALL NOT require AI access, so free-tier users can create novels.

#### Scenario: Name-only create
- Given an author opens the create modal
- When they enter a book name and click create
- Then a novel is created with that name and they enter the novel page
- And no synopsis, genre or AI steps were involved

#### Scenario: Empty name blocks
- Given the create modal is open
- When the name input is empty
- Then the create button is disabled

### Requirement: Rename (display name only)
- The backend PATCH /api/novels/{id} endpoint SHALL rename the display name only.
- slug and root_path SHALL remain unchanged.
- An empty name SHALL return 422.
- Saving the same name SHALL be idempotent (200).
- A missing novel SHALL return 404.
- Two frontend entries SHALL exist: the list-card dropdown menu and the detail-page title inline edit.
- The inline-edit pencil SHALL be always visible (not hover-only).

#### Scenario: Rename keeps slug
- Given an existing novel with slug "abc"
- When the author renames it via PATCH
- Then the name changes and the slug stays "abc"

#### Scenario: Rename from two entries
- Given a novel on the list page
- When the author uses the card dropdown "重命名" or the title inline edit
- Then the rename modal/input appears and saving updates the name in place

### Requirement: Settings backfill (manual synopsis)
- GET /api/novels/{id}/story SHALL read story.yaml.synopsis.
- PUT /api/novels/{id}/story SHALL write story.yaml.synopsis and SHALL NOT trigger AI prefill.
- A synopsis card SHALL be globally visible across all settings sub-items.
- The AI one-click generation entry SHALL be hidden in settings this iteration.

#### Scenario: Write and read back synopsis
- Given a novel with empty synopsis
- When the author saves a synopsis via the card
- Then GET /story returns the same text and the card shows "已补录"

#### Scenario: Free-tier create/rename not blocked
- Given a free-tier user without AI access
- When they create a novel or rename one
- Then the request succeeds (no 403 from require_ai_access)

### Requirement: 设定视图三段式布局

设定视图 SHALL 与写作视图采用一致的三段式布局：左侧设定项导航、中间当前设定项表单、右侧 AI 栏。AI 相关功能在右侧 AI 栏呈现，而非嵌入表单内部。

#### Scenario: 三栏呈现

- **WHEN** 用户进入设定视图（≥1024px 宽）
- **THEN** 界面呈三栏：左为设定项导航与进度，中为当前设定项表单与确认按钮，右为 AI 栏
- **AND** AI 栏有左边框分隔，视觉与写作视图的右栏一致

#### Scenario: 主线面板的 AI 栏

- **WHEN** 用户选中「主线」设定项
- **THEN** 右侧 AI 栏显示「AI 写作助手」三行能力卡（起草主线 / 结局校准 / 主线体检），答案落对应格下方、采纳才写回
- **AND** 主线表单内不再渲染四步向导入口（结局基调第三问的行内「AI 帮我填」属字段级入口，不受此限）

#### Scenario: 其他面板的 AI 栏

- **WHEN** 用户选中「世界 / 风格 / AI痕迹控制」
- **THEN** AI 栏显示该设定项的 AI 能力说明与入口提示（字段内「AI 帮我填」按钮保持原位）
- **WHEN** 用户选中无 AI 能力的设定项（题材/简介/伏笔/AI 模型）
- **THEN** AI 栏显示「当前设定项暂无 AI 功能」占位说明

#### Scenario: 角色面板的 AI 栏

- **WHEN** 用户选中「角色」设定项
- **THEN** 右侧 AI 栏显示「AI 写作助手」四行能力（人设补充 / 基础信息补充 / 认知补充 / 一致性体检），四行只对当前选中的角色生效
- **AND** 每行结构沿用既有能力行（名称 + 描述，描述内含「会读什么」）
- **AND** 补全类能力的答案落卡片内对应字段区的结果区（`.ai-sink`），体检结论落卡片内结果区，右栏只作按钮、不内嵌答案

#### Scenario: 多对象设定的内嵌子双栏

- **WHEN** 用户选中「角色」或「伏笔」设定项
- **THEN** 中间栏呈内嵌子双栏：左侧为对象列表（含新增入口），右侧为选中对象的配置表单
- **WHEN** 用户在内嵌左栏点「新增」
- **THEN** 列表加入新对象并选中，右侧表单切换为新对象的配置
- **WHEN** 用户在内嵌左栏切换选中对象
- **THEN** 右侧表单切换为该对象已保存的内容；未保存修改时的切换保护与现有面板切换口径一致
- **WHEN** 用户选中单对象设定项（题材/简介/主线/世界/风格/AI痕迹控制/AI 模型）
- **THEN** 中间栏保持单表单（无内嵌左栏）

#### Scenario: 窄屏堆叠

- **WHEN** 视口宽度 <1024px
- **THEN** 设定视图左栏置顶、主栏与 AI 栏纵向堆叠，AI 栏不隐藏（AI 能力仍可用）
### Requirement: 多对象设定的内嵌子双栏

「角色」「伏笔」设定项的中间栏 SHALL 呈内嵌子双栏，且占满中间栏内容区。

#### Scenario: 子双栏占满中间栏

- **WHEN** 用户选中「角色」或「伏笔」设定项（≥1024px 宽）
- **THEN** 内嵌子双栏占满中间栏内容区的整宽（不受 660px 版心限制）与整高（列表自上而下贯穿，表单区内部滚动）
- **AND** 面板头部标题与底部确认按钮位置保持不变

#### Scenario: 单对象设定项不受影响

- **WHEN** 用户选中单对象设定项（题材/简介/主线/世界/风格/AI痕迹控制/AI 模型）
- **THEN** 中间栏保持 660px 版心卡居中不变

#### Scenario: 新增与切换对象

- **WHEN** 用户在内嵌左栏新增或切换对象
- **THEN** 行为与改版前一致（新增即选中、切换加载已保存内容、脏切换保护口径不变）

#### Scenario: 角色列表按类型分组且可搜

- **WHEN** 用户选中「角色」且书中角色数量达到数十人量级
- **THEN** 内嵌左栏按「主角 / 配角 / 反派 / 路人」分组折叠，显示各组数量，列表自身滚动
- **AND** 顶部有搜索框，按键入即时在本地过滤（按名称或别名命中，不发网络请求）
- **AND** 新增入口固定在列表顶部，不随滚动消失

#### Scenario: 大列表不产生请求放大

- **WHEN** 用户打开「角色」面板或在其内切换选中对象
- **THEN** 列表内容由一次请求返回（含类型、别名、首次出场与缺口提示），切换选中不逐角色再取
