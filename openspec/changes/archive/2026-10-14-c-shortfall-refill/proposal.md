# c-shortfall-refill — 字数不足的一键续写补足与写链遥测

## Why

c-scene-density（PR #843/#7）把「写不满」的根因链修了，但评审收尾留下两个缺口：①字数仍不达标（`done.word_check.below_limit`）的章没有**用户可见的确定性出路**——数据（target/actual/下限）都已在 done 事件里，作者却只能整章重掷骰子（重试=丢弃已写稿+重烧 tokens）；②两条验收观察项（写侧 max_tokens×thinking 截断率、抽卡档内命中率）**没有测量落点**，5.6 验收只能人肉数——PM 判「先测量、不先干预」，测量本身得先存在。

## What Changes

- **续写补足**：生成完成且 below_limit 时，完成卡提供「补足字数」动作——从当前正文末尾**续写**至下限（append，不重掷整章、不改写已写内容），沿用同章素材与恒定层，续写指令行按写链治理口径（下限要求合法、不投逐场配额）。补后重算 word_check；达标即不再显示动作。
- **写链遥测**：生成调用留痕扩记 target/actual/below_limit/finish_reason（截断判定）＋本章建议档位与实发条数的命中判定；档位与命中口径与 c-scene-density 的 `plot_count_hint`/`word_target_floor` 同源。截断率与命中率据此可聚合（5.6 观察项的数据面）。
- 不自动重抽、不自动补（动作永远作者触发）；不改写侧默认预算（截断数据说话后再议，本 change 只负责让它可见）。

## Capabilities

### New Capabilities

（无。）

### Modified Capabilities

- `prose-writing`: ADDED「字数不足续写补足」（完成卡动作＋append 语义＋门槛与回退）与 ADDED「写链字数与档位遥测」（留痕字段＋截断判定＋命中口径）。

## Design Impact

- 受影响端：C端单端。受影响屏：正文生成完成卡（word_check 展示位）新增一个动作按钮＋续写进行中的阶段呈现（复用既有 SSE 阶段流）；无新弹层。
- 对象状态：复用 `word_check.below_limit` 既有态，不新增状态语义；按钮词动词「补足字数」，补救文案带可点击出口（即本按钮本身）；语气词沿用 warn。
- 不触两端共享段；原型先行＝apply 首任务（完成卡布局微调需一版原型或按既有卡式自查）。
- 依赖：`plot_count_hint`/档位字段在 c-scene-density（#843）内——本 change apply 须排在 #843 合入之后。

## Impact

- 后端：`write/router.py`（续写端点 or 复用 /write 的 append 通道——apply 定形）、`write/chapter_writer.py`（续写素材组装：沿用恒定层＋user 素材＋「续写定位」指令行；治理自查同词不同句）、`api_configs/usage`（留痕列扩，照 TokenLog 既有加列先例）。
- 前端：完成卡动作位＋阶段呈现；`chapterTarget` 无涉。
- 测试：续写 append 不回退已写、达标后动作消失、免费档拦截零调用、遥测字段落痕、finish_reason 截断判定；5.6 验收单的两项观察转为可查询指标。
- 双仓：本件纯 C端行为＋遥测，模板零改动（提示词仓无同批件）；若 apply 发现续写指令行需模板承载，届时在本仓 change 内补记关联。
