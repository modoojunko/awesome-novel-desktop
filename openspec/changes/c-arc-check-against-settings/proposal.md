# 主线体检加第五条：和世界/人物对得上

## Why

`主线体检`（arc_check）目前只有四条检查线（故事连贯/开头接结局/三问对得上/和简介一个方向），且素材只有书名/简介/题材——c-arc-draft-material 明确把体检排除在设定素材之外。结果是「主线里写的势力、人物跟设定对不对得上 / 有没有踩世界铁律」这类冲突**结构上查不出来**：模型手里没有设定可对照。用户 2026-09-27 拍板加第 5 条判据。依据同族口径：《提示词素材给量》决策记录「校验型环节拿设定全量——裁判手里的法典必须全」。

## What Changes

- **体检纳入设定素材**（与起草/校准同源零件）：【世界观】（含「世界铁律·」红线）＋【人物档案】（全人物档案原文，六层只主角与反派）＋题材全字段＋书名/简介＋当前主线；素材顺序与边界声明同起草侧，任务与「只输出 JSON」压尾。
- **`arc_check.prompt` 增第 5 条检查线**，name 逐字：`和世界/人物对得上`——主线里出现的势力/人物/地点是否都在设定里（名字以设定原文为准）、是否违反世界铁律、与人物档案的定位有无硬冲突；**设定为空时本线给 miss** 并在 note 写「设定还没填，先补再查更准」。status 仍 ok/warn/miss，只提醒不拦确认。
- **旧口径收窄**：上一 change 冻结的「体检只看主线自身」改为「前四条只看主线自身，第 5 条以设定为对照」；「体检不多跑人物表与题材解析」的条款撤销（体检现在要设定全量）。
- **反证保持**：`tone`（行内基调）继续不吃设定素材——单格建议不需要法典。
- 前端零改动（面板级结果区按 `checks` 数组动态渲染，五条自动出）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `storyline-settings`: MODIFIED「右栏 AI 三行（全部聚焦主线）」——体检判据四条→五条（新增「和世界/人物对得上」）、体检素材改「设定全量（校验型口径）」、空设定时第 5 条降级为 miss 提示；其余素材边界（不含已拆卷/伏笔/文风/人物关系）与门槛不变。

## Design Impact

无用户可见界面改动（前端 `StoryArcForm` 以 `checks.map` 动态渲染体检结果，不写死条数），故不触发原型先行与 design 门禁；受影响端＝仅 C端 后端（`client/backend`）。

## Impact

- **代码**：`client/backend/settings/ai_router.py`（素材组装 gate 增 `check`）、`client/backend/prompts/arc_check.prompt`（素材块＋第 5 条判据）；零件复用不变（`world_summary_text(raw, None)`／`list_characters`／`build_genre_section`）。
- **计费/记账**：体检输入 token 上升到与起草同量级；`operation=arc_check` 与温度（判定类 0.3）、`json_mode` 不变。
- **接口/存储**：无形状变化（响应仍是 `{value:{checks,summary}}`，只是 checks 多一条）。
- **测试**：`test_story_arc.py` 的「check/tone 不组装素材」断言翻转为「check 组装、tone 不组装」；新增体检提示词断言（五条线名、世界/人物块在包、空设定占位）。
