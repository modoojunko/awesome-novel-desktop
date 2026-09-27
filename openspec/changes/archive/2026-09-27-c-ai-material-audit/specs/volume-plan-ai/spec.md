# volume-plan-ai

## MODIFIED Requirements

### Requirement: 提示词契约与输出校验

- 八条硬规则与体检判据（含「对节奏」组）的**文本单源** SHALL 落成一份片段文件（两个模板用占位符引用），
  并配逐字对拍测试；界面上的八条（作家语言）SHALL 声明为有意的第三份改写，SHALL NOT 与提示词文本同源对拍。
- 三份提示词 SHALL 为 `prompts/volume_options.prompt`、`volume_expand.prompt`、`volume_check.prompt`；
  素材 SHALL 取自既有非章域单源（SHALL NOT 复用章域的 `build_chapter_context`——它必须传章 ref，0 章书用不了）：
  主线全景与结局三问（`novels/router` 的 arc 归一，**全景全量不截**）、
  **世界观块（`settings/world_model` 渲染，全量不截：舞台/力量/代价骨架＋势力/历史/细节条目全量；铁律仍走红线区全量；
  渲染的预算参数 SHALL 修活——预算真实可传入，拆卷三端点显式传全量；条目放不下被截时从略注 SHALL 按类别计数——
  「另有 N 个势力从略」，SHALL NOT 混称「世界细节」）**、
  核心人物（**全名单一行卡**：角色表全部角色，每人一行＝名字＋定位＋一句人设，主角置顶，不设数量上限；
  既有 6 张×80 上限与聚光单换位机制 SHALL 退役）、
  **已拆卷清单（新块，options/expand）：每卷一行＝卷号＋标题＋主旨＋坎类型·一句话＋卷末落点，不设卷数上限；
  options 含全部既有卷，expand SHALL NOT 含本次展开的目标卷自身；check 不含（本卷卷纲在手）**、
  **无卡出场名单（新派生块，options/expand）：既有各卷主线章章纲出场名单中无卡的名字＋出场章号
  （剔旧稿支线，与 `_aggregate_cast` 同口径），SHALL 从既有派生、SHALL NOT 新增存储**、
  上一卷的结尾（事实优先，取数收敛在一个函数里；取该卷末章的摘要与末段，无章时取上一卷卷纲的预期结局）、
  伏笔台账（active 全量 ＋ 本卷之前已收/已弃各一条摘要，带编号与计划收束位置——体检要判「漏收/提前揭」，
  只看 active 不够）、
  题材与节奏（`genres/service` 的题材段）。
- **设定侧块 SHALL NOT 设预算**：世界块、人物全名单、已拆卷清单、无卡出场名单、主线全景 SHALL 全量进入；
  其余格式约束保留（结局三问各 ≤200、伏笔台账 active 全量（≤8 上限已退役：第 9 条起的未收伏笔曾在下游全部不可见）、作者那句话 ≤150 字）；P1 读归档章时正文 SHALL 只取该卷
  末章的摘要与末段，SHALL NOT 整卷正文入包。
- 素材包顺序 SHALL 按端点分别写死（options 不含本卷卷纲与已写内容，含全部既有卷的已拆卷清单；
  expand 含上一卷卷纲文本、伏笔台账与目标卷之前的已拆卷清单；check 含本卷卷纲文本、世界观块、世界铁律、
  核心人物全名单与已写内容——check 现状仅注入 `world_rules` 不含世界块，SHALL 补齐）。
- **首卷位置片段**：`volume_expand.prompt` SHALL 含独立 `<<volume_pos_rules>>` 占位符（置于 `<<hard_rules>>`
  之后）；vol_no＝1 时注入 `prompts/volume_pos_first.prompt`（开卷即入戏：conflict 写明主角在第 1–3 章
  被哪个事件、被谁逼进核心冲突；不设铺垫期：进场这道坎按全书前期最高强度设计——即使选中的走法偏慢热，
  冲突进场也不晚于第 3 章），其余卷渲染为空串（连标题不留）；片段 SHALL NOT 拼进 `<<hard_rules>>` 文本
  （保 rules 单源＋锚点切分＋对拍测试三件套）；`volume_options` SHALL NOT 注入任何节奏片段（三套互斥优先，
  节奏由 expand 统一执行）。
- 三个端点 SHALL 走既有「判定/短答复类」的关闭思考路径（`ai_client` 的 thinking 关闭与端点拒绝时的去掉
  重试），`max_tokens` SHALL 用默认档。
