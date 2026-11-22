## ADDED Requirements

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
