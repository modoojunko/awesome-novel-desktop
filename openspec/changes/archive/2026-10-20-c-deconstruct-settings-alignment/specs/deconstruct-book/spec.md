# deconstruct-book — 拆书输出对齐设定页字段契约

## ADDED Requirements

### Requirement: 产物呈现作家视角

产物 Markdown SHALL 由代码按「键名→中文标签」映射渲染（如 intro→简介、evidence_ch→证据章节、summary→梗概），SHALL NOT 把 JSON 英文键名或 Python 对象原文（dict repr）直出给作家。confidence SHALL 渲染为「可信度：高/中/低」；顶部单值 confidence SHALL 并入结果抬头行，SHALL NOT 单独成节。对象值（如主线 ending 的 scene/hero/tone）SHALL 逐字段展开为中文标签行。标量节正文 SHALL 为裸值（标签已在节标题），SHALL NOT 重复自身标签；空列表/空对象/空标量 SHALL NOT 渲染空节。页脚 SHALL 为作家视角口径说明（条目章号＝原文出处；可信度＝原文依据程度），SHALL NOT 出现「三铁律」等内部质检话术。

#### Scenario: 结局对象逐字段展开
- **WHEN** 主线剧情产物含 ending 对象（scene/hero/tone）
- **THEN** 主线.md 的「结局」节渲染为「结尾场景：…／主角结局：…／收束基调：…」三行，SHALL NOT 出现 dict 原文

#### Scenario: 标量节不重复标签
- **WHEN** 某维度产物含标量节（如世界 stage）
- **THEN** 节标题下正文为裸值，SHALL NOT 再出现「标签：值」形式的自身标签前缀

#### Scenario: 无正文不出节
- **WHEN** 某键的产物值为空列表/空对象/空标量
- **THEN** 该键 SHALL NOT 渲染只有标题的空节

### Requirement: 建书逐字段回填与旧产物兼容

建书灌设定 SHALL 按设定页字段契约逐字段映射：主线 fullstory SHALL 直灌故事弧全景（兜底链＝弧条目串→旧产物 ending 字符串→原文未明确）、ending 三格（scene/hero/tone）SHALL 回填 story_arc.ending 且「原文未明确」SHALL 置空；文风 SHALL 回填三区（role 叙事身份一句话／rules「名：怎么用」条目／craft 手法），旧形状（narration/dialogue/rhythm 描述段）SHALL 降级双认且回退条目 SHALL NOT 出现空前缀；角色 SHALL 回填 aliases 数组；关系 SHALL 回填 stance；伏笔 SHALL 回填 type/priority，且有回收对应（payoff_ch 或 status=paid）SHALL 置台账状态为已回收并把回收章并入描述。旧产物 SHALL 双认降级，SHALL NOT 因缺新契约格而中断或编造。

#### Scenario: 结局三格回填
- **WHEN** 勾中主线剧情建书且产物 ending 为新契约对象
- **THEN** story_arc.fullstory＝全书全景叙述、story_arc.ending 三格＝产物 ending；未完结书三格为空而非「原文未明确」

#### Scenario: 旧产物 ending 字符串兜底
- **WHEN** 存量任务产物 arcs 为空且 ending 为字符串（旧形状）
- **THEN** story_arc.fullstory 兜底为该结局文案，SHALL NOT 落「原文未明确」

#### Scenario: 伏笔回收状态回填
- **WHEN** 产物伏笔带 payoff_ch 或 status=paid
- **THEN** 台账该条状态为已回收、type/priority 按产物写入，回收章并入描述；只有埋设的条目保持待收状态

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
