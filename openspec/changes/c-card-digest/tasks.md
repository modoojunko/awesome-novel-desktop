## 1. 摘要基建

- [x] 1.1 新增 `client/backend/assistant/card_digest.py`（候选/报告/长文三渲染＋单卡 1500 装箱＋截断标注＋收口句），验证：`tests/test_assistant_card_digest.py` 的 helper 用例通过（已在工作区实现，待提交）
- [x] 1.2 工具步折叠行改取摘要首行（`loop.py:_step_note`，220 上限保留），验证：`test_step_note_takes_first_line_and_marks_clip` 通过（已实现，待提交）

## 2. 设定域产卡摘要改造

- [x] 2.1 病 A 三处：`settings_intro`（draft/check）、题材四问、伏笔 draft/check 改人话摘要，验证：`test_settings_intro_*` / `test_settings_field_*` / `test_hooks_*` 通过（已实现，待提交）
- [x] 2.2 病 B 八个工具：世界观起草/体检、lore、主线四能力、卷级体检、命名、两个发散 摘要带内容，验证：`test_world*` / `test_arc_*` / `test_volume_check_*` / `test_draft_names_*` / `test_diverge_*` 通过（已实现，待提交）
- [x] 2.3 `read_settings` 预算 800→2000＋世界 yaml 空壳兜底，验证：`test_read_settings_intro_keeps_1500_chars` / `test_read_settings_world_empty_shell_returns_placeholder` 通过（已实现，待提交）

## 3. lore_suggest 修复

- [x] 3.1 工具加可选 `chapter_ref`：缺省取 frontier 当前章，无章可提回人话失败语；验证：`test_lore_suggest_passes_chapter_ref_and_keeps_fields` / `test_lore_suggest_defaults_to_frontier_chapter` / `test_lore_suggest_no_chapter_returns_human_message` 通过
- [x] 3.2 pick 卡 candidates 保留 `key/value/set/origin`（展示名 `set·key`），摘要逐条；工具 description 改为「指定章（缺省当前写作章）」；验证：`test_lore_suggest_passes_chapter_ref_and_keeps_fields` 断言四键齐全
- [x] 3.3 在 `tests/test_assistant_card_digest.py` 补 lore 用例（给定 ref / 缺省前沿 / 无章 / 空结果四场景）；验证：文件 25 passed

## 4. 回归与验收

- [x] 4.1 `cd client/backend && .venv/bin/python -m pytest tests/test_assistant_card_digest.py -q` → **26 passed**（工作树 `ai-novel-wt-card-digest`）
- [x] 4.2 `cd client/backend && .venv/bin/python -m pytest -q` → **3594 passed / 331 skipped / 0 failed**（8:58；该次全量在最后一处「空章文案映射」之前启动，该分支由 4.1 的 26 用例覆盖）
- [x] 4.3 `.venv/bin/ruff check` 改动 6 个文件 → **All checks passed**
- [x] 4.4 设计门禁豁免登记：本 change 无 UI 结构与共享段改动（依据 proposal「Design Impact」），不跑原型/`design:check`
- [ ] 4.5 真机走查（装包后）：① 设定·简介页说「你帮我起草简介」→ 摘要三条全见、不再出现「被截断」；② 设定·世界观页说「这章有哪些世界要素可以提」→ 出候选卡且无异常

## 5. 评审整改（review-agent）

- [x] 5.1 名册读取预算钉成独立常量 `READ_SETTINGS_CAST_BUDGET_CHARS=1600`，不再随 `read_settings` 基数翻倍；验证：常量入代码、全量测试绿
- [x] 5.2 折叠行带首个条目开头（≤60 字）作区分位，避免回放把两次不同产出并成「同样步骤 ×N」；验证：`test_step_note_distinguishes_two_generations` 通过
- [x] 5.3 「无章可提」改为 `ok=false`，与「正文为空」同一失败语义；验证：`test_lore_suggest_no_chapter_returns_human_message` 断言 `ok is False`
- [x] 5.4 顺手修存量：`_as_check_items` 对 `{name,status,note}` 出参按「name：note」收口，不再把 dict repr 画到报告卡；验证：`test_as_check_items_humanizes_name_note` 通过
- [x] 5.5 定向回归：`pytest tests/test_assistant_card_digest.py -q` → **28 passed**；`ruff check` 改动文件全过；`openspec validate --strict` → valid
- [x] 5.6 二轮评审 P2：折叠行首行不以句读结尾时补分隔空格（修「正常 2 条1.」粘连）；验证：`test_step_note_takes_first_line_and_marks_clip` 覆盖无标点首行
