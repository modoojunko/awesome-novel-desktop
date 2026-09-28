# c-prose-refine-retire：正文tab精修两行「补全负向约束/精简提示词」整体退役（#578，用户拍板）

## Why
用户拍板（09-29）：章页面正文 tab 下的「补全负向约束」「精简提示词」去掉。这两行是
「提示词精修」（c-prompt-tab-retire 时随提示词页签退役收编进正文 tab）的**唯一入口**，
按「当前没有用户、破坏性改动选干净方案」口径做全链退役，不是只藏 UI。

## What Changes（#578=6e621efe，含评审修复 acfbfeb4）
- 前端：AiAssistPanel 正文动作清单撤两行；RefinePromptModal 组件删除；ChapterWorkspace/Rail
  的 refineMode 状态与 onPromptRefine 接线撤；aiCheck.ts 删 RefineMode/REFINE_TITLE/refinePrompt/saveWritePrompt
- 后端：write/router.py 删 /prompt/refine 端点与 _REFINE_MODES；prompts/prompt_refine.prompt
  模板删除（分层闸门动态枚举目录，自动出名单）
- 测试：aiAssistModals 删精修 describe；aiCheck/AiAssistPanel 收窄断言；e2e ai-assist 删
  精修链路段与桩分支＋免费档标题去「精修」；后端删 TestPromptRefine 类
- 评审修复三处：e2e 首测标题去「＋提示词精修采纳」残留；workbench spec「AI 入口唯一化」
  枚举去死词「精修」；Rail.tsx props 缩进归位（git diff -w 证实纯空白）

## Capabilities
（skip_specs: true——specs 已随 #578 直接同步 main：prompt-crafting 删「提示词精修端点」
Requirement；workbench 删「提示词精修（提案制写回）」Requirement，正文页签动作清单条目改
「精修两行 SHALL NOT 出现」＋「AI 入口唯一化」枚举去「精修」）

## Impact
正文 tab 右栏动作清单收窄为五行（生成正文/续写/去AI味/扩写/压缩）；提示词的查看/编辑/存稿
仍走「生成正文」弹窗既有链路不受影响；S 端零引用；design-parity 基线零涉及（全窗口截屏
只拍默认章纲页签）。门禁：vitest 967/tsc 零错/pytest 1692（基于 main+#574 双跑复核）。
关联：在途 c-write-prompt-layering 叙事里「提示词精修是 to_prompt() 调用方」表述过时；
#574 挂起的演示栈重建随本落地解锁。
