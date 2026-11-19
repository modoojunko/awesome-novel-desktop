# c-agent-writing-flow-context

## Why

作家实测（2026-11-19，boss 报障）：对已写 4,199 字正文但未归档的第 7 章说「规划下一章」，助手一直围着第 7 章出方向。根因：① 系统提示词里没有任何写作流程知识（模型不知道「归档＝本章完结信号」，也就无从判断「下一章」指什么）；② 书级 brief 进度行把「有正文未归档」标成「草稿」，真值含混，模型被喂了假锚点；③ 判断「写到哪里了」的接口 read_progress 虽全页签可见，但模型不知道什么场合该用它。boss 拍板：不做死流程（不铸硬闸、不搞窄正则 prime），把写作流程作为背景知识给 agent，让它自主判断要不要查进度、怎么接话。

## What Changes

- 系统提示词新增静态「写作流程背景」段：一章生命周期＝拆方向→确认章纲→写正文→归档；归档是「这一章完结」的唯一信号；「下一章／继续／规划」类请求落点拿不准时先调 read_progress 对齐进度真值（判断启发，不是行为脚本）。
- 书级 brief 进度行按前沿章真实完成态陈述：draft→「正文已写 N 字·未归档」；planned→「已排定·正文未写·未归档」；pending→「各章均已归档；下一章 第 N 章（待拆纲）」。frontier chapters dict 补 word_count 字段支撑。
- read_progress 面向该判断场景微调：description 点明用途（「下一章／继续写」类拿不准落点先查这个）；摘要尾部补「下一章＝第 N+1 章」；「草稿」口径改「正文已写·未归档」（人话判例）。
- 前端 Aui2Dock：pendingHintRef 提交后置空（一次性）——对齐 assistant-chat-ui spec 既有条款「tool_hint 随下一次发送携带」；现状不清空会让旧 chip hint 随后续每条自由文本强制重放工具首步，破坏模型自主选工具。
- 明确不做：`draft_chapter_split` 不加硬闸（保持 max+1 原语义）；不加窄正则 prime；提示词包不动；存量会话不清洗。

## Capabilities

### New Capabilities

（无——全部落在既有能力内）

### Modified Capabilities

- `writing-assistant`: 新增 Requirement「写作流程背景与进度真值随行」——系统提示词 SHALL 携带静态写作流程背景段；brief 进度行 SHALL 按前沿章完成态说真话；read_progress 摘要 SHALL 给全决策依据；行为决策（查不查进度、如何接话）SHALL 由模型自主决定，系统 SHALL NOT 以硬编码闸拦截「下一章」类请求。