- 输出 SHALL 为纯 JSON（无解释文字），并 SHALL 经代码侧校验兜底：JSON 可解析、字段齐全与上限、套数 2–3、
  三套的侧重去重后数量等于套数、每套卷末非空、**模型申报的实体集合做差**（options/expand SHALL 在输出里
  显式申报 `factions` 与坎处点名的人物（antagonist 为人物/势力型时），代码用角色表的
  name+aliases、世界势力名**与既有章纲出场名单的无卡名字**做集合差，差集非空进 warnings 提示建卡——
  不从自由文本抽词）。
  options 输出的**服务端钳位值 SHALL 等于提示词字段上限说明**（走向 ≤40／冲突 ≤40／卷末 ≤40／侧重说明 ≤20／
  坎一句话 ≤150／卷数估计 ≤20），SHALL NOT 以更宽的兜底架空上限说明。
- 首调温度 SHALL 为 options 0.7／expand 0.4／check 0.2，重试 SHALL 降到 0–0.2；
  options 的输出契约 SHALL 含 `note`（套数 <3 时必填，写明为什么给不出第三套）与 `volume_estimate`
  （**预计本卷的章数范围一句话，如「35–45 章」，≤20 字**，供规划台的「卷数」材料显示；
  提示词 SHALL 附该字段说明——模板曾只在 JSON 示例出现、全文无解释）。
- 每套方案与 expand 草稿 SHALL 带四问答案（含 `antagonist_type`/`antagonist_line`）；
  **SHALL NOT 申报角色清单**（角色从章聚合）。expand 草稿的 `plants`/`reveals` 为
  **台账建议**：确认成卷时经既有 hooks 登记接口入台账（带编号与计划收束卷），
  SHALL NOT 写入卷表文本列（卷的伏笔唯一登记处＝台账）。
- **侧重轴双轨字段**：每套 SHALL 以 `focus_axis`（侧重轴闭集词，互不相同）为机读字段、`focus`（≤20 字
  侧重说明）为展示文本分别声明；提示词 SHALL 将两者分开声明（SHALL NOT 一句混说）；服务端 SHALL 只从
  `focus_axis` 读轴，闭集外自造轴照既有兜底顺位补未用轴，SHALL NOT 从 `focus` 推断轴。
- **`antagonist_type` 闭集声明**：两份生成模板 SHALL 声明五类型闭集（人物／难题／环境／自我／势力）——
  options 已有，expand 补声明；闭集外非法值照既有兜底处置（非空 → 人物），提示词声明即以降低其发生率为目的。
- **expand `summary` 关键配角口径**：SHALL 声明「以主角经历为主线；本卷要唱重头戏的关键配角把名字带一笔
  （照设定原文写全）」——卷纲点名配角随**核心人物全名单**自然可见，供拆章素材消费（chapter-plan-ai
  「拆章素材包与输出契约」⑦；既有 ⑥ 聚光口径随 6 张上限一并退役）。
- 校验失败 SHALL 重试一次（降低温度并把失败原因作为追加消息喂回），仍失败 SHALL 降级为「只给四件事」的纯文本
  并提示可重试；**每次尝试（含失败）SHALL 计量**（失败记 `*_fail`）。

#### Scenario: 推理模型上的 JSON

- **WHEN** 用推理型模型（如 deepseek-v4 系列）调这三个端点
- **THEN** 调用走关闭思考路径并拿到 JSON 文本块；若不关闭思考，预算会全部用于思考而不返回文本

#### Scenario: 首卷展开注入位置片段

- **WHEN** 空书第一次展开卷纲（vol_no＝1）与非首卷展开各发生一次
- **THEN** 前者系统提示词含「开卷即入戏／不设铺垫期」片段且 `<<hard_rules>>` 文本仍与 rules 单源逐字一致；
  后者该占位符渲染为空串；两次调用的三套走法端点（options）均不含节奏片段

#### Scenario: 模型把轴词填进 focus 而非 focus_axis

- **WHEN** 模型输出把侧重轴词写进 `focus`、`focus_axis` 缺失或含自造值
- **THEN** 服务端只从 `focus_axis` 读轴并照既有兜底顺位补未用轴，SHALL NOT 从 `focus` 文本反推；
  卡面侧重轴标签与机读轴保持同源

#### Scenario: 势力全量进世界块

- **WHEN** 一本书的世界设定登记了三个势力（各带长注记），且舞台/力量/代价三段骨架文本较长
- **THEN** 拆卷 options/expand/check 的素材世界块 SHALL 包含全部三个势力的名字与注记，
  SHALL NOT 因骨架占满预算而整条略去任何势力

#### Scenario: 已拆卷清单与无卡名单进素材

- **WHEN** 书里已有四卷卷纲（第 4 卷已拆章且出场名单含无卡名字「哑叔」），作者展开第五卷
- **THEN** 素材的已拆卷清单 SHALL 含第 1–4 卷各一行（含各自的坎），SHALL NOT 含第五卷自身；
  无卡出场名单 SHALL 含「哑叔」及其出场章号；模型申报实体做差时「哑叔」SHALL 记为已知，SHALL NOT 进 warnings
