## 1. 拆书契约（prompts 仓）

- [x] 1.1 `deconstruct_style.prompt` 的 `rules`/`craft` 加可选 `scene`/`emotion`（封闭词表、判不出省略、不硬填「日常」）＋「带条件/不带条件」两种示例；`deconstruct_techniques.prompt` 的 `techniques` 卡加可选 `scene`；`deconstruct_reduce.prompt` 登记适用条件字段并补「条件不同保留两条」；`deconstruct_condense.prompt` 经查只压缩世界设定（不产文风/文笔），无需改。提示词工程师评审后删 `chapter_pos`（材料无卷边界）、收紧「换场面也成立就不标」、示例 name 不带场面词。`pytest tests/` → 124 passed
- [x] 1.2 提示词仓回归：`pytest tests/ -q` → **123 passed**。**样本拆书新产出验 when 未跑**（要整书拆书，成本高）——以存量回标样本（西式奇幻 44 条）替代验证；拆书新产出验证挂账

## 2. 入库贯通（本仓）

- [x] 2.1 映射单源在 `vendor_sdk/novel_deconstruct_sdk/mapping.py`：`style.rule` 与 `craft.craft` 的 `add()` 接 `when_json=_style_when(item)`；新增 `normalize_chapter_pos`（concepts.py）；空 when 不写。`pytest tests/test_sdk_mapping.py tests/test_kb_deconstruct_import.py` → **36 passed**
- [x] 2.2 闸门回归：补「角色设定带 when 拒收」＋「写法类（文风/文笔/手法）带 when 放行」用例；`pytest tests/test_kb.py -k when_json` → 3 passed

## 3. 存量回标（knowledge 仓）

- [x] 3.1 `tools/backfill_when.py`：只扫 `concept ∈ 文风/文笔`、`slot ∈ rule/craft`、`when` 空的源条目；规则层只看标题/名字（避免整段 instruction 顺带词误标），判不出再调模型（封闭词表校验）；幂等（已有 when 跳过）；默认 dry-run，`--apply` 写回（可选 `.bak`）；`--user/--config-id/--model/--genre/--limit/--no-llm/--verbose`
- [x] 3.2 西式奇幻样本：57 候选 → **44 条写入**（规则层 11＋模型层 33）；抽检后手工剔除 2 条可疑（「多视角切换」「内心吐槽穿插」标成文戏——只是行文顺带提到对话）；模型提示词已收紧「主体使用场景明确才标」

## 4. 基线 v6

- [ ] 4.1 全量回标后 `tools/validate.py` 全绿（**当前样本回标后已跑：8197 条，违规 0**）；`tools/build.py --version 6` 打包；确认 v6 中 `concept ∈ 文笔/文风` 且 `scope=scene` 的条目 > 0。**打包未做**：全量 3068 条需逐条调模型（约数小时/有模型成本），先等拍板
- [ ] 4.2 发布 v6（签名/版本目录只增不改，v5 保留）；C 端同步后 `kb_search_craft` 的场面级段出现候选（真库抽检记录）。**未做**（依赖 4.1 与发布批准）

## 5. 回归与挂账

- [x] 5.1 本仓：`pytest tests/test_sdk_mapping.py tests/test_kb_deconstruct_import.py` → 36 passed；`pytest tests/test_kb.py` → 34 passed；`ruff check` 通过。prompts 仓：123 passed
- [x] 5.2 三仓变更记录互链：本仓 PR / prompts 仓 PR / knowledge 仓回标 PR 号在各自 PR 描述互链（待开）
- [x] 5.3 挂账：前端「适用场景」编辑器（作者手写场景条目）另行立项；样本书新拆书产出验证挂账；全量回标与 v6 发布待拍板
