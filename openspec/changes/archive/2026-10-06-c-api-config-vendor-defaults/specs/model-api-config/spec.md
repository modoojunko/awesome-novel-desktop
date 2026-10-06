# model-api-config Delta — 供应商默认值预填

## ADDED Requirements

### Requirement: 供应商默认值预填

系统 SHALL 提供供应商默认值登记表（键＝供应商×接口格式，值＝官方 Base URL＋默认模型名称＋备选模型候选），作为创建表单预填的单一数据源。登记纪律＝有据才登记（实测或厂商官方文档），无据字段 SHALL 留空，SHALL NOT 编造；首批全量登记 DeepSeek，其余内置供应商按官方文档核对后登记。

创建模型配置时，用户选中登记表内的供应商（或切换接口格式）后，表单 SHALL 自动填入该「供应商×接口格式」登记的 Base URL 与默认模型名称，用户只需填写 API Key 即可保存；「模型名称」SHALL 为创建表单的一级字段，保存后为该配置模型列表首项。预填字段 SHALL 可编辑。字段为空、或仍等于预填值（用户未手改）时，SHALL 随供应商/格式切换更新为新登记值；用户手改过的字段 SHALL NOT 被覆盖。「OpenAI 兼容」等无登记值的供应商 SHALL NOT 预填（沿用 placeholder 示例域名引导）。编辑已有配置 SHALL NOT 施加预填（沿用已存值）。

#### Scenario: 选 DeepSeek 只填 Key 即可保存
- **WHEN** 用户在添加弹窗选择 DeepSeek 供应商
- **THEN** Base URL 与模型名称自动填为登记默认值，用户填入 API Key 后保存成功，配置的 Base URL 与模型列表即为预填值

#### Scenario: 预填字段可编辑且手改不被覆盖
- **WHEN** 用户把预填的 Base URL 改成自己的地址后切换供应商再切回
- **THEN** 用户改过的 Base URL 保持不变（不被预填值覆盖）；未手改的字段随所选供应商更新为对应登记值

#### Scenario: 无登记值的供应商不预填
- **WHEN** 用户选择「OpenAI 兼容」供应商
- **THEN** Base URL 与模型名称留空（placeholder 引导），不自动填入任何猜测值

#### Scenario: 登记表无据字段留空
- **WHEN** 某供应商的默认模型 id 尚无实测或官方文档依据
- **THEN** 该供应商的模型名称预填值留空由用户自填，SHALL NOT 编造模型 id

## REMOVED Requirements

### Requirement: Base URL 不自动预填
**Reason**: 2026-10-05 用户拍板反转（「创建模型，用户选择了默认的供应商，如 deepseek，就默认帮用户把模型名称，base url 填好，用户只需要填 key」）——「登记表内有据才填、填了可改」比让用户裸填更不易错（内测实锤：用户把控制台网页当 Base URL 填入）。
**Migration**: 由「供应商默认值预填」需求承接：登记纪律（有据才登记）、预填可编辑、手改不覆盖、无登记值不预填、placeholder 随格式给示例域名的行为保留。
