# Change: c-field-truncation-alignment

## Why

2026-10-09 渲染产物评审（工程师报告 C3/C4/C6）实证：三处生成侧字数钳位以硬切片方式把断句烙进书档，再作为正常数据被提示词消费——最重的一处（卷纲 conflict/ending 40 字）已进入 system 恒定层逐章注入。

样本（《我在夜晚打吸血鬼》vol-1-ch-6）：卷纲「核心矛盾：……同时应对」（恰 40 字）、「预期结局：……独自走」（恰 40 字）；章纲概要「体温计水银停在活人」（恰 150 字，断的恰是「结果」句，且下一章「上章写的是」同源中毒）；角色状态「……蒙在夜巡—」（恰 40 字，断在破折号前）。

**同日两次拍板**：先「句读截断＋上限对齐」（首版实现：clamp 改截到最后一个句读点、上限上调到 schema 容量）→ 当日用户追加拍板 **「不要截断，按完整的来引入」**——升级为终版：**内容字段不设字符钳位，完整直通**（含进提示词）；只保结构计数（条数）与卡片微标签（标题/评注类）预算。首版的句读截断实现随之退役（`clip_sentence`/`clip_plot_item` 保留为可选工具，生产链不再调用）。

## What Changes（终版口径）

- **生成侧钳位删除（内容字段完整直通）**：
  - `chapters/ai_plan._fit`：plot/obstacle/ending（→章纲概要/要撞的墙/章末落点，均进提示词）直通不截；卡片微标签 title/why/gap 保列宽。
  - `chapters/ai_plot._sanitize_versions`：剧情条目（entry/middles/exit）不截断，「已截到最后一个句号」告警退役；条数预算（`_MAX_MIDDLE`）保留。
  - `chapters/schemas.normalize_plot_items`：单条不再 `[:200]`，只保 12 条计数预算。
  - `volumes/ai_plan._sanitize_plans`：spine/conflict/ending/antagonist_line 直通（旧 40/40/40/150 退役）；`_sanitize_expand` summary/conflict/ending/antagonist_line 直通（旧 150/150/300/150 退役）；expand 卡面带入值（body.conflict/ending/antagonist_line）同步直通（旧 60/60/150）。
  - `volumes/ai_plan` 材料渲染：伏笔台账 description `[:60]`、人物 brief persona `[:80]` 直通。
  - `chapters/ai_cast` 人物 brief persona `[:80]` 直通。
- **存储与装配侧夹删除**：`chapters/store` 章纲 summary 列宽夹（`_fit(…,300)`）与角色状态 `state_change` `[:200]` 退役；`chapters/ai_draft` fills `[:300]` 退役。
- **提示词装配侧**：`write/chapter_writer` 角色状态逐格 40 字封顶退役（逐格完整直通；六层有标题分隔，长格不再挤掉后层）。
- **验证上限放宽**（完整内容可保存）：`volumes/schemas` summary 300→2000、core_conflict 150→1000、ending 300→2000、antagonist_line 150→1000（SQLite 不强制 VARCHAR 长度，此上限即真校验；放宽防「AI 完整文本 > 旧上限 → 保存 422」）。
- **模板侧**（prompts 仓，配合提交）：预算声明与代码口径对齐——`chapter_split` plot ≤150→≤300、`volume_options` conflict/ending ≤40→≤150/≤300、`volume_expand` summary/conflict/ending ≤80/60/60→≤150/150/300。终版下这些声明为**目标值**（引导模型输出体量），代码不再强制。
- **测试**：旧契约钉子 4 处改写为直通契约（test_plot_ai 超长条目、test_plot_items_save ×3），新增 3 处防回归钉子（角色状态直通、卷纲 sanitize 直通、剧情条目直通）；受影响套件 200/200 绿；全量套件 2156 passed（15 个存量环境失败不变，已对照原版实证）。

### 明确保留（非内容钳位，不在此列）

- **计数预算**：剧情条目 ≤12 条、卷 plants/reveals ≤2 条、fills 缺失键 ≤12、卡片列表 ≤6 等。
- **卡片微标签**：章标题 ≤12、why/gap ≤30、focus ≤20、卷名 ≤6、checks ≤40、评注类 ≤30。
- **设计内窗口/摘行**：上章结尾原文 ≤800 窗口、拆章「上一章一行」60 字摘行、提示词前提 ≤600、前情 ≤800、外观/情绪标量（mood ≤50）、归档摘要 ≤300（AI 目标 200，兜底永不触发）。
- **归档/台账元数据**：ChapterPayoffItem content ≤300（不进提示词）。

### 不做

- 存量断句数据（卷纲/章纲已烙断句）不自动回改——作者在表单手工补全。
- prompts 仓不再需要「钳位＝提示词上限对齐」的双侧同改纪律（代码端已无钳位）；模板字数为目标值。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `chapter-plan-ai`：「拆章卡面」字段内容不再截断（plot/obstacle/ending 完整进卡与提示词）；条目计数预算不变。
- `volume-plan-ai`：「两条并行入口」/「生成、生成完成与回填」内容字段完整直通；验证上限放宽。

## Impact

- C端：`chapters/{ai_plan,ai_plot,schemas,store,ai_draft,ai_cast}.py`、`volumes/{ai_plan,schemas}.py`、`write/chapter_writer.py`；受影响测试 200/200 绿，全量 2156 passed＋15 存量环境失败（对照实证）
- 提示词仓：`prompts/{chapter_split,volume_options,volume_expand}.prompt` 预算声明（前一批已提交 3b0ebec）
- 效果：新生成的卷纲/章纲/剧情条目/角色状态/伏笔/人物 brief 不再腰斩，完整内容直达提示词；无字符截断发生点
- 无 schema 结构/端点/前端变化；5274 演示栈重建后生效
