## MODIFIED Requirements

### Requirement: 建书逐字段回填与旧产物兼容

建书灌设定 SHALL 经 `deconstruct.settings_map` 单点投影：产物 JSON 是分析稿（证据章号、confidence、原文未明确保留在任务资料与 md），设定页只收可执行文本；自由文本 SHALL 剥除章号、「（第N章）」、裸章号、`confidence`/`note` 尾巴与「原文未明确」分析小句，显式证据字段（world.history.origin、relations.ch_ref、characters.plot 末尾一条）除外。

主线 fullstory SHALL 直灌故事弧全景（兜底链＝弧条目串→旧产物 ending 字符串→原文未明确）、ending 三格（scene/hero/tone）SHALL 回填 story_arc.ending 且「原文未明确」SHALL 置空；文风 SHALL 回填三区（role 叙事身份一句话／rules「名：怎么用」条目／craft 手法）＋examples 前 3 条→few_shot_examples＋taboo→硬约束（避免…），旧形状（narration/dialogue/rhythm 描述段与 features 特征表）SHALL 双认且回退条目 SHALL NOT 出现空前缀；世界 extra SHALL 按 `{key,value}` 映射，并按 HISTORY_MAX/FACTIONS_MAX/CONSTRAINTS_MAX/EXTRA_MAX 截断并 warning；题材 promise SHALL 清洗后写 novel_genre.promise_note（tags 留任务资料）；章卷 title 含「原文未明确」SHALL 交服务端兜底；写作技法 SHALL 由 repro_steps/emotion_chain 组成 how、borrowable→craft、avoid→硬约束；角色 SHALL 每书只保留首位主角、其余降配角并 warning，单卡 DB 约束冲突 SHALL 跳过该条不中断；人物关系 SHALL 按解析后的 `(owner,other)` 归并、同对多关系取并集、rel_type 超 20 字溢出并入 note、ch_ref 保留证据；伏笔 SHALL 回填 type/priority，有回收对应（payoff_ch 或 status=paid）SHALL 置台账状态为已回收并把回收章并入描述，note SHALL 并入描述；建书幂等返回 SHALL 提示「已建过书、本次未重复写入」。旧产物 SHALL 双认降级，SHALL NOT 因缺新契约格而中断或编造。

#### Scenario: 结局三格回填
- **WHEN** 勾中主线剧情建书且产物 ending 为新契约对象
- **THEN** story_arc.fullstory＝全书全景叙述、story_arc.ending 三格＝产物 ending；未完结书三格为空而非「原文未明确」

#### Scenario: 旧产物 ending 字符串兜底
- **WHEN** 存量任务产物 arcs 为空且 ending 为字符串（旧形状）
- **THEN** story_arc.fullstory 兜底为该结局文案，SHALL NOT 落「原文未明确」

#### Scenario: 文风三区、例句与禁忌回填
- **WHEN** 产物 style 含 role/rules/craft/examples/taboo
- **THEN** 叙事身份取 role 首句、rules/craft 落「名：怎么用」、examples 前 3 条落 few_shot_examples、taboo 以「避免…」落硬约束；旧 narration/dialogue/rhythm/features 双认；证据章号与 confidence 不进自由文本

#### Scenario: 世界 extra 与上限留痕
- **WHEN** 产物 world.extra 为 `{key,value}` 条目且超过 EXTRA_MAX
- **THEN** 前 EXTRA_MAX 条按 key/value 落世界设定，超出部分不进设定并在 warnings 说明截断数量；history.origin 保留证据章号

#### Scenario: 多主角与同对多关系不中断
- **WHEN** 产物含两个以上「主角」或同一对角色存在多种 rel_type
- **THEN** 首位保留主角、其余降配角并 warning；关系按 `(owner,other)` 合并为一条（rel_type/stance/note 取并集，rel_type 溢出并入 note），建书 SHALL NOT 因唯一约束 500 中断

#### Scenario: 证据与指令分离
- **WHEN** 产物自由文本含「如第17、49、55章」「（第N章）」「confidence: low」「原文未明确」
- **THEN** 设定页文本 SHALL 剥除这些分析工件；显式证据字段（world.history.origin、relations.ch_ref、characters.plot 末尾）仍保留，产物 md/任务资料不受影响

#### Scenario: 伏笔回收状态回填
- **WHEN** 产物伏笔带 payoff_ch 或 status=paid
- **THEN** 台账该条状态为已回收、type/priority 按产物写入，回收章并入描述；只有埋设的条目保持待收状态

#### Scenario: 幂等返回提示
- **WHEN** 任务已建过书再次请求建书
- **THEN** 返回同一 book_id，并在 warnings 提示「已建过书、本次未重复写入」
