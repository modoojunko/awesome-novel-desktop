# assistant-tools Specification

## Purpose
agent 工具面：后端既有能力封装为封闭注册表的 agent 工具——作家在对话里一句话完成结构管理与世界观起草，写类走授权梯度。

## Requirements

### Requirement: 结构管理动作收编

agent SHALL 提供书结构管理写工具（封闭注册表，写类，走授权梯度默认每写必确认）：确认章纲/撤回章纲确认、章节归档/取消归档、新增一卷、新增一章。写授权卡 SHALL 携带人话预览（作家批前看得见改什么）；拒绝则不执行。结构动作 SHALL 复用既有后端服务（与面板同源），SHALL NOT 新建平行写路径。

#### Scenario: 一句话确认章纲
- **WHEN** 作家说「确认第七章的章纲」
- **THEN** 助手经写工具执行确认（授权卡批复后），回执告知确认完成

#### Scenario: 新增一卷一章
- **WHEN** 作家说「开第二卷，加第一章」
- **THEN** 授权后建卷建章，回执带卷/章定位，左侧目录即时可见

### Requirement: 世界观能力收编

agent SHALL 提供世界观三读/产卡工具：世界观起草（按设定出世界观候选卡）、世界观校验（找设定冲突）、传说建议（lore 候选）——与设定·世界观面板同源（同一后端能力），产物过目采纳，SHALL NOT 自动写回设定。

#### Scenario: 起草世界观
- **WHEN** 作家在设定语境说「帮我起草这个世界的设定」
- **THEN** 助手产世界观候选卡（含锚点标注），过目后由作家采纳；不自动写回

### Requirement: 域挂账与启动校验

新工具 SHALL 挂入 scopes 域（结构动作全域共享；世界观挂设定域）并通过启动校验（registry ⊆ 域∪共享）；未挂账工具拒绝加载。

#### Scenario: 启动校验覆盖
- **WHEN** 应用启动装配工具注册表
- **THEN** 校验通过（无表外工具），新工具在全页签可被意图命中

### Requirement: 页面操作工具族——导航与字段级写

注册表 SHALL 新增页面操作工具（除写正文外——对话不代笔纪律不变）：

- `navigate`（kind=read，全域共享，免授权）：跨大视图（书架/写作/设定/预览）与跨章＋章内页签的真跳转，走既有 navigate effect 通道；target 编码 `view[:章ref[:页签]]`，工具层校验视图/页签白名单；
- `write_chapter_fields`（kind=write）：章纲字段 patch 写（概要/出场角色/挑战/阶段/章末落点/剧情条目/必须完成的变化/禁则/主情绪/目标字数），白名单外字段拒绝；落库走 `save_chapter` patch-gates（缺键保现值）；
- `write_settings_field`（kind=write）：设定字段写，按面板分派（genre 五字段 core_promise/promise_note/forbidden_list/cost_ratio/battlefield 现卡合并后整卡校验落库、story synopsis 单键、world v2 键合并），SHALL NOT 覆盖未提及字段；题材目录（theme/sub_genre）SHALL NOT 进本白名单——题材写走题材目录采纳卡单一通道，SHALL NOT 出现双写路径。

字段级写工具 SHALL 走能力核（caps 字段写族：读现值→合并→既有服务链），SHALL NOT 直调路由 handler 或伪造表单快照；SHALL 抓取写入前值构造「字段：写入前 → 写入后」对比（授权卡 preview 与 write_log 撤销数据源同源）；SHALL 无 feature_key（作家编辑自己的字段不吃付费档位闸）；作用域 SHALL 按编辑面挂域（章纲字段写→章纲域、设定字段写→设定域）并过启动校验。

#### Scenario: 字段级写只动给定字段
- **WHEN** agent 调 write_chapter_fields 只写「碰到的挑战」
- **THEN** 该章其他章纲字段保持现值（patch-gates），changes 携带「写入前 → 写入后」

#### Scenario: genre 单字段写不覆盖他字段
- **WHEN** agent 调 write_settings_field 写 genre.battlefield
- **THEN** 现卡整体合并后整卡校验落库，core_promise/promise_note/forbidden_list 保持现值

