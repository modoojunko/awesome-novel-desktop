# c-deconstruct-settings-contract · tasks

## 1. 投影层

- [x] 1.1 新增 `deconstruct/settings_map.py`：`clean_settings_text` 剥括注/裸章号、continuous 引用、指代尾巴、confidence/note、「原文未明确」；句界截断；纯标点归空
- [x] 1.2 style：role 首句、rules/craft、examples 前 3→few_shot_examples、taboo→硬约束；旧 narration/dialogue/rhythm/features 双认
- [x] 1.3 world：extra `{key,value}` 修复；按真实 HISTORY_MAX/FACTIONS_MAX/CONSTRAINTS_MAX/EXTRA_MAX 截断并 warning；history.origin 保留证据
- [x] 1.4 genre promise→promise_note；mainplot/intro 清洗；structure 分析标题兜底
- [x] 1.5 techniques：repro_steps/emotion_chain→how、borrowable→craft、avoid→硬约束；foreshadow note 并入描述

## 2. 建书健壮性

- [x] 2.1 角色：每书只保留首位主角，其余降配角并 warning；单卡 IntegrityError 回滚该笔、刷新 project、继续
- [x] 2.2 关系：按解析后的 (owner,other) 归并；同对多关系取并集；rel_type 20 字溢出并入 note；savepoint 逐条写入
- [x] 2.3 幂等返回明确提示「已建过书、本次未重复写入」

## 3. 提示词仓（#19 / 37fde95）

- [x] 3.1 style rules/craft/taboo → {name, how, confidence, evidence_ch, note}；how 纯指令；examples 只取卡片逐字 quote（0–6，同卡 evidence）
- [x] 3.2 reduce：按维度证据落点、taboo 兼容合并/冲突不并集、同名/异名近义冲突规则、examples ≤6、how≤60/name≤8/rules 5–10/craft 3–8
- [x] 3.3 card/card_batch 增加 style quote；batch 补齐 alias/places/mainplot/presence 纪律；card_batch 进 TIER_FREE
- [x] 3.4 提示词测试钉：quote 来源、confidence 总则、证据落点、冲突分支、形状/格式、card_batch JSONL；sync.py lint 通过

## 4. 回归与归档

- [x] 4.1 桌面仓 #926（4bd70d61）：拆书套件 179 passed；带源全量 2692 passed/1 skipped；ruff 全过
- [x] 4.2 本地 258 章真实产物完整建书：35 角色（1 主角）、46 条关系、文风 29 规则/19 手法/3 例句、world extra 50，自由文本无证据残留
- [x] 4.3 提示词仓 #19（37fde95）：lint 通过；118 passed/1 skipped
- [x] 4.4 归档本 change 并把 delta sync 进 `deconstruct-book` 主 spec
