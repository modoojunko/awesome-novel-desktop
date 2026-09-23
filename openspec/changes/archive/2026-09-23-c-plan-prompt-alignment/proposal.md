## Why

拆卷/拆章提示词评审（对照外部「卷/章骨架能不能只写主角」建议，2026-09-23）发现两类问题：

**字段声明与代码读取不一致**——options 的 `focus`/`focus_axis` 在提示词里一句混说（「≤20 字，从侧重轴里取一个词」），而服务端只从 `focus_axis` 读闭集轴：模型照文案把轴词填进 `focus` 时落到「顺位补轴」兜底，轴与内容脱钩乃至同轴误丢。expand 的 `antagonist_type` 漏闭集声明（闭集外非法值被兜底静默改成「人物」——正是章级设计文档引以为戒的静默改写）。`volume_estimate` 只在 JSON 示例出现、全文无解释（未声明的字段，模型要么漏掉要么填成散文）。

**写法约束缺失**——章卡五段没有任何「客观局面」要求，而卡面 cast/factions/places 申报不落库，落库五段是「谁在场」信息的唯一持久通道（正文写作链只吃五段；下一章拆章的「已拆过的章」块只带剧情一句话＋阶段）：只写主角的章卡会让「谁在场」在排上那一刻丢失，正文 AI 只能编路人或写成独角戏。另有一处素材缺口：拆章调 `_book_material` 不传 `author_line`，人物聚光只扫主线前 200 字——多人物书里卷纲点名的关键配角对拆章 AI 不可见，与硬规则 2「不凭空添人」正面相撞（想用也没素材）。

## What Changes

- **volume_options**：`focus`（侧重说明 ≤20 字）与 `focus_axis`（侧重轴闭集词）拆分声明；`antagonist_type` 措辞统一为「从…里选一个」；`antagonist_line` 补 ≤150；`volume_estimate` 补字段说明（预计本卷章数范围）。
- **volume_expand**：`antagonist_type` 补五类型闭集声明；`summary` 字段带「关键配角点名」口径（照设定原文写全）；`antagonist_line` 补 ≤150。
- **chapter_split**：硬规则 10＝剧情写整个场面不只写主角（在场者写客观状态、不写性格心理；独处才只写主角）；`acts` 定义含在场其他人物的关键动作；`plot` 结果／`ending` 带局面从句；`checks` 加「点名的人这一章没出场」示例。
- **`chapters/ai_plan._chapter_material`**：卷纲聚光——主旨/冲突/坎点到的名字经 `author_line` 挤进【核心人物】（6 张上限、主角置顶、单换位机制不变；聚光文本只参与名字扫描、不进素材块）。
- **`volumes/ai_plan._sanitize_plans`**：钳位对齐提示词上限（spine 60→40、conflict/ending 120→40、focus 60→20、volume_estimate 60→20）——上限说明不该被更宽的兜底架空。
- **有据放弃两项（评审原案）**：自检加卷纲块（spec「章级 AI 自检」明文「不含卷纲四问」——缺席检查改由 chapter_split 的 `checks` 示例承担，split 素材里才有卷纲）；体检判据补缺坎 warn（已由体检素材 `ant_pair`「（未填——判据输出 warn，不编造）」实现，spec 已满足）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `chapter-plan-ai`：「拆章素材包与输出契约」——⑥核心人物卡补卷纲点名者聚光口径；新增「章卡写法提示词约束（客观局面）」条（提示词层 SHALL，不作服务端断言，照「三句互换位置读不通」先例）。
- `volume-plan-ai`：「提示词契约与输出校验」——侧重轴双轨字段声明、输出钳位与提示词说明一致、`antagonist_type` 闭集声明、expand `summary` 关键配角口径、`volume_estimate` 字段说明钉死。

## Impact

- 后端：`client/backend/volumes/ai_plan.py`（钳位）、`client/backend/chapters/ai_plan.py`（聚光）、`client/backend/prompts/volume_options.prompt`／`volume_expand.prompt`／`chapter_split.prompt`（文案）。
- 测试：4 个新钉子（模板逐字 ×3＋聚光功能用例 1 条）；全量 1359 passed（基线 1355 净增 4）。
- 不改：DB schema、前端契约字段、素材块清单与块级预算、章级自检输入边界、越纲对拍、门禁路径。
- 设计影响：无（无 UI／原型改动；S端 不涉及 → 免 `design-cross`）。
- 预期收益：拆章卡「谁在场」信息随五段落库进入正文写作与后续拆章素材；多人物书的卷纲关键配角可被拆章 AI 正确起用；模型输出的侧重轴与机读字段一致率上升；闭集外 `antagonist_type` 取值率下降。

> **补录说明**：实现已随 PR #484（squash＝8e166e02）于 2026-09-23 合入 main。本夹按 #480→#481 先例补建，随本归档 PR 同步 specs。