#### Scenario: 口述转写主要看什么
- **WHEN** 作家说「把我刚说的这段写进主要看什么」，授权卡批复
- **THEN** write_settings_field 写 genre.promise_note 成功落库（超长/非法值被人话报错拦下）；授权卡 preview 显示「主要看什么：写入前 → 写入后」

#### Scenario: 题材不走字段级写
- **WHEN** agent 被要求写 01 题材
- **THEN** write_settings_field 拒绝 theme/sub_genre（白名单外）；题材经题材目录采纳卡成对写入
### Requirement: 任务计划工具

注册表 SHALL 新增 `update_plan` 工具（kind=read 的会话状态工具，全域共享，免授权）：入参 `items`（每项含稳定 id、人话标题、状态）＋ `mode`（replace/merge，缺省 merge）＋可选 `note`。该工具 SHALL 只写会话内任务计划，SHALL NOT 写书内数据、SHALL NOT 触发授权梯度、SHALL NOT 出现在写类授权卡清单。

工具结果摘要 SHALL 是人话回执（如「计划已更新：3 件，做完 1 件」），SHALL NOT 回显裸 JSON。计划工具 SHALL 挂入共享读集并通过启动校验（registry ⊆ 域∪共享）；连续同工具同参数的调用去重守卫照常生效。

#### Scenario: 建立计划

- **WHEN** 模型在一条多交付物请求的首步调用 `update_plan` 建三项计划
- **THEN** 会话内计划建立，工具回执为人话摘要，不弹授权卡、不写书内数据

#### Scenario: 更新状态

- **WHEN** 模型完成第一项后调用 `update_plan` 把该项置为做完
- **THEN** 计划快照更新，回执说明当前完成件数

#### Scenario: 启动校验与去重

- **WHEN** 应用启动装配注册表且模型连续两次同参调用 `update_plan`
- **THEN** 启动校验通过（工具在共享读集）；第二次调用被去重劝退，不执行

### Requirement: 起草工具入参分层——素材与写法约束

`draft_arc` 的参数 SHALL 拆为两层：`material`（素材——设定、人物、世界观等故事内容）与 `constraints`（写法约束——主题、节奏、文风、披露时机等，只影响怎么写，不是故事内容）；`input` SHALL 保留为兼容别名（`material` 为空时回落 `input`）。

工具层 SHALL 以明确分隔块把两层拼给既有能力核，SHALL NOT 让写法约束混进故事素材被当内容扩写。产物卡 SHALL 回显本次使用的写法约束（人话标签「写法约束」），使作家能核对「按哪条约束校准」。

#### Scenario: 分层入参

- **WHEN** 模型调用 `draft_arc`，`material` 写故事素材、`constraints` 写「真谛前期不点，中期撕开」等写法要求
- **THEN** 能力核收到带分隔的两段文本；写法约束不被扩写成故事内容

#### Scenario: 旧调用兼容

- **WHEN** 旧提示词或旧调用只传 `input`
- **THEN** 工具按 `material` 回落处理，行为与本次变更前一致

#### Scenario: 卡面回显约束

- **WHEN** 带 `constraints` 的 `draft_arc` 返回文本卡
- **THEN** 卡面出现「写法约束」行，列出本次约束；作家过目后可采纳

### Requirement: 当前设定页字段按需查询

助手 SHALL 通过只读工具 `read_page_fields` 按需查询当前设定面板的字段清单与已保存现值，SHALL NOT 依赖自动注入的页面字段值：

- 工具 SHALL 为零参数；当前面板 SHALL 由请求的 `thread`（`set:<panel>`）决定，模型 SHALL NOT 传 `thread/page/book_id`。
- 工具 SHALL 只挂设定域（`set:*`）；SHALL NOT 返回章节正文/章纲、别的面板、别的书、模型配置、未保存输入或选中文字。
- 返回 SHALL 包含：当前面板名、字段中文标签、可写字段键、已保存现值、未保存提醒（如有）；题材面板 SHALL 覆盖 01 题材目录＋02 主要看什么＋03 绝对禁止＋04 吃苦指数＋05 本小说斗什么，且与 `read_settings(genre)` 同源渲染。
- 值 SHALL 裁短并受总预算约束；空字段 SHALL 统一显示「未填」（数值格可用「未定」）；读失败 SHALL fail-soft 成可读提示，不打断对话。
- 工具描述/设定纪律 SHALL 定义调用条件：作家用「这个/这格/这里/这一项/当前页面」指字段但未点名，或要按现值改/补，或问本页哪些填了哪些没填，或写前目标字段不唯一时 SHALL 先调；字段已点名且值在上下文、通用知识、导航/命令、同轮已调且页面未变、与页面无关的讨论 SHOULD NOT 调。
- 同一轮同一面板 SHALL 最多查询一次；页面/面板变化后才重新查询；写工具 preview 自读 before，SHALL NOT 为 preview 额外查询。
- 查询后仍不唯一 SHALL 用返回的字段名向作家确认一句；SHALL NOT 猜页面上不存在的字段或把「未填」当值写回。

