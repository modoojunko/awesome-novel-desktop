# knowledge-baseline Specification

## Purpose
官方精选全题材基线知识包：只读 lower 层（整层替换同步）、用户层写时复制覆盖（隐藏/副本）、
以及写法块与知识库页的 merged 取数口径。

## Requirements

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
### Requirement: 用户层覆盖（写时复制）

作家对基线条目的「修改」SHALL 以写时复制实现：在用户层物化一份私有副本（覆盖记录），
merged view 以副本遮蔽原件，基线原件 SHALL NOT 发生任何变化。「隐藏」SHALL 以白名单外
记录（whiteout）实现。作家 SHALL 能随时「恢复默认」（删除覆盖记录，原件重新透出）；
官方发布同条目的新版时，用户副本 SHALL 继续生效并可提示「官方有新版」。

#### Scenario: 修改基线条目实为存副本

- **WHEN** 作家修改一条基线知识的文本
- **THEN** 用户层新增该条目的覆盖副本，基线层原件不变；写法块与知识库页此后呈现副本内容

#### Scenario: 隐藏与恢复

- **WHEN** 作家隐藏一条基线知识，随后选择「恢复默认」
- **THEN** 隐藏期间写法块与默认视图不含该条；恢复后原件重新透出，基线层全程未变

#### Scenario: 基线包升级不覆盖用户副本

- **WHEN** 基线包更新且某条目存在用户覆盖副本
- **THEN** 副本继续遮蔽新版原件；条目呈现「官方有新版」提示，作家可主动恢复官方版

### Requirement: merged 视图与消费

写法块选择器与知识库页 SHALL 消费 merged 视图：基线层（排除隐藏、套用覆盖）∪ 用户自有
条目，来源标签「官方精选」随基线层呈现。同步 SHALL 在启动补偿点静默执行，SHALL NOT 弹窗；
失败 SHALL 进知识库页可重试状态，SHALL NOT 阻断写法块主链（未就绪＝写法块不出现）。重复
同步 SHALL 幂等。

#### Scenario: 未同步完成不阻断

- **WHEN** 基线层尚未就绪（首装未同步/同步失败）
- **THEN** 写法块不出现、知识库其余功能照常，状态行可重试；不产生错误弹窗

### Requirement: 更新探测与触达

用户已同步某版官方知识后，官方发布了新版本时，用户**无需重启 app** 即可在知识库页
获知有更新，并可一键更新；层缺失时登录/校验成功自动补装。

#### Scenario: 探测端点同版
- **WHEN** GET /api/kb/baseline/probe 且 CDN latest 版本与本地已装版本相同
- **THEN** 返回 `{installed: N, latest: N, update_available: false}`

#### Scenario: 探测端点发现新版
- **WHEN** CDN latest 版本号与本地已装版本不同
- **THEN** 返回 `{installed: N, latest: M, update_available: true}`

#### Scenario: 探测端点失败不打扰
- **WHEN** CDN 不可达或 latest 验签失败
- **THEN** 返回 `{update_available: false, reason: "<原因>"}`，不抛错、不触发同步

#### Scenario: 层缺失时登录/校验钩子补装
- **WHEN** 登录或 check-auth 成功且本地从未同步过基线（或层为空）
- **THEN** 后台静默触发一次同步，失败不阻塞登录、下次钩子再试

#### Scenario: 已装用户钩子零外呼
- **WHEN** 登录或 check-auth 成功且本地已有基线版本且层非空
- **THEN** 不发起任何网络请求（纯本地早退）

#### Scenario: 知识库页自动弹更新窗
- **WHEN** 知识库页挂载探测到 update_available 且该 CDN 版本未被用户「暂不更新」锚压制
- **THEN** 自动弹出更新窗：显示「当前 vN → 最新 vM」＋「立即更新」「暂不更新」两个动作

#### Scenario: 暂不更新同版不重弹
- **WHEN** 用户点了「暂不更新」后再次进入知识库页且 CDN 仍为同一版本
- **THEN** 不再自动弹窗；CDN 版本号变化后恢复自动弹

#### Scenario: 立即更新落层
- **WHEN** 用户在弹窗点「立即更新」
- **THEN** 调用同步端点（幂等），完成后本地基线层为新版、提示「官方知识已更新到 vM」；
  失败则提示「更新没有完成，稍后可再试」且可重试

#### Scenario: 手动检查入口
- **WHEN** 用户点击知识库页头部「官方知识 vN」入口
- **THEN** 打开手动弹窗：显示当前版本；有新版时提供「立即更新」，无新版时显示已是最新

#### Scenario: 测试闸不受影响
- **WHEN** 环境变量 KB_BASELINE_SYNC=0（测试/诊断态）
- **THEN** 补装钩子不发起同步；既有启动同步闸语义不变
