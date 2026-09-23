# c-plan-prompt-alignment · tasks

> 补录 change：实现已随 PR #484（squash＝8e166e02）合入 main（2026-09-23）。本夹记录契约增量，随归档 PR 同步 specs。

## 1. 提示词模板（3 份）

- [x] 1.1 volume_options：`focus`（侧重说明 ≤20 字）与 `focus_axis`（侧重轴：从 <<focus_axes>> 里选一个词）拆分声明；`antagonist_type` 措辞统一「从 人物/难题/环境/自我/势力 里选一个」；`antagonist_line` 补 ≤150；`volume_estimate` 补字段说明 —— **证据**：`prompts/volume_options.prompt`；钉子 `test_options_template_declares_focus_and_axis_separately`（三断言：focus 语义行／focus_axis 闭集引用行／volume_estimate 说明行）✓
- [x] 1.2 volume_expand：`antagonist_type` 五类型闭集声明行＋`summary` 关键配角口径行＋`antagonist_line` 补 ≤150 —— **证据**：`prompts/volume_expand.prompt`；钉子 `test_expand_template_declares_antagonist_closed_set_and_summary_cast` ✓
- [x] 1.3 chapter_split：硬规则 10（客观局面）＋`acts` 含在场其他人物＋`plot`/`ending` 局面从句＋`checks` 缺席示例；负面清单（伏笔台账／主线全景）不破 —— **证据**：`prompts/chapter_split.prompt`；钉子 `test_split_template_scene_state_rules`（三处文案断言＋负面清单断言）✓

## 2. 代码（2 处）

- [x] 2.1 `_chapter_material` 卷纲聚光：spotlight＝主旨｜冲突｜坎三字段拼接，经 `author_line` 挤进【核心人物】；空卷纲退化回原行为（`filter(None,…)`）—— **证据**：`chapters/ai_plan.py`；功能用例 `test_volume_named_character_spotlights_into_cast`（7 张角色卡＋坎点名第 7 张：点名者进块、主角置顶、6 张守恒、队尾非点名卡让位）✓
- [x] 2.2 `_sanitize_plans` 钳位对齐：spine[:60]→[:40]、conflict[:120]→[:40]、ending[:120]→[:40]、focus[:60]→[:20]、volume_estimate[:60]→[:20] —— **证据**：`volumes/ai_plan.py`；消费方全核：e2e 桩（volume-plan.spec.ts `THREE_PLANS`）为 HTTP 层完整响应壳不经过 sanitizer 且桩值全在新上限内；vitest 走 HTTP mock；采纳路径 DB 列宽无虞 ✓

## 3. 门禁、评审与放弃项

- [x] 3.1 全量后端 pytest：**1359 passed**（Python 3.12 venv，`pytest tests/ -q --timeout=30`；基线 1355 净增 4）—— **证据**：PR #484 描述；CI 秒挂＝已知基建签名（CodeQL/package 全家 3–6 秒失败），按先例本地补验合入 ✓
- [x] 3.2 review-agent 评审：**No findings**（钳位消费方全核＋聚光 `author_line` 单消费点复核＋空卷纲退化路径核对）✓
- [x] 3.3 有据放弃两项并记录在案：①自检加卷纲块——spec「章级 AI 自检」明文「不含卷纲四问/人物卡/铁律」，缺席检查由 1.3 的 checks 示例承担；②体检判据补缺坎 warn——体检素材 `ant_pair` 已渲染「（未填——判据输出 warn，不编造）」，spec volume-plan-ai 该条已满足 ✓