#### Scenario: 「这格」指代
- **WHEN** 作家在题材页说「这格改成更狠的」，未点名字段
- **THEN** 助手先调 `read_page_fields`，按返回的 02/03/05 候选用字段名问一句，不直接写、不猜

#### Scenario: 字段已点名
- **WHEN** 作家说「把 02 主要看什么改成『靠算计翻盘』」
- **THEN** 助手不调 `read_page_fields`，直接走写工具；preview 自读 before

#### Scenario: 页面状态盘点
- **WHEN** 作家问「这页还有哪些没填？」
- **THEN** 助手调 `read_page_fields`，逐格如实报已填/未填，不编值

#### Scenario: 未保存修改
- **WHEN** 页面有未保存修改，作家问「我刚改的主要看什么你看到了吗？」
- **THEN** 工具结果头标明「已保存值」与「本页有未保存修改」；助手说明读到的是已保存值，并问按哪个写

#### Scenario: 非设定页
- **WHEN** 作家在章纲页问「这页有几个问题？」
- **THEN** 工具不在本域；助手用 `read_outline`/`read_chapter`，不调 `read_page_fields`

### Requirement: 正文检测问题行按需查询

助手 SHALL 通过只读工具 `read_prose_checks` 按需查看一章正文被检测标出的问题行，SHALL NOT 依赖自动注入的检测结果：

- 工具 SHALL 为只读低风险、免付费档位；`chapter_ref` MAY 缺省（＝当前聚焦章）。
- 结果 SHALL 包含两段：人味检测（本地现算：人味率/条数汇总；逐条段号＋级别（一票否决/提示）＋规则名＋该段整句原文＋为什么＋改法）与朱雀检测（最近一次存档：判 AI/疑似的段号与原句、结果是否过期；无存档如实说明）。
- 正文源 SHALL 按此优先级：请求章恰为当前章且有屏上文本 → 屏上文本（头部标注「按屏上当前正文现算（可能有未保存改动）」）；否则 → 已保存正文（头部标注来源；`page_unsaved` 含未保存而拿不到屏上文本时 SHALL 提示结果可能与屏上标注不一致）。SHALL NOT 用屏上文本冒充别的章。
- 朱雀存档与当前正文指纹不一致时 SHALL 标注「结果已过期」，只给段号/级别、SHALL NOT 给原句（段号可能对不上，防误导），并提示重新检测。
- 结果 SHALL 受总预算约束（明细超出记「后面 N 条先不展开」）；空正文/缺章号 SHALL fail-soft 成可读提示。
- 工具 SHALL 只挂正文域（`ch:prose`）与文风域（`ch:style`）；工具描述与正文纪律 SHALL 定义触发条件：作家提到人味检测/朱雀检测/标红/标黄/标记的问题行，或要复述、解释、按这些问题行改时先调；整章正文仍用 `read_chapter`。

#### Scenario: 屏上未保存正文的问题行
- **WHEN** 作家在正文页（正文尚未保存）问「人味检测标红的几行你都看到了吗」
- **THEN** 助手调 `read_prose_checks`（缺省当前章），结果头标注「按屏上当前正文现算」，逐条给出段号/原句/为什么/改法，与屏上标注同口径

#### Scenario: 跨章提问
- **WHEN** 作家在打开第 7 章时问「第 3 章人味检测标了什么」
- **THEN** 工具用第 3 章已保存正文现算，SHALL NOT 拿第 7 章屏上文本冒充

