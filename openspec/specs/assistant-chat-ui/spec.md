# assistant-chat-ui Specification

## Purpose
TBD - created by archiving change c-agent-chat-memory. Update Purpose after archive.

## Requirements

### Requirement: 对话前端以 @agentscope-ai/chat 定版

写作助手对话前端 SHALL 以 @agentscope-ai/chat（ChatAnywhere）为唯一实现（Aui2Dock），自研 ChatDock 与 assistant-ui spike（AuiDock）SHALL 退役删除，`?aui` 遗留切换参数 SHALL 移除；既有自研会话链（useChatSession 手搓状态机）SHALL 一并退役，历史装载与流式交付 SHALL 走 ChatAnywhere ref 直控（updateMessage）＋后端 SSE 事件桥。每页签独立会话（独立上下文/历史/流程）SHALL 不变。

#### Scenario: 旧前端退役
- **WHEN** 作家不带任何 URL 参数打开任一页签的助手
- **THEN** 渲染的是 ChatAnywhere 版 dock，`?aui=0` 不再有任何效果；代码库中 ChatDock.tsx、AuiDock.tsx、SseChatAdapter.ts、useChatSession 均已删除

#### Scenario: 页签会话隔离不变
- **WHEN** 作家在章纲页签对话后切换到正文页签再切回
- **THEN** 两页签各自的历史与上下文互不串扰，切回接续原对话（既有页签线程语义零变化）

### Requirement: 产物卡与授权卡以真卡面呈现

产物卡与授权卡 SHALL 以 ChatAnywhere 自定义卡片（customCards）渲染真实卡面：产物卡复用既有 CardBody 卡面组件按 kind 渲染，授权卡 SHALL 含变更预览与「允许」「拒绝」两个可点按钮，点击直接驱动授权端点并在流内更新卡面状态；SHALL NOT 再以文本占位（「产物卡已生成」「● tool ✓」）替代卡面。卡面视觉 SHALL 沿用既有 chat.css 语义类，不新增设计形态。

#### Scenario: 产物卡卡面
- **WHEN** 助手起草一段章纲并交付产物
- **THEN** 对话流内出现结构化产物卡（按 kind 渲染既有卡面），作家可直接读稿并继续对话改稿

#### Scenario: 授权卡流内决策
- **WHEN** 助手请求写回授权
- **THEN** 授权卡含变更预览与允许/拒绝按钮，点击后卡面立即更新为已授权/已拒绝态，流程继续无需刷新

### Requirement: 全模型逐字流式

所有模型的助手回复 SHALL 逐字流式呈现：原生 FC 模型走既有 narration_delta 增量链；文本协议模型的回复 SHALL 经流式解析增量抽取叙述段逐字交付，SHALL NOT 整段等待完成后一次性显示；协议 JSON 壳 SHALL NOT 裸露给作家（deepseek 裸 JSON 回复教训）。协议壳的定义 SHALL 覆盖哨兵分节、整段单 JSON、以及无哨兵但含 `"action"`／`"tool"`／`"args"` 键的裸片段；命中任一形态 SHALL 在流式阶段冻结，SHALL NOT 作为叙述增量流出。回合收口 SHALL 只交付清理后的叙述；清理后无叙述则交付明确失败话术。坏片段 SHALL NOT 写回会话历史或在回放中重现。流式路径解析失败 SHALL 静默降级为整段交付（narration 兜底事件已消费），SHALL NOT 白屏或重复拼接。

#### Scenario: 文本协议模型逐字出字

- **WHEN** 作家选用 deepseek 等文本协议模型发起对话
- **THEN** 回复随生成逐字上屏，全程看不到协议 JSON 片段

#### Scenario: 流式解析失败降级

- **WHEN** 文本协议流式解析中途失败
- **THEN** 该回合降级为整段交付一次显示，已流出内容不重复拼接

#### Scenario: 无哨兵裸片段不流给作家

- **WHEN** 模型输出无哨兵、以引号开头的 `"action": ...` 裸片段
- **THEN** 该片段不在气泡中逐字出现；收口只显示清理后的叙述或明确失败话术，重开历史也看不到坏片段

### Requirement: 换前端功能契约保持

换用 ChatAnywhere 后，既有对话功能契约 SHALL 全部保持：斜杠命令（/new 清线程、/compact 手动压缩）、工具步过程呈现（步开始→步结束逐条可见、完成后可展开回看）、思考增量呈现与回看、能力盘 chips 结构化触发（tool_hint 随下一次发送携带）、页签切换分隔标记、断流保底与错误卡收尾、容量条（≥80% 警示并提示 /compact）。过程呈现 SHALL 采用独立过程泡泡：思考与每次工具调用各自一张默认单行的折叠卡，位于本回合正文之上；正文 SHALL NOT 混入工具调用文本行。思考与工具过程 SHALL 随回合持久化，切页签或重开书后可展开回看。缺失项 SHALL 在新前端补齐实现，SHALL NOT 以「换前端」为由静默缩水。

