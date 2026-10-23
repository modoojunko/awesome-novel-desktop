# 拆书建书设定投影契约（c-deconstruct-settings-contract）

## Why

本地 258 章真实拆书产物审计发现：产物 JSON/md 是分析稿，但建书时证据章号、`confidence`、`原文未明确` 会被写进设定页并注入后续写作提示词；同时多个维度存在字段丢失或形状错配（world.extra 74 条归零、techniques 只落名称、genre promise 丢失等），角色多主角与关系同对多类型还会让建书直接 500，且 `book_id` 已落导致重试幂等早退、半成品不可恢复。

## What Changes

- **单点投影层**：新增 `deconstruct/settings_map.py`，只读产物 JSON、产出设定值；源 JSON 与 md 保持分析稿原样。统一 `clean_settings_text` 剥括注/裸章号、`confidence/note` 尾巴、「原文未明确」小句，句界截断。
- **全维度映射**：style 三区＋examples→few_shot_examples＋taboo→硬约束；world extra 按 `{key,value}`，按真实上限裁断并留 warning；genre promise→novel_genre.promise_note；mainplot/intro 清洗；structure 分析标题兜底；techniques repro_steps/emotion_chain→how、borrowable→craft、avoid→硬约束；foreshadow note 并入描述。
- **冲突安全**：角色每书只保留首位主角，其余降配角；单卡 DB 约束冲突只跳过该条；关系按解析后的 `(owner,other)` 归并，同对多关系取并集，`rel_type` 溢出并入 note；幂等返回明确提示未重复写入。
- **提示词源头（prompts #19）**：文风 `rules/craft/taboo` 改为 `{name, how, confidence, evidence_ch, note}`，how 纯指令、证据只进 evidence_ch；card/card_batch 增加逐字 `quote` 供 examples；reduce 按维度证据落点、taboo 冲突合并、examples 上限与同名冲突规则收口。
- **回归闸门**：新增投影单测＋全维度真实形状集成测试；带提示词源全量后端 2692 passed/1 skipped。

## Capabilities

### Modified Capabilities

- `deconstruct-book`: 建书逐字段回填与旧产物兼容——新增单点投影、证据清洗、全维度字段映射与冲突降级口径。

## Design Impact

- 仅 C 端拆书建书出口与提示词仓拆书模板；不改设定页既有 schema，不改产物 md/任务详情。
- 显式证据字段保留：world.history.origin、relations.ch_ref、characters.plot 末尾一条 evidence_ch，供回查。
- 旧形状（narration/dialogue/rhythm/features、ending 字符串）仍双认降级。

## Verification

- 桌面仓 #926（4bd70d61）：拆书套件 179 passed；带提示词源全量 2692 passed/1 skipped；ruff 全过；本地 258 章真实产物完整建书通过（35 角色/1 主角、46 条关系、文风 29 规则/19 手法/3 例句、world extra 50）。
- 提示词仓 #19（37fde95）：`sync.py lint` 通过；`pytest tests/` 118 passed/1 skipped。
