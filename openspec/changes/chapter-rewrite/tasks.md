# Tasks

> 停审批口：待用户确认 proposal「待拍板」三条后开工，tasks 逐项勾销。

## 1. 后端

- [ ] 1.1 快照端点：`POST /api/novels/{id}/chapters/{ref}/rewrite-snapshot`——把当前正文快照为 `{ref}-r{n}` 支线章（title/正文/ghost_of；不给章纲派生数据），无正文章 409——验证：pytest 行/幂等/无正文拦截/多次重写 r1/r2
- [ ] 1.2 下游 stale 派生查询：`chapters/stale.py`——stale(X) = ∃ 更早主线章支线快照 created_at > X.updated_at；批量接口并入树/章详情——验证：pytest 前中后三态（重写前 false / 重写后 true / 本段改写后 false）
- [ ] 1.3 导出/导入：后缀 ref 支线章随包往返与 ref 重绑——验证：backup roundtrip 断言（旧稿正文与 ghost_of 关系保留）

## 2. 前端

- [ ] 2.1 操作页签「重写这一章」卡（仅 has_prose 且非支线渲染）＋影响面确认弹窗（三行说明，wbStyle）——验证：vitest 渲染与确认回调
- [ ] 2.2 确认流：调快照端点 → 归档章先走解锁链 → 落正文页签聚焦编辑；归档完成 toast 口径「已重写归档 · 后续章节标记『基于旧设定』」——验证：e2e 全链（重写→改写→归档→角标出现）
- [ ] 2.3 角标呈现：章节树行 `.tag-stale`／设定投影「基于旧设定」／右栏「操作」统计「下游挂着旧设定 N 章」接线——验证：vitest 三呈现面＋e2e 角标可见/消失
- [ ] 2.4 原型与登记：ADJUSTMENTS 增补 ⑨（重写流；`.tag-stale` 虚线中性款——§5 常态徽标禁警示色口径）——验证：登记条目落地

## 3. 回归与归档

- [ ] 3.1 全量 pytest／vitest／e2e／design:lint 绿——验证：本机 docker 栈执行
- [ ] 3.2 `openspec validate chapter-rewrite --strict` → archive（workbench/chapter-data 增量 sync）——验证：归档输出
