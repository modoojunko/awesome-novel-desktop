## 1. 剥离核心

- [x] 1.1 实现跨 chunk 内联思考剥离状态机（HOLDING/STRIPPING/PASSING 三态＋`</think>` 尾部滑窗＋未闭合兜底＋异常按原始交付），非流式一次喂入、流式逐 chunk 喂入共用同一核心；用单元测试驱动（前缀判定/裂边界矩阵/中段字面不剥/未闭合/异常兜底）
- [x] 1.2 接入非流式 `chat()` openai 出口：交付前剥离；用测试钉「思考前缀剥净、普通响应逐字不动」

## 2. 流式接入与守卫对齐

- [x] 2.1 接入 `chat_stream()` openai 分支：以状态机放行正文事件，STRIPPING/HOLDING 零产出；用测试钉「思考段零事件、正文逐字完整、跨 chunk 裂标签不泄漏」
- [x] 2.2 首字守卫撤点从「首个 delta.content」改为「状态机放行首个正文事件」；用测试钉「内联思考期守卫不撤销、超限判死不重开流、正文到达即撤」

## 3. 回归与验证

- [x] 3.1 存量 ai-client 相关测试全绿（pytest client/backend，重点 test_ai_client_layering/test_chat_stream_usage/test_prose_pipeline），ruff 干净
- [x] 3.2 `openspec validate c-inline-think-strip` 通过；逐 scenario 对拍测试覆盖清单（ADDED 5 条＋MODIFIED 守卫 4 条）
