## 1. P0（必修）

- [x] 1.1 章纲起草素材：`chapters/ai_draft.py` 新增 `_setting_blocks(db, project, ctx)`（【世界观】全量含铁律／【题材与节奏】／【人物】全名单一行卡·主角置顶·人设原文），接入 `ai_draft_outline` 与 `fill_outline_gaps`（`_material_from_ctx` 改 async）；出场者状态不再封 5 人、活跃伏笔不再封 8。验证：`test_outline_ai_draft.py::test_draft_material_includes_settings`（三块在包＋铁律行＋角色行）。
- [x] 1.2 世界铁律单源：`volumes/ai_plan.py` `world_rules` 改 `render_red_lines(raw)` 单源（删 `constraints` 死分支），拆章 ⑦／章内剧情／卷体检三消费方随之恢复；新增 `test_chapter_plan_ai_t3.py::test_world_rules_block_renders_when_defined`（有铁律必在块，替代原先"因数据为空而恒真"的负面断言）。验证：pytest 绿＋真机（见 4.3）。

## 2. P1（批量）

- [x] 2.1 角色 AI：`_world_summary` 改 `world_summary_text(raw, None)`（修 `factions[*].value` 恒空＋势力/铁律/history 全量）；`no_power` 改读 `normalize_world` 结构真值（修渲染标签变更导致的判据失效）；卡文本取消 `[:2000]`；主线取消 600；名册取消 12 人封顶。验证：`test_characters_ai.py` 全套绿（含力量向项集用例）。
- [x] 2.2 世界体检/起草/lore：`world_summary_text(..., 1200)` → `None`（三处，含 `_world_context` 共享件）。验证：世界体检相关套件绿。
- [x] 2.3 写正文：在场者 5 人上限退役（三处）；角色状态改逐格 40 字（`WRITE_STATE_PER_CELL_MAX` 真用起来）；`write/router.py` 精修取消 `[:12000]`。验证：`test_chapter_writer_context.py` 改断言为「角色7 在」（原断言＝5 人上限）。
- [x] 2.4 续写/润色：角色快照改真表（`list_characters`＋别名匹配＋人设/语言特征；未建卡显式「（未建卡）」），删退役 YAML 读路径与由此空置的 `get_storage` import；禁用词/句式不截。验证：`write/` 相关套件绿（`test_style_settings_v2` 等）。
- [x] 2.5 伏笔链：`_hooks_draft_context` 的主线与 `hooks_ai` check 的世界改全量。验证：`test_hooks_ai.py` 套件绿。

## 3. P2（含两处 spec 自相矛盾的裁决）

- [x] 3.1 拆卷「已拆卷清单」去掉 summary/坎/卷末 各 60 字截断；拆章「已经拆过的章」去掉 `[-12:]` 与每行 `[:40]`。验证：拆卷/拆章套件绿。
- [x] 3.2 卷体检补两问：`volume_check.prompt` 增「主角最终怎样／读者读后的感觉」两行，`volumes/ai_plan.py` 传 `hero`/`tone`。验证：卷体检套件绿＋真机（4.3）。
- [x] 3.3 活跃伏笔注入全量：`prompt/context.py` `[:8]` 退役；`test_hooks_consumers.py` 断言改为「12 条全在、按 seq」。验证：pytest 绿。

## 4. 归档与收尾类

- [x] 4.1 归档：`archive/service.py` 摘要正文取消 `[:3000]`；`archive/reconcile.py` 收尾提案 set_changes/lore 带「现有世界设定（与之重复的不要提）」＋正文全量。验证：`test_reconcile.py` / 归档相关套件绿。
- [x] 4.2 spec 同步面：`outline-ai-draft`（素材包条目＋新场景）、`chapter-plan-ai`（预算例外＋新场景）、`volume-plan-ai`（伏笔全量）、`storyline-settings`（≤8 引用改写）四份 delta 生成并 `validate --strict` 通过。

## 5. 门禁与证据

- [x] 5.1 `pytest tests/` 全量 → **1538 passed**（新增 2 例、改 2 例）；`ruff check` 覆盖全部改动目录 → 仅 2 条存量告警（`PLW0127` style 蒸馏段、`F841` 写章自检未用变量），**零新增**；模块导入自检通过。
- [x] 5.2 前端门禁判定：零前端改动（proposal Design Impact：前端不消费这些文本），design 三项不适用；验证：`git status` 仅 `client/backend/` 与 `openspec/`。
- [x] 5.3 真机抽查（隔离栈）：章纲起草素材含世界三势力与铁律（对照改前"零世界素材"）；卷体检渲染真实铁律而非「（世界设定未登记铁律）」。验证：证据文件 `real-machine-check.md`。
- [x] 5.4 收尾：`openspec validate c-ai-material-audit --strict` 通过；非目标四项（反推/归档提示词治理、写正文深卡全量、known_entities 窄口径、写正文世界块预算）已在 proposal/design 登记。
