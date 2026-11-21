## 1. 原型先行与设计判定

- [x] 1.1 更新 `docs/design-c/drafts/ai-novel-c端-写作助手对话框-原型.html` 与同目录设计说明：补计划卡四态（未开始／在做／做完／没做成）、收口「还有 N 件没做」、重开恢复态；验证：原型可在浏览器打开，四态与设计说明逐条对得上。`ADJUSTMENTS.md` 无写作助手屏对应条目，不新增登记（依据 proposal 的 Design Impact）。证据：`/tmp/plan-card.png`（Playwright 1440×900，四态 DOM 校验 4/4）
- [x] 1.2 设计影响判定：计划卡只复用 `chat.css` 既有卡面骨架与语义类，未改 `base.css` 令牌、基础组件类或 `pill/notice/sk/panel/f-err` 家族；验证：diff 中无共享段文件、无裸 hex、无新胶囊形态，判定结论写入 change 目录。结论：diff 仅设计草稿两文件（未跟踪），实现侧复用既有 `.card/.card-head/.card-kind` 骨架与 §5 状态色，不触共享段

## 2. 动作协议硬化（后端）

- [x] 2.1 `actions.py` 增加协议片段识别（`"action"`／`"tool"`／`"args"` 键形态），`stream_slice` 从命中位置冻结；验证：`test_assistant_actions.py` 新增「无哨兵裸片段不流出」用例通过
- [x] 2.2 `parse_action` 无哨兵分支先切「叙述前缀＋片段尾巴」，尝试抢救解析，失败返回 `protocol_error`；验证：无哨兵裸片段、哨兵后坏 JSON、纯文本回答三形态用例通过，纯文本仍按 final
- [x] 2.3 `action` 槽填工具名的确定性修复（`tool_exists` 注入，`args` 归一）；验证：`{"action":"draft_arc","args":{"action":"draft"}}` 解析为 `draft_arc` 工具调用
- [x] 2.4 `loop.py` 重试判据与 final/degraded 解耦：`protocol_error` 触发一次重试，回喂清理文本；验证：`test_assistant_loop.py` 两连坏协议用例只交付清理叙述、坏原文不入 transcript
- [x] 2.5 清理后无叙述的失败话术与「坏文本零落盘」；验证：空叙述用例交付明确失败话术，会话文件无协议原文

## 3. 能力边界（后端）

- [x] 3.1 `tool_catalog_text` 每行追加 kind 标签（读／产卡／写），末尾追加固定边界块（清单外不存在、正文不在对话、产卡不写书、写入走面板/授权卡）；验证：快照测试字节稳定，按域收窄后仍含边界块
- [x] 3.2 边界块与注册表同源：新增 `update_plan` 后清单自动出现该工具，无需改提示词包；验证：缺包与包在位两种路径的 system 前缀都含新工具与边界块
- [x] 3.3 产卡文案去落库：`_draft_arc` 等产卡工具摘要改为「草稿已出，还没写进书里」口径；验证：grep 注册表摘要无「落库」表述，相关测试通过

## 4. 任务计划对象（后端）

- [x] 4.1 新增 `update_plan` 工具（items/mode/note，kind=read 会话状态工具，免授权，共享读集）；验证：`test_page_scopes.py` 启动校验通过，工具执行不弹授权、不写书
- [x] 4.2 计划状态与快照：merge/replace 语义、一个线程一个活跃计划、`role=event`＋`card_kind=plan` 追加落盘；验证：`test_assistant_session` 往返加载取最新快照
- [x] 4.3 SSE `plan` 事件与 `run_end.planIncomplete`；安全网（error 收口 active→failed，正常收口 active→pending）；验证：`test_assistant_loop.py` 事件序列与状态降级用例通过
- [x] 4.4 历史恢复：会话加载折叠 plan 快照，切页签/重启可取回未完成项；验证：接口返回 plan 行，前端恢复用例通过

## 5. 前端 dock 与卡面

- [x] 5.1 `Aui2Dock` 消费 `plan` 事件并注册 `plan` 卡（按 `planId` upsert，位于当前回合轨迹组上方）；验证：`Aui2Dock.test.tsx` 事件驱动四态更新用例通过
- [x] 5.2 历史 `card_kind="plan"` 行折叠恢复，空 content 旧事件行照旧跳过；验证：恢复用例 + 旧行兼容用例通过
- [x] 5.3 收口未完成呈现「还有 N 件没做」，没做成项按阻断缺项语气；验证：三件完成两件用例文案与状态正确
- [x] 5.4 `CardBody` 回显 `constraints_used`（标签「写法约束」）；验证：`CardBody` 测试出现该行，未知键兜底不变
- [x] 5.5 `chat.css` 计划卡样式：只用既有令牌与卡面骨架，无新胶囊/语气词/裸 hex；验证：`npm run design:lint` 严格范围零新增违规（仅存量 `prototypes/preview.html` emoji 红，主检出同红，非本 change 引入）

## 6. draft_arc 入参分层

- [x] 6.1 `draft_arc` 工具入参分层（`material`／`constraints`，`input` 兼容别名）；验证：schema 测试与旧调用兼容用例通过
- [x] 6.2 `caps.settings.arc_ai_action`／`run_arc_ai` 接受 `constraints`，格式化 `{input}` 前拼分隔块；验证：约束不混入素材的单元测试通过，提示词包零改动
- [x] 6.3 `draft_arc` 卡 payload 增加 `constraints_used`，采纳无关字段零影响；验证：卡面用例与既有采纳用例通过

## 7. 回归

- [x] 7.1 后端：`pytest client/backend/tests/test_assistant_actions.py test_assistant_loop.py test_page_scopes.py test_assistant_session*.py` 全绿，`ruff check` 通过；把实际输出结论写进本任务。实测：目标文件 91 passed（含 review 补钉）；全量 `pytest tests/ -q --timeout=30 -m "not perf"` = 3390 passed / 1 failed（`test_kb_baseline_fullchain` 子进程发布内容仓 30s 超时，与本 change 无关）/ 327 skipped；`ruff check --extend-select F811,F821,F841 .` all passed
- [x] 7.2 前端：`npx tsc --noEmit`、`npm run test -- Aui2Dock CardBody`、`npm run design:lint` 通过；`npm run design:check` 按 Design Impact 判定为不受影响并记录实际执行结论。实测：tsc 0 错；全量 vitest 2286 passed/1 skipped；design:lint 严格范围零新增违规（仅存量 preview.html emoji 红，主检出同红）；design:check 7/8 通过，preview 阅读器 4.5% 为存量基线漂移（本 change 未触 preview 文件）
- [ ] 7.3 e2e：`chat-dock.spec.ts`、`ai-assist.spec.ts` 更新后通过（含计划卡与坏协议不裸泄锚点）；记录实际输出
- [ ] 7.4 真机走查：一条消息提三件交付物（主线/主角/卷一开头）看到 3 项计划与未完成说明；注入坏协议不裸泄；重启恢复计划；记录截图与结论
- [x] 7.5 `openspec validate c-agent-action-contract --strict` 通过，任务勾选与设计判定归档说明齐全
