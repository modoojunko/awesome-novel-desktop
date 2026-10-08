# c-chtab-confirm-bubbles — 归档「待确认」页签泡泡

## Why

归档提取完成后，「变化待确认」只活在 toast 一瞬与「操作」页签的归档卡里：作者停在正文/章纲页签写字时，余光里没有任何待办信号；逐条确认的过程中也没有渐进反馈，「跑完即刷新」的实时感无从谈起。微信式未读泡泡是成熟的「动作队列」隐喻（用户拍板 2026-10-08：初议微信红 pill，规范裁决后见 Design Impact）。

## What Changes

- 章工作台页签行新增三枚计数泡泡：
  - **设定**页签＝本章变化待确认数（设定＋物品＋角色认知三域 pending 合计，与页签内「全部采纳（N）」同口径）；
  - **角色关系**页签＝人物关系域 pending 数；
  - **伏笔**页签＝「该收 N」（台账该收了计数，与 HooksPane「该收了」标注同规则同源）。
- 实时链路全部复用现成管线：提取完成（archiveJob `extracting→done` 终态）即出现；逐条/批量确认、驳回经既有 `DOSSIER_CHANGED_EVENT` 广播即时递减；清零自消（缩隐退场）；未归档章无泡；切章回落重取。
- 视觉＝现有 `.pill` 家族既有 role×tone 组合（`pill-count × pill-accent`／`pill-count × pill-warn`），零新胶囊形态、零新语气档、零共享段改动；泡泡挂 `pill` 挂载 pop 微动画（屏级 book.css，先例＝ai-streaming 呼吸点）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `chapter-dossier`: 新增「页签『待确认』泡泡」Requirement——三域/关系域 pending 数以泡泡上页签，提取完成出现、确认即时递减、清零自消，口径与对应页签「全部采纳（N）」一致。
- `foreshadow-settings`: 新增「伏笔页签『该收』泡泡」Requirement——页签行以 warn 计数徽标投影「该收了」计数，规则与台账行标注同源，归档推进 mentioned 后随之变化。
- `design-system`: 状态语言总表新增「待确认」一行（design-language §5.1，先加行再写样式的既定流程），并把「页签计数泡泡」纳入徽标词汇 scenario（`.pill` 家族 count role × 既有 tone，实底红／新胶囊形态禁止）。

## Design Impact

- 受影响端＝**C端 单端**；受影响屏＝书工作台中栏页签行（book.html）。
- 对象状态：状态语言总表**新增一行「待确认」（AI 产出等裁决）**＝accent 计数泡泡（清零自消，非恒显警示）；「该收了」沿用既有 warn 语义，仅新增页签行投影位。
- **共享段判定：不触碰**。`.pill`/`.pill-count`/`.pill-accent`/`.pill-warn` 均为 base.css 既有类，本 change 只做既有 role×tone 组合与屏级（book.css）排版微调，不新增/修改任何共享段类；故免双端同改与 design-cross（依据＝design-system spec「Component vocabulary reuse before invention」）。
- **原型先行＝需要**：本批更新 `docs/design-c/prototypes/book.html` 页签行（本地资产）＋ `ADJUSTMENTS.md` 登记；标准正文 `docs/ux/design-language.html` §5.1 同批加行。
- 设计工件由**实现侧**产出：交互原型已先行交付并经用户过目拍板（`docs/design-c/drafts/ai-novel-c端-归档待确认页签泡泡.html`，含全流程动效演示）。
- **配色裁决（用户已拍板口径的偏差说明）**：初议为「微信红 pill＋琥珀该收」；按 design-language §5 规则 N6「红（--err）只表示不可逆或即时生效，警示但不危险的内容用 --warn 或 accent」与同页签行既有「缺 N 项」（cnt.err＝阻断缺项）的红色占用，待确认泡泡改用 **accent**（本应用「下一步动作」色，与页签内「全部采纳」主按钮同语言），伏笔沿用 **warn**。形态（实底观感由 pop 动画与软底对比承担）、出现/递减/自消行为、琥珀该收均维持拍板口径不变。

## Impact

- 前端：`client/frontend/src/components/novel/workbench/ChapterWorkspace.tsx`（按域 pending 计数状态＋`DOSSIER_CHANGED_EVENT` 监听＋页签泡泡渲染）、该收计数与 HooksPane 「该收了」规则抽共享单源、`client/frontend/src/design/book.css`（`.chtab` 内 pill 组合微调＋pop 动画）。
- 测试：vitest（泡泡出现/递减/清零/未归档无泡/口径一致性）；e2e 章档链路补泡泡断言（testid）。
- 门禁：`npm run design:lint`、`tsc --noEmit`、vitest、相关 e2e；`design:check` 之 book 屏为**存量红**（归 `c-book-parity-rebaseline` 专户），本批原型改动不新增其门槛，book.html 为本地资产不入 PR。
