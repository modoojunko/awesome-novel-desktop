## MODIFIED Requirements

### Requirement: 提示词契约与输出校验

- 七条硬规则与体检判据的**文本单源** SHALL 落成一份片段文件（两个模板用占位符引用），并配逐字对拍测试；
  界面上的七条（作家语言）SHALL 声明为有意的第三份改写，SHALL NOT 与提示词文本同源对拍。
- 三份提示词 SHALL 为 `prompts/volume_options.prompt`、`volume_expand.prompt`、`volume_check.prompt`；
  素材 SHALL 取自既有非章域单源（SHALL NOT 复用章域的 `build_chapter_context`——它必须传章 ref，0 章书用不了）：
  主线全景与结局三问（`novels/router` 的 arc 归一）、世界观摘要（`settings/world_model` 的世界块，铁律全量）、
  核心人物（主角卡＋上一卷结尾/作者那句话点名的人＋本卷 cast，每人 ≤80 字、上限 6 张）、
  上一卷的结尾（事实优先，取数收敛在一个函数里；取该卷末章的摘要与末段，无章时取上一卷卷纲的预期结局）、
  伏笔台账（active 全量 ＋ 本卷之前已收/已弃各一条摘要，带编号与计划收束位置——体检要判「漏收/提前揭」，
  只看 active 不够）、
  题材与节奏（`genres/service` 的题材段）。
- 各块 SHALL 带预算上限（全景 ≤2000、结局三问各 ≤200、世界摘要 ≤1200、人物每人 ≤80×6、伏笔 ≤8 条、
  作者那句话 ≤150 字）；P1 读归档章时正文 SHALL 只取该卷末章的摘要与末段，SHALL NOT 整卷正文入包。
- 素材包顺序 SHALL 按端点分别写死（options 不含本卷卷纲与已写内容；expand 含上一卷卷纲文本与伏笔台账；
  check 含本卷卷纲文本、世界铁律与已写内容）。
- 三个端点 SHALL 走既有「判定/短答复类」的关闭思考路径（`ai_client` 的 thinking 关闭与端点拒绝时的去掉
  重试），`max_tokens` SHALL 用默认档。
- 输出 SHALL 为纯 JSON（无解释文字），并 SHALL 经代码侧校验兜底：JSON 可解析、字段齐全与上限、套数 2–3、
  三套的侧重去重后数量等于套数、每套卷末非空、**模型申报的实体集合做差**（options/expand SHALL 在输出里
  显式申报 `factions` 与坎处点名的人物（antagonist 为人物/势力型时），代码用角色表的
  name+aliases 与世界势力名做集合差，差集非空进 warnings 提示建卡——不从自由文本抽词）。
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
  （照设定原文写全）」——卷纲点名配角，拆章才不全程独角戏（章卡侧的消费见 chapter-plan-ai
  「拆章素材包与输出契约」⑥的卷纲点名者聚光口径）。
- 校验失败 SHALL 重试一次（降低温度并把失败原因作为追加消息喂回），仍失败 SHALL 降级为「只给四件事」的纯文本
  并提示可重试；**每次尝试（含失败）SHALL 计量**（失败记 `*_fail`）。

#### Scenario: 推理模型上的 JSON

- **WHEN** 用推理型模型（如 deepseek-v4 系列）调这三个端点
- **THEN** 调用走关闭思考路径并拿到 JSON 文本块；若不关闭思考，预算会全部用于思考而不返回文本

#### Scenario: 模型把轴词填进 focus 而非 focus_axis

- **WHEN** 模型输出把侧重轴词写进 `focus`、`focus_axis` 缺失或含自造值
- **THEN** 服务端只从 `focus_axis` 读轴并照既有兜底顺位补未用轴，SHALL NOT 从 `focus` 文本反推；
  卡面侧重轴标签与机读轴保持同源
