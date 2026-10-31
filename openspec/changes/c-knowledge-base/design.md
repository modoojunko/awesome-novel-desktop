# 设计 · 写作知识库（c-knowledge-base）

## Context

完整设计已在仓内三份文档定稿并评审（本文只记关键决策与实现指向，不复述）：

- 分层/消费/分期：`docs/design-c/drafts/ai-novel-c端-写作知识库-整体方案.md`（§2 分层、§3 消费、§5 表模型、§7.1 组装流水线、§8 来源与初始化、§11 P0-A..E）
- 存储与检索选型：`docs/design-c/drafts/ai-novel-c端-写作知识库-选型.md`（SQLite 单表＋JSON 载荷＋标签物化＋FTS5）
- 每类知识字段表与本体约束：`docs/design-c/drafts/ai-novel-c端-写作知识库-数据结构.md`（§0 信封、§0b 场景条目、§1–6 六概念、§8 闸门、§10 关系元数据、§12 容量）
- 原型（OpenDesign v29，自检 60 项全绿）：交互与视觉基线；界面主题已逐字对齐 `client/frontend/src/design/base.css`。

## Goals / Non-Goals

**Goals（P0）**：知识模型与闸门落地；手录＋拆书导入＋蒸馏沉淀＋种子四来源；默认库自动生成；知识库首页/库页/抽屉/2D 全局图；批1：模型/注册表/闸门/默认库/手录/首页/库页/条目抽屉/全局图。批2–7 见拆分策略。

**Non-Goals**：3D 星图三视图（Lab，P1+）、情节消费、手动/条件圈库、向量检索、自定义题材、库版本回滚、知识导出（P1）。

## Decisions

1. **单表＋按概念载荷＋标签物化**（选型已拍板）：`kb_entries` 一张实体表，`payload_json` 按概念 Pydantic 强校验；`kb_entry_tags` 物化 concept/genre/scope/scene/emotion/chapter_pos/slot——**选择器只查标签不查 JSON**（SQLite 不能索引 JSON 路径），标签可随时重建。
2. **概念是注册表不是表**：情节概念进注册表供展示，但 payloads/手录/推断对情节 SHALL 拒收创建（消费链未建），只展示占位文案"即将上线"。原决策改为：`kb/concepts.py` 注册 {schema, relations, quality_rules, renderer, contract}；加类型零迁移；无消费链的类型不进注册表。
3. **场景条目由字段值决定**：`when_json` 空/非空 → base/scene（读时推导，不落库）；文风场景条目槽位闸（role/pov 禁改）在入库校验执行。
4. **默认库自动长成**：题材×概念与通用×概念两组格子，首条目入库触发 `rule_json={"kind":"auto_all"}`；无预建、无派生流程。
5. **选择器确定性优先**：信号只读作家章纲（角色直取；场面/情绪走 `kb/concepts.py` 注册的封闭词表＋别名归类，不调模型）；两段式（标签短名单 ≤200 → 内存打分，prefs 只查短名单）；同槽 rule/craft/tic 场景覆盖基线；同章同素材哈希复用 run。
6. **注入位**：user 层、输出契约收尾行之前；块模板与防注入剥离规则见整体方案 §7.1；system 逐章字节一致红线不变（prose-writing 既有 spec）。
7. **备份版本**：`FORMAT_VERSION` 8→**9**（当前值已是 8）（8 已被角色库在途占用）；账号级八表进配置包新段 `knowledge_base`；书内三表（bindings/match_runs/match_items）进 `dump_book_into` 随书级联。
8. **全局图（→ ⑦，PM 评审拍板）**：组件与交互设计不变（npm force-graph、聚合＋下钻＋面包屑、六色 oklch token、同屏 ≤500），但**推迟到 ⑦ AI 整理上线时同批发**——① 没有关系数据（边），图是纯层级树没有"发现关联"的价值；省下 force-graph 依赖、布局冻结与性能回归成本。
9. **档位**：拆书入库与 AI 整理随 AI 拆书 PRO；手录/蒸馏沉淀/浏览免费。

