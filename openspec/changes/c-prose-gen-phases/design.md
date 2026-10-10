## Context

见 `proposal.md`。实现相关的现状与约束：

- 写正文端点 `POST /api/novels/{id}/chapters/{ref}/write`（`client/backend/write/router.py`）当前把「素材组装（`build_chapter_context`）／提示词定稿（存量稿回落判定 + `save_prompt` ＋阶段推进）／AI 客户端构造／system 恒定层组装」全部放在**响应开始之前或 `try` 之外**；响应以 `StreamingResponse` 开始后，该段异常不会产生任何事件——客户端只收到 200＋干净结束的空流（c-prose-stream-silent-hang 路径①，已实测）。
- 现有 SSE 契约：`data: {"type":"chunk"|"done"|"error", ...}`（`client/frontend/src/lib/ai.ts::doStreamFetch` 逐行解析，只认这三种；流结束未见终态事件时无任何回调）。
- 视觉词汇已存在：`client/frontend/src/design/base.css` 的 `.pm-steps/.pm-step(.done/.doing/.wait)/.pm-ic`（写作能力弹窗分步行；§5 状态语言表已登记形态：当前步＝accent 呼吸点、完成步＝accent 对勾、未到步＝描边空点）。
- 规划台 `genbox` 的步骤列表（`VolumePlanModal`）是三行全部「进行中」的演示态——本 change **不**沿用这种非真实进度，改为服务端事件驱动的真实阶段。
- 门禁约束（openspec config）：原型先行（`prototypes/book.html` ＋ `ADJUSTMENTS.md` 登记）；`design:lint` → C端 `design:check`（book 屏不在 parity 矩阵内，设计-parity-book 为独立 spec）→ `tsc`；文案遵 §13。

## Goals / Non-Goals

**Goals:**

- 首字等待期呈现**真实**阶段（准备本章素材 → 组装提示词 → 模型思考中），事件驱动、可测试。
- 准备段任何失败不再静默：以 `error` 事件收尾，落到既有 toast＋收尾路径。
- 前端补齐「流无终态事件」兜底：失败收尾＋半截保留，SHALL NOT 永续生成态。
- 视觉零新形态：复用既有分步行词汇与令牌，不触碰两端共享段。

**Non-Goals:**

- 不修「上游空流（0 内容）按成功落库＝静默清空正文」路径②（另一拍板项，见 c-prose-stream-silent-hang）。
- 不做百分比进度、阶段耗时统计、预计剩余时间；不做等待秒表。
- 不改动 `chunk`/`done`/`error` 语义与门禁（会员/档位/模型就绪/排队/按次模型对）语义。
- 不改 SSE 传输方式（仍为 POST + 单向流，不引入 WebSocket/轮询）。

## Decisions

**D1｜阶段事件形态＝「当前阶段」语义的单个事件**

新增 `data: {"type":"phase","phase":"assemble"|"prompt"|"model"}`；一个事件标记该阶段**开始**，此前阶段即视为完成（首字到达隐含完成 `model`，无需补事件）。

- 备选 a：每阶段 start/end 两条事件——冗余且前端状态机复杂；备选 b：把阶段时间线塞进 `done`——等待期恰恰没有终态事件，无法用于本目标。
- 兼容性：旧解析器只匹配三种 `type`，未知 `type` 被忽略 → 前向兼容；本仓前后端同批发布。
- 语义边界：`phase` 事件 SHALL NOT 进入正文/落库；后端不保证阶段密度与耗时（诚实反映真实进度，不人为控速）。

**D2｜准备段移入流内；可读 4xx 校验留在开流前**

- 移入流内：`build_chapter_context`、提示词定稿（覆盖 > 存量回落 > 组装）、`save_prompt`、阶段推进＋commit、`build_system_prompt`、AI 客户端构造（本书模型路径）。
- 留在开流前：会员/档位/模型就绪/排队门禁（403/409/503）、按次模型对校验与其 override 客户端构造（400）——这些必须能以状态码表达失败。
- 备选：加一个「预检查」端点先跑准备再开写流——多一跳、两段状态难对齐，否决。
- 影响：准备段异常从「500（开流前）」变为「error 事件」；两者对作者都是可读报错，且后者不再受「响应已开始」限制。

**D3｜流内准备段包错误收尾（消掉一类静默断流）**

移入流内的整段（含客户端构造与 system 组装）包进 `try/except`，失败 `yield error` 事件并 return。这是「阶段可见」的必要配套：否则准备段失败时阶段卡片会永久停在首步、仍是静默。

**D4｜前端兜底：流结束未见终态事件＝失败收尾**

