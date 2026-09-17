## Why

右栏「AI 辅助」面板的「规划中」占位动作按用户拍板「后面一个个补」进入补货期。首批挑共用机器最顺、价值最高的两组：①正文选区变换族补上「压缩啰嗦段落」（与既有润色/扩写同通道，零新架构）；②把「提取本章变化／识别角色与物品变化／登记新伏笔」三个入口接到刚关账的收尾提案服务（按类按需触发，产出仍走待确认）。其余占位（冲突检测族/摘要建议族/提示词辅助族/补全缺失字段等）留后续批次。

## What Changes

- **选区变换族新增「压缩啰嗦段落」**：后端 `POST …/write/compress`（新 `prompts/compress_text.prompt`＋`write/auxiliary.py::compress_text`，与 polish/expand 同构：PRO＋本书模型门控、失败留 _fail 账、返回 `compressed_text`）；前端 `compressText`＋对照预览三态（润色后/扩写后/压缩后）＋右栏正文页签动作接 `onAiSelection("compress")`（选中才可点）。
- **收尾按类按需触发**：`POST …/reconcile/run`（body.kind 限一类且校验 KINDS 白名单，缺省全量五类；PRO＋本书模型门控；单飞语义沿用——已有任务在跑返回 started=false）；`start_reconcile_job` 增加 `kinds` 过滤。右栏三入口接线：设定「提取本章变化」→set_changes、关系「识别角色与物品变化」→relations、伏笔「登记新伏笔」→hooks（**归档后可点**，产出仍落「操作」页签待确认；点击后 toast 指路）。
- 其余占位保持「规划中」呈现（后续批次逐个补）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `prose-writing`：ADDED「选区变换（润色/扩写/压缩）」——三模式同通道契约（压缩为新增模式）。
- `archive-reconcile`：ADDED「按需触发本章收尾（run）」——kind 白名单/缺省全量/门控/单飞/右栏三入口。

## Design Impact

- **受影响端**：C端（正文页签与右栏 AI 辅助）。
- **对象状态**：无新语气档；压缩沿用对照预览与 toast 家族。
- **共享段**：未触碰 → 免 design-cross。
- **原型先行**：storyline.html 正文辅助「压缩啰嗦段落」为事实源；三入口对应 aiShell 各页签 acts。

## Impact

- 后端：`write/router.py`、`write/auxiliary.py`、`prompts/compress_text.prompt`、`archive/reconcile.py`（kinds）、`archive/reconcile_router.py`（/run）。
- 前端：`lib/ai.ts`、`lib/reconcileApi.ts`、`ProsePane`、`ContrastPreviewModal`、`Rail`、`AiAssistPanel`、`NovelWorkspace`。
- 测试：后端 `test_write_transform_modes.py` 3 例＋`test_reconcile.py::TestRunNow` 4 例；前端 AiAssistPanel 2 例；e2e reconcile 补右栏按类触发断言。