10. **kb 依赖方向钉死**：`kb/` SHALL NOT import `write/`、`deconstruct/`——章纲信号抽取直读 outline/chapter 模型（`chapters/store.py` 或独立 loader）；`write/router.py`、`deconstruct/router.py` 单向调 `kb/`；配 import 断言测试（照 theme parity 测试路数）。
11. **注入实现位置**：`write/router.py`（存储稿选定之后、`WRITE_CLOSING_LINE` 追加之前拼接写法块）；`prompt_sources.py` 只加第八来源做展示 parity，不参与生成链路。
12. **kb_prefs 拍板**：改为 `(user_id, entry_id)` 账号级全局权重（有用率跨书共享），去掉 novel_id 字段——书内级的匹配留痕已有 `kb_match_items` 承担。
13. **唯一索引用 partial index**：幂等键 `(user_id, src_ref, src_key) WHERE src_ref <> ''`（手录不走幂等）；默认库格子 `(user_id, genre, concept) WHERE rule_kind='auto'`＋IntegrityError 回读兜并发（先例：`models/character_library.py` uq_char_lib_src）。
14. **kb_entry_tags 冗余 user_id 列**：物化索引本可重建，冗余 user_id 使 `(user_id, dim, value)` 单表索引成立，选择器短名单不 join。
15. **拆分策略**：本变更收敛为批1（底座＋浏览界面），批2–7 各立子变更（c-kb-write-block / c-kb-snapshot / c-kb-import / c-kb-character / c-kb-organize / c-kb-backup），各带 delta＋tasks，各自归档。

16. **概念推断**（批1 必须定义）：封闭词表确定性规则——作家输入文本与六概念的 `aliases` 表做关键词匹配，命中最多的概念为推断结果；匹配不出默认预选"手法"（最常用）；作家可改；推断不出不阻塞（"手法"兜底合法）。不跑模型。
17. **情节占位**：注册表含情节（供展示），但 `payloads.py` 对情节 SHALL 拒收创建（消费链未建），手录/推断/全局图对情节条目 SHALL 只展示占位文案"即将上线"。
18. **概念变更后库迁移**：条目概念修改 SHALL 将该条目从旧自动库 members 移除、加入新自动库 members；旧库空了不删除（保留给未来条目）。

19. **角色库迁移**：角色库不是独立系统，是知识库在"角色"维度的投影。扩 CharacterPayload 到全量字段＋写幂等迁移脚本＋角色库 UI 改读写 kb_entries＋`character_library` 表 deprecated。迁移幂等（重复执行不产生副本）。

## Risks / Trade-offs

- **章纲无场面字段**（c-og-slim-v2 已退役场景行）→ 别名归类是 P0 主路径，归类不出只出兜底不硬猜；P1 可在章纲表单加可选场面/情绪下拉（仍是作家声明）。
- **备份体积**（10 万条 ≈100MB）→ P1 加「备份含/不含知识库」开关；P0 先在导出摘要显示段体积。
- **关系表膨胀** → active ≤5×条目，按置信淘汰；每章每素材哈希一个 run。
- **kb_organize 模板跨仓发布**：模板缺失时整理 run 记 error 不阻断知识库（照起名模板兜底先例），不依赖提示词包发版。
- **拆书产物 schema 演进 → src_key 漂移**：src_key 钉死为稳定业务键（任务 id＋维度＋槽位序号）而非产物内容哈希，schema 改版不破幂等。
- **多设备配置包往返**：手录条目幂等键为空 → 恢复后 src_ref 冲突未定义；拍板恢复策略＝跳过已有同名同题材条目＋显示冲突清单。
- **与角色库 v8 备份顺序** → 本变更升 v9 且只在新表；迁移用列交集搬运既有机制，全列带默认值。

## Migration / Rollout

全加法：新表新段，旧代码不读；未启用库的书零变化。分批合入（见 tasks）：批1 底座＋界面；批2 写法块；批3 快照启用；批4 拆书入库；批5 角色原型；批6 AI 整理；批7 备份收口。本变更（批1）独立可发；批2–7 各立子变更独立合入归档。
