## MODIFIED Requirements

### Requirement: 十维度拆解管线与断点续拆

拆解 SHALL 按**创建时勾选的维度子集**执行（默认全选、下限 1 份；维度清单为简介/题材/世界设定/
角色设定/人物关系与势力/主线剧情/章卷结构/写作文风/写作技法/伏笔），采用「逐章拆卡 → 分维度分级
语义归并」两阶段管线（v2，2026-10-13 拍板）：阶段一每章一次模型调用产出十维拆书卡（含一句话
梗概，条目只以本章可见内容为据）；阶段二按维度收集逐章卡片碎片、按字数分批归并（L1），再对归并
产物**树状收敛**（通用合并迭代至单份），全程 SHALL NOT 有头尾截断。每个维度 SHALL 有独立状态
（排队/进行中/完成/失败），单元级失败 SHALL 自动重试有限次后置维度失败并终止任务。续拆 SHALL 只
执行创建时勾选且尚未完成的维度，卡片按**章粒度**复用不重取，已完成维度产物 SHALL 保留且不重复
计费。用户取消 SHALL 在章/批边界停止并把任务置为已取消、保留已完成维度产物。进度 SHALL 报「逐章
拆卡 x/y 章、分维度归并到哪一步」，SHALL NOT 输出拆解内容。

各维度输出契约 SHALL 对齐书内设定页字段（2026-10-20 拍板）：主线剧情 SHALL 产出 fullstory 全书
主线全景叙述（300–500 字连贯散文）、剧情弧明细（arcs，含起止章/梗概/证据章/可信度）与 ending
结局三格（scene/hero/tone），弧 SHALL 按全书起承转合归纳、SHALL NOT 按材料分段机械切分；文风
SHALL 按三区产出（role 叙事身份一句话／rules「名：怎么用」条目／craft 手法＋examples 原文短例）；
角色卡 SHALL 含 aliases 别名数组且 plot SHALL 合并跨材料行动；关系边 SHALL 含 stance（一方对另一
方的立场）；伏笔 SHALL 含 type（九值闭集）与 priority；题材 SHALL 从注入的题材库词表逐字选词（词
表外才给自由词并降 low）。树状收敛合并 SHALL 按维度分策略执行：实体类维度 SHALL 并集补全合并
（SHALL NOT 以「信息全的一条」丢弃其他段的独有信息）；主线剧情 SHALL 归纳重写为全书级剧情弧
（3–8 条，可跨段，起止章取实际覆盖范围）并以全书视角重写 fullstory；伏笔 SHALL 跨段接线（埋设与
回收散在不同段时并成一条完整台账）；文风与世界舞台等叙述字段 SHALL 以全书视角重写而非各段拼接。

题材维度的输出契约 SHALL 与书内题材面板五格一一对应（c-deconstruct-genre-fields）：除
`genre`（主题材，词表逐字选）与 `tags`（≤5）外，SHALL 产出
`core_promise`（核心承诺，一句话 ≤60 字，SHALL NOT 含章号——证据写 `note`）、
`promise_note`（承诺说明 ≤200 字）、
`forbidden`（禁写清单 ≤6 条，**SHALL 从注入的禁写词表选**，词表外才给自由文本）、
`cost_ratio`（代价比例，1–10 整数，SHALL 依据世界设定的代价）、
`battlefield`（战场 ≤2 条，**SHALL 从注入的战场词表选**），
以及 `confidence` 与 `note`；每格沿用三铁律（硬事实回指章号、标可信度、原文没写的标「原文未明确」，
SHALL NOT 脑补）。管线 SHALL 在题材维度的模型输入中注入题材/禁写/战场三份词表；其余维度模板
无对应占位符，注入 SHALL NOT 影响其行为。模型给出词表外标签时，消费侧 SHALL 按自定义文本落库
（SHALL NOT 硬塞 vocab id）。

#### Scenario: 维度失败可续拆
- **WHEN** 某个维度某批模型调用重试后仍失败
- **THEN** 任务置为已失败，详情显示失败维度/批次/错误码与已完成维度（保留）；续拆只跑创建时勾选且未完成的维度

#### Scenario: 用户取消
- **WHEN** 用户在拆解中详情点「取消任务」
- **THEN** 当前章/批跑完即停，任务置为已取消，已拆卡片与已完成维度产物保留；取消不产生新的模型调用

#### Scenario: 章级断点续拆
- **WHEN** 拆卡进行到 40/100 章时应用退出，用户从断点续拆
- **THEN** 只补取剩余 60 章卡片，前 40 章卡片复用不重取、不重复计费

#### Scenario: 创建时勾选部分维度
- **WHEN** 用户创建任务时仅勾选部分维度（如 10 选 5）
- **THEN** 管线只拆勾中维度，结果目录只列已拆产物，出口计数以勾选集为基础；续拆也只补该勾选范围内未完成的维度

#### Scenario: 主线全书级归纳
- **WHEN** 258 章的书分 7 段拆解主线，各段产出各自的剧情弧
- **THEN** 合并产物为全书级剧情弧（3–8 条，可跨段）与全书视角 fullstory 叙述，SHALL NOT 是各段弧的顺序拼接

#### Scenario: 伏笔跨段接线
- **WHEN** 同一伏笔的埋设碎片在第 1 段、回收碎片在第 7 段
- **THEN** 合并产物并成一条完整台账（埋设章取埋设段、回收章/状态取回收段），SHALL NOT 留两条残条目

