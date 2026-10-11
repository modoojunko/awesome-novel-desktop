# Change: c-chapter-seam-check

## Why

2026-10-10 章际衔接诊断（样本《我在夜晚打吸血鬼》vol-1-ch-6，见 c-field-truncation-alignment 同期评审）：章际衔接的**原料机制**（上章结尾原文→契约 7 章首接点）工作正常，但**状态数据会过期且无检测网**——归档 pending 行不进素材（已另行修复 accept 流程）、关系温度跳变、道具断环、条目重复这类「章际断点」没有任何检查面。卷级有「对节奏」体检与升档提醒，章级缺对应物。用户拍板推进 D＝章际衔接体检。

## What Changes

- `write/ai_check.py`：
  - `CHECK_KINDS` 新增第七类 `chapter_seam`（章际衔接检查）：对照「上章结尾（原文）」「前文回顾」「故事状态（截至上章）」查本章正文五类断点——①开场没接住上章结尾（另起炉灶/无过渡跳切/重写上章画面）②人物态度与关系域矛盾且无过渡拍 ③道具与物品域/世界细节断环 ④同一拍重复写两遍 ⑤与状态域「已得知/仍不知」认知矛盾；每条须给证据（引用本章原句＋对照素材点）。
  - `_material` 新增 chapter_seam 分支：注入【上章结尾（原文）】（`ctx.previous_tail`）＋【前文回顾】＋故事状态块（`_story_state_block(ctx.story_state)`）——三者 `build_chapter_context` 已组装，零新查询。
- `client/frontend/src/lib/aiCheck.ts`：`AiCheckKind` 联合类型＋`CHECK_TITLE` 新增 `chapter_seam: "章际衔接检查"`。
- `client/frontend/src/components/novel/workbench/AiAssistPanel.tsx`：正文页签新增「章际衔接检查」动作行（置于文风检查之前；生成中/无正文禁用）。
- `awesome-novel-prompts`（配合提交 cb202c7）：ai_check 纳管注释元数据六→七类（desc＋{instruction} 行号＋{material} 描述补章际素材）；模板正文零改动——指令字面量在 C端 CHECK_KINDS。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `prose-writing`：「正文 AI 痕迹检测」六类→七类案头检查（新增章际衔接 kind，素材组装含章际三块）。

## Impact

- C端：`write/ai_check.py`＋前端 `lib/aiCheck.ts`、`AiAssistPanel.tsx`；受影响测试 14/14 绿（新增 seam 素材分支用例：造 ch-2 断言 ch-1 末段进素材——注意按 project 过滤章查询，跨项目 ref 不唯一）；全量 2245 passed＋16 存量环境失败（15 个既有＋test_ai_flavor_scan 1 个来自 #828 的存量失败，单跑同样挂，与本 change 无关）
- 提示词仓：仅元数据（cb202c7）
- 无 schema/门禁变化；ai_feature("ai-generate") 沿用既有 PRO＋本书模型双门控
- 5274 演示栈重建后即可在正文页签体验「章际衔接检查」
