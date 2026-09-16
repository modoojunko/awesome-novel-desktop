# foreshadow-settings 变更（增量）

## Purpose

伏笔设定面板的行为契约：以真表 `novel_hooks` 承载伏笔台账（状态三分组、收束闭环、章节 id 引用），提供条目级 CRUD＋ops token 撤销、自动保存、确认门禁与右栏 AI 四行（只出建议、采纳走前端组合），替代 KV 整存整取的裸表单。

## ADDED Requirements

### Requirement: 真表存储与稳定 id

- 伏笔 SHALL 存储于真表 `novel_hooks`：id（UUID 主键，服务端生成）、novel_id、seq（每书单调递增，同事务取号）、description（必填，≤300 字）、type（9 值 slug 白名单：mystery/threat/promise/clue/relationship/power/emotion/choice/desire）、priority（Integer 1/2/3）、status（active/resolved/abandoned 单列）、introduced_chapter_id / planned_chapter_id / resolved_chapter_id（→chapters.id，可空，ondelete=SET NULL）、payoff_note（≤300 字，可空）、mentioned_in_chapter_id（可空）、created_at / updated_at。
- 展示编号 `#H-####` SHALL 由 seq 派生；seq SHALL 永不复用（删除后新建不顶号）。
- 前端 SHALL NOT 生成 id；新增行走「乐观插入临时行→服务端返回真 id 替换」。
- 词表（type 枚举、status 枚举、长度常量、priority 归一）SHALL 单源定义并前后端镜像（parity 测试锁定）。

#### Scenario: 新建条目获得稳定编号

- **WHEN** 用户删除编号最大的伏笔后再新建一条
- **THEN** 新条目的 seq 大于所有历史 seq（编号不回收），已有条目的编号与 id 均不变

#### Scenario: 删除章节不连带删除伏笔

- **WHEN** 删除一条被伏笔引用的章节（或删除整卷级联删章）
- **THEN** 伏笔行保留，其 introduced/planned/resolved/mentioned 章引用列置 NULL
- **AND** 前端对该伏笔的章节位显示「章节已删」，不显示空白

### Requirement: 条目级 CRUD 与 ops token 撤销

- 伏笔 SHALL 提供条目级 API：列表（含展示编号）、新增、部分更新、删除、恢复。
- 删除 SHALL 即时落库并返回撤销凭证（ops token，沿角色先例）；撤销 SHALL 按原 id 原样恢复（id 与 seq 不变）；token 有效期到下次操作或刷新。
- 状态切换 SHALL 只改 status 列并移动条目分组归属；resolved→active 回切 SHALL 保留收束记录（resolved_chapter_id / payoff_note 不清）。
- 旧 `PUT /settings/hooks` 三数组整存整取端点 SHALL 退役。

#### Scenario: 删除后撤销按原编号恢复

- **WHEN** 用户删除一条伏笔并在回执窗口内点「撤销」
- **THEN** 该伏笔以原 id、原 seq、原字段内容恢复到原分组，台账中编号连续性不受影响

#### Scenario: 状态回切保留收束记录

- **WHEN** 用户把一条已收束伏笔切回「活跃」再切回「已收束」
- **THEN** 收束章节与「怎么收的」内容保留不清空

### Requirement: 自动保存与确认前 flush

- 面板编辑 SHALL 字段级防抖持久化（串行队列），面板脚呈现保存态（保存中…/已自动保存）。
- 「存草稿」按钮对伏笔 SHALL 隐藏（草稿态＝已落库未确认）。
- 确认动作 SHALL 先 flush 在途保存队列，再执行确认；保存失败 SHALL 阻断确认并提示重试。

#### Scenario: 编辑即持久化

- **WHEN** 用户修改任一字段后直接刷新应用
- **THEN** 重新打开伏笔面板可见刚才的修改（无「未保存行」）

### Requirement: 台账与伏笔卡

- 中间栏 SHALL 呈内嵌子双栏：左＝伏笔台账（活跃/已收束/废弃三分组，状态点 活跃=warn／已收束=ok／废弃=muted 描边，与卡面状态徽标同色同源；空分组不渲染；描述搜索本地过滤；「添加伏笔」置顶），右＝选中伏笔卡。
- 伏笔卡 SHALL 含：伏笔描述（必填）、引入章节、计划收束章节、类型、优先级（高/中/低）、状态（显式三态切换，切换即挪组且选中跟随）。
- 章节 三格 SHALL 为卷章选择器（按卷 optgroup 分组，选项含 chapter id，落库存 chapter id、显示「第 N 章 · 章名」）；计划收束指向未建章 SHALL 降级为留空（hint 明示「章未建可先留空」），由埋坑体检点名「未定期」承接。
- 收束记录（收束章节＋怎么收的）SHALL 仅在已收束态展开，为软引导留痕——不硬拦保存与确认；已收束无留痕时面板内提示，埋坑体检持续点名。
- 术语 SHALL 以「收束」为唯一系统词（「回收/排期」不出现于用户可见层；「埋/还」仅限讲解层文案）。

