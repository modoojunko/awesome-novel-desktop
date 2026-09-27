# c-ai-rail-shared — 右栏 AI 助手全局统一设定模版：ra-* 布局公共化

## Why

用户 2026-09-27 拍板：AI 助手应做成一**公共的前端布局和结构**——各页内容可以不一样，造型样子全局一致，
以设定域 AiWriterAssistant（ra-head/ra-step/ra-foot 卡）为模版。此前写作域三处面板（章八页签/卷验证/idle）
与设定域零共享元素：外层同名类两套定义、PRO 徽三种、门控四套、无 foot。

## What Changes

- **CSS 公共化**：`.rail-assist` 卡壳与 `ra-head/.plan-badge/.ra-step/.ra-body/.ra-arrow/.ra-foot/.ra-off/
  .ra-running/.ra-hint/.locked` 家族从 `.settings-v` 作用域提升为全局；写作域旧裸 flex 基线退役。
- **组件公共化**：AiWriterAssistant 迁 `components/novel/`；扩展行级 `testid` 与 `children` 插槽。
- **AiAssistPanel 八页签换装**：`AI 助手 · X` 头部＋ai-target 作用域行（原统计卡口径）＋ra-step 能力行
  （名称＋会读什么/落到哪＋箭头）＋ra-foot 声明；rail-acts/rail-stats/rail-list/ai-sec 退役。
- **Rail 外壳瘦身**：LockedCard/pill-pro/ai-ctx/续写润色扩写三张 .ai-tool 卡/免费「规划中的能力」卡退役，
  续写/润色/扩写收编正文页签能力行；免费态统一整卡 locked＋点击统一升级出口。
- **VolumeAssistPanel 三态换装**：验证面板与两 idle 态改 ra-*；体检报告 rp-*/分卷依据/卷的验证作 children
  保留；拆下一章免费锁定行＋独立升级出口按既定产品口径保留。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `workbench`: 右栏「AI 辅助」面板 requirement 全面改写为 ra-* 统一布局口径（头部/作用域行/能力行/声明；
  免费档统一门控；三域同构场景）。

## Impact

- 前端：AiWriterAssistant（迁公共+扩展）、AiAssistPanel、Rail、VolumeAssistPanel、book.css；e2e 五文件。
- 门禁：tsc、vitest 874、build、design:lint、隔离栈 8 文件 e2e——全绿（PR #515，squash=46be6357）。
- 零数据面改动。
