## 1. 测试先行（钉行为再改实现）

- [x] 1.1 在 `client/backend/tests/test_dialog_prose_tools.py` 补 picks 形态用例：JSON 字符串形态成功解析为条目、坏 JSON/对象/纯文本形态返回 `ok=False` 且不出卡、`[]` 出卡并回执「未带写法条目」、无效 id 进 `invalid_entry_ids` 且回执点名；先跑确认新用例按预期红（9 failed），实现后全绿
- [x] 1.2 补 `kb_search_craft` 分桶用例：手法与场面级文笔/文风同时命中时分两段返回；style 组为空时回执说明「无场面级文笔/文风条目；全书级不参与写章检索」；构造本书 `style` 三区为空的 ProjectSetting，断言回执附「本书文风三区未配置」与至多 6 条草稿；三区写满的对照断言不附草稿段
- [x] 1.3 补 `settings/style_kb` 回归钉：抽取 `load_style_entries` 后 `GET /settings/style/kb-draft` 的返回逐字段不变；跑 `pytest tests/ -k "style_kb or kb_draft"` → 12 passed

## 2. picks 参数契约（assistant/tools_cards.py）

- [x] 2.1 `_draft_prose_plan` 入口增加 `_normalize_picks`：字符串先 `json.loads`（8K 上限）→ 必须为数组；解析失败/非数组返回 `ToolResult(ok=False)` 并说明期望形态，不再静默降级
- [x] 2.2 回执分三态：未带条目（附「把 entry_id 放进 picks」）、无效 id 逐个点名、已解析 N 条列名；reason 为空时提示补一句裁决理由
- [x] 2.3 更新 `draft_prose_plan` 工具 description（picks 接受数组或 JSON 字符串、失败会报错）；`pytest tests/test_dialog_prose_tools.py` 23 passed

## 3. 候选分桶与场面级说明（assistant/tools_kb.py）

- [x] 3.1 `_kb_search_craft` 候选行按 `concept` 分 tech/style 两组，各自沿用 `_craft_terms` 打分（同公式、同 `overlap>0` 门槛）、排序取 `limit`；summary 分「手法候选」「场面级文笔/文风候选」两段
- [x] 3.2 style 段为空时按原因输出文案：域内只有全书级（附 base 文笔·文风计数）或库内没有文笔/文风条目；分桶用例 23 passed

## 4. 书级文风草稿出口（settings/style_kb.py + assistant/tools_kb.py）

- [x] 4.1 抽出 `load_style_entries(db, user_id, theme)`（用户条目＋基线 merged、`concept ∈ 文风/文笔`、`when_json` 空、同题材优先），`style_draft_from_kb` 改调它且返回契约不变；style-kb 回归 12 passed
- [x] 4.2 `assistant/tools_kb.py` 新增 `_book_style_draft_lines`＋`assistant/style_gap.py` 三区空判断（读取失败按未配置）；未配置时同题材优先、文风/文笔按概念交替取 6 条（真库实测剧情词排序会挑出不贴调性的条目，已改为不按剧情打分）；段头标注「按题材列出，需按基调筛选；不进 picks；建议设定·文风 → 按题材填文风采纳」
- [x] 4.3 三区已配置不追加草稿段；无题材沿用既有「先定题材」提示；对照用例通过

## 5. 文案对齐

- [x] 5.1 `kb_search_craft` 工具 description 改为准确口径（分两段；全书级走三区；未配置给草稿提示）；`tests/test_assistant_registry.py` 通过
- [x] 5.2 `assistant/scopes.py` 正文页纪律改为准确口径（候选分两段；三区正门；草稿不进 picks）；`tests/test_page_scopes.py` 通过
- [x] 5.3 预算：草稿 ≤6 条、instruction ≤120 字；分桶＋草稿合计断言 ≤2600 字（用例内钉住）

## 6. 书级通用 vs 章级场景的裁决纪律

- [x] 6.1 `assistant/scopes.py` 正文纪律补裁决口径：书级三区通用基线；章级按剧情选场景条目；同义/近义去重；冲突按「贴场面节奏→贴人物声线→念读顺口→不与书级基调撕裂」；理由写 picks.reason/本次写法要求；作者章级影子优先。`test_page_scopes.py` 关键词断言通过
- [x] 6.2 `draft_prose_plan` 回执补「裁决可见」：picks 的 reason 为空时提示补一句去重/让位理由；三区空时回执带「建议先到设定·文风按题材填文风」。用例通过
- [x] 6.3 裁决用例：单测层可断言的已钉（纪律文案含四判据/去重/影子优先；reason 缺失提示；三区空提示）。**语义裁决本身（「提示词只出现一条」「冲突选短句」）取决于 agent 按纪律执行，单测无法替代**——转真机走查（7.2），本 task 在此如实收窄

## 7. 回归与收尾

- [x] 7.1 全量后端回归：`pytest tests/ -q` → **3577 passed / 331 skipped / 1 failed**；唯一红 `test_deconstruct_import_async.py::test_cancel_during_write_cleans_partial_book` 单跑复绿（全量并发时序 flake，与本次改动无关；本次未触拆书导入）。`ruff check .` → All checks passed
- [ ] 7.2 真机/真库抽检（本机 0.49.5 库·西式奇幻书）：**真库只读抽检已过**（复制 0.49.5 库→临时副本，`kb_search_craft` 分桶＋「库内 58 条均为全书级」＋草稿段；JSON 字符串 picks 经 `draft_prose_plan` 解析为 1 条、invalid=[]、回执带三区未配置提示）。真机 UI 走查（agent 在方案卡上的去重/裁决理由）待装新包后做
- [x] 7.3 挂账登记：`c-agent-dialog-prose` 归档时同步分桶/草稿措辞；拆书侧产出 `when` 与存量回标由 `c-kb-scene-tagging` 负责