#### Scenario: 斜杠命令在新前端可用
- **WHEN** 作家在 ChatAnywhere 输入框输入 /compact
- **THEN** 命令不进入对话历史，压缩执行后收到前后规模对比回执

#### Scenario: 思考回看不丢
- **WHEN** 一轮含思考增量的对话完成，或切页签/重开书回看该回合
- **THEN** 正文之上的思考泡泡默认折叠为一行，点开展开全文

### Requirement: 授权模式在对话框常显可切

dock 输入框区 SHALL 常显当前授权档位选择器（选择器长在输入框区、文案命名**已选档位**而非通用「模式」，点击展开选项；渲染使用对话库自带模式选择组件），提供两档：每写必确认（默认）、自动执行·本书内；切换 SHALL 即时生效并持久化（会话级 grants），SHALL NOT 需要重开会话；历史存量「全部自动放行」值 SHALL 兼容显示为自动档（两档行为与服务端判定本等价）。硬地板（须作家亲自确认类）写操作 SHALL 不受档位影响、始终停车弹授权卡。助手自身 SHALL NOT 能变更档位（档位变更不进工具注册表——结构性缺席）；作家询问当前授权模式时助手 SHALL 能如实答出（只读）。档位切换 SHALL 在对话流留一行回执。授权档位另有专用斜杠命令 `/auth`（查档与两档切换；命令不进对话历史），`/mode` SHALL NOT 承载授权。

#### Scenario: 切到自动执行档
- **WHEN** 作家在输入框区选择器选「自动执行·本书内」（存量旧称「本书内自动放行」）
- **THEN** 对话流出现切换回执，后续本书实体写字段自动执行并带回执（写步留 write_log 撤销数据源，撤销入口照旧）；硬地板类写仍弹授权卡确认

#### Scenario: 助手不可自改档位
- **WHEN** 作家让助手「给自己开自动放行」
- **THEN** 助手无档位变更工具可调，档位不变，并说明需要作家自己在输入框区选择器上切换

#### Scenario: 档位持久接续
- **WHEN** 作家切到「自动执行·本书内」后关闭应用重开、切页签再切回
- **THEN** 授权选择器仍显示该档位，行为一致

#### Scenario: 存量全部自动放行兼容
- **WHEN** 会话 grants 存量为「全部自动放行」历史值
- **THEN** 选择器显示为自动档，行为与自动档一致（后端判定本等价）

### Requirement: 停止与打断（openwriter/coding agent 必备）

生成进行中作家 SHALL 能随时停止：dock 停止钮/发送区停止钮 SHALL 调服务端停止端点（POST /assistant/stop），后端以**协同取消**收口当前 run（最近检查点自停——步界＋模型流 chunk 级＋授权停车等待），已产出内容保留并落库，流内收到收口话术后停止钮退场；SHALL NOT 出现「只能干等跑满墙钟」的假停止。作家在生成进行中发送新消息 SHALL 打断当前 run（服务端等旧 run 收口后处理新消息，openworker 打断语义），SHALL NOT 以「生成中」为由拒绝新消息；等待收口超时（>4s）才明确提示稍候再试。客户端断开连接 SHALL 尽力置位取消（服务端收尾落库照常）。同一会话并发拒绝语义由打断语义取代。

#### Scenario: 生成中点停止
- **WHEN** 助手正在逐字输出长回复，作家点停止
- **THEN** 流在最近检查点收口并收到「已产出保留」收口话术，停止钮退场，半截内容完整保留可继续对话

#### Scenario: 授权等待中点停止
- **WHEN** run 正停车等待授权批复，作家点停止
- **THEN** 该步骤标记「已停止——这一步没有执行」，run 收口，不产生幽灵授权卡

#### Scenario: 生成中发新消息打断
- **WHEN** 生成进行中作家直接输入新指令发送
- **THEN** 当前 run 被打断收口（半截保留），新指令随即被处理，SHALL NOT 被并发拒绝

### Requirement: 渲染崩溃兜底

ChatAnywhere 渲染异常 SHALL 被 React 错误边界捕获（AuiErrorBoundary 常驻包裹），降级为对话内错误提示与重试入口，SHALL NOT 白屏拖垮整个工作台；错误边界恢复后既有对话历史 SHALL 重新装载。

