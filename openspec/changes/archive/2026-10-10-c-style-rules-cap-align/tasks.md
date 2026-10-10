# Tasks: c-style-rules-cap-align

## 1. 实现

- [x] 1.1 `StyleSettingForm.tsx` 硬约束 ListEditor：`maxItems` 5→100（注释点明与后端 `_MAX_RULES` 对齐；计数器/添加按钮行为随之恢复）
- [x] 1.2 原型 `style-settings.html`：`LIMITS.rules` 5→100（预填 5 条不动）＋`ADJUSTMENTS.md` 登记（评审 P3）

## 2. 测试

- [x] 2.1 新增 `StyleSettingForm.rulesCap.test.tsx`：预填 58 条 → 计数「58/100 条」、「添加一项」可见，点击 +1 行、填值可保存
- [x] 2.2 同文件边界钉：预填 100 条（后端上限）→ 「添加一项」不渲染
- [x] 2.3 vitest 全量绿＋`tsc` 绿

## 3. 文档与归档

- [x] 3.1 `openspec validate`（本 change）过
- [x] 3.2 归档时 sync 主 spec（style-banned-words ① 禁令上限口径）