`doStreamFetch` 记录本流是否见过 `done`/`error`；`reader` 结束后未见 → 调 `onError("生成中断：未收到完成信号…")`（同时该流只报一次，防 error＋兜底双报）。`ProsePane` 既有 `onError` 路径（toast＋`finishStream(partial, false)`）自动承接，半截保留语义与「停止」一致。

**D5a｜等待期呈现＝无框行内（用户 10-10 拍板）**

正文版心内、与正文同字体同首行缩进的行内呈现；三个候选变体待用户选定：**A 文案＋光标（推荐）**／B 版心顶细线＋工具行文案／C 纯光标。共同口径：无边框卡片、无底色块、不进文档、首字到达即退场、**首字前不出现呼吸框**。已出真界面原型草稿供拍板（`docs/design-c/drafts/ai-novel-c端-生成等待呈现-无框三变体-真界面原型.html`）。

**D5b｜阶段状态位与渲染（ProsePane）**

- 状态：`genStage: "assemble"|"prompt"|"model"|null`；`startStream` 即置 `assemble`（请求在飞＝后端确在准备，诚实落首步，防卡片空白）；`onPhase` 推进；**首个 `onChunk`**、`finishStream`（含停止/失败）一律清空。
- 渲染：`streaming && 首字未到` 期间，在正文区挂覆盖层卡片（非文档）：标题行＋三步分步行＋尾注（时长预期与「停止」出口指路）。`position:absolute` 与 680 版心同位对齐，`pointer-events:none`——不参与编辑链布局、不挡任何操作；滚动与 `scrollInsertIntoView` 不受影响。
- 备选：插入到 `.editor-host` 内的兄弟节点——会被编辑态纵向 flex 链（host flex:1）挤到版心底部，否决；直接改文档内容——违反「非文档」要求，否决。

**D6｜生成态占位退场 ＋ 呼吸灯后置**

呼吸灯不再在开流即挂载：等待期挂「等待态」（不作呼吸动画），首个片段到达时亮起。**环的范围同时修正**（用户 10-10 反馈：环不够大）：由「只环 680 版心（`.editor.generating`）」改为「环全文编辑体」——实现侧在 ProsePane 里给 [编辑工具行 ＋ `.editor-wrap`] 加一层包裹（`.prose-body`，`display:flex; flex-direction:column; flex:1 1 auto; min-height:0; border-radius:10px`），环（`stream-breath`）挂在包裹层上；`.editor.generating` 不再承担环（保留 `cursor:progress` 语义）。环为 box-shadow，不动版式——流式写入位置（680 版心）不变。原「流式开始即起、收尾即止」的既有规格句随本 change 更正为「首个正文片段起」。


`.editor.generating` 下 Placeholder 的 `::before` 置 `content:none`（CSS 单条），不改 `Placeholder` 扩展与 `data-placeholder` 属性（查看态/普通空章占位不变）。

**D7｜原型先行**

`docs/design-c/prototypes/book.html`：生成态补同款阶段卡片（样式复用 `.pm-steps` 段，原型自包含），演示链改为「三阶段逐个推进→首字」；`ADJUSTMENTS.md` 登记（新增条目：产品侧阶段卡片落地，附原因与实现位置）。

## Risks / Trade-offs

- [准备段移入流内导致既有测试对 500 的断言失效] → 实现期全量检索 `/write` 相关用例（后端 `tests/`＋e2e 路由 mock），同步改为断言 `error` 事件；回归小节记录实际输出。
- [阶段卡片在瞬时生成时闪现] → 接受（真实反映；不人为延时）。若观感刺眼，后续单列「最短展示时长」讨论。
- [覆盖层与既有呼吸灯/徽章叠加显噪] → 卡片克制（单卡片、三步、尾注一行）；`design:lint`＋截图复核；必要时收敛尾注。
- [文案触 §13 内部术语红线]（如「阶段」「事件」字样）→ 文案只出现作者语汇（准备/组装/模型/等待首字/停止）；`design:lint`＋人工复核。
- [旧前端＋新后端／新前端＋旧后端 的组合]（开发中同一检出不存在，打包分布时可能瞬时存在）→ 旧前端忽略 `phase`（卡片停在首步至首字，可接受）；新前端遇旧后端＝阶段不推进（同样停在首步），兜底逻辑不受影响。发布为单包，不构成长期兼容面。

## Migration Plan

- 前后端同批提交、同包发布；无数据迁移。
- 回滚＝整包回退；SSE 为增量事件，无破坏性变更。

## Open Questions

- 阶段卡片尾注最终文案（「通常需要半分钟到一分钟；期间可点「停止」」草案）在实现期过 §13 与 lint 后定稿——不改变方案与任务拆解。