#### Scenario: 章节选择落库为 chapter id

- **WHEN** 用户在引入章节选择「第 03 章 · 柳安坊」
- **THEN** 该伏笔落库的 introduced_chapter_id 等于该章的数据库 id，界面回显「第 03 章 · 柳安坊」

#### Scenario: 状态切换挪组且选中跟随

- **WHEN** 用户在状态切换里选「已收束」
- **THEN** 该条目从「活跃」组移入「已收束」组，选中跟随、收束记录区展开，界面提示补收束章节与「怎么收的」

### Requirement: 确认门禁与内容有变降级

- 确认「伏笔」SHALL 要求 ≥1 条描述非空的伏笔（任意状态——全收束/全废弃亦可通过）；空表确认 SHALL 被拒并给出出路文案（先埋一条或先跳过）。
- 确认按钮 SHALL 恒可点（前端提示性预检，后端门禁兜底），不得 disable。
- 已确认后内容指纹变化 SHALL 使面板徽标降级为「内容有变 · 待重新确认」（warn）；重新确认后恢复「已确认」系徽标。
- 面板徽标口径：无伏笔=「还没有伏笔」（empty）；有活跃条目=「N 条待收束」（warn）；已确认=「已确认 · N 条待收束」（done）；全部收束=「全部收束」（ok）；内容有变优先于以上各态。

#### Scenario: 空表确认被拦且有出路

- **WHEN** 用户在台账为空（或描述全空格）时点「确认完成」
- **THEN** 得到「伏笔不能为空：先埋一条……或先跳过」类指引，设定树徽标不变，不前进

#### Scenario: 确认后清空台账出现降级徽标

- **WHEN** 用户在确认后又删除全部伏笔
- **THEN** 面板徽标显示「内容有变 · 待重新确认」，与设定树/进度口径不再自相矛盾

### Requirement: AI 四行（只出建议）

- 右栏 AI 助手卡 SHALL 提供四行：起草伏笔（输入 简介＋题材＋世界＋主线，出 3 条候选，勾选采纳）、拟收束方案（对当前选中伏笔；采纳后写入收束记录并移入已收束）、埋坑体检（扫全部活跃伏笔×已写章纲，点名超期/在期/未定期/无留痕，结果行可点跳转对应条目字段）、查一致性（对当前选中伏笔×简介/题材/世界）。
- AI 端点 SHALL 只出建议、无副作用；采纳 SHALL 由前端组合条目级 CRUD 完成，回执可一步撤销（精确逆操作，不影响其后其他改动）。
- 覆盖已有收束记录时 SHALL 明示「覆盖并收束」（警示级，不加二次弹窗），撤销兜底。
- 拟收束方案与查一致性在无选中条目时 SHALL 置灰并提示「先选一条伏笔」。
- 起草伏笔 SHALL 保留最近 5 次结果可切回。
- 埋坑体检在已写章纲为空时 SHALL 降级为纯台账自检（点名未定期/无留痕），不报错、不阻断。
- 门控：四行与空态「让 AI 起草」旁路 SHALL 可见＋锁定（免费态），点击走统一升级出口；「未配置模型」指路仅对可自配 Key 的状态出现。空态旁路为「编辑区零 AI 按钮」的唯一例外。

#### Scenario: 候选勾选采纳与精确撤销

- **WHEN** 用户取消勾选 1 条候选后采纳（2 条入台账），随后在回执窗口点撤销
- **THEN** 仅回滚这次采纳的 2 条，用户此前的其他编辑不受影响

#### Scenario: 体检点名可跳转

- **WHEN** 埋坑体检点名某条「未定期」且用户点击该行
- **THEN** 选中对应伏笔、聚焦计划收束字段并滚动到可见

#### Scenario: 免费态锁定

- **WHEN** 免费用户打开伏笔面板
- **THEN** 右栏四行与空态旁路可见＋锁定，点击出现统一升级提示，不发生 AI 调用

### Requirement: 旧 AI 端点退役

- 旧单字段生成端点 `POST /settings/ai/hooks/description` SHALL 退役，返回 400 退役文案（沿角色先例）；对应 prompt 模板与字段白名单项同批移除，全仓零残留。

#### Scenario: 旧端点不再可用

- **WHEN** 客户端调用旧伏笔字段生成端点
- **THEN** 收到 400 与退役说明，服务端无对应 prompt 文件残留
