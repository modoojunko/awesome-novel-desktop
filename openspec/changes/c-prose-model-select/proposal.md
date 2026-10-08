# c-prose-model-select — 「AI 生成正文」弹窗可按次换模型（跨配置/供应商）

## Why

用户 2026-10-08 提出：「方便作家规划的时候用一种模型，生成正文的时候可以更换」。今天全书 AI 只有一个权威模型（`project.ai_config_id` + `project.ai_model`，规划类 AI 与正文生成同源）——想用 A 模型做规划、B 模型写正文，只能去「设定 › 本书模型」把全书切过去：规划类 AI 跟着一起换，且是持久变更，来回切没有出口。生成正文弹窗需要一个「本次生成用哪个模型」的选择位。

## What Changes

- **弹窗选择位**：「AI 生成正文」弹窗新增「生成模型」选择位，列出**全部 API 配置（跨供应商）× 各自模型清单**，默认选中「本书模型」；可选项少于 2 个时该行不出现（弹窗与今日逐字一致）。
- **仅本次生成生效**：所选模型 SHALL NOT 写回 `project.ai_config_id`/`ai_model`——本书模型、规划类 AI（章纲/设定/推演）与其他 AI 功能一律不受影响。
- **请求体按次携带模型对**：`POST /api/novels/{id}/chapters/{ref}/write` 接受可选 `api_config_id` + `model`；给定时按对校验（配置存在且属于本书用户 / `vendor != zhuque` / Key 可解密 / `model ∈ config.models`）后本次调用使用它，校验失败在**开流前** 400 返回可读错因（可换一个模型重试）；未给定时行为与今日逐字一致（本书模型）。
- **生成记账修正（存量违规收敛）**：`write_chapter` 用量行 SHALL 记**实际生效模型 id** 与配置 id。现状该路径传 `model="haiku"` 别名且 `api_config_id` 为空——intro-genre-settings 既有条款「`record_usage` 记实际模型 id」已要求如此（守卫 grep 因变量传递漏网）；按次换模型后用量面板必须能分辨每次生成是谁写的。
- **明确不做**：不改「本书模型」绑定语义与 `require_novel_model` 就绪门禁（按次选择是叠加在本书已就绪之上的选择，不承担「本书未绑模型」的救援职能）；不改提示词润色/刷新链路的模型（仍走本书模型）；不给规划类 AI 加按次选择；不新增设置页入口（要持久换请走「设定 › 本书模型」）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `prose-writing`: 生成端新增「按次选择模型」——弹窗选择位（跨配置分组、默认本书模型、仅本次生效）+ `POST /write` 可选模型对与开流前校验；生成记账改记实际生效模型/配置。
- `intro-genre-settings`: 模型选择控件族补「生成弹窗按次选择」形态的边界——沿用同一分组词汇与「SHALL NOT 原生 select」口径，且明确不落库、不改本书绑定（与设置页「选择与生效分离」的区别一句话说清）。
- `design-system`: 组件词汇登记——`.mp-*` 组合框弹层族首次复用到生成弹窗，新增 `.mp-trigger`（触发位）/`.mp-group`（配置组头）/`.mp-flag`（本书模型标记）三词；`.mp-item` 改 flex 容纳尾注；无新令牌、无新语气档。

## Design Impact

- **受影响端**：C端（单端）。S端 无对应面，不触 `base.css` 令牌与 `pill/notice/sk/panel/f-err` 共享段（→ 无需 design-cross，依据：本次只组合 C端 model-config 作用域的 `.mp-*` 词汇）。
- **受影响的屏/弹层**：「章工作台 › 正文页签 › AI 生成正文」弹窗（`#modalAi`）新增一行字段＋弹层；弹窗本身不进 parity 截图场景（design-parity-book 场景清单只有 workbench/volume/settings/modal-delete/modal-prefs/modal-upgrade），故无基线像素变更。
- **用到或新增的对象状态**（对照状态语言总表）：无新状态语义——模型行选中态沿既有「选中/未选中」（accent-soft 底 + accent 字）与 `.mp-item .on`；说明文字沿 `opt` 灰字；本书模型标记走既有 muted 小字（不新增胶囊形态、不新增语气档 info/ok/warn/err 之外的词）。
- **是否触碰两端共享段**：否。
- **是否需要原型先行**：需要——`prototypes/book.html` `#modalAi` 补选择位与弹层形态，`ADJUSTMENTS.md` 登记（注明不进 parity 截图，先例＝model-config 组合框）。
- **设计工件产出**：实现侧自查（词汇组合，无新视觉形态），无需设计侧会话。

## Impact

- 前端：`client/frontend/src/components/novel/workbench/modals.tsx`（AiModal 选择位 + `ModelPicker`/`ModelField`）、`NovelWorkspace.tsx`（确认透传）、`workbench/ProsePane.tsx`（`startWriting`/`startStream`）、`lib/ai.ts`（`streamChapterWrite` 请求体）、`types/api-config.ts`（`ModelSelection`）、`design/model-config.css`（`.mp-trigger`/`.mp-group`/`.mp-flag`）。
- 后端：`client/backend/write/router.py`（body 解析 / 开流前客户端解析与 400 / 三处记账）、`client/backend/ai_client.py`（`get_ai_client_for_novel` 支持按次覆盖对）。
- 测试：pytest（按次覆盖：校验四例＋记账一例＋无覆盖回归一例）、vitest（AiModal 选择位：默认本书模型 / 换模型透传 / 单项不显示 / 弹层分组）、e2e（prompt-pipeline：所选模型进 `POST /write` 请求体）。
- 原型：`docs/design-c/prototypes/book.html` + `prototypes/ADJUSTMENTS.md`。
- 依赖：无新增依赖；复用 `useModelStatus`（`GET /novels/{id}/ai-model` + `GET /api-configs`）。
