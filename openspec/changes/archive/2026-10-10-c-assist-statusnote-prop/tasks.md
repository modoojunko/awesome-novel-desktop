# c-assist-statusnote-prop — Tasks

- [x] 1. 定位：实勘 `AiAssistPanel.tsx` 渲染段，确认 `statusNote={…}` 落在 `<AiWriterAssistant>` 开标签闭合之后的 children 区（#766 引入），JSX 当纯文本渲染
- [x] 2. 修复：该行连同注释挪回开标签 props（`rows` 与 `data-od-id` 之间）
- [x] 3. 防回归三钉（`AiAssistPanel.test.tsx`）：章纲页签无 `statusNote` 字面量／朱雀开关关副行出注记且不漏字面量／开关开不出注记
- [x] 4. 全量验证：前端 vitest 114 文件 / 1368 用例绿＋`tsc --noEmit` 干净（新用例零 act 警告）
- [x] 5. 实现 PR #809 合 main（CI「C端 前端」绿，squash＝b08eded1）
- [x] 6. 归档：补档落 `archive/2026-10-10-c-assist-statusnote-prop/`（`skip_specs: true`，主 spec 零改动）
