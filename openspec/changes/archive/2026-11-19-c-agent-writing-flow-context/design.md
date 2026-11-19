# c-agent-writing-flow-context 设计

## Context

事故链（2026-11-19 boss 报障）：作家对已写 4,199 字正文但未归档的第 7 章说「规划下一章」，助手围着第 7 章出方向。实锤：

- 系统提示词零写作流程知识（grep 下一章/生命周期零命中）。
- L1 brief（`assistant/context.py:49-58`）进度行「当前写到 第 7 章（草稿）」——frontier state 三值（`chapters/frontier.py:119-126`：draft=有正文未归档/planned=无正文未归档/pending=占位）被 `_STATE_ZH` 压成单一「草稿」，「已写完」与「没写」不可区分。
- 判断「写到哪里」的接口已存在且全页签可见：`read_progress`（`assistant/tools.py:266-288`，`_SHARED_TOOLS`），但 description 未点明用途，模型不知道何时该调。
- boss 拍板（2026-11-19）：不做死流程——不铸硬闸、不搞窄正则 prime；背景知识＋真值给足，行为决策留给模型。

## 技术决策

1. **背景段落点＝`scopes.py` 域纪律机制**：`discipline_of_thread`（scopes.py:209-222）尾拼（prompts.py:101-102），提示词包在位与否都生效（pack 路径会整层替换 identity，纪律段不受影响）；静态字符串＝字节稳定＝前缀缓存友好（判例 write/router.py:191-193）。全域追加（书级 thread 都注入），不是行为脚本——措辞是概念＋能力指针＋判断启发。
2. **brief 真值＝复用 frontier_info**：chapters dict 补 `word_count`（Chapter 行现成字段，pending 占位补 0），`build_book_brief` 按 state 三态改写进度行。守 ≤300 字预算（BOOK_BRIEF_BUDGET_CHARS）。不动 frontier 语义本身（归档驱动是主线单源，不因「有正文」跳章）。
3. **read_progress 只做小改**：description 点用途；摘要尾部补「下一章＝第 N+1 章（待拆纲／未归档收尾后可拆）」；state 中文映射「草稿」→「正文已写·未归档」（照 :280 人话判例「内部词禁出模型口」）。
4. **前端 hint 一次性**：`pendingHintRef` 在 onSubmit 读走后置 null——assistant-chat-ui spec:46 既有条款「tool_hint 随下一次发送携带」的本义即一次性，现状不清空是实现偏离 spec；且强制重放旧工具首步直接破坏模型自主选工具。
5. **不加闸不加 prime**（boss 拍板）：`draft_chapter_split` 保持 max+1；模型有背景＋真值后自主决定调不调、怎么答。产物本就「不落库过目采纳」，误判成本低。

## 风险与既知

- 自主判断是概率行为：走查按 3 次取稳；brief 真值随行使「不调工具也能答对」成为兜底。
- golden/提示词测试无 brief 字节钉（已 grep 确认）；`test_read_progress_summary_is_human` 与 `test_discipline_per_thread` 需随新口径更新。
- discipline_of_thread 追加全局段会影响所有书级 thread 的提示词尾拼——注意 test_page_scopes 的断言口径（在/不在，非全等）。
