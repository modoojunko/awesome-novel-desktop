## 1. 正文预算与守卫余量

- [x] 1.1 `write/router.py` 落 `PROSE_FIRST_CONTENT_TIMEOUT=600.0`／`PROSE_MAX_TOKENS=32768` 常量并接入 write_chapter 流式调用；用测试钉常量值（防误回 90/8192）
- [x] 1.2 全链路验证：M3 形态（anthropic＋thinking）长思考不再 90 秒判死（存量守卫钉全绿＋新增钉）

## 2. anthropic 路径内联思考剥离（同构）

- [x] 2.1 `ai_client.py` anthropic 流式分支接入 `_InlineThinkStripper`（text_delta feed、守卫撤点＝放行正文、finish 收尾）；用测试钉「内联 `<think>` text_delta 零泄漏＋不缴械守卫」
- [x] 2.2 anthropic 非流式 text 块出口 `strip_inline_think`；用测试钉前缀剥净／普通逐字不动

## 3. 回归与验证

- [x] 3.1 全量 pytest＋ruff＋`openspec validate` 通过
- [ ] 3.2 demo 栈换包实测：MiniMax M3 生成正文有产出、无 `<think>`、无 90 秒误杀
