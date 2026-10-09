# design — c-prose-model-select（生成弹窗按次换模型）

## Context

- 全书 AI 只有一个权威模型：`novels.ai_config_id` + `novels.ai_model`（`intro-genre-settings`「AI 就绪状态的单一事实源」）；业务代码走 `get_ai_client_for_novel(novel_id)`，`chat(model="haiku")` 经 `AIClient.resolve()` 落到**构造期**的 `self._model`（字面模型名直通，别名恒被吞）。
- 前端已具备跨配置的模型全集：`useModelStatus` 由 `GET /api-configs`（后端已剔朱雀）与 `GET /novels/{id}/ai-model` 组装 `modelOptions: FlatModelOption{api_config_id, config_name, model, vendor}[]` + `currentConfigId/currentModel/currentConfigName/aiState`；设置页 `ModelSettingForm` 是「按配置分组卡片列表 + 选择与生效分离」。
- 生成链路：`POST /api/novels/{id}/chapters/{ref}/write` 今天只收 `{prompt?}`，`_stream_chapter` 内部 `get_ai_client_for_novel` 构造客户端；记账 `record_usage(model="haiku" 变量, api_config_id=None)`——违反 `intro-genre-settings`「计量层记实际模型 id」条款（守卫只 grep 字面量，变量传递漏网）。
- 设计约束：模型选择控件 `SHALL NOT` 用原生 `<select>`/optgroup（`intro-genre-settings`）；弹窗内浮层会被 `.mcard` 滚动裁剪 —— 既有对策是 `.mp-*` 组合框弹层 portal 到 body + fixed（model-config 先例，见 `design/model-config.css` 注释）。
- 弹窗 `#modalAi` 不在 parity 截图场景内（`design-parity-book` 只覆盖 workbench/volume/settings/modal-delete/modal-prefs/modal-upgrade），原型只需同步形态 + ADJUSTMENTS 登记。

## Goals / Non-Goals

**Goals：**
- 生成正文可用与本书模型不同的模型，跨配置/供应商，**仅本次**生效、零持久副作用。
- 覆盖缝落在客户端构造处，`resolve()`/别名语义与「业务层禁字面模型名」的门禁都不动。
- 非法模型对的可读拒绝发生在开流前；记账记实际模型 + 配置。

**Non-Goals：**
- 不改本书绑定与 `require_novel_model` 门禁（按次选择不承担「本书未绑模型」的救援）。
- 不给规划类 AI 加按次选择（生成弹窗是唯一按次口）；提示词「AI 润色」已随 c-retire-prompt-polish 退役，弹窗内仅生成一处模型调用。
- 不做「记忆上次选择」与任何持久化；不新增设置页入口。
- 不引入自由输入的模型 id（只允许从配置清单选）。

## Decisions

