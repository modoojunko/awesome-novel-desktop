## MODIFIED Requirements

### Requirement: S端 下发用户权益快照

- check-auth 成功（code 0）响应 SHALL 包含可选字段 `entitlement: {v, features, limits}`；`v` 恒为 1。
- `features` SHALL 为该用户当前档位在档位目录中配置的功能 key 数组；档位行无配置、列缺失或 JSON 损坏时，SHALL 回退到服务端内置默认表（按档位键），两者皆无时 SHALL 下发免费基线（空 features + `limits.max_projects=1`）。
- **默认表与 DB 行 SHALL 覆盖四档**：free（空）、standard（流程/评估/设定/文风 key ＋ max_projects=3）、pro（＋正文/提示词 key ＋不限）、max（pro 全量＋ai-plot＋ai-detect）；**trial 行=pro 行减 ai-plot/ai-detect**（试用同 PRO 不含 MAX 件——原 trial 行含 ai-detect 的配置移除）。
- `limits.max_projects` SHALL 为数字或 null（null=不限）。
- 快照计算 SHALL 继承现有权益合并语义（跳过已收回/冻结的权益记录；排队中记录按现有合并行为参与）。
- 响应 SHALL 附带档位目录投影（见 billing/tier-catalog）。

#### Scenario: PRO 用户收到会员权益

- WHEN check-auth 返回 code 0 且用户有效档位为 pro、档位目录已配置 pro 行
- THEN `data.entitlement.features` 非空（含 AI 能力 key）且 `limits.max_projects` 为 null

#### Scenario: 标准用户收到标准权益

- WHEN check-auth 返回 code 0 且用户有效档位为 standard
- THEN `data.entitlement.features` 含 ai-plan/chapter-review/settings-ai-fields/style-quant/outline-advanced-fields 且 `limits.max_projects` 为 3，不含 ai-generate/ai-plot/ai-detect

#### Scenario: 试用不含 MAX 件

- WHEN trial 用户 check-auth 成功
- THEN features 同 pro 行但不含 ai-plot 与 ai-detect

#### Scenario: 档位无配置回退默认表

- WHEN 用户有效档位在档位目录中无 entitlement 配置
- THEN 服务端按内置默认表下发该档位的标准权益；默认表亦无该档位时下发免费基线

#### Scenario: 免费用户收到免费基线

- WHEN 用户无任何有效权益记录
- THEN `data.entitlement.features` 为空数组且 `limits.max_projects` 为 1

### Requirement: C端 快照驱动判定

- 存在完整快照（features 与 limits.max_projects 齐备）时，会员判定与建书上限 SHALL 由快照自证：`is_member = features 非空或 max_projects 不限`；`project_limit = limits.max_projects`。
- 无快照时 SHALL 按档位目录缓存兜底（目录行合成 features/limits；目录亦无时按已知档兜底名单，须含 standard/trial/pro/max 与历史档位名）；名单内为会员，否则免费 1 本。
- 过期与注销撤销期判定 SHALL 先于快照消费，命中的 SHALL 只获得免费基线。
- trial 无到期数据在生产环境 SHALL 按免费基线处理；开发/测试环境可通过环境变量保留旧宽限。
- verify 响应（前端上下文数据源）SHALL 附带 `entitlement`（快照原文，无快照时省略）与 `entitlement_degraded`（bool，缺省 false）。
- 快照异常降级 SHALL 取保守方向（按档位标准表收紧），误伤靠 60 秒重同步自愈；SHALL NOT 因降级放大权益。

#### Scenario: verify 响应携带快照与降级标志

- WHEN 本地快照完整
- THEN verify 响应含 entitlement 原文且 entitlement_degraded 为 false；快照经兜底供给时 entitlement_degraded 为 true

#### Scenario: PRO 完整快照解锁全部

- WHEN 本地快照 features 非空且 max_projects 为 null、未过期
- THEN is_member 为 true 且 project_limit 为 None（建书不限）

#### Scenario: 无快照档位兜底

- WHEN 本地无快照且 tier 为 "pro"（老 S端 未下发）
- THEN 判定为会员，project_limit 为 None

#### Scenario: 无快照 standard 按目录兜底

- WHEN 本地无快照、tier 为 "standard"、档位目录缓存含 standard 行
- THEN 判定为会员（features 按目录行合成），project_limit 为 3

#### Scenario: 过期先于快照

- WHEN expires_at 已过且快照仍为会员内容
- THEN 判定为免费基线（is_member=false、project_limit=1）

#### Scenario: trial 无到期生产收紧

- WHEN tier 为 trial、expires_at 为空、且非开发/测试环境变量
- THEN 判定为免费基线

### Requirement: 快照异常三段式

- 快照存在但字段不全时，C端 SHALL 先触发一次重同步；同步成功 SHALL 采用新快照。重同步 SHALL 带 60 秒节流（连续命中降级分支不逐请求打 S端；design 决策 5）。
- 重同步不可得（离线/仍缺）时 SHALL 按**档位目录缓存行**合成该档位标准权益（目录缓存的机制与单源见 tier-catalog）；目录缓存亦无时方可用已知档兜底常量（与档位标准表同源的镜像），并同时置降级标志驱动界面提示。降级方向 SHALL 保守（收紧不放权）。
- 降级提示 SHALL 包含可复制的问题详情（缺失字段、档位、抓取时间）与可点击的联系客服出口。
- 未知功能 key SHALL 被忽略，SHALL NOT 引发错误。

#### Scenario: 本地快照缺失字段重同步恢复

- WHEN 本地快照缺 max_projects 且重同步成功
- THEN 采用重同步后的完整快照，无降级标志

#### Scenario: 重同步不可得走档位标准兜底

- WHEN 快照缺字段且设备离线
- THEN 按档位目录缓存行合成当前档位标准配置判定（目录亦无时用已知档兜底常量），置降级标志，界面出现含问题详情与客服出口的提示条

#### Scenario: 未知 key 忽略

- WHEN 快照 features 含 C端 未实现的 key
- THEN 该 key 视为未开通，不报错
