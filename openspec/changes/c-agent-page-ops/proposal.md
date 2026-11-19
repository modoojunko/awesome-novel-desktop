# c-agent-page-ops

## Why

boss 拍板（2026-11-19）：除写正文外，让写作助手 agent 拥有页面的**读、写、改**能力——跨视图/跨章导航、字段级编辑与保存；**凡写、改必须过作家授权策略**；授权**两层**（每写必确认／自动执行·本书内），选择器**放在用户对话框（输入框区）**，参考 OpenWorker 的 Composer 权限选择器设计、用阿里组件（`@agentscope-ai/chat` 的 `Sender/ModeSelect`＋`uiConfig.input.header`）落地；`/mode` 不承载授权，另立专用 `/auth` 命令。

现状缺口：agent 只有章内七页签导航（switch_tab）、只能产卡过目采纳写回（无字段级直接写）、授权芯片三档且在 dock 芯片行（不在输入框区）。

## What Changes

- 新增 `navigate` 工具（kind=read）：跨大视图（工作台/设定/预览/书架）＋跨章＋章内页签的真跳转；switch_tab 保留（章内七页签）。
- 新增字段级写工具族（kind=write，全过 write_gate 两层策略）：
  - `write_chapter_fields(chapter_ref, fields)`：章纲字段 patch 写（`save_chapter` patch-gates，缺键保现值），白名单＋previous 进 write_log；
  - `write_settings_field(stype, field, value)`：设定字段写，按 stype 分派（genre 四字段 GET+merge+PUT／intro synopsis 单字段端点／world topic merge），语义镜像 dockWriteBack、落服务端 caps；
  - 写工具 preview 增强：`{tool, entity, changes:[{field, before, after}]}` 字段级前后对比，授权卡渲染人话行。
- 授权两层化：前端档位芯片（移入输入框区，`uiConfig.input.header`＋lib 自带 `Sender/ModeSelect`）只留两档（每写必确认／自动执行·本书内）；`allow_all` 从选项移除（后端行为本等价，存量值兼容映射）；后端 `KNOWN_TIERS`/evaluate 零改动；硬地板照旧任何档位必弹卡。
- `/mode` 授权分支退役，新增 `/auth` 专用命令（查档/`确认`/`自动` 切档，复用书级改写逻辑；命令不进对话历史）。
- 页面状态随行：scope 上行未保存标记（settings/volume/og/prose dirty），`build_page_note` 注入提示词（只进模型，界面零渲染）。
- 明确不做：正文写入（对话不代笔）；草稿态填充；standing approvals；undo 扩 settings/chapter 实体；跨书操作。

## Capabilities

### New Capabilities

（无——全部落在既有能力内）

### Modified Capabilities

- `writing-assistant`: 授权两层化（芯片两档/`/auth` 专用命令/硬地板不变）＋ navigate/字段级写工具进注册表与作用域 ＋ 页面状态随行注入 ＋ 授权卡字段级前后对比渲染。
- `assistant-tools`: 新工具注册（navigate/read、write_chapter_fields/write_settings_field/write）与能力核（caps 字段写族）登记。
