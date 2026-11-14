## MODIFIED Requirements

### Requirement: 基线只读层与整层替换

官方基线知识 SHALL 存于只读层（kb_baseline_entries）：基线包同步 SHALL 以整层事务替换完成
更新（清旧插新＋记 pack_version），SHALL NOT 对其做单条修改。条目 SHALL 携带固定 src_key
（baseline:<题材>:<slug>）与包版本号。分发包 SHALL 先过与 C 端同口径硬闸自检（单行、无
结构标记、无块首字样、撞句 <8 字）方可发布；分发 SHALL NOT 加密、SHALL NOT 设档位门。

同步 SHALL 向前兼容：本端不认识的条目（新概念、新适用维度等）SHALL 沿用旧层原文落层，
SHALL NOT 因存在不识别条目而拒收整包；SHALL NOT 把「本端读不懂」当作「官方下架」（否则
用户副本会被误提升为自有条目）。官方确实移除的条目（整包里无该 src_key）SHALL 按移除处理。
包级与条目级新增字段 SHALL 可被忽略而不影响解析。仅当整包一条都不可识别时，同步 SHALL
保持旧层（SHALL NOT 落空层）。同步结果 SHALL 透出 accepted/skipped/carried，便于发现两端
判据漂移。

基线包 SHALL 只有两个版本概念：内容包 `version`（第几版，单调递增、目录不可变）与
`format_client`（这份内容按哪一代客户端的结构写，如 `0.45.0`）。SHALL NOT 引入独立格式
编号或 `min_client_version` 等与客户端版本重复的字段——格式随客户端版本走，多一套号会漂。
本端不认识的 `format_client` SHALL 静默跳过并保持旧层；缺省该字段的历史包 SHALL 视为
第一代照收。新增不兼容代际 SHALL 在本端与内容仓同批登记。

**失败原因细分（代理环境）**：fake-ip 代理环境下（可信域解析结果全部落在 fake-ip 保留段）
同步取不到官方包时，失败状态 SHALL 记代理环境专用原因 `proxy_fake_ip`（与既有失败原因
可区分）；官方知识更新弹窗对该原因 SHALL 呈现代理指路文案（关闭代理软件的 TUN 模式，
或将本站域名加入代理软件的白名单后重试），并保留既有重试出口；文案 SHALL NOT 出现内部
术语（fake-ip/198.18/DNS 等）；其余失败文案语义不变。

#### Scenario: 同步整层替换

- **WHEN** 基线包新版本同步完成
- **THEN** 只读层内容与新包中本端支持的条目一致，用户层（自有条目与覆盖记录）零变化

#### Scenario: 老客户端吃新包

- **WHEN** 新版基线包含本端尚不支持的条目（如新概念或新适用维度）
- **THEN** 同步成功并落层本端支持的子集，未识别条目跳过并计入 skipped，其余条目照常可用

#### Scenario: 整包代际不兼容

- **WHEN** 新包所有条目均无法被本端识别
- **THEN** 同步判失败并保持旧层（不落空层），状态可重试

#### Scenario: 发布前硬闸

- **WHEN** 内容仓条目未过硬闸自检（结构标记/撞句/槽位错）
- **THEN** 打包发布被 CI 拒绝

#### Scenario: 代理环境下同步失败可辨可指引

- **WHEN** 用户处于 TUN fake-ip 代理环境，官方知识同步取不到 latest（代理已接管解析但节点不通官方域）
- **THEN** 同步判失败且保持旧层（不落空层），失败原因为 `proxy_fake_ip`；弹窗呈现代理指路文案（无内部术语）与既有重试出口
