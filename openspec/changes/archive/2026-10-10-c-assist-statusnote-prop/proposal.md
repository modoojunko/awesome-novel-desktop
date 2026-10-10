# c-assist-statusnote-prop

## Why

用户在写作台右栏「AI 助手」卡面（章纲/正文等各页签）看到一行代码样文本 `statusNote=`（v0.30.2 实机截图，2026-10-10 报告）。根因在 #766（c-rail-tier-badge）：`statusNote={…}` 被写进了 `<AiWriterAssistant>` **开标签闭合之后的 children 区**（夹在注释与章纲升级出口之间）——JSX 把 children 里的 `statusNote=` 当纯文本节点渲染进卡面，后面的 `{tab === "prose" && !zqShow ? … : undefined}` 成了独立表达式节点（章纲页签求值 `undefined` 不渲染），于是每个章页签恒见字面量。真正的 `statusNote` prop 从未传入：`zhuque-workbench` 主 spec 已 SHALL 要求的「工作台显示开关为关时，卡片功能性副行注明『朱雀检测已关闭 · 其余可用』」从未生效（二次影响）。

单测没抓到的原因：`AiWriterAssistant.test.tsx` 是正确按 prop 传的，问题只在 `AiAssistPanel` 调用点，且没有「children 里不得出现该字面量」的断言；tsc/eslint 对 JSX children 文本不拦（编译期合法）。

## What Changes

- **修**：`AiAssistPanel.tsx` 该行连同注释挪回 `<AiWriterAssistant>` 开标签 props（`rows` 与 `data-od-id` 之间）。一行挪位，两个症状同修：卡面字面量消失；朱雀关闭注记恢复显示。
- **测试钉**：`AiAssistPanel.test.tsx` 补 3 条防回归——章纲页签卡面不得出现 `statusNote` 字面量；正文页签朱雀开关关时副行出「朱雀检测已关闭 · 其余可用」且不漏字面量；开关开时不出关闭注记。
- **不做**：无 spec delta——`zhuque-workbench/spec.md` 早已钉此行为，本修是实现回归到 spec，不新增/不修改任何需求，故声明 `skip_specs: true`（先例 c-og-badge-archived-confirm）；无原型/设计资产改动（`statusNote` 槽位视觉为 #766 既有形态，本次只是接通）。

## Capabilities

### New Capabilities

（无——本 change 声明 `skip_specs: true`。）

### Modified Capabilities

（无——`zhuque-workbench` 等主 spec 零改动。）

## Impact

- 前端：`components/novel/workbench/AiAssistPanel.tsx`（一行挪位）；`__tests__/AiAssistPanel.test.tsx`（＋3 钉）。
- 验证：定向套件 `AiAssistPanel` 13 过＋`AiWriterAssistant` 18 过（新用例零 act 警告）；前端全量 vitest 114 文件 / 1368 用例绿；`tsc --noEmit` 干净。
- 实现 PR：#809（squash＝b08eded1，CI「C端 前端」绿）已合 main。
- 发版：随下个 C端 发版带出（v0.30.2 已含缺陷，线上用户下版消失）。
