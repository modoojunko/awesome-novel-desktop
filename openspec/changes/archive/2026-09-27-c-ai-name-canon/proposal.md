# 主线专名口径：规则单源＋名册＋对拍告警（c-ai-name-canon）

## Why

起草主线时，AI 会**沿用作者旧稿里的专名**——真书实测：作者的 `story_arc.fullstory` 里写着「与'豢养派'的旧贵族做交易」，而世界设定势力表只有三家（夜巡守夜人／血族议会／圣银教团），新起草的产出照旧带「豢养派」，越传越广（卷纲、章提示词里也跟着有）。

用户 2026-09-27 明确要求：**不要按个案打补丁**（"这次是豢养派，下次呢？"），要**通用框架**——适应各类题材与作者。

**关键实测**（两条，决定了框架形态）：
1. 只加一条抽象规则（"专名以设定为准"）**无效**：真机产出里「豢养派」照旧。
2. 给**名册（清单）＋规则**后有效：同一本真书重跑，产出里「豢养派」消失、「主战派」（写在世界设定注记里）保留。
3. "发现后自动纠正一次"**无效**：把违规名点名要求改名重写，纠正轮产出依旧沿用（白烧一次调用）→ 砍掉，改为**只提醒**（随响应带 `name_warnings`）。

## What Changes（范围：仅主线起草/校准）

- **规则单源**：新增 `prompts/name_canon.prompt`（与题材/作者无关的通用措辞：名字只取名册里登记的；作者自由文本里未登记的专名不得沿用，改用登记名或通称；某一类未登记就退通称）。主线硬约束② 改为引用它（`{name_rules}`），不再各模板手抄。
- **名册**：新增 `settings/name_registry.py`——`known_names`（角色名＋别名／势力名／地点）＋`roster_text`（把清单摆进提示词）。起草/校准提示词新增【本书专名册】块；空类别写明"这一类要提就退通称"（现实题材无势力同样成立）。
- **对拍告警**：`suspect_unregistered`（确定性扫描：以组织/派系词尾为锚，命中名册或世界设定原文即放行；纯汉字＋粘连字过滤，宁可漏报不误报）＋产出 `names` 申报面 diff；命中则响应带 `value.name_warnings`（**不自动纠正**）。
- **输出契约**：起草/校准的 JSON 增 `names` 字段（照实申报用到的人物/势力/地点名，供对拍）。
- **不涉**：拆卷/拆章/章纲起草/写正文等环节（用户明确本批只做主线）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `storyline-settings`：MODIFIED「右栏 AI 三行」——起草/校准的硬约束②改为「专名口径＝规则＋名册」；产出申报 `names` 与名册外专名的 `name_warnings` 告警口径入规格。

## Design Impact

无用户可见界面改动（后端提示词与响应附加字段；`name_warnings` 前端暂不消费，主线体检第五条同源可查）。受影响端＝仅 C端 后端。

## Impact

- **代码**：`settings/name_registry.py`（新）、`prompts/name_canon.prompt`（新）、`prompts/arc_hard_rules.prompt`、`prompts/arc_draft.prompt`、`prompts/arc_calibrate.prompt`、`settings/ai_router.py`、`tests/test_story_arc.py`。
- **计费**：起草/校准输入 token 略升（名册清单）；**不追加调用**（纠正轮已砍）。
- **接口**：响应 `value` 可能多 `name_warnings`（未知键，前端零影响）。
- **真机证据**：`real-machine-check.md`——同一本真书：只加规则时「豢养派」仍在 → 加名册后消失（「主战派」保留）→ 自动纠正轮无效故砍掉。