1. **按次覆盖（不落库）而非持久切换。** 理由＝用户原话「规划用一种、生成可更换」；持久切换会连规划类 AI 一起换（本书模型是全书唯一权威）。备选：① 在设置页加第二个「生成模型」绑定——否（引入第二绑定权威，与「单一事实源」条款冲突且用户要的是弹窗内换）；② 每次生成后把本书模型改成所选——否（污染规划 AI、且是全书持久变更）。
2. **覆盖参数开在 `get_ai_client_for_novel(novel_id, *, api_config_id=None, model=None)`。** 覆盖体现在构造期 `AIClient(model=...)`，`chat(model="haiku")` 与 `resolve()` 不动。备选：把覆盖做成 `resolve()` 的入参——否（resolve 的入参是符号别名位，语义会歪，且业务层传字面模型名违门禁）。
3. **开流前解析客户端（handler 内 await），不在流内。** 非法模型对＝HTTP 400 JSON，走前端既有 `!response.ok → detailMessage → toast` 链路；流内报错会先摆出流式态再吐 error 事件。代价＝handler 多一次 DB 读。
4. **校验谓词与本书就绪同源**：配置存在且未删除、归属本书用户、`vendor != "zhuque"`、**`config_key_usable`（非空＋可解密＋最近连接测试非失败态）**、`model ∈ parse_models(config.models)`。评审整改（P3）：原实现只查「Key 可解密」，比本书就绪判据松一维——Key 已吊销但清单仍有模型的配置会被放行到流内才炸（同一状态若发生在本书配置上会被 503 拦在调用前），现统一到 `ai_state.config_key_usable`，宽严一致。
5. **前端仅在所选 ≠ 本书模型时携带模型对。** 默认路径请求体逐字不变（零回归面）；且避免「本书绑定已失效但仍照旧生成」的存量行为被新校验拦下。
6. **可选模型少于 2 个（或本书模型未就绪）时整行不渲染。** 对齐用户前提「模型配置有多个模型可选」；单模型用户 UI 零变化，不引入 disabled 死控件。`ai_state !== "ready"` 时也不渲染——按次选择是叠加在本书模型已就绪之上的选择，门禁语义不变。
7. **控件＝组合框＋弹层（`.mp-*`，portal + fixed 定位）**，触发位显示「配置名 · 模型名」，弹层按配置分组；新增三词 `.mp-trigger`（触发位）/`.mp-group`（组头）/`.mp-flag`（本书模型标记），`.mp-item` 改 flex 容纳尾注。备选：设置页同款卡片列表内联——否（弹窗纵向预算不足，且用户明确要「下拉」）。
8. **选项全集＝`useModelStatus.modelOptions`（全部配置 × 各自 `models`，后端已剔朱雀）**；`ai_state === "ready"` 时本书绑定对必在清单内（ready 谓词含 `model ∈ config.models`、配置未软删且非朱雀）——故无需额外补项，默认项＝绑定对。
9. **选择位每次打开重置为本书模型**（不记忆）：按次语义最可预测；选择位常显当前值，避免隐藏状态。
10. **记账记实际模型 id + 配置 id**（成功/超时/失败三处同口径）；同时收敛 write 路径的 `model="haiku"` 变量传递违规（`intro-genre-settings` 既有条款已要求）。
11. **字段只在弹窗打开时挂载**（`ModelPicker`/`ModelField` 随 `open` 挂载，`useModelStatus` 随之取数）：不占章工作台的常驻请求预算（每章多两次取数无谓）；顺带让「每次打开重置」天然成立。
12. **弹层定位收进共享助手 `lib/panelAnchor.ts`（评审整改 P2）**：`placePanel(rect, 视口高)` 一并算「大屏 zoom 折算、放不下翻转、限高」。① zoom：large-screen.css 是 `html { zoom: var(--ui-zoom) }`（≥2000px 视口起，2560→≈1.28），rect 给的是放大后的视觉值，直接铺到 fixed 的 top/left/width 会被再放大一次（实测 zoom=1.28 时宽 +186px、左偏 15px、下移 54px）→ 一律 `/zoom` 折算回布局 px；② 翻转/限高：按可用空间决定挂 `top` 还是 `bottom` 并给 `maxHeight`，弹层整层滚动。两条同族弹层共用（生成弹窗选择位＋模型配置页模型选择器——后者是本 change 之前就有的同一模式，一并收口，`zoom=1` 时数值逐字不变故无基线影响）。
13. **弹层高度改由弹层自身承担（评审整改 P2）**：`.mp-panel` 加视口上限（`max-height: 360px`＋`overflow-y: auto`），`.mp-list` 收掉自带的 `max-height/overflow`——原实现每组各吃 240px 上限、外层不限高，多配置累加后下缘落出视口且 fixed 弹层拽不回来（触发位在 900px 高窗口里约 600px 处，只剩 ~296px）。

## Risks / Trade-offs

- [按次换模型造成成本/质量漂移而作者忘记] → 选择位常显当前值；每次打开回本书模型；不改任何绑定；用量面板按模型/配置可辨。
- [所选模型未做过真实连通测试] → 只能从配置清单（探测产物）里选，服务端再按同源谓词校验；不提供自由输入。
- [规划类 AI 用本书模型、正文用所选模型让作者困惑] → 控件说明写明「仅本次生成生效，不改本书模型」。
- [记账口径变化可能触碰存量断言] → pytest 全量回归；若有断言依赖 write 用量为别名/空配置，按新口径更新并记录。
- [e2e 桩需要读请求体] → `prompt-pipeline` 的 `/write` 桩改为读 `route.request().postDataJSON()` 断言所选模型；既有断言不动。
- [大屏 zoom 层与弹层几何相冲（评审 P2）] → 定位换算抽成 `placePanel`（`/zoom` 折算＋翻转/限高），并加两层钉子：`panelAnchor.test.ts` 纯函数单测（含 1.28 折算用例）＋ e2e 在 2560×1400 下断言弹层与触发位对齐、视觉间距 = 6×zoom；变异自证：把 `/zoom` 抹掉后该 e2e 用例实测红（宽度差 450px）。
- [多配置时弹层落出视口、选项点不到（评审 P2）] → 弹层封顶＋整层滚动（D13）；e2e 用 4 组配置断言弹层下缘不越视口、`scrollHeight > clientHeight`、末组模型滚到底 `toBeInViewport`。

## Migration Plan

无数据迁移、无 schema 变更（请求体可选字段 + 记账内容）。回滚＝还原前端传参与后端覆盖分支即可，无持久副作用（不写库、不改绑定）。

## Open Questions

- 是否要做「记忆上次选择 / 按书持久生成模型」？本 change 按次语义（每次回本书模型）；若作家反馈重复选择太烦，另立 change。
