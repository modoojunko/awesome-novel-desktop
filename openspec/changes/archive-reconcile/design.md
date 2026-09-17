# archive-reconcile — 设计要点

## D1. 同对象不另建表（用户约束 → 归属裁决）

| 原型概念 | 归属对象 | 落点 |
|---|---|---|
| 章内「伏笔 · X」变化 | novel_hooks（已有 introduced/planned/resolved/mentioned 四章引用列） | 零 schema，提案采纳写 hooks 服务 |
| 章内「关系 · A↔B」 | character_relations | +origin_chapter_id（存量 ch_ref 解析回填，不可解析留空） |
| 章内「人物 · X」状态 | chapter_characters（章×角色关系行） | +state_change 文本列（重归档/重试覆盖） |
| 卷纲「待埋伏笔」 | novel_hooks.planned_chapter_id | 派生视图（planned 落本卷章范围），不落字段 |
| 卷纲「待揭信息」 | novel_hooks（type=clue/mystery，**并入伏笔**，用户拍板） | 提案采纳走 hooks 服务 |
| 世界 lore origin | world KV 条目自身（已有 origin 字段） | 零 schema，建议入提案表 |
| 文风本章影子 | chapters 自身 | +JSON 列（本期不做，属文风影子独立条目；**备选** chapter_prompts name=style-shadow——已裁决 A：记章节档案） |
| 收尾产出（提案/进度） | **新对象** → 唯一新表 chapter_reconcile | status/payload/kind/chapter 引用 |

「截至本章」投影＝各列表按来源章排序过滤的**派生视图**，无账本表、无聚合存储；提示词组装（build_chapter_context）与体检的既有过滤语义不变——未确认提案不在目标对象上，天然不参与。

## D2. 提案表形态（用户拍板 A：一个抽屉）

`chapter_reconcile` 一张表，行＝「某章某类收尾的一次产出」：
`id / novel_id / chapter_id / kind(set_changes|relations|hooks|lore|char_states) / status(pending|accepted|rejected|failed) / payload(JSON) / created_at / decided_at`
- 进度（进行中/待确认/失败数）由行聚合派生，**不建任务表**。
- 同章同键（kind+业务键）未决行覆盖；已决行保留留痕。
- payload 只存待确认差异（建议值＋证据句），**不复存对象数据**；采纳调对象自身服务（relations/hooks 服务、lore-apply、出场引用行写），失败回滚为 failed 保留 payload。

## D3. 归档拆分

- 同步段（请求内，即刻生效）：archives 行 upsert、mark_hooks_mentioned、threads、状态迁移——全部维持现状。
- 后台段（单飞线程，模式照抄 backup/export._job）：AI 收尾三类＋lore＋角色状态提取，产出写 chapter_reconcile；进度由行状态聚合，前端轮询 `GET /reconcile?chapter_id=`。
- legacy 清理：update_character_states 的 YAML state_history 追加退役（改写出场上引用行 state_change）；legacy 键与存量数据保留（回滚安全）。

## D4. schema 迁移（含指纹门禁的现实约束）

- character_relations +origin_chapter_id（FK chapters.id SET NULL）＋存量回填（ch_ref 解析，一次性，幂等）。
- chapter_characters +state_change（Text default ""）。
- 新表 chapter_reconcile（含 novel_id/chapter_id FK CASCADE——随书删）。
- main.py 幂等 ALTER 台阶保留（对全新库/导入库为 no-op 或兜底）。

**⚠️ 指纹门禁现实（实现期实测确认）**：`legacy_archive.compute_schema_fingerprint` 是全库「表+列+类型」哈希，`archive_if_legacy` 按**等值**判定——本变更改了模型 → 指纹必变 → 存量库升级首启**整库自动留档**（license 同款三道防线：自动留档 / .bak / 导出包），随后建新空库。因此：
1. 用户的升级路径 = 导出包 → 升级 → 导入（新包含 state_change/origin_chapter，见 D4 导出契约）；旧库文件自动留档可人工救回——这是 export-roundtrip 立的既有协议，本 PR 不改其语义。
2. `ch_ref→origin_chapter_id` 回填的真正价值在**导入旧格式包**（v3 包含 ch_ref 无 origin）后：启动期幂等回填把来源章补上。
3. 架构级后续（不在本期）：让留档门禁识别「纯增量」schema 差异并原地 ALTER，免整库留档——需把 app_meta 从哈希改为结构清单，单独立项。
4. 验收含**删库救回演练**（导出→升级触发留档→导入恢复全量数据）。
- 导出/导入：state_change、origin_chapter 随对象进包（ref↔id 重绑，目标章缺失留空＋告警）；chapter_reconcile 界外（登记归属）。

## D5. 门控与 AI 成本

- 收尾 AI 全归 PRO（对齐现状「体检只读免费、生成/归档 PRO」口径）；免费档归档即刻生效、无收尾区。
- 调用次数：归档从「摘要 1 次」→「摘要＋设定提取＋关系建议＋伏笔登记＋lore＋角色状态」最多 6 次（烧本书模型）；失败一律降级为 failed 行，不影响归档成功。