#### Scenario: 组件渲染异常
- **WHEN** ChatAnywhere 内部渲染抛错
- **THEN** dock 区域显示错误提示与重试入口，工作台其余区域正常可用；点重试后历史重新装载

### Requirement: 任务计划卡呈现与恢复

dock SHALL 在对话流内渲染任务计划卡，数据来自服务端 `plan` 事件快照（SHALL NOT 以文本占位或假进度替代）。计划卡 SHALL 包含人话标题与逐项清单，每项按 §5 状态语言呈现四态：未开始（未填／中性）、在做（进行中／warn）、做完（已确认／ok）、没做成（阻断缺项／err，仅当该件是作家点名的交付物）。

计划卡 SHALL 在执行中实时更新，收口后保留可回看；存在未完成项时 SHALL 明示「还有 N 件没做」。切页签返回或应用重启 SHALL 按落盘快照恢复最近计划与状态。计划卡 SHALL NOT 新增胶囊形态、语气词或第四种状态色；按钮文案 SHALL 使用动词。计划卡 SHALL 以独立卡面接在当前回合消息之后（不占文本气泡），与产物卡同一卡面骨架。

#### Scenario: 多件事计划卡实时更新

- **WHEN** 作家一条消息提出三件交付物且助手建立计划
- **THEN** dock 出现三项计划卡，执行中各项状态实时变化，收口后卡保留

#### Scenario: 未完成项如实呈现

- **WHEN** 三件中只完成两件
- **THEN** 计划卡明示「还有 1 件没做」，已完成项显示做完态，不出现全部完成的假象

#### Scenario: 恢复计划

- **WHEN** 执行中途重开会话或切走页签再切回
- **THEN** 计划卡按落盘快照恢复最近状态，未完成项仍可见

#### Scenario: 失败不伪装完成

- **WHEN** 某一步执行失败
- **THEN** 对应项显示没做成（err 仅在阻断作家点名交付物时使用），SHALL NOT 显示做完

### Requirement: 输入区控制条（助手模型与深度思考）

助手输入框底栏 SHALL 常显一行控制条，与授权档位选择器同排，提供三控件：助手模型选择、深度思考开关、授权档位。模型选择 SHALL 复用按 API 配置分组的模型选择弹层，默认本书模型并在弹层内标注「本书模型」；选择 SHALL 只作用于该助手对话的后续回合（按当前页签线程记住），SHALL NOT 修改本书绑定模型、SHALL NOT 影响写作链路。深度思考开关 SHALL 默认开启、按当前页签线程记住，并随每次对话请求下发：开启时助手调用 SHALL 显式请求思考（压过 API 配置的思考开关），关闭时 SHALL 显式请求不思考；端点不支持思考参数时 SHALL 自动去参回落，SHALL NOT 打断对话。模型覆盖校验失败时 SHALL 在流内以可读提示收尾，SHALL NOT 静默改用本书模型。

#### Scenario: 切助手模型
- **WHEN** 作家在底栏选择一个非本书模型后继续对话
- **THEN** 后续回合用该模型，本书写作模型与其它页签线程不变；切回该页签仍记住选择

#### Scenario: 深度思考开关
- **WHEN** 作家关闭深度思考后发起对话
- **THEN** 本轮不再请求思考，过程区不出现思考泡泡；重新打开后恢复思考呈现

#### Scenario: 覆盖模型失效
- **WHEN** 作家选中的模型配置被删除或 Key 失效
- **THEN** 对话流内给出可读提示，作家可重选模型或切回本书模型，不静默改用本书模型

### Requirement: 过程进度行与工具参数

助手回合 SHALL 在过程卡列首显示一行实时进度（非折叠）：生成中显示「运行中 · 当前动作 · 第 N 步 · 已等 X 秒」，收口显示「完成/已停止 · N 步 · 用时 X」。步骤数 SHALL 取本轮真实完成的工具步数，当前动作 SHALL 取正在执行的工具/思考中/整理回答/等待模型/等待授权（授权卡停车），秒数 SHALL 为本轮起始至今的实测时长；SHALL NOT 渲染任何未由真实事件产生的进度。收口后计时 SHALL 停止；会话回放 SHALL 显示「完成/已停止 · N 步」（不伪造起止时刻）。工具卡展开 SHALL 在「打算/结果/模型调用」之外显示本步参数预览（截断 ≤600 字）；参数预览 SHALL 随过程落盘，回放同样可见。

#### Scenario: 生成中进度实时更新
- **WHEN** 助手开始一轮，先思考、再执行一个工具、再思考
- **THEN** 过程列首一行显示运行中·思考中·第 1 步·已等 X 秒；工具执行时显示正在执行的工具；工具完成后步骤数递增；收口显示完成·1 步·用时

