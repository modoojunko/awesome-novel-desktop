## MODIFIED Requirements

### Requirement: 思考参数可配

每个 API 配置 SHALL 携带思考参数二元组并落库：思考开关 `thinking_enabled`（布尔，默认
关）与思考强度 `thinking_effort`（`low`/`high`/`max`，默认 `low`——GLM-5.3 契约三档
`reasoning_effort`，整条链按「省 token 省延迟」取向取最省一档）。生成调用与连接探针
SHALL 按该配置下发思考参数：关＝`thinking:{type:disabled}`（与既有行为等价，存量配置
零变化）；开＝`thinking:{type:enabled}`＋顶层 `reasoning_effort`（openai 格式随
extra_body，anthropic 格式 thinking 走形参、effort 随 extra_body 透传）。effort SHALL
NOT 随「关」下发。「添加/编辑 API Key」弹窗 SHALL 提供两控件：思考模式（开启/关闭）与
思考强度（低 low/高 high/深 max，关闭时灰置且保留已选值），编辑态 SHALL 回读已存值。

判定/短答复类调用（`_judge_chat` 漏斗，volume-plan-ai 口径）SHALL 恒以显式关思考传参
压过配置；调用方显式传 `thinking` 时——disabled 形态 SHALL NOT 搭车配置强度；enabled
且未自带 effort 时 SHALL 按该配置的 `thinking_effort` 下发（GLM 嵌套进 `thinking{}`，
其余 vendor 随顶层 `reasoning_effort`；Gemini/opencode-go-claude 按既有 vendor 映射），
自带 effort 时以显式为准。端点打回思考参数时
SHALL 去参（`thinking`＋`reasoning_effort`）重试一次并记住该 base 不再主动发——判据
SHALL 含中文「思考」与 `reasoning`/`effort` 字样（GLM-5.3 拒关思考的报错是纯中文，仅
匹配英文 `thinking` 会漏判）；连接探针的触发 SHALL NOT 依赖文案措辞（带思考参数的 400
一律去参重试），去参重试时 SHALL 同步放大输出预算（强制思考模型会把预算花在推理上，
短预算只够思考、正文为空）。

#### Scenario: 配置 GLM-5.3 开思考 low

- **WHEN** 配置 `thinking_enabled=true`、`thinking_effort="low"` 后发起生成或连接测试
- **THEN** 请求携带 `thinking:{type:enabled}`＋`reasoning_effort:"low"`，GLM-5.3 正常回复

#### Scenario: 默认关思考与存量行为等价

- **WHEN** 配置不传思考参数（旧前端）或保持默认
- **THEN** 请求仅携带 `thinking:{type:disabled}`、无 `reasoning_effort`，落库回读为关/low

#### Scenario: GLM-5.3 关思考被拒自动去参重试

- **WHEN** 强制思考模型（GLM-5.3 系）对携带 `thinking:{type:disabled}` 的请求回 400
  （报错为纯中文「该模型始终思考，不支持关闭思考；请使用 low、high 或 max」）
- **THEN** 探针与生成调用均自动去掉思考参数重试一次并成功，连接测试判「连接正常」；
  重试请求 SHALL NOT 携带 `thinking`/`reasoning_effort`，且输出预算放大

#### Scenario: 判定类调用恒关思考

- **WHEN** 配置开思考后触发 JSON 判定/短答复类调用（卷规划等 `_judge_chat` 路径）
- **THEN** 请求显式携带 `thinking:{type:disabled}` 且不携带 `reasoning_effort`，
  判定类延迟与预算口径不变

#### Scenario: 助手显式开思考按配置强度

- **WHEN** 助手底栏开「深度思考」（显式 `thinking:{type:enabled}`），配置 `thinking_effort="low"`
- **THEN** 请求携带 `thinking:{type:enabled}`＋`reasoning_effort:"low"`（GLM 嵌套），
  不再吃供应商默认 high；显式自带 effort 时以显式为准

#### Scenario: 表单两控件与编辑回读

- **WHEN** 在「添加 API Key」弹窗开启思考并选「深 max」后保存，再打开「编辑配置」
- **THEN** 保存的配置携带 `thinking_enabled=true`、`thinking_effort="max"`；编辑弹窗
  思考模式呈「开启」、强度呈「高/深」对应档位；关闭思考时强度控件灰置但保留已选值

#### Scenario: 备份与升级带回

- **WHEN** 导出配置备份包并在他处导入，或经版本升级迁入链带回旧库
- **THEN** 思考参数随行携带；旧包/旧库缺键时按关/low 兜底（与旧版运行行为等价）
