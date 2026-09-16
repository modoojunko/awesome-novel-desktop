## 1. 后端——schema 与迁移

- [ ] 1.1 `models/character.py`：character_relations +origin_chapter_id（FK SET NULL）；`models/chapter.py`：ChapterCharacter +state_change（Text default ""）；新 `models/reconcile.py`：ChapterReconcile（novel_id/chapter_id FK CASCADE、kind、status、payload JSON、时间戳）——pytest：建行/枚举/级联删除
- [ ] 1.2 迁移：main.py 幂等 ALTER 三处＋schema 指纹更新；存量 ch_ref→origin_chapter_id 一次性解析回填（幂等，不可解析留空）——pytest：旧库升级/重复启动幂等/回填正确性
- [ ] 1.3 导出/导入接线：chapters 段出场引用含 state_change；relations 段含 origin_chapter（ref 形式）＋导入 ref→id 重绑（缺失留空＋告警）；chapter_reconcile 登记界外不随包——pytest：roundtrip 断言 + **删库救回演练**（迁移 PR 验收硬门禁）

## 2. 后端——归档拆分与收尾服务

- [ ] 2.1 `archive/service.py`：同步段维持（archives/mentioned/threads/状态迁移）；AI 收尾三类＋lore＋角色状态提取迁后台单飞线程（照抄 backup/export._job 模式）；归档响应改返收尾任务标识——pytest：归档即刻生效不阻塞/收尾行落库/失败降级
- [ ] 2.2 收尾服务：三类 AI prompt 模板（提取设定变化/关系建议/伏笔登记含证据句）＋lore 建议＋角色状态提取；同章同键未决覆盖、已决保留；采纳写回走对象自身服务（relations/hooks/lore-apply/出场引用行）、失败置 failed 保留 payload——pytest：采纳写回/去重/失败回滚/同键覆盖/已决留痕
- [ ] 2.3 端点：`GET /reconcile?chapter_id=`（行列表＋聚合进度）、`POST /reconcile/{id}/accept`、`POST /reconcile/{id}/reject`、`POST /reconcile/{id}/retry`；门控（免费档 403/无行）；退役 legacy `update_character_states` YAML 追加（legacy 键保留）——pytest：门控/端点语义/legacy 退役后旧数据可读
- [ ] 2.4 提示词与体检不回归：未确认提案不注入（build_chapter_context 与体检只读对象表）——pytest：有 pending 提案时写章提示词不含提案内容
- [ ] 2.5 后端全量回归：容器内 pytest 全绿（存量受影响：test_archive/test_chapters/test_write_pipeline/test_backup_roundtrip）

## 3. 前端——两页签与收尾 UI

- [ ] 3.1 `ChapterWorkspace`：页签 3→5（＋设定/操作）；「设定」页签两子视图（本章变化可编辑/截至本章只读投影带来源章标注）——vitest：页签渲染/切换/本章变化保存
- [ ] 3.2 「操作」页签：归档入口（沿用确认流）＋收尾进度区（聚合轮询/展开明细/采纳/驳回/重试）；免费档占位「PRO 可用」——vitest：进度聚合/确认交互/免费占位
- [ ] 3.3 `ChapterStore`/事件：收尾状态轮询挂 store、`reconcile:advanced` 事件刷新；投影视图数据来自既有 volumes/hooks/relations 接口的来源章字段——vitest：轮询触发/事件刷新
- [ ] 3.4 原型先行补登记：storyline.html 中栏设定/操作页签与收尾卡为设计事实源，`ADJUSTMENTS.md` 补实现偏差登记（若有）；文案过 §13（动词按钮词/无内部术语/补救带出口）
- [ ] 3.5 e2e：归档→收尾进度→逐条采纳/驳回→未确认不进下一章提示词→免费档无收尾区；「截至本章」投影场景——全绿

## 4. 回归与门禁

- [ ] 4.1 `npx tsc`／`npm run design:lint`／`npx vitest run` 全绿；design:check（parity）不受影响（新页签属 storyline 范围，book.html 不动）
- [ ] 4.2 后端容器内 pytest 全绿＋ruff；ruff 侧效检查（副作用 import 禁令）
- [ ] 4.3 导出/导入演练：含 state_change/origin_chapter 的包跨机恢复＋删库救回演练通过
