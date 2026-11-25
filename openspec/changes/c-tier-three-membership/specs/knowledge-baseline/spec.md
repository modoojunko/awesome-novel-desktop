## ADDED Requirements

### Requirement: 官方基线消费挂 PRO（同步仍系统内部）

- 官方基线包的下载/校验/整层替换 SHALL 保持系统内部能力：分发不加密、同步/探针不直接向作家暴露，SHALL NOT 在同步链路上加会员门。
- 作家侧对官方层的**消费**（官方库查询、官方写法检索、官方知识树/图谱节点、按题材取文风）SHALL 挂 `kb-official`（PRO 起）；标准（免费）入口可见但锁定，点击走 PRO 升级出口。
- 本地层（本书/用户条目/拆书产物）SHALL NOT 受 `kb-official` 影响；标准（免费）照常可用。
- 旧权益快照不含 `kb-official` 时，未过期 PRO/MAX/trial SHALL 隐式放行官方层消费；标准（免费）/过期 SHALL 锁定。

#### Scenario: 标准（免费）官方层锁定

- **WHEN** 标准（免费）用户请求官方库条目或官方知识树
- **THEN** 返回 `feature_required`/`tier_required=pro`，不返回官方内容；本地层请求不受影响

#### Scenario: 旧快照隐式放行

- **WHEN** 未过期 PRO 用户的完整旧快照缺少 `kb-official`
- **THEN** 官方层消费按 PRO 隐式放行；标准（免费）/过期仍锁定

#### Scenario: 同步不挂会员门

- **WHEN** 客户端启动执行官方基线同步/探针
- **THEN** 同步链路正常执行，不因当前档位返回 403；作家侧官方层读取才按 `kb-official` 判定
