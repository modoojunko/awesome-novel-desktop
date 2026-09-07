# entitlement-sync 变更（Delta）

## ADDED Requirements

### Requirement: S端 下发用户权益快照

- check-auth 成功（code 0）响应 SHALL 包含可选字段 `entitlement: {v, features, limits}`；`v` 恒为 1。
- `features` SHALL 为该用户当前档位在档位目录中配置的功能 key 数组；档位行无配置、列缺失或 JSON 损坏时，SHALL 回退到服务端内置默认表（按档位键），两者皆无时 SHALL 下发免费基线（空 features + `limits.max_projects=1`）。
- `limits.max_projects` SHALL 为数字或 null（null=不限）。
- 快照计算 SHALL 继承现有权益合并语义（跳过已收回/冻结的权益记录；排队中记录按现有合并行为参与）。

#### Scenario: PRO 用户收到会员权益

- WHEN check-auth 返回 code 0 且用户有效档位为 pro、档位目录已配置 pro 行
- THEN `data.entitlement.features` 非空（含 AI 能力 key）且 `limits.max_projects` 为 null

#### Scenario: 档位无配置回退默认表

- WHEN 用户有效档位在档位目录中无 entitlement 配置
- THEN 服务端按内置默认表下发该档位的标准权益；默认表亦无该档位时下发免费基线

#### Scenario: 免费用户收到免费基线

- WHEN 用户无任何有效权益记录
- THEN `data.entitlement.features` 为空数组且 `limits.max_projects` 为 1

### Requirement: C端 权益快照缓存与刷新

- C端 SHALL 在 check-auth 成功时把 `entitlement` 原文与抓取时间写入本地配置；会话失效（code 1）SHALL 连同快照一并清除。
- **刷新是两跳链，路由切换 SHALL 触发完整链**：① 调 C端 `/auth/check-auth`（内部对 S端 静默 check-auth 往返并写本地快照）；② 随后前端刷新 verify 上下文（读本地、更新界面）。只做②不做① SHALL NOT 视为满足本要求（verify 不联网，快照不会更新）。60 秒去抖；SHALL NOT 使用定时轮询。
- S端 不可达（网络错误/冷启动）SHALL 沿用上次快照，SHALL NOT 把会员降级为免费。
- 注销撤销期（code 2）SHALL 置 deletion_pending 标记并按免费基线判定，本地作品不受影响。

#### Scenario: 登录写入快照

- WHEN check-auth 返回 code 0 且携带 entitlement
- THEN 本地配置写入 entitlement 原文与抓取时间

#### Scenario: 路由切换触发完整刷新链

- WHEN 用户 60 秒内首次从书列表进入工作台
- THEN 先调 /auth/check-auth（S端 往返、覆盖本地快照），随后前端 verify 上下文更新；60 秒内重复切换不重复触发

#### Scenario: S端 不可达沿用旧快照

- WHEN 刷新时 S端 超时或返回网络错误
- THEN 本地快照保持不变，既有会员待遇不变

#### Scenario: 会话失效清除快照

- WHEN check-auth 返回 code 1 且本地曾有凭据
- THEN token/username/tier/expires_at/entitlement 一并清除

#### Scenario: 注销撤销期免费基线

- WHEN check-auth 返回 code 2（deletion_pending）
- THEN 判定走免费基线，重新登录/撤销后自动恢复

### Requirement: C端 快照驱动判定

- 存在完整快照（features 与 limits.max_projects 齐备）时，会员判定与建书上限 SHALL 由快照自证：`is_member = features 非空或 max_projects 不限`；`project_limit = limits.max_projects`。
- 无快照时 SHALL 按档位兜底名单判定会员（名单须含 trial/pro/max 与历史档位名）；在名单内为会员不限，否则免费 1 本。
- 过期与注销撤销期判定 SHALL 先于快照消费，命中的 SHALL 只获得免费基线。
- trial 无到期数据在生产环境 SHALL 按免费基线处理；开发/测试环境可通过环境变量保留旧宽限。
- verify 响应（前端上下文数据源）SHALL 附带 `entitlement`（快照原文，无快照时省略）与 `entitlement_degraded`（bool，缺省 false）。

#### Scenario: verify 响应携带快照与降级标志

- WHEN 本地快照完整
- THEN verify 响应含 entitlement 原文且 entitlement_degraded 为 false；快照经兜底供给时 entitlement_degraded 为 true

#### Scenario: PRO 完整快照解锁全部

- WHEN 本地快照 features 非空且 max_projects 为 null、未过期
- THEN is_member 为 true 且 project_limit 为 None（建书不限）

#### Scenario: 无快照档位兜底

- WHEN 本地无快照且 tier 为 "pro"（老 S端 未下发）
- THEN 判定为会员，project_limit 为 None

#### Scenario: 过期先于快照

- WHEN expires_at 已过且快照仍为会员内容
- THEN 判定为免费基线（is_member=false、project_limit=1）

#### Scenario: trial 无到期生产收紧

- WHEN tier 为 trial、expires_at 为空、且非开发/测试环境变量
- THEN 判定为免费基线

### Requirement: 快照异常三段式

- 快照存在但字段不全时，C端 SHALL 先触发一次重同步；同步成功 SHALL 采用新快照。重同步 SHALL 带 60 秒节流（连续命中降级分支不逐请求打 S端；design 决策 5）。
- 重同步不可得（离线/仍缺）时 SHALL 按该档位的标准配置兜底（与 S端 默认表同源的镜像），并同时置降级标志驱动界面提示。
- 降级提示 SHALL 包含可复制的问题详情（缺失字段、档位、抓取时间）与可点击的联系客服出口。
- 未知功能 key SHALL 被忽略，SHALL NOT 引发错误。

#### Scenario: 本地快照缺失字段重同步恢复

- WHEN 本地快照缺 max_projects 且重同步成功
- THEN 采用重同步后的完整快照，无降级标志

#### Scenario: 重同步不可得走档位标准兜底

- WHEN 快照缺字段且设备离线
- THEN 按当前档位的标准配置判定，置降级标志，界面出现含问题详情与客服出口的提示条

#### Scenario: 未知 key 忽略

- WHEN 快照 features 含 C端 未实现的 key
- THEN 该 key 视为未开通，不报错

### Requirement: 契约兼容

- entitlement 字段 SHALL 为纯新增可选字段；旧客户端 SHALL 可忽略之，行为不劣于现状。
- 新客户端遇到无 entitlement 字段的旧服务端 SHALL 走档位兜底判定。

#### Scenario: 旧客户端忽略新字段

- WHEN 未升级的客户端收到携带 entitlement 的 check-auth 响应
- THEN 多余字段被忽略，行为与升级前一致

#### Scenario: 新客户端遇旧服务端

- WHEN 新客户端收到不含 entitlement 的 code 0 响应
- THEN 按档位兜底名单判定，不报错
