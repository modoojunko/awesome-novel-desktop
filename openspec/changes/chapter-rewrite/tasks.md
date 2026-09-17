# Tasks

> 停审批口：待用户确认 proposal「待拍板」三条后开工，tasks 逐项勾销。

## 0. 评审前置修复（P0，首做）

- [ ] 0.1 `chapters/frontier.py::frontier_info` 补 `ghost_of IS NULL` 过滤（重写旧稿抢 frontier 致端点章 409 的根因；已复核实码）——验证：pytest 造 ghost 后 frontier 仍指真端点
- [ ] 0.2 ref 解析单源：新增 `client/frontend/src/lib/chapterRef.ts`（parseChapterRef/isGhostRef）替换 `useWorkbench.parseRef` 与 6 处 `-ch-(\d+)$` 取号 + `focusNode` 接受 `-r\d+`——验证：vitest 解析表＋e2e 点旧稿可打开
- [ ] 0.3 正文写路径显式刷新 `updated_at`（含等字数改写/纯空白保存）——验证：pytest「等字数改写后 updated_at 前进」
- [ ] 0.4 补建 `tests/test_rewrite.py`（包 frontier 过滤/三态 stale/r1r2/409/ghost 源/双击幂等/roundtrip；顺带覆盖 revert 关键路径——勘误：原归档任务书引用的 test_revert_ghost.py 从未存在）

## 1. 后端

- [ ] 1.1 合成端点 `POST /api/novels/{id}/chapters/{ref}/rewrite`（一事务：快照＋归档章解锁；拒绝 ghost 源/无正文 409；双击幂等吸收）——验证：pytest 全分支
- [ ] 1.2 `chapters/stale.py` 派生查询（stale(X) = ∃ 更早主线 Y：Y.updated_at > X.updated_at 且 Y 有重写快照）——验证：pytest 前中后三态（未改写→不标；改写落地→标；本段改写→消）
- [ ] 1.3 契约字段：`/volumes` 章 `stale`；章详情 `stale`+`stale_downstream`；`/ghosts` 加 `origin`——验证：pytest 契约断言
- [ ] 1.4 导出/导入：`-r{n}` 支线章往返＋ref 重绑；修复 `prompts/{ref}-`/archives 子串误吞——验证：roundtrip 断言

## 2. 前端

- [ ] 2.1 `useChapterData.flush()`（复用 in-flight 保存）＋操作页签「重写这一章」卡（仅 has_prose 且非支线）＋影响面确认弹窗（三行，wbStyle；快照期间禁用防连点）——验证：vitest 渲染/确认回调/flush 先于快照
- [ ] 2.2 确认流：flush → 合成端点（快照＋解锁同事务）→ 落正文页签聚焦；归档 toast「已重写归档 · 后续章节标记『基于旧设定』」；成功后刷新树/ghosts——验证：e2e 全链（重写→改写→归档→角标出现）
- [ ] 2.3 角标呈现：树行 `.tag-stale`（ghost 行加 `r{n}` 徽标防同号混淆）／设定投影／右栏统计（props 链路，不加请求）；正文保存成功本地清角标——验证：vitest 三呈现面＋e2e 可见/消失
- [ ] 2.4 原型与登记：ADJUSTMENTS 增补 ⑨（重写流；`.tag-stale` 虚线中性款；避让 cfg 摘要 `.tag`）——验证：登记条目落地
- [ ] 2.5 e2e 波及核验：modals-pr5 dialog 计数、free-writing-flow `.ghost-row`/`.ghost-group` 类名保留、AiAssistPanel 提示词页签请求数不变——验证：全量 e2e 绿

## 3. 回归与归档

- [ ] 3.1 全量 pytest／vitest／e2e／design:lint 绿——验证：本机 docker 栈执行
- [ ] 3.2 `openspec validate chapter-rewrite --strict` → archive（workbench/chapter-data 增量 sync）——验证：归档输出
