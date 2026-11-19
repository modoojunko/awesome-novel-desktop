# c-agent-panel-consolidate：设定面板 AI 弹窗收编——「让助手办」统一入口

## Why

boss 拍板（2026-11-18，按 AI 弹窗确认盘点分析立项）：把设定面板里「意图可言说、产物写书数据」的 AI 弹窗收编到 agent 对话流——弹窗退役改「让助手办」。

关键前提（实勘）：**agent 侧工具已全部存在**（题材四格 draft、世界观三件、伏笔起草/体检、主线 draft_arc、角色发散、命名、体检——注册表齐），且 dock chips 11-15 已收编过一轮（settings.default 每面板 chip 发自然语言，产物卡回对话过目）。面板内嵌的 AiCardModal 是**平行重复路径**——本 change 退役重复入口，统一成一个入口，作家不用学两套。零新工具开发。

覆盖缺口（chips 没有的三项补齐）：世界观各要素格、角色出稿（发散/定向）、命名。

## What Changes

- **七项收编**：题材四格／主线起草与自检／伏笔起草与体检／角色出稿／世界观各要素格／命名——面板内嵌 AI 按钮（AiCardModal 路径）退役，改「**让助手办**」按钮：一键聚焦 dock＋自动发指令（带面板上下文：格名／底稿直传）
- **dock autoAsk 信号**：Aui2Dock 新增 autoAsk prop（seq＋message，信号模式同 aiWriteSignal）——面板/宿主可命令式触发 dock 提交（复用既有 submit 链与 chips tool_hint 机制）
- **chips 补缺**：世界观各要素格、角色出稿（定向/发散）、命名进 settings.default/settings.chars chips
- **三项保留弹窗**：AI 生成正文（提示词弹窗＋清空重写警示，核心写作流安全面）、文风三区起草（前后对照表单 UI）、简介 AI 起草（建书流内联三选一）
- **两项挂账待实测**：剧情抽卡（卡墙并排 vs 对话卡）、剧情推演——本 change 不动

## Capabilities

### New Capabilities
- `assistant-panel-consolidate`——面板 AI 入口收编：autoAsk 通道、面板触发契约、chips 覆盖

### Modified Capabilities
<!-- 无新增行为契约冲突：被退役的弹窗能力其 agent 等价工具与产物卡链路已存在（此前 change 落地），本 change 只动入口 -->

## Impact

- 受影响端：C端（设定七面板＋dock；S端无关；不触碰令牌/组件词汇/状态语言——按钮沿用既有语义类）
- 受影响屏：设定·题材/主线/伏笔/角色/世界观（AI 按钮改「让助手办」）；dock（autoAsk 信号）；AiCardModal 组件保留（文风三区仍用）
- 对象状态：无新增对象状态；按钮文案 §13 口径（动词「让助手办」）
- 原型先行：否（入口替换＋信号接线，无新视觉形态）
- 设计工件：实现侧自查
- 风险点：作家就地填表习惯（面板按钮改跳对话）——保留一键直达＋自动发指令，作家只多看一眼对话卡；AiCardModal 移除后各面板 AiCardState 残留状态清理要彻底（防死代码）
