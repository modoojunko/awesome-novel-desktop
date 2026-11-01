# c-shelf-settings-nudge

## Why

0 设定 0 章的书在书架上没有任何地方告诉作者「先去补设定」：徽章「设定中」听着像进行中，CTA「继续创作」对 0 章书还是误导（点进去落的是设定页不是写作）；同卡无封面占位「可稍后添加」没告诉作者入口在哪（⋯ 菜单），点了没反应像坏了。2026-11-01 用户反馈，拍板口径＝**文案提示就够**，不做后端进度下发、不做进度徽章、不改落点。

## What Changes

- 书卡设定态（0 章）页脚 CTA 文案：「继续创作」→「去补设定」（与既有默认落点设定页对齐；纯文案，点击行为零改动）。
- 书卡无封面 0 章占位块弱化文案：「可稍后添加」→「可在 ⋯ 菜单添加」（告知入口位置；占位块仍不可点、⋯ 菜单「封面…」入口不变）。
- 原型 `list.html` 同步两处文案（parity 基线）；e2e/vitest 相应文案钉改写。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `works-finish-flow`：书架卡片页脚 requirement 的设定态 CTA 文案改口（写作中恒「继续创作」不变）。
- `cover-avatar`：「0 章书占位弱化」场景文案改为「可在 ⋯ 菜单添加」（不可点语义保留，只改提示文案）。

## Impact

- **前端**：`NovelListPage.tsx` 两处文案常量；无逻辑/接口/样式改动（`is-later` 弱化态保留）。
- **原型**：`docs/design-c/prototypes/list.html` 同步文案（design:check parity 对拍面）。
- **测试**：`novelListPage.test.tsx`／e2e `image-workshop.spec.ts` 文案断言更新。
- **不触碰**：后端零改动；`lib/novelStage.ts` 四态判据不动；两端共享段不涉。

## Design Impact

- 受影响端：**C端** 书架屏，两处文案。
- 对象状态：无新状态——设定态/占位弱化态视觉原样，只换字。
- 共享段：不触碰。
- 原型先行：**需要**——`list.html` 文案与实现同批改，ADJUSTMENTS 无新增偏差（文案随实现走，无样式变化）。
- 文案：两处均无内部术语；「去补设定」动词开头（design-language §13）。
