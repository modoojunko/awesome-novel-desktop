# style-quant 变更（增量）

## MODIFIED Requirements

### Requirement: 量化基线注入写章提示词

- `confidence > 0` 时，写章提示词 SHALL 注入量化基线段：六行基线以「约 X（±容差）执行，可按本章剧情在容差内自行调节」口径渲染；`confidence = 0` 或缺失时 SHALL NOT 注入该段（文字文风三区恒生效兜底）。
- 容差 SHALL 由 confidence 分档：≥70→±10%、≥50→±20%、其余→±30%。
- 注入 SHALL 应用本章文风影子（若存在）：被影子命中的行 SHALL 以「约 X（本章覆盖：理由）」替换该行基线值渲染；未命中的行 SHALL 按基线渲染；影子为空/缺失/非对象时输出 SHALL 与无影子行为逐字节一致。
- 伏笔注入 SHALL 为「计划收束章等于当前章」的活跃伏笔追加「建议本章收束」派生标记（纯派生，不改存储）。

#### Scenario: 蒸馏后提示词含基线段

- **WHEN** 某书 confidence=82 且组装某章提示词
- **THEN** 提示词含量化基线段（含「约 48%」（±10%）形态的对话占比等条目与「按本章剧情在容差内自行调节」指令）

#### Scenario: 本章影子按行覆盖
- **WHEN** 某章存在影子行（如句法＝「短句为主」，理由「打斗章节奏」）
- **THEN** 提示词对应行渲染为「约 短句为主（本章覆盖：打斗章节奏）」，其余行按基线渲染

#### Scenario: 未蒸馏不注入量化段

- **WHEN** 某书无 style-quant 或 confidence=0
- **THEN** 提示词无量化基线段，文字文风三区照常注入

#### Scenario: 本章该还的伏笔被点名

- **WHEN** 某活跃伏笔 planned_chapter_id 等于当前写作章 id
- **THEN** 该伏笔注入行带「建议本章收束」标记；其他活跃伏笔不带

## ADDED Requirements

### Requirement: 本章文风影子

- 系统 SHALL 以 `chapters.style_shadow`（JSON 文本列，原表加列）存储每章的覆盖行：`{行名: {value, reason}}`；损坏值 SHALL 按空影子处理，不阻塞章读取。
- 系统 SHALL 提供三端点：`GET .../chapters/{ref}/style-shadow/baseline`（全书六行基线（含 locked/容差/画像/置信度）＋本章影子现状）、`PUT .../style-shadow`（专用小端点：`{rows}` 形状清洗——非对象行与非对象 rows 丢弃、值与理由全空白行丢弃、维度名与值字符串化保留原样（不脱空格）、响应回读清洗结果）、`POST .../style-shadow/suggest`（AI 建议：读基线＋本章章纲，产出行级建议并记账，不落库）。
- PUT SHALL NOT 挂 AI 门控（免费档可写影子——门禁属待拍板项，现状锁定）；suggest SHALL 挂 PRO 与本书模型双门控（与全站 AI 端点同口径），未蒸馏基线时 SHALL 返回 409（含「蒸馏」出口文案），模型未就绪（调用未发生）SHALL NOT 记账。
- suggest 产物清洗 SHALL 按六行白名单过滤：非白名单行、空值行丢弃；理由 SHALL 截断至 200 字；非法 JSON/非列表 SHALL 返回空建议。
- 影子行 SHALL 随章档案导出/导入（chapter-data 侧同步登记）；SHALL NOT 影响全书基线。

#### Scenario: 写入并回读影子
- **WHEN** 作者对某章 PUT 影子行（如句法覆盖）
- **THEN** 响应与后续 GET baseline 均返回该清洗后的影子行

#### Scenario: 脏形状被清洗
- **WHEN** PUT 的 rows 含非对象行、全空白行
- **THEN** 这些行被丢弃，其余行按字符串化原样保留

#### Scenario: 未蒸馏时拒绝建议
- **WHEN** 本书 confidence=0（未蒸馏）时发起 AI 建议
- **THEN** 返回 409 并提示先完成蒸馏；无模型调用

#### Scenario: 建议白名单清洗
- **WHEN** AI 建议含六行之外的维度或空取值
- **THEN** 这些条目被丢弃，理由超长截断至 200 字