#### Scenario: 题材词表选词
- **WHEN** 管线执行题材维度
- **THEN** 模型输入含题材库词表，genre 从词表逐字选最贴近词；词表确实不贴才给自由词并降 low

#### Scenario: 题材五格齐备

- **WHEN** 题材维度完成，产物落 `products_json.genre.data`
- **THEN** 该对象 SHALL 含 `genre/tags/core_promise/promise_note/forbidden/cost_ratio/battlefield`；`core_promise` ≤60 字且不含章号，`cost_ratio` 为 1–10 整数，`forbidden` ≤6 条、`battlefield` ≤2 条且均取自注入词表（词表外给自由文本）

#### Scenario: 词表注入只作用于题材维度

- **WHEN** 管线执行非题材维度
- **THEN** 其模型输入不含禁写/战场词表，行为与本次变更前一致

### Requirement: 建书逐字段回填与旧产物兼容

建书灌设定 SHALL 经 `deconstruct.settings_map` 单点投影：产物 JSON 是分析稿（证据章号、confidence、原文未明确保留在任务资料——作家 md 不再承载证据，证据在应用内证据报告呈现），设定页只收可执行文本；自由文本 SHALL 剥除章号、「（第N章）」、裸章号、`confidence`/`note` 尾巴与「原文未明确」分析小句，显式证据字段（world.history.origin、relations.ch_ref、characters.plot 末尾一条）除外。

主线 fullstory SHALL 直灌故事弧全景（兜底链＝弧条目串→旧产物 ending 字符串→原文未明确）、ending 三格（scene/hero/tone）SHALL 回填 story_arc.ending 且「原文未明确」SHALL 置空；文风 SHALL 回填三区（role 叙事身份一句话／rules「名：怎么用」条目／craft 手法）＋examples 前 3 条→few_shot_examples＋taboo→硬约束（避免…），旧形状（narration/dialogue/rhythm 描述段与 features 特征表）SHALL 双认且回退条目 SHALL NOT 出现空前缀；世界 extra SHALL 按 `{key,value}` 映射，并按 HISTORY_MAX/FACTIONS_MAX/CONSTRAINTS_MAX/EXTRA_MAX 截断并 warning；题材 SHALL 回填 novel_genre 五字段：core_promise/promise_note/forbidden_list/cost_ratio/battlefield；优先采用产物新字段（`core_promise`/`forbidden`/`cost_ratio`/`battlefield`），**`core_promise` 缺失时 SHALL 回退读旧字段 `promise` 并按 60 字收口**（旧产物与旧提示词包同样能取到真值），仍缺才按题材承诺、主线与世界观代价给可编辑推断起点（warnings 留痕，SHALL NOT 留空），候选标签 SHALL 映射到稳定 genre_vocab id（词表外按自定义文本），tags 留任务资料；章卷 title 含「原文未明确」SHALL 交服务端兜底；写作技法 SHALL 由 repro_steps/emotion_chain 组成 how、borrowable→craft、avoid→硬约束；角色 SHALL 每书只保留首位主角、其余降配角并 warning，单卡 DB 约束冲突 SHALL 跳过该条不中断；人物关系 SHALL 按解析后的 `(owner,other)` 归并、同对多关系取并集、rel_type 超 20 字溢出并入 note、ch_ref 保留证据；伏笔 SHALL 回填 type/priority，有回收对应（payoff_ch 或 status=paid）SHALL 置台账状态为已回收并把回收章并入描述，note SHALL 并入描述；建书幂等返回 SHALL 提示「已建过书、本次未重复写入」。旧产物 SHALL 双认降级，SHALL NOT 因缺新契约格而中断或编造。

题材推断提示 SHALL 如实且面向作家：仅当某格**确实取不到产物值**时才列入推断清单，用中文标签（核心承诺／禁写清单／代价比例／战场）表述，文案说明「按题材与主线推的起点，请去设定 → 题材核对」；SHALL NOT 出现数据库键名（core_promise 等）、SHALL NOT 把已取到值的格列为「未覆盖」。

#### Scenario: 旧题材产物 02–05 补齐
- **WHEN** 勾中题材建书且产物只有 genre/tags/promise
- **THEN** 02–05 由 core_promise/promise_note/forbidden/cost_ratio/battlefield 补齐（core_promise 取 promise 前 60 字）；推断字段在 warnings 说明，SHALL NOT 留空

#### Scenario: 核心承诺回退旧字段
- **WHEN** 产物 `genre.data` 含 `promise` 但不含 `core_promise`
- **THEN** 设定页「核心承诺」SHALL 取 `promise` 收口 60 字，`promise_note` 取完整 `promise`；该格 SHALL NOT 出现在推断清单里

#### Scenario: 题材新字段优先
- **WHEN** 产物 genre 已含 core_promise/forbidden/cost_ratio/battlefield
- **THEN** 原样采用，不以推断覆盖；tags 只留任务资料

#### Scenario: 推断提示只说真推断

- **WHEN** 产物含 `core_promise` 与 `cost_ratio`，缺 `forbidden` 与 `battlefield`
- **THEN** 提示只列「禁写清单、战场」两项（核心承诺与代价比例已取到值，SHALL NOT 列入），用中文表述，SHALL NOT 出现 `forbidden`/`battlefield` 等键名

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
- **WHEN** 任务已建过书且原书仍在（未删除），再次请求建书
- **THEN** 返回同一 book_id，并在 warnings 提示「已建过书、本次未重复写入」；原书已删除时按「建书出口 · 删书后再建书」新建一本