#### Scenario: 授权等待有明确进度
- **WHEN** 工具步触发写授权卡、助手停车等待作家批复
- **THEN** 进度行显示「运行中 · 等待授权 · 已等 X 秒」；批复后恢复后续动作

#### Scenario: 工具参数可展开查看
- **WHEN** 作家展开一张工具卡
- **THEN** 除打算/结果/模型调用外，可见本步参数 JSON 预览（长值截断）

#### Scenario: 回放不伪造计时
- **WHEN** 重开书回看该回合
- **THEN** 过程列首显示完成/已停止·N 步；工具参数预览仍在，不显示虚构的已等/用时秒数

### Requirement: 页面身份与字段注入边界

助手 SHALL 保留最小的页面身份上下文，但页面字段值 SHALL NOT 自动拼进 system/user 提示词：

- 页面身份（当前页面名、`set:*` 面板名、`ch:*` 页签）MAY 继续随轮注入，用于让模型知道「作家在哪一页」。
- 页面字段清单与当前值 SHALL NOT 自动注入；模型需要时 SHALL 调只读工具 `read_page_fields`（见 `assistant-tools`「当前设定页字段按需查询」）。
- 前端 `page_state` SHALL 只带未保存标记（外加「页面态可携带屏上正文文本」的屏上正文文本）；SHALL NOT 为页面字段新增 `panel`/`chapter_tab` 请求字段（当前面板由 `thread` 决定）。
- 同一字段的自动注入与工具结果 SHALL NOT 同时存在（去重），避免模型看到两份口径不同的值。
- 工具结果 SHALL 明确标注「已保存值」；页面有未保存修改时 SHALL 如实提醒，避免把落库值当成屏幕值。

#### Scenario: 调工具前没有字段值
- **WHEN** 作家在题材页发消息，助手尚未调 `read_page_fields`
- **THEN** 当轮 system/user 提示词里只有页面身份，没有 01-05 的字段值；模型需要时自己调工具

#### Scenario: 页面身份仍可用
- **WHEN** 作家在 `set:world` 线程说话
- **THEN** 提示词可含「当前页签：设定·世界」，但不含世界八格的当前值

#### Scenario: 重复注入已移除
- **WHEN** 作家在题材页说话
- **THEN** 提示词中不再出现自动生成的五格字段真值；字段值只出现在 `read_page_fields` 的工具结果里

#### Scenario: 前端不新增页面字段
- **WHEN** 前端提交助手消息
- **THEN** `page_state` 只带未保存标记（外加屏上正文文本）；不因本能力新增 panel/chapter_tab 字段

### Requirement: 页面态可携带屏上正文文本

前端 `page_state` MAY 额外携带当前章屏上正文全文 `prose_text`，用于只读工具 `read_prose_checks` 现算：

- 取值 SHALL 在发送时刻从正文编辑器取（与自动保存同一序列化单源），SHALL NOT 在装载时缓存。
- `prose_text` SHALL 只进入后端工具上下文（`ToolContext.page_prose`），SHALL NOT 拼进 system/user 提示词，SHALL NOT 落库。
- SHALL 仅在章视图提供（getter 缺失时不带该键）；空串 SHALL NOT 带键。
- 后端 SHALL 对超长文本设上限（50000 字）丢弃并以已保存正文兜底。
- 本字段不属于页面字段值：与「页面身份与字段注入边界」中页面字段禁令不冲突，`panel`/`chapter_tab` 仍 SHALL NOT 新增。

#### Scenario: 章视图发送消息
- **WHEN** 作家在正文页发送消息
- **THEN** 请求 `page_state` 带 `prose_text`（编辑器当前全文）；提示词中不出现正文全文

#### Scenario: 非章视图
- **WHEN** 作家在卷纲页/设定页发送消息
- **THEN** 请求不带 `prose_text`

### Requirement: 题材推荐采纳卡

助手产物卡 SHALL 正确呈现「01 题材目录」推荐，不得把程序字段名直接上屏：

- `payload.stype="genre"` 且 `field="catalog"` 时，卡面 SHALL 以中文行标签显示「题材」「子类」「理由」；`sub_genre` 为空时显示「（只定大类）」或省略该行，SHALL NOT 显示 `value`/`theme`/`sub_genre` 等裸键。
- 题材推荐卡 SHALL 可采纳：点「采纳 · 写入」后读取当前题材设置，写入 `theme`/`sub_genre` 并整包保存，其余题材四格、简介、世界等字段 SHALL NOT 被清空或覆盖。
- 设定字段卡（`stype`/`field` 存在，如 `core_promise`）SHALL 使用字段中文名（主要看什么/绝对禁止/吃苦指数/本小说斗什么/简介/世界各格）作为行标签；对象形 `{value,note}` SHALL 拆成主值与「备注」两行，SHALL NOT 显示裸 `value`。
- 写回成功回执 SHALL 说人话（如「已写进 01 题材：都市 / 都市职场」），并触发设定域刷新。