#### Scenario: 朱雀存档过期
- **WHEN** 朱雀档案是在正文修改前测的
- **THEN** 结果标注「正文改过，结果已过期」，只列段号与级别、不给原句，并建议重新检测

#### Scenario: 非正文域
- **WHEN** 作家在章纲页问检测问题行
- **THEN** 工具不在本域，助手用 `switch_tab` 引导切到正文页签

### Requirement: 题材目录选择工具

助手 SHALL 具备「按标题选 01 题材目录」的能力，与题材四格（爽点/红线/代价/战场）区分：

- 只读工具 `read_genre_catalog` SHALL 返回封闭题材目录（`genres/theme_catalog.py` 的全部大类与子类，含解读与案例），供模型按书名/简介判断；SHALL NOT 允许模型自造目录外题材。
- 产卡工具 `settings_genre_pick` SHALL 接收 `theme`（必填）、`sub_genre`（可空）、`note`（理由，可空），并按目录校验：大类不存在或子类不属于该大类时 SHALL 返回可读的可选清单（不抛裸异常、不落库）。
- 合法调用 SHALL 产出采纳卡，payload 为 `{stype:"genre", field:"catalog", value:{theme, sub_genre, note}}`；工具 SHALL NOT 直接写设定（写回只在作家点采纳后发生）。
- 助手在作家说「选/定/判断/推荐题材」「这本书算什么题材」时 SHALL 优先使用上述两工具；SHALL NOT 用 `settings_genre_core_promise` 等四格工具顶替「选题材」。说「爽点/红线/代价/斗什么」时才用四格工具。
- 两工具 SHALL 在设定域（`set:` 线程）声明；读工具免档位，产卡工具沿用 `settings-ai-fields` 档位。
- 设定域内，作家消息命中「根据/按标题选/定/判断/推荐题材」「这本书算什么题材」时，循环 SHALL 首步确定性调用 `read_genre_catalog`（显式 chip tool_hint 优先；域外不触发），确保目录真值进入当轮上下文。

#### Scenario: 按标题推荐题材
- **WHEN** 作家说「根据标题，帮我选定题材」
- **THEN** 助手先读题材目录，再给出一个大类＋子类（或仅大类）的推荐卡，含推荐理由；不产出爽点/红线等四格卡

#### Scenario: 目录外题材被拒
- **WHEN** 模型传入目录外的 `theme` 或不属于该大类的 `sub_genre`
- **THEN** 工具返回可选清单的人话提示，不产卡、不写库，模型可改对后重试

#### Scenario: 采纳写回 01 题材
- **WHEN** 作家在题材推荐卡点「采纳 · 写入」
- **THEN** 写回本书 `theme`/`sub_genre`，其余题材四格与设定字段保持不变，并给可读回执

### Requirement: 设定读面——五格与简介真值

`read_settings` 工具 SHALL 在既有 premise/world/cast/hooks 之外新增两个共享读分区，使模型按需可读设定页现值（与 `read_page_fields` 分工：本工具给全量/全文按需细读，`read_page_fields` 给当前面板字段＋已保存现值；两者都不自动注入提示词）：

- `genre` 分区：返回题材五格现值与未填点名（未填字段逐格点名「未填」，已填给值；题材含大类＋子类；禁忌/战场为中文词汇 label）——与题材目录工具（读 36 类封闭目录的「可选值」）分工明确：本分区读「这本书现在填了什么」。
- `intro` 分区：返回简介现值；无简介时返回「（简介还没有内容）」。
- 两分区 SHALL 保持共享读属性（全域页签可读、免授权），并随注册表过启动校验。

#### Scenario: 读五格现值

- **WHEN** 模型在任意页签调 read_settings(area="genre")，五格已部分填写
- **THEN** 返回已填字段现值＋未填字段逐格点名（非整段空白或异常）

#### Scenario: 读简介

- **WHEN** 模型调 read_settings(area="intro") 且简介已写
- **THEN** 返回简介全文（预算截断内）；未写时返回「（简介还没有内容）」

#### Scenario: 全域可读

- **WHEN** 作家在章纲页签让助手「看看题材定了没」
- **THEN** read_settings 在共享读集内可被调用，模型如实报五格状态

