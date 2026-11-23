# 任务：助手对话框编排生成正文（c-agent-dialog-prose）

## 批A 后端·助手工具

- [x] 1.1 `write/chapter_writer.py`（或 write 域新模块）抽 `assemble_write_prompt(project, chapter_ref, fresh=True)` 公共函数；`GET /write/prompt` 端点改同调（行为不变）
- [x] 1.2 `assistant/tools_kb.py` 增 `kb_search_craft`（read）：域解析（book_scope/genre 同 prepare_write_block）＋digest_candidates＋bigram 打分＋上限 30＋零命中文案
- [x] 1.3 `assistant/tools.py` 增 `read_write_prompt`（read，调 assemble_write_prompt）；增 `draft_prose_plan`（card）：章校验/picks 三域解析/prompt 上限 16000/已有正文探测/prose_plan 卡 payload
- [x] 1.4 `assistant/scopes.py`：三工具登记（kb_search_craft/read_write_prompt 入共享读；draft_prose_plan 入 ch:prose 域）；正文域纪律改写
- [x] 1.5 `assistant/tools.py` 边界块改写（删「正文生成不在对话里」）
- [x] 1.6 `assistant/router.py` 增 `GET /assistant/capabilities`（ASSISTANT_PROSE_FLOW）

## 批B 后端·write 链

- [x] 2.1 `write/write_block.py` 增 `build_block_from_picks(db, novel_id, chapter_ref, user_id, picks, prompt_sha)`：三域解析/保序/run selector="agent"/同 hash 复用/零有效无块
- [x] 2.2 `write/router.py` `_stream_chapter`/`write_chapter` 收 `kb_picks`（含键走 agent 模式；不含键零改动）
- [x] 2.3 body 解析扩 `kb_picks`（[{entry_id, reason?}]，非法形状按缺省处理）

## 批C 前端

- [x] 3.1 `lib/chatApi.ts` 增 getAssistantCapabilities；`lib/chatRegistry.ts` prose chips 按 dialog_prose 动态形态（command「生成本章正文」/off 直开）
- [x] 3.2 `lib/ai.ts` streamChapterWrite 增 kbPicks → body.kb_picks（键存在即发）
- [x] 3.3 `workbench/ProsePane.tsx` startWriting(promptOverride?, modelSelection?, extras?: {kbPicks?})
- [x] 3.4 `chat/CardBody.tsx`＋`chat/Aui2Dock.tsx` prose_plan 卡渲染（条目清单/提示词折叠全文/警示/开始生成→宿主回调/adopted 翻转）
- [x] 3.5 `NovelWorkspace.tsx` onProsePlanStart 宿主桥（归档拦截/RegenConfirm/startWriting）；AiModal 挂载与入口移除（组件保留）
- [x] 3.6 chips 镜像钉（test 对齐 chatRegistry）

## 批D 测试

- [x] 4.1 后端：kb_search_craft（域/题材/打分/上限/零命中）、read_write_prompt（同源）、draft_prose_plan（校验/上限/payload）
- [x] 4.2 后端：write 端点 kb_picks 路径（组装/零命中无块/selector=agent/重试复用/不含键旧路）
- [x] 4.3 后端：上下文隔离钉（fake client 抓实参断言无会话片段）
- [x] 4.4 前端 vitest：chips 形态/prose_plan 卡/开始生成桥/startWriting body 契约
- [x] 4.5 本地验证：ruff＋pytest（全量 3854，2 失败为主检出现存环境问题对拍同红＋2 隔离复跑绿）＋vitest（2340 全绿）＋tsc＋openspec validate
- [ ] 4.6 真机走查（独立栈）：chip→取材过程卡→方案卡过目提示词→开始生成→正文区流式；零命中书回退文风设定；重试字节一致；env off 直开回退
