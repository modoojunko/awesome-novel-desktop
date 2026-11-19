# c-agent-writing-flow-context 任务

## 1. 后端：写作流程背景段

- [x] 1.1 `client/backend/assistant/scopes.py`：新增静态 `WORKFLOW_BACKGROUND` 常量（生命周期/归档语义/read_progress 用途指针/判断启发，字节稳定），`discipline_of_thread` 为书级 thread 尾拼
- [x] 1.2 `tests/test_page_scopes.py`：补背景段断言（全域可及、语义钉、字节稳定）＋默认域断言随新口径更新

## 2. 后端：brief 三态真值

- [x] 2.1 `client/backend/chapters/frontier.py`：chapters dict 补 `word_count`，pending 占位补 `"word_count": 0`
- [x] 2.2 `client/backend/assistant/context.py`：`build_book_brief` 进度行三态改写（draft 含字数「未归档」/planned「已排定·正文未写·未归档」/pending「各章均已归档；下一章 第 N 章（待拆纲）」），守 300 字预算
- [x] 2.3 `build_book_brief` 三态测试（`tests/test_assistant_router_helpers.py` 新增 draft/planned/pending 三用例）

## 3. 后端：read_progress 小改

- [x] 3.1 `client/backend/assistant/tools.py`：description 点明「写作落点拿不准先查进度」用途；摘要尾部补「再往后是 第 N+1 章」；pending 态直接给「下一章是 第 N 章」；「草稿」改「正文已写 N 字·未归档」口径
- [x] 3.2 更新 `test_read_progress_summary_is_human` 并补 planned/pending 态用例

## 4. 前端：hint 一次性

- [x] 4.1 `client/frontend/src/components/novel/chat/Aui2Dock.tsx`：onSubmit 读走 `pendingHintRef.current` 后置 null
- [x] 4.2 `src/__tests__/Aui2Dock.test.tsx`：补「chip 触发后紧随消息携带 tool_hint、再下一条（autoAsk 同链路自由文本）不携带」用例

## 5. 验证与收口

- [x] 5.1 后端全量 `pytest tests/ -q --timeout=30 -m "not perf"`＝3337 passed/0 failed＋`ruff check` 过
- [x] 5.2 前端 `vitest --coverage` 过阈值（Aui2Dock 12/12 含新用例）
- [x] 5.3 走查（隔离栈：worktree 后端 8110＋vite 5193，种子书「血哨站走查」＝6 归档＋第 7 章 240 字正文未归档，真模型 glm-5.3-flash）：
  - 端点级 3 遍「规划下一章」：4 步内自主调 read_progress→凭真值两路摆给作家（收第 7 章/开第 8 章），1 遍因 ASSISTANT_STEP_MAX_TOKENS=2048 截断但方向仍对（走查栈调 8192 后干净收口）
  - 真 UI「规划下一章」：轨迹卡 1 步 read_progress，回复先对齐真值再两路拍板 ✓
  - 真 UI 对照「给本章出三版剧情清单」：锚死第 7 章零漂移（draft_chapter_plot→章纲缺项→手动出概要/挑战/落点候选）✓
  - 真 UI chip「拆下一章」：tool_hint 首步确定性执行 draft_chapter_split ✓（隔离环境缺提示词包致工具降级，模型诚实坦白并照正文手拆三方向；真机有包不发生）
  - 真 UI hint 一次性：chip 后自由文本仅 1 步 remember_decision，旧 hint 未重放 ✓
  - 存量观察（非本次引入，挂账）：glm 文本协议路径偶发 `===ACT===` 协议行漏进叙述（主检出同在）
- [x] 5.4 `openspec validate` 过；归档移档随 boss 验收
