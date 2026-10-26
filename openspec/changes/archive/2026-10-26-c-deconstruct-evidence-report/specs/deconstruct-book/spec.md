## MODIFIED Requirements

### Requirement: 产物呈现作家视角

产物 Markdown SHALL 由代码按「键名→中文标签」映射渲染（如 intro→简介、summary→梗概），SHALL NOT 把 JSON 英文键名或 Python 对象原文（dict repr）直出给作家。证据类字段（evidence_ch/confidence/note/quote/raw）SHALL NOT 出现在作家 Markdown 的任何位置（含页脚与抬头行）：条目渲染前 SHALL 剥除证据类字段，剥后无内容字段的条目与无剩余条目的节 SHALL NOT 渲染；对象值（如主线 ending 的 scene/hero/tone）SHALL 逐字段展开为中文标签行；列表值（如 repro_steps/emotion_chain）SHALL 以「；」连接为单行说人话文本，SHALL NOT 出现 Python 列表 repr。标量节正文 SHALL 为裸值（标签已在节标题），SHALL NOT 重复自身标签；空列表/空对象/空标量 SHALL NOT 渲染空节；页脚章号/可信度口径说明 SHALL 退役。产物 Markdown 读取侧（应用内预览、存本地文件夹导出、结果目录字符数）SHALL 一律由任务资料 JSON 现渲染，SHALL NOT 读取历史存储的 md 字段——存量任务 MUST NOT 因历史 md 内嵌证据而在预览/导出中出现证据内容。

#### Scenario: 结局对象逐字段展开
- **WHEN** 主线剧情产物含 ending 对象（scene/hero/tone）
- **THEN** 主线.md 的「结局」节渲染为「结尾场景：…／主角结局：…／收束基调：…」三行，SHALL NOT 出现 dict 原文

#### Scenario: 标量节不重复标签
- **WHEN** 某维度产物含标量节（如世界 stage）
- **THEN** 节标题下正文为裸值，SHALL NOT 再出现「标签：值」形式的自身标签前缀

#### Scenario: 无正文不出节
- **WHEN** 某键的产物值为空列表/空对象/空标量
- **THEN** 该键 SHALL NOT 渲染只有标题的空节

#### Scenario: 证据字段不入作家 md
- **WHEN** 文风产物条目含 name/how/confidence/evidence_ch/note
- **THEN** 该条在作家 md 只呈现规则名与怎么用；「证据章节」「可信度」「说明」与页脚口径说明不出现在全文

#### Scenario: 列表值说人话
- **WHEN** 技法条目 repro_steps 为步骤数组
- **THEN** 渲染为「；」连接的单行文本，SHALL NOT 出现「['…']」列表原文

#### Scenario: 存量任务同口径
- **WHEN** 打开历史任务（其存储 md 曾内嵌证据章节与可信度）
- **THEN** 预览全文、导出文件与结果目录字符数均为现渲染口径的干净 md

### Requirement: 建书逐字段回填与旧产物兼容

建书灌设定 SHALL 经 `deconstruct.settings_map` 单点投影：产物 JSON 是分析稿（证据章号、confidence、原文未明确保留在任务资料——作家 md 不再承载证据，证据在应用内证据报告呈现），设定页只收可执行文本；自由文本 SHALL 剥除章号、「（第N章）」、裸章号、`confidence`/`note` 尾巴与「原文未明确」分析小句，显式证据字段（world.history.origin、relations.ch_ref、characters.plot 末尾一条）除外。

主线 fullstory SHALL 直灌故事弧全景（兜底链＝弧条目串→旧产物 ending 字符串→原文未明确）、ending 三格（scene/hero/tone）SHALL 回填 story_arc.ending 且「原文未明确」SHALL 置空；文风 SHALL 回填三区（role 叙事身份一句话／rules「名：怎么用」条目／craft 手法）＋examples 前 3 条→few_shot_examples＋taboo→硬约束（避免…），旧形状（narration/dialogue/rhythm 描述段与 features 特征表）SHALL 双认且回退条目 SHALL NOT 出现空前缀；世界 extra SHALL 按 `{key,value}` 映射，并按 HISTORY_MAX/FACTIONS_MAX/CONSTRAINTS_MAX/EXTRA_MAX 截断并 warning；题材 SHALL 回填 novel_genre 五字段：core_promise/promise_note/forbidden_list/cost_ratio/battlefield；优先采用产物新字段，旧产物缺字段时 SHALL 按题材承诺、主线与世界观代价给可编辑推断起点（warnings 留痕，SHALL NOT 留空），候选标签 SHALL 映射到稳定 genre_vocab id，tags 留任务资料；章卷 title 含「原文未明确」SHALL 交服务端兜底；写作技法 SHALL 由 repro_steps/emotion_chain 组成 how、borrowable→craft、avoid→硬约束；角色 SHALL 每书只保留首位主角、其余降配角并 warning，单卡 DB 约束冲突 SHALL 跳过该条不中断；人物关系 SHALL 按解析后的 `(owner,other)` 归并、同对多关系取并集、rel_type 超 20 字溢出并入 note、ch_ref 保留证据；伏笔 SHALL 回填 type/priority，有回收对应（payoff_ch 或 status=paid）SHALL 置台账状态为已回收并把回收章并入描述，note SHALL 并入描述；建书幂等返回 SHALL 提示「已建过书、本次未重复写入」。旧产物 SHALL 双认降级，SHALL NOT 因缺新契约格而中断或编造。

#### Scenario: 旧题材产物 02–05 补齐
- **WHEN** 勾中题材建书且产物只有 genre/tags/promise
- **THEN** 02–05 由 core_promise/forbidden/cost_ratio/battlefield 补齐；候选标签映射到 genre_vocab id；推断字段在 warnings 说明，SHALL NOT 留空

#### Scenario: 题材新字段优先
- **WHEN** 产物 genre 已含 core_promise/forbidden/cost_ratio/battlefield
- **THEN** 原样采用，不以推断覆盖；tags 只留任务资料

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

## ADDED Requirements

### Requirement: 证据报告

完成详情 SHALL 提供「证据报告」入口（应用内弹窗呈现）：按维度分组呈现任务资料的证据账——维度级顶层可信度与条目级证据单元格（证据章节/可信度/说明/原文佐证/原文措辞，中文标签呈现），条目行 SHALL 带条目结论 head（名称/条目/读者需求等）以便对回作家 md。数据 SHALL 由任务资料 JSON 现渲染（专用端点下发，鉴权与产物预览同口径、按用户过滤），SHALL NOT 依赖历史 md 反解；存量任务 SHALL 同样可看。没有证据类信息的任务 SHALL 给空态文案。证据报告 SHALL 为只读呈现，SHALL NOT 进结果目录勾选与导出文件清单，SHALL NOT 提供编辑或写回。

#### Scenario: 证据报告查看
- **WHEN** 完成态点「证据报告」
- **THEN** 弹窗按维度分组列出带证据的条目（head＋证据章节/可信度/说明等单元格）；加载失败 toast 报错并收起；✕／关闭／点击遮罩均可收起

#### Scenario: 存量任务可看
- **WHEN** 打开历史完成任务（早于证据报告能力创建）
- **THEN** 证据报告照常呈现（由任务资料 JSON 现渲染），作家 md 预览同步为去证据口径

#### Scenario: 无证据空态
- **WHEN** 任务产物不含证据类字段
- **THEN** 弹窗呈现空态文案，SHALL NOT 报错

#### Scenario: 不进出口
- **WHEN** 用户勾选导出/建书
- **THEN** 证据报告不进「已选 N/M」勾选集、不产生导出文件，出口行为与此前完全一致
