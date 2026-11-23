# 设计：助手对话框编排生成正文（c-agent-dialog-prose）

## 架构

三段式，跨三条既有通道拼装，不新造协议：

```
[对话框 SSE] agent 取材（read_* + kb_search_craft，工具步卡可见）
      │ agent 调 read_write_prompt（服务端组装稿=提示词基底）
      │ agent 调 draft_prose_plan → artifact 事件 → prose_plan 卡
      ▼
[宿主桥] 卡按钮 → onProsePlanStart → RegenConfirm(如有正文) → proseRef.startWriting(prompt, kbPicks)
      ▼
[write SSE] POST /write {prompt(覆盖), kb_picks} → _stream_chapter：
      prompt 覆盖生效 → _build_block_from_picks 组装写法块（agent 模式）→ 收尾行 → 流式正文
```

## 关键决策

- **D1 上下文隔离**：write 调用素材=卡上提示词（既有 prompt 覆盖语义，AiModal 同款）＋写法块＋收尾行。不读 assistant 会话；跨边界仅 `prompt`/`kb_picks` 两字段。测试以 fake client 抓实参钉死。
- **D2 提示词基底单源**：`read_write_prompt` 与 `GET /write/prompt` 抽公共函数 `assemble_write_prompt(project, chapter_ref, fresh=True)`（chapter_writer 域），两边同调；工具返回 fresh 组装稿＋warnings（不读 write-prompt 存稿——对话流提示词恒以当前素材为准）。
- **D3 候选域单源**：`kb_search_craft` 候选域=写法块同源 `digest_candidates`（书副本/merged 基线），保证 agent 挑的 id 可注入；域解析（book_scope 判定/genre 来源）复用 prepare_write_block 同款逻辑。
- **D4 确定性打分**：中文无空格分词不可用决策档案的 split()；改用 CJK 二字串（bigram）＋ASCII 词重合计分：score=命中 bigram 占查询 bigram 比例×有用率×新鲜度；平序 (−score, title, id) 与 select_block 惯例一致。纯函数好钉测试。
- **D5 agent 模式判定**：以「body 是否含 kb_picks 键」为闸（空数组也算），不猜意图；不含键路径零改动（熔断直开/旧客户端兼容）。
- **D6 run 语义**：agent 模式 brief_hash=novel+ref+prompt_sha+picks；同 hash 复用（重试字节一致）；selector="agent"；IntegrityError 并发回读同款 F1 处理。refill 不改（复用当章最新 run，agent run 的 text_snapshot 同样可用）。
- **D7 卡即确认**：不接授权档位——结论卡按钮就是确认点（boss 拍板手动点）；已有正文警示＋宿主 RegenConfirmModal 二次确认。
- **D8 熔断面**：env 只切前端 chip 形态（capabilities 端点），后端两条路径常驻（agent 模式由请求体驱动，env off 不影响 API 兼容）。

## 不做（挂账）

- AiModal 组件/`/write/prompt` 端点/write-prompt 存稿清理（本版保留不挂载）。
- 卡内 inline 编辑提示词（作家改提示词走对话让 agent 重出卡）。
- WriteBlockPanel 渲染面重建（write_block SSE 数据链保留）。
- 「有用/没用」反馈面板重建。

## 风险

- agent 拼接提示词质量依赖 read_write_prompt 纪律（description 钉「基底不凭空拼」）＋卡上全文可见可纠。
- kb_picks 跨卡到生成的时差内条目被删：生成时三域解析失败即剔除（零有效→无块），不炸链。
