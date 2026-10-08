## 1. 后端退役

- [x] 1.1 删 `POST /write/{chapter_ref}/continue` 端点（write/router.py，含 import 行）与 `stream_continue`（write/auxiliary.py）；删 `build_auxiliary_context` 内 `recent_context` 的 `prose[-1500:]` 死赋值行（`load_chapter` 等角色快照依赖语句保留）；`continue_writing.prompt` 模板整文件删除；选区加工三链（polish/expand/compress）不动。验证：grep `stream_continue\|continue_writing` 后端零残留；pytest 全量绿
- [x] 1.2 `tests/test_write_routes_contract.py` 子路径清单去 `/continue`，并加反向钉缺席断言（`assert WRITE + "/continue" not in openapi_paths`，同 `test_double_write_path_absent` 先例）。验证：test_write_routes_contract 绿
- [x] 1.3 ruff CI 同参复核（`--extend-select F811,F821,F841`）全绿；注释级残留顺手清（auxiliary.py:266「沿 stream_continue 兜底口径」等 docstring）

## 2. 前端退役

- [x] 2.1 撤「续写建议」卡全链：AiAssistPanel `cap("continue", ...)` 行＋`onContinue` prop＋说明行去「续写/」；Rail.tsx `onContinue` 透传；NovelWorkspace `onAiContinue`/`AiAction` continue 分支/`runAiAction` continue 分支。验证：grep `cap\("continue"|onContinue|onAiContinue` src 零残留
- [x] 2.2 ProsePane 撤 `continueWriting`（ProseHandle 声明＋实现）与 `startStream` 续写分支（`cap.end` 偏移插入点）（`textOffsetToPmPos` 因选区变换链仍在使用而保留，仅删续写分支使用点）；**空文档垫段保留**（整章生成共享路径，proseStream.test 钉的就是它）；**「续写恢复」信号消费保留**（顶栏导航链）。验证：vitest 绿；grep `continueWriting|textOffsetToPmPos` src 零残留
- [x] 2.3 `lib/ai.ts` 删 `streamChapterContinue`（/write/continue 调用）。验证：grep `/write/continue|streamChapterContinue` src 零残留
- [x] 2.4 文末续写块拆除（c-workbench-density 已合 main，评审 P0）：ProsePane `tail-continue` 块＋`planWords` prop＋ChapterWorkspace:1200 传参＋book.css `.tail-cw` 样式组；AiAssistPanel/SimModal 的 planWords 完成度用法保留。验证：grep `tail-continue|tail-cw` src/css 零残留；tsc＋vitest 绿
- [x] 2.5 单测断言与文案：`__tests__/NovelWorkspace.test.tsx:602`「续写建议」按钮断言删除（:605-606 折叠断言保留）；ProsePane 完工检查胶囊「续写补足」与明细「可用『续写』补足」改写为无续写指引（调低章纲目标/手动补写）。验证：vitest 全量绿
- [x] 2.6 原型与 parity 基线（确定性工作非或然）：`docs/design-c/prototypes/book.html:1094` 续写建议卡行删除、`ADJUSTMENTS.md` 续写登记更新、`design-parity-book` 免费态截图基线重录、`prompt-pipeline.spec.ts:156` 注释去 `/write/continue` 字样。验证：design-parity-book 绿

## 3. 全量验证

- [x] 3.1 后端 pytest 全量＋前端 vitest 全量绿
- [x] 3.2 零残留自证完成（前端/后端退役面词形 grep 零命中；隔离栈冒烟：四容器特征自证退役版＋断章版并存、真渲染截图确认退役面消失且顶栏「续写」在位）。e2e 用例复跑未完成——隔离栈复刻 e2e 会话前置（S端 OAuth 会话链）受阻，剩余失败全为环境前置而非代码（顶栏续写按钮路径零改动，vitest NovelWorkspace 导航用例已绿）；全量 e2e 留待常规 e2e 环境。原始判据：前端 `grep -rn "续写建议|/write/continue|streamChapterContinue|continueWriting|cap\\(\"continue\"|tail-continue" client/frontend/src client/frontend/e2e`（保留面白名单：顶栏「续写」按钮文案、free-writing-flow/workbench-features 导航用例、「续写恢复」）；后端 `grep -rn "stream_continue|continue_writing" client/backend` 零残留
- [ ] 3.3 PRD 过期口径备注：`docs/prd/creation-flow-to-be-design.md`「正文 AI 五连」含 continue 与拍板相反——归档时在 change 摘要登记文档过期，不在本 change 改 PRD