#### Scenario: 题材卡显示人话
- **WHEN** 助手产出 `field="catalog"`、`value={theme:"都市", sub_genre:"都市职场", note:"书名带城市夜班与职场冲突"}` 的卡
- **THEN** 卡面显示「题材：都市」「子类：都市职场」「理由：书名带城市夜班与职场冲突」，且没有 `value` 字样

#### Scenario: 爽点字段卡也不再露裸键
- **WHEN** 助手产出 `core_promise` 卡，value 为 `{value:"以弱破强的痛快", note:"…"}`
- **THEN** 卡面显示「主要看什么」与「备注」两行，不显示 `value`

#### Scenario: 读目录与出卡两步都可见
- **WHEN** 助手先 prime 读题材目录、再由模型出题材卡
- **THEN** 过程区出现两张工具卡（read_genre_catalog 与 settings_genre_pick），stepId 不同，不互相覆盖

#### Scenario: 采纳不破坏其它设定
- **WHEN** 当前书已有 forbidden_list/cost_ratio/battlefield 与简介，作家采纳题材卡
- **THEN** 只更新 theme/sub_genre，其余字段保持原值，回执说明写到 01 题材

### Requirement: 设定页签与字段读取边界

对话线程落在设定域（`set:*`）时，服务端 SHALL 随当轮 user 消息尾注入页签身份，但 SHALL NOT 自动注入设定字段值：

- 面板名真值：`set:*` 线程 SHALL 注入「［当前页签：设定·<面板名>］」——面板键（genre/intro/world/chars/arc/style/foreshadow）映射中文名（题材/简介/世界/角色/主线/文风/伏笔）；`set:default` 与未知面板键 SHALL 回退「设定」。
- 字段值 SHALL NOT 随提示词自动注入；模型需要本页字段与已保存现值时 SHALL 调 `read_page_fields`（见 `c-agent-page-context` / `assistant-tools`「当前设定页字段按需查询」）。题材五格、简介、世界八格等字段值只应出现在工具结果里。
- 工具结果 SHALL 标注「已保存值」；页面有未保存修改时 SHALL 如实提醒，避免模型把落库值当屏幕值。
- 章节页签线程（`ch:*`）与其它线程 SHALL NOT 带设定字段真值（不串味）。

#### Scenario: 设定面板页签真值

- **WHEN** 作家在世界面板对助手说话（线程 `set:world`）
- **THEN** 本轮提示词含「［当前页签：设定·世界］」，但不含世界八格的当前值

#### Scenario: 题材面板字段按需读

- **WHEN** 新书五格全空，作家在题材面板问「当前页面有几个问题」
- **THEN** 提示词只有「［当前页签：设定·题材］」；助手调 `read_page_fields` 后，工具结果逐格点名「未填/未定」

#### Scenario: 已填给值只在工具结果

- **WHEN** 五格已填（题材=玄幻（凡人流）、主要看什么=一句话、禁忌两条、吃苦指数 7、战场一个）
- **THEN** `read_page_fields` 结果逐格给现值，未填项仍点名；提示词本身不出现这些值

#### Scenario: 章节页签不串味

- **WHEN** 作家在章纲页签（`ch:og`）对话
- **THEN** 注入「［当前页签：章纲］」照旧，SHALL NOT 出现设定字段真值


### Requirement: 书情 brief 题材行

书情 brief（系统前缀稳定段）的题材行 SHALL 反映题材目录现值：题材大类已填时 SHALL 注入「题材：<大类>（<子类>）」（子类空时只给大类）；题材未填或读取失败 SHALL 跳过该行，SHALL NOT 注入空行或占位符。题材行数据键 SHALL 与题材上下文解析结果的实际键名一致（回归钉：不得再读不存在于返回结构的键）。

#### Scenario: 题材已填进 brief

- **WHEN** 书的题材目录已存「玄幻／凡人流」，任意页签发起对话
- **THEN** 系统前缀书情段含「题材：玄幻（凡人流）」

#### Scenario: 题材全空不给空行

- **WHEN** 题材五格全空
- **THEN** 书情 brief 只含书名（与进度动态段），无「题材：」空行
