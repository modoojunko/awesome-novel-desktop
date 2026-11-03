## Why

新建一本书打开「文风」页，三区被填了一堆东西：默认人设一句、硬约束 58 条、手法 5 条，外加 37 个禁用词与 8 条句式规则。页面还写着「进页即按题材蓝图填好」，但全仓没有任何按题材预填的逻辑——文案在说一件不存在的事。

这些内容来自建书时的静态模板 `reference/writing-style.yaml.template`（6.0 时代的全量「低AI味」指南），与本书题材无关，也与作者想写的东西无关。

## What Changes

- **建书种子瘦身**：style 只播种通用 AI 腔护栏（`banned_words` 37 词、`tic_patterns` 8 条）；`role/rules/craft/few_shot_examples/style_samples` 一律留空，旧键（`core_principles`/`possible_mistakes`/`depiction_techniques`/`tone` 等）退出种子。
- **右栏首行「按题材填文风」**：读本书题材对应的知识库基线（文风/文笔），进面板时取一次摘要决定行的描述与置灰；该行不调模型、不吃 Key、免费可用（`ungated`）。
- **勾选卡过目**：点行后复用 `AiCardModal`（候选勾选卡）——作家在弹窗里勾选条目、可直接改叙事身份一句话，点「采纳，填进文风」才填进表单；三区按勾选替换，护栏（禁用词/句式/示范段）合并去重；不自动保存，回执一步撤销。
- **徽标改三态**：未填 / 未改动 / 已自定义 · N 处，不再出现「题材默认」这个假标签。
- **needess 文案修正**：删掉「进页即按题材蓝图填好」「重置为题材默认」，改成实话。

## 拍板（2026-11-03）

1. 只给按钮，不自动写。（作者点了才填。）
2. 内容来自**知识库**同题材条目（用户条目＋官方基线包的 merged 视图），不另造一份硬编码蓝图。
3. 建书那份 58 条通用原则退出硬约束，只保留 DIY 护栏。

## Impact

- 后端：`reference/writing-style.yaml.template`、`settings/style_kb.py`（新）、`settings/router.py`、`kb/snapshot.py`。
- 前端：`SettingsView.tsx`（右栏行＋摘要查询）、`StyleSettingForm.tsx`（弹窗＋采纳＋徽标＋文案）、`lib/styleApi.ts`。
- 行为变化：新书 `readiness.style` 不再开箱就绪（role 空 → 需作者写一句或按题材填）；存量书 KV 不变（读路径归一照常）。
- 依赖：知识库需有同题材（或跨题材通用）基线条目才取得到内容；库空时按钮给「先拆一本同题材的书 / 去知识库记几条」的出口。
