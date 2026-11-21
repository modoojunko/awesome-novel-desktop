## 1. 原型先行 / 影响判定

- [x] 1.1 判定并登记：本改动落在助手 dock 内部（输入底栏 + 对话流过程卡），不在 `docs/design-c/prototypes/` 四屏 parity 基线（list/book/model-config/model-config）覆盖范围内，无需改原型文件；在 proposal「Design Impact」记录设计依据（boss 2026-11-21 截图与文字）与「不触共享段」结论（base.css 令牌 / pill·notice·sk·panel·f-err 家族零改动）——验证：proposal 该段存在且与实际 diff 一致
- [x] 1.2 跑 `openspec validate c-agent-thinking-bubbles --strict` 并确认通过（artifacts 齐、delta 合法）

## 2. 后端：思考开关与模型覆盖

- [x] 2.1 `assistant/loop.py`：`LoopConfig` 增 `thinking: dict | None`，text/native 两分支 `chat_stream(...)` 均透传；`ASSISTANT_STEP_MAX_TOKENS` 默认 2048→4096——验证：单测断言 fake client 收到的 `thinking` kwarg 与默认预算
- [x] 2.2 `assistant/router.py` `/chat`：解析 `thinking: bool`（→ enabled/disabled dict）、`api_config_id`+`model` 成对覆盖；`_stream_chat` 用覆盖对构造 client，覆盖失败走现有 `client_error` gate 且文案区分「你选的助手模型用不了」——验证：HTTP 级测试断言 fake client 收到覆盖对、thinking 进入 LoopConfig、错误分支出 gate

## 3. 后端：过程落盘与回看

- [x] 3.1 `session_store.update_message_status` 增可选 `payload` 合并参数——验证：单测断言旧 payload 保留、新键并入
- [x] 3.2 `router._consume` 维护有序 process items（thinking 合并 / step_start 建项 / step_end 原位补 note·ok·apiCalls）；`_finalize` 把 `{"process":[...]}` 并入本轮 assistant 行，未收口项标 interrupted——验证：HTTP 级测试发 thinking+step_start+step_end 后 GET /session，断言 assistant payload.process 顺序/字段/收口态
- [x] 3.3 旧会话回放兼容：无 `payload.process` 的回合仍由 tool 行走旧「运行轨迹」折叠卡（含 ×N 去重）——验证：既有 session store / Aui2Dock 历史用例保持绿

## 4. 前端：输入底栏三控件

- [x] 4.1 `lib/chatApi.ts` body 类型增 `thinking?: boolean`、`api_config_id?: string`、`model?: string`——验证：`npx tsc --noEmit`
- [x] 4.2 `Aui2Dock` 底栏用 `morePrefixActions` 包一层 flex-wrap 容器，同排放模型 pill（复用 `workbench/modals.tsx::ModelPicker` + `useModelStatus`）、深度思考 pill（`aria-pressed`，默认开）、授权 pill；选择按 `projectId:threadKey` 存 localStorage 并在切线程时重读——验证：单测断言默认本书模型、切模型后请求体带覆盖对、关思考后请求体 `thinking:false`、授权 pill 仍工作
- [x] 4.3 模型覆盖等于本书模型时不发覆盖对；选中项失效（配置删除/不在清单）回落本书模型并清 localStorage——验证：单测覆盖两条分支
- [x] 4.4 底栏 pill 视觉：复用 `.cd-auth-pill` 形态，新增少量容器/省略号 CSS，使用既有 oklch 令牌，不新增胶囊形态/裸 hex/emoji——验证：`npm run design:lint` 本改动文件零违规（全库仅预存 docs 原型 emoji 红）+ 截图自查

## 5. 前端：过程泡泡与回放

