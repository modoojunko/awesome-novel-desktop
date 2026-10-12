# model-api-config Delta — 保存前连通门禁

## ADDED Requirements

### Requirement: 保存前连通门禁

创建或编辑模型配置 SHALL 在落库前执行连接探测——与「测试连接」同一探测实现、同一判据（判据单源见「按接口格式探测连接」需求，此处不复述）；探测判败 SHALL NOT 落库（含覆盖更新），并 SHALL 在保存入口（弹窗）原位展示探测错误、保持编辑态不关闭。判败＝探测结果非 ok 的**一切**形态（endpoint_mismatch、auth_error、timeout、network_error、rate_limited、unknown 等，枚举不封闭，实现 SHALL 按「非 ok 即拦」而非白名单）。

门禁适用面＝经 `POST/PUT /api-configs` 保存入口的创建与编辑；备份包导入、库迁移回填、朱雀配置 upsert 等非保存入口的建行路径 SHALL 豁免（旧数据恢复/固定端点，不因离线或上游抖动不可用）。创建 SHALL 恒触发；编辑更新 SHALL 仅在连接相关字段（`base_url`、`api_format`、`api_key`）**值与已存值不同**时触发（`api_key` 以非空为变更；仅更新名称或模型列表等非连接字段 SHALL NOT 触发探测）；编辑态 Key 留空（保留当前密钥）时探测 SHALL 使用已存密钥，SHALL NOT 报「API Key 为空」。

落库成功时系统 SHALL 将本次探测结果持久化到该配置的测试结果字段（`last_test_status`/`last_test_error`/`last_tested_at`/`models`，与连接测试同源写库），保存响应 SHALL 携带嵌套探测结果 `probe`（ok/status/models/note），SHALL NOT 与配置对象顶层既有字段（`status`/`models`）撞名；前端据此呈现卡片状态（刷新后经库列回读保持一致），SHALL NOT 在保存成功后再发第二次探测。

#### Scenario: 创建时坏 URL 当场拦下
- **WHEN** 用户在添加弹窗填入网站地址（如 `https://platform.deepseek.com/api_keys`）作为 Base URL 并点「保存并测试连接」
- **THEN** 配置不落库，弹窗保持打开，连接测试结果位原位显示探测错误（说明该地址返回的不是 API 数据/请检查 Base URL），用户修正后可重新保存

#### Scenario: 创建判过才落库
- **WHEN** 用户填入真实 API 端点与有效 Key 并保存
- **THEN** 配置落库且探测结果（状态与模型列表）已持久化到测试结果字段，卡片状态直接呈现「连接正常」且刷新后不回退，且不再发起第二次连接探测

#### Scenario: 编辑改坏 URL 同样被拦
- **WHEN** 用户编辑一条已有配置，把 Base URL 改成错误地址后保存
- **THEN** 本次更新不落库（原配置保持不变），弹窗保持打开并原位显示探测错误

#### Scenario: 编辑仅改名不触发探测
- **WHEN** 编辑保存时连接相关字段值与已存值均相同（如只改名称）
- **THEN** 不执行连接探测，更新正常落库

#### Scenario: 判败即拦全集
- **WHEN** 保存前探测判败为鉴权失败、超时、网络错误、频率限制、unknown 等任一非 ok 形态
- **THEN** 一律不落库，错误文案与「测试连接」同一判据同一文案（不另造第二套说法）

#### Scenario: 编辑 Key 留空用已存密钥
- **WHEN** 用户编辑配置只改 Base URL、API Key 留空（保留当前密钥）后保存
- **THEN** 门禁探测使用已存密钥执行（不报「API Key 为空」），判败不落库、判过照常持久化

## MODIFIED Requirements

### Requirement: 编辑态可改接口格式

编辑已有配置时供应商保持锁定，接口格式 SHALL 允许修改且不弹二次确认；修改后该配置已拉取的模型列表与最近测试结果 SHALL 立即失效，需重新测试——经保存入口保存时，保存前连通门禁以**新格式**完成的探测即为重新测试：探测通过 SHALL 将模型列表与测试状态更新为本次探测结果（SHALL NOT 清空为「未测试」）；探测判败 SHALL NOT 落库，原配置的模型列表与测试状态保持原样。

#### Scenario: 改格式后模型缓存失效
- **WHEN** 用户编辑一条已有模型列表的配置并切换接口格式后保存
- **THEN** 保存门禁以新接口格式重测：探测通过时该配置的模型列表与测试状态更新为本次探测结果；探测判败时本次更新不落库、原配置不变
