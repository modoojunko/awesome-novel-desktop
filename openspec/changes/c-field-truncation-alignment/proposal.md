# Change: c-field-truncation-alignment

## Why

2026-10-09 渲染产物评审（工程师报告 C3/C4/C6）实证：三处生成侧字数钳位以硬切片方式把断句烙进书档，再作为正常数据被提示词消费——最重的一处（卷纲 conflict/ending 40 字）已进入 system 恒定层逐章注入。用户 2026-10-10 拍板「现在修」。

实证样本（《我在夜晚打吸血鬼》vol-1-ch-6）：卷纲「核心矛盾：……同时应对」（恰 40 字）、「预期结局：……独自走」（恰 40 字）；章纲概要「体温计水银停在活人」（恰 150 字，断的恰是模板要求完整的「结果」句，且下一章「上章写的是」同源中毒）；角色状态「……蒙在夜巡—」（恰 40 字，断在破折号前）。

根因：`_sanitize_plans`：498 行 `conflict[:40]`、`ending[:40]`；`_sanitize_expand`：693 行 `summary[:80]/conflict[:60]/ending[:60]`；`chapters/ai_plan._LIMITS["plot"]=150`＋`_fit` 硬切；`chapter_writer` 角色状态逐格 `[:40]`。均与 schema 实际容量（summary 300／conflict 150／ending 300）或下游需求错位——40/150 是生成卡面自设的窄瓶颈。

## What Changes

- `chapters/schemas.py`：新增 `clip_sentence(text, limit)` 句读点截断单源（超限截到最后一个「。！？；…」，整段无句读才硬截）——`clip_plot_item` 的实现下沉为唯一版本，禁止再写第二份循环。
- `chapters/ai_plot.py`：`clip_plot_item` 委托 `clip_sentence`（函数名保留，既有调用方与测试不动）。
- `chapters/ai_plan.py`：`_LIMITS["plot"]` 150→**300**（对齐下游 summary 容量）；`_fit` 改用 `clip_sentence` 并**超限告警**（logger.warning，静默烙断不再可能）。
- `volumes/ai_plan.py`：`_sanitize_plans` 的 conflict/ending 40→**150/300**（对齐 `VolumeCreate` schema），spine 保持 40（一句话走向的合理约束）＋全部句读截断；`_sanitize_expand` 的 summary/conflict/ending 80/60/60→**150/150/300**＋句读截断。
- `write/chapter_writer.py`：角色状态逐格 40 字改 `clip_sentence`（40 上限保留——c-ai-material-audit 防首格挤掉后五层，只修硬切不回退句边界）。
- prompts 仓（配合提交）：预算声明与代码钳位同一次对齐——`chapter_split` plot ≤150→≤300、`volume_options` conflict/ending ≤40→≤150/≤300、`volume_expand` summary/conflict/ending ≤80/≤60/≤60→≤150/≤150/≤300。仓库既有约束「钳位＝提示词字段上限（对齐）」要求两侧同改。

### 不做

- 存量断句数据（卷纲/章纲已烙断句）**不自动回改**——作者在表单手工补全（自动回改需要重跑模型，成本与风险更高）。
- 伏笔台账 description[:60] 保持（与 hooks 模板「60 字以内」口径一致，属设计内预算）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `chapter-plan-ai`：「拆章卡面」字段预算 plot 150→300（生成侧钳位与提示词声明同步）。
- `volume-plan-ai`：「两条并行入口」/「生成、生成完成与回填」字段预算 conflict/ending 对齐 schema（150/300），全部截断改句读点优先。

## Impact

- C端：`chapters/{schemas,ai_plan,ai_plot}.py`、`volumes/ai_plan.py`、`write/chapter_writer.py`；受影响测试文件 107/107 绿（test_plot_ai／test_chapter_writer／test_volume_plan_ai／test_volume_plan_t1_fixtures／test_volume_render）
- 提示词仓：`prompts/{chapter_split,volume_options,volume_expand}.prompt` 预算声明＋sync 元数据；51 绿
- 效果：新生成的卷纲/章纲/角色状态不再腰斩；截断发生时可从日志追查（warning）
- 无 schema/端点/前端变化；5274 演示栈重建后生效