- [x] 5.1 新增 `trace_thinking` / `trace_tool` 两个 card（`OperateCard` + `OperateCard.LineBody` + `@agentscope-ai/icons`）：思考默认单行「思考中/思考过程」，工具默认单行「工具名 + 摘要」，点开显示思考全文 / 打算·结果·模型调用；状态 running/ok/error/interrupted——验证：单测断言默认 body 不在 DOM、点头部展开后全文/详情出现
- [x] 5.2 事件映射：`thinking` 合并到当前思考项、`step_start` 建 running 工具卡、`step_end` 原位补 note/ok/apiCalls、`onDone/onError` 收口 live/running；卡片挂本轮 assistant 消息 `cards[]`（正文之上）——验证：单测驱动 SSE 断言卡片顺序、无重复、正文无 `● tool ✓`
- [x] 5.3 回放：assistant 行有 `payload.process` → 生成同序卡片并挂回该回合；抑制该回合后续旧 tool 行的轨迹折叠；thinking 不计入容量条估算——验证：单测构造带 process 的历史断言出卡与正文顺序、容量不虚增
- [x] 5.4 CSS：过程卡容器边框/间距/思考正文限高滚动/工具摘要省略，全部走既有令牌——验证：`npm run design:lint` + 真机/截图

## 6. 前端测试与 e2e

- [x] 6.1 更新 `Aui2Dock.test.tsx`：底栏三控件、过程泡泡实时/回放、正文无 tool 行、旧 trace 回放用例继续绿——验证：`npx vitest run src/__tests__/Aui2Dock.test.tsx` 31/31 绿
- [x] 6.2 更新 `e2e/chat-dock.spec.ts` ⑧：真实两步工具改为断言两张 `chat-proc-tool` 并点开详情；新增 mock SSE 的思考/工具泡泡用例（默认折叠→点开全文；正文无 `●`）——本机无 Docker 四服务栈未跑；用例已更新并通过 `tsc`，记录原因供 CI/nightly 覆盖

## 7. 回归门禁

- [x] 7.1 后端定向 + 全量：`cd client/backend && .venv/bin/python -m pytest tests/test_assistant_loop.py tests/test_assistant_chat_stream_http.py tests/test_assistant_session_store.py -q`，再 `python -m pytest tests/ -q`——实测定向 35/35；全量 3365 passed / 327 skipped / 0 failed（539s），排除 `tests/test_kb_baseline_fullchain.py`（其发布子进程在 60s timeout 挂起，属环境性存量，与本改动无关）
- [x] 7.2 前端：`cd client/frontend && npm run coverage`（100% 覆盖率契约）、`npx tsc --noEmit`、`npm run build`——实测 coverage exit 0（2288 passed / 1 skipped）、tsc 0、build 0
- [x] 7.3 设计门禁：`npm run design:lint`、`npm run design:check`（像素差 <0.2%）——记录各场景输出；实测 design:lint 仅预存 `docs/design-c/prototypes/preview.html:1` emoji 违规（非本改动；本改动文件零违规），design:check 因该基线红停在 lint；不触共享段，design-cross 不适用
- [x] 7.4 隔离栈真机烟测：临时 DATA_ROOT 副本 + 独立端口起后端（不碰主库/主栈），用真实模型发一轮带工具调用的对话，验证 SSE 有 thinking、assistant payload.process 落盘、重载 session 能回放——实测：真实 SSE thinking 4003 字（1381 增量）＋step_start/step_end(read_settings)＋run_end；assistant payload.process 落 [thinking, tool, thinking]；重载后 DOM 9 张过程卡（回放生成）；截图 `/tmp/ai-novel-smoke/21-live-dock-fixed.png`（底栏三控件同排＋思考/工具单行卡）、`24-expanded-fixed.png`（点开全文/结果）、`13-footbar-fixed.png`

## 8. 评审与合入

- [x] 8.1 合前跑 `review-agent` 审 diff，findings 修完再合（判例：feature PR 合前必过 review）——审出 1 项 P2（工具卡「模型调用」行漏模型名，spec 要求次数/操作名/模型三件），已修（`apiModels` 进同一行）＋测试断言；其余无 findings
- [x] 8.2 建 PR（说明根因/方案/门禁输出），CI 双绿后 squash 合 main，清理 worktree/分支；本地重建装机覆盖 `/Applications` 另行向 boss 确认。证据：PR #1108 squash=`6b81bb01`，CI 双绿；worktree/分支已清，装机仍待确认
