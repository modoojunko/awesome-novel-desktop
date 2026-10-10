# Change: c-style-rules-cap-align

## Why

2026-10-10 测试反馈「禁用词有数量上限」＋截图「57/5 条」。定诊（截图列表是文风面板**硬约束**，不是禁用词组——那组上限 100、无计数器）：

- 模板 `reference/writing-style.yaml.template` 仍带 v1 旧键 `core_principles`(32 条)＋`possible_mistakes`(26 条)＝58 条通用反 AI 红线；建书 seed 整份落 KV（新书），存量书首次读/写经 `normalize_style` 归一（老书）——两路都把旧键**全量并入 `rules`**（style-settings-v2 评审 P2 拍板「宁多勿丢」，测试 `test_template_scale_rules_not_truncated` 钉死「≈58 条不得截断」）。
- 前端硬约束 ListEditor 上限 `maxItems={5}`（「3–5 条」设计意图）→ 计数恒显示「58/5 条」超限形态；且 `items.length >= maxItems` 时「添加一项」按钮不渲染 → **每一本按模板建/迁移过的书都加不了新硬约束**；条目全是「禁止/不要…」句，测试同学把这份清单当成了禁用词表。
- 后端 `_MAX_RULES=100` 本就允许到 100——与实际冲突的是 UI 那个 5。

实锤：demo 库 `.docker-data/client/novel-v0.31.db`「提示词验证-测试书」rules=58、banned 37、tic 8，与模板归一结果逐一对上。

## What Changes

- **前端 `StyleSettingForm`**：硬约束 ListEditor `maxItems` 5→100（与后端 `style_model._MAX_RULES` 对齐）；计数器随即显示「N/100 条」；`items.length < 100` 时「添加一项」恢复可用。提示文案保留「（3–5 条）」建议口径（模板预填的通用红线计入上限、可直接删改）。
- **原型**：`docs/design-c/prototypes/style-settings.html` 硬约束 `LIMITS.rules` 5→100（与实现口径对齐，预填 5 条不动）＋ `ADJUSTMENTS.md` 登记——评审 P3：原型此前演示的正是本笔修掉的形态。
- **测试**：新增钉子——预填 58 条（> 旧上限 5）时「添加一项」可见可用、计数「58/100 条」、点添加行数 +1 且保存载荷含新行；预填 100 条时按钮收起（真上限行为不变）。
- **spec delta**：`style-banned-words`「硬约束三块与面板退役」① 禁令上限口径改写（「上限不变」→「上限 100 条，与后端 `_MAX_RULES` 对齐」）＋新增「预填超旧上限仍可添加」与「上限 100 收起添加」两个场景。

### 明确不做（本 change）

- **模板 v2 化**（新书不再预填 58 条通用红线）——改动面大：存量书已归一落库 58 条须单独处置，触碰「宁多勿丢」评审决定，且改变写章提示词注入内容（可能影响产出质量），另案拍板再议。
- **后端零改动**：`_MAX_RULES=100` 与 PUT 截断既已就位，本 change 只对齐前端。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `style-banned-words`：「硬约束三块与面板退役」① 禁令上限与后端对齐（100 条），新增两个场景。delta 见本 change `specs/style-banned-words/spec.md`。

## Impact

- C端 前端：`components/novel/settings/StyleSettingForm.tsx`（一处 maxItems）＋新增 `__tests__/StyleSettingForm.rulesCap.test.tsx`；e2e `settings-forms.spec.ts` 无感知（其「添加一项」点击按折叠组定位、填首行硬规则不受上限影响）。
- 设计产物：`docs/design-c/prototypes/style-settings.html`（`LIMITS.rules`）＋`ADJUSTMENTS.md` 登记条目；parity 无像素影响（该文件不在 `design:check` 截图矩阵）。
- 无后端/契约/数据变化；已归一的 58 条 rules 原样保留（作者可删改）。
