# Proposal: c-workbench-storyline-parity

> 补建卷宗：实现已经 PR #445 合入 main（用户直报缺陷直修，未走先行提案）；
> 本卷宗按 openspec 归档纪律补记需求变化并归档立卷。

## Why

2026-09-19/20 用户三连反馈写作工作台与 storyline 原型不一致：

1. 章页签条被 editor-toolbar 独立工具行压低，与卷视图不同位（原型两视图均为
   e-head→e-toolbar（仅页签）两段式）；章页签顺序也与原型不符（提示词应在正文之后）。
2. 卷视图内容零衬垫贴边：storyline 皮肤把 `.col-panel` 衬垫归零后，原型的
   `.e-pad{padding:18px 22px 24px}` 规则漏落地，ol-top/分节贴死页签条与中栏左右缘。
3. AI 功能散落在章 body（头部「AI 生成正文」、章纲页签「AI 起草／剧情推演」、
   文风页签「AI 建议本章调整」触发按钮），用户拍板「卷、章页面的AI功能都挪到右侧
   AI 助手」。

## What Changes

- **页签同位与顺序**：撤 editor-toolbar 独立工具行，排版/专注/版本历史/归档并入
  e-head 右侧（`.e-head-row`）；章页签条紧贴头部＝卷视图同位；章页签顺序对齐原型
  （章纲→正文→提示词→设定→文风→角色关系→伏笔→操作，提示词 PRO-only）。
- **卷视图衬垫**：`.vol-shell .e-pad` 补原型 18/22/24 衬垫；清旧版 tpl-row/.field
  死选择器；「章节拆分」分节补 open（六节全展）。
- **AI 入口唯一化右栏**：章 body 的 AI 按钮全部退役（头部生成正文＝右栏卡同链路、
  起草/推演＝右栏章纲页签动作本就有、文风建议＝新增右栏 style 页签动作经信号通道
  触发页签内拉取）；免费态语义从「隐藏」改「右栏 rail-locked 置灰」。

## Capabilities

### Modified Capabilities

- **workbench** —— 三条需求改写：①章纲面板 AI 起草入口（位置→右栏）；②章纲页签
  剧情推演入口（位置→右栏；免费态置灰）；③文风页签（AI 建议触发移右栏，页签内留
  结果与采纳）。新增一条：AI 入口唯一化右栏＋卷/章页签结构（storyline 对齐）。

## Impact

- 代码（已合入，PR #445＝commit 4d5459a）：ChapterWorkspace/OgPane/StyleShadowPane/
  Rail/AiAssistPanel/NovelWorkspace/VolumeWorkspace/book.css＋4 e2e＋2 vitest。
- 原型登记：ADJUSTMENTS.md 条13修订（工具行撤并＋e-pad 衬垫＋分节展开）与 ⑪-a
  （AI 入口唯一化）——已随 #444 先行带上 main。
- 测试：vitest 674/674、全量 e2e 162 过 0 挂、design:lint 0 错、DOM 断言（页签条
  Y 同位 209.09px、顺序逐一比对、右栏触发文风建议→页签内呈现）。
