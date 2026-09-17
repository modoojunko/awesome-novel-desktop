# style-quant 变更（增量）

## MODIFIED Requirements

### Requirement: 本章文风影子

- 系统 SHALL 以 `chapters.style_shadow`（JSON 文本列，原表加列）存储每章的覆盖行：`{行名: {value, reason}}`；损坏值 SHALL 按空影子处理，不阻塞章读取。
- 系统 SHALL 提供三端点：`GET .../chapters/{ref}/style-shadow/baseline`（全书六行基线（含 locked/容差/画像/置信度）＋本章影子现状）、`PUT .../style-shadow`（专用小端点：`{rows}` 形状清洗——非对象行与非对象 rows 丢弃、值与理由全空白行丢弃、维度名与值字符串化保留原样（不脱空格）、响应回读清洗结果）、`POST .../style-shadow/suggest`（AI 建议：读基线＋本章章纲，产出行级建议并记账，不落库）。
- PUT SHALL NOT 挂 AI 门控——**免费档可写影子（2026-09-17 拍板定案：手工覆盖行与全书文风三区同权，非「现状锁定」）**；suggest SHALL 挂 PRO 与本书模型双门控（与全站 AI 端点同口径），未蒸馏基线时 SHALL 返回 409（含「蒸馏」出口文案），模型未就绪（调用未发生）SHALL NOT 记账。
- suggest 产物清洗 SHALL 按六行白名单过滤：非白名单行、空值行丢弃；理由 SHALL 截断至 200 字；非法 JSON/非列表 SHALL 返回空建议。
- 影子行 SHALL 随章档案导出/导入（chapter-data 侧同步登记）；SHALL NOT 影响全书基线。

#### Scenario: 写入并回读影子
- **WHEN** 作者对某章 PUT 影子行（如句法覆盖）
- **THEN** 响应与后续 GET baseline 均返回该清洗后的影子行

#### Scenario: 免费档可写影子（拍板定案）
- **WHEN** 免费档用户经工作台手工添加覆盖行
- **THEN** PUT 影子端点放行并落库（随后 GET baseline 可见），不收会员门控

#### Scenario: 脏形状被清洗
- **WHEN** PUT 的 rows 含非对象行、全空白行
- **THEN** 这些行被丢弃，其余行按字符串化原样保留

#### Scenario: 未蒸馏时拒绝建议
- **WHEN** 本书 confidence=0（未蒸馏）时发起 AI 建议
- **THEN** 返回 409 并提示先完成蒸馏；无模型调用

#### Scenario: 建议白名单清洗
- **WHEN** AI 建议含六行之外的维度或空取值
- **THEN** 这些条目被丢弃，理由超长截断至 200 字
