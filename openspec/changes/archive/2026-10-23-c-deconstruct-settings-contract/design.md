## Context

拆书建书出口在 `client/backend/deconstruct/apply.py`，消费 `products_json[dim].data`；产物 md 仅渲染展示。真实产物审计（2026-10-22，本地 258 章任务）暴露三类问题：

- 分析工件进设定：rules/craft 的 `how` 含「如第17、49、55章」，world power/cost/history 含「（第N章）」，intro/mainplot 含章号范围与 `confidence` 尾巴。
- 字段丢失/形状错配：world.extra 产物是 `{key,value}`、映射读 `{name,note}` → 74 条归零；techniques 的 `how` 不存在（在 repro_steps/emotion_chain）→ 只落名称；genre promise/tags、foreshadow note 未映射。
- 建书中断：产物 2 个「主角」撞 `uq_char_protagonist`；同对角色多 `rel_type` 撞 `(owner,other)` 唯一键；`book_id` 已落使重试幂等早退，半成品不可补。

## Goals / Non-Goals

**Goals**

- 产物 JSON 是分析稿、设定是操作稿：证据/confidence/原文未明确不进自由文本。
- 每个非空产物字段要么映射到已登记设定字段，要么在契约中显式声明为「只留任务资料」。
- 单条 DB 约束冲突只降级该条，不拖垮整本建书。
- 用真实形状测试锁住投影与冲突降级。

**Non-Goals**

- 不反解 md；不改设定页/角色页/伏笔页既有 schema；不为存量已建书做自动回写。

## Decisions

### D1 单点投影，不改源 JSON

新增 `deconstruct/settings_map.py`，所有建书文本经 `clean_settings_text`。源 JSON 与 md 保留证据章号、confidence、原文未明确；设定只收清洗后的可执行文本。显式证据字段（world.history.origin、relations.ch_ref、characters.plot 末尾）按既有模型语义保留。

### D2 逐维度映射矩阵

- style：role（首句）/rules/craft；examples 前 3→few_shot_examples；taboo→硬约束（避免…）；旧 narration/dialogue/rhythm/features 双认。
- world：stage/power/cost/history/factions/constraints/extra；extra 按 `{key,value}`；超 HISTORY_MAX/FACTIONS_MAX/CONSTRAINTS_MAX/EXTRA_MAX 截断并 warning。
- genre：promise 清洗后→novel_genre.promise_note；tags 留任务资料。
- mainplot：fullstory/ending 清洗；arcs 留任务资料。
- structure：title 含「原文未明确」交服务端兜底；chapters/pacing_notes 留任务资料。
- techniques：repro_steps/emotion_chain→how；borrowable→craft；avoid→硬约束；reader_needs 留任务资料。
- foreshadow：note 并入描述；埋设/回收章 tags 预留预算。
- characters：每书只保留首位主角，其余降配角；plot 保留一条 evidence。
- relations：按解析后的 `(owner,other)` 归并；同对多关系取并集；rel_type 超 20 字溢出并入 note；ch_ref 保留证据。

### D3 冲突安全

角色单卡 `IntegrityError` 回滚该笔并刷新 project；关系按 pair 预归并后用 savepoint 逐条写入。`task.book_id` 仍早落，但幂等返回会明确提示「已建过书、本次未重复写入」。

### D4 测试闸门

纯投影单测（清洗/形状/legacy/例句/taboo/世界/技法/关系标签）＋全维度真实形状集成测试（多主角、同对多关系、world extra、style examples/taboo、genre promise、structure title、hooks note）。产物 JSON 不被修改由单测断言。

## Risks / Trade-offs

- 清洗是正则+句界启发式：证据后接「所述/所示」等指代已处理，但极端写法仍可能留残词；源头提示词已把证据移出 how，清洗是兜底。
- world/relationships 有硬上限，超限内容只留任务资料并 warning；不追求无损进设定。
- 已建书幂等不自动重写；需要重跑拆书或新建书导入。
- 提示词包发布仍是独立步骤；旧包产物由投影层兼容。
