## Tasks

- [x] 1. 后端首字守卫机制：`chat_stream` 增 `first_content_timeout`（openai 分支：非正文 chunk 到达时核对首字前总时长，超限抛 `AIThinkingTimeoutError`；首字到达即撤守卫；零 chunk 静默仍由 read 超时兜底）
- [x] 2. 异常归一与留痕：`AIThinkingTimeoutError`（`AITimeoutError` 子类，归一出口原样放行）；判死经 `_log_call` 落 llm.log 失败行（error 类＝thinking timeout＋实测时长）
- [x] 3. 写作链挂守卫：`_stream_chapter` 传 90 秒（`FIRST_CONTENT_TIMEOUT`）；判死走可读 error 文案（实测秒数＋降思考强度指路）＋`write_chapter_fail` 记账；异常在 `is_done` 前抛出走不到落库——存稿原样
- [x] 4. anthropic 分支同构守卫：首个 `text_delta` 前核对总时长（时钟含建连与至多一次拒参重开）；守卫裁决在重试口先行原样上抛（防 `_is_thinking_rejection` 模糊匹配把判死误判成拒参剥参重开）
- [x] 5. 前端等首字秒表：gen-line 同行 `· Ns`（起表归零、阶段推进不重置、tabular-nums 弱化）；首字/收尾/停止随等待呈现停表退场
- [x] 6. 测试：openai/anthropic 守卫三态（判死＋不重开／首字撤销／缺省关闭）＋路由级保稿钉（判死无 done、已存稿逐字不变）＋前端秒表用例（归零／逐秒走／不重置／退场）；后端全量 2241 passed、前端 vitest 31/31、tsc 干净
- [x] 7. 评审整改：anthropic 分支同构＋防误判重开回归钉（opens==1）＋判死秒数改实测值
- [x] 8. 实现先行合入（PR #827＝7e865720，main CI 双绿）；本 change 为补档归档
