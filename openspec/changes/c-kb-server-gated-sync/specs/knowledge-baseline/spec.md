## MODIFIED Requirements

### Requirement: 基线只读层与整层替换

官方基线知识 SHALL 存于只读层（kb_baseline_entries）。基线包同步 SHALL **按题材**事务
替换：只删除并重插该题材的行（含对应标签），其他题材的行与用户层（自有条目/覆盖记录）
SHALL 零变化；条目 SHALL 携带固定 src_key（baseline:<题材>:<slug>）与包版本号。

分发包 SHALL 经 S 端 `POST /api/kb/sign` 换腾讯云 COS 私有桶的短时签名 URL 获取；
SHALL NOT 从公开静态托管/CDN 下载、SHALL NOT 在安装包内置；获取 SHALL 要求登录与档位
（`baseline_genre` 每日题材配额：free/none 2、standard 5、pro 20、max 50，trial＝pro；
pointer/manifest 探测免费）。未登录/档位不含/额度用完/无该题材 SHALL 以稳定原因返回，
客户端 SHALL 保持旧层并按原因提示；同一用户同 version+path 的重试不重复扣额度。

同步 SHALL 向前兼容：本端不认识的条目（新概念、新适用维度等）SHALL 沿用该题材旧层原文，
SHALL NOT 拒收整个题材文件，SHALL NOT 把「本端读不懂」当作「官方下架」。官方确实移除的
条目（该题材文件里无该 src_key）SHALL 按移除处理。仅当该题材文件一条都不可识别时，
同步 SHALL 保持该题材旧层（SHALL NOT 落空层）。同步结果 SHALL 透出
accepted/skipped/carried。

客户端 SHALL 记录按题材的已同步状态（version/sha256/path/entries/synced_at），并按题材
高水位拒绝降级（release version 低于本地该题材 version → older_than_installed，旧层不动）。

基线包 SHALL 只有两个版本概念：内容包 `version` 与 `format_client`；SHALL NOT 引入独立
格式编号或 `min_client_version`。本端不认识的 `format_client` SHALL 静默跳过并保持旧层；
缺省该字段的历史包 SHALL 视为第一代照收。

撤回恢复：`latest.json` 的 `resume_baseline=true` 是显式放行；只有带该标记才清
`kb_baseline_retired`。清标记后 SHALL NOT 自动下载题材，仍需用户选题材。

**失败原因细分（代理环境）**：fake-ip 代理环境下取不到签名包时，失败状态 SHALL 记
`proxy_fake_ip`（与普通网络失败可区分）；弹窗 SHALL 呈现代理指路文案（关闭 TUN 模式或将
本站域名加入代理白名单），SHALL NOT 出现内部术语。

#### Scenario: 按题材替换只动该题材

- **WHEN** 用户同步「玄幻」题材完成
- **THEN** 玄幻只读层为新版；「都市」等其他题材行、用户自有条目与覆盖记录零变化

#### Scenario: 探测不下载

- **WHEN** 启动/登录/周期复查执行
- **THEN** 只做 pointer+manifest 免费探测并刷新可用题材/配额；不请求任何题材数据对象、
  不扣每日题材额度

#### Scenario: 未登录/档位/额度拒绝

- **WHEN** 用户未登录、档位不含官方知识库、或今日题材次数用完请求同步某题材
- **THEN** 分别返回 401/403/429 的稳定原因；旧层保持，界面按原因提示（用完/套餐不含/未登录）

#### Scenario: 同内容不重复扣额度

- **WHEN** 某题材在 release 中的 sha256 与本地已同步一致
- **THEN** 同步返回 current，不请求 genre ticket、不扣额度

#### Scenario: 按题材高水位

- **WHEN** release 的 version 低于本地该题材已同步 version
- **THEN** 返回 older_than_installed，该题材旧层与用户覆盖不动

#### Scenario: 本端读不懂的条目沿用旧层

- **WHEN** 新版该题材包含本端不认识的条目（新概念/新维度）
- **THEN** 该条沿用旧层原文计入 carried，其余条目照常落层，不缩水、不误提升用户副本

#### Scenario: 整题材都读不懂

- **WHEN** 该题材文件所有条目均无法被本端识别
- **THEN** 该题材同步判失败并保持旧层（不落空层），状态可重试

#### Scenario: 坏哈希保旧层

- **WHEN** 下载体 sha256/size 与签名 manifest 声明不符
- **THEN** 同步失败，该题材旧层与用户覆盖不动

#### Scenario: 撤回恢复

- **WHEN** 本地 `kb_baseline_retired=1` 且 `latest.json` 带 `resume_baseline=true`
- **THEN** 清撤回标记并展示题材清单；不自动下载，等用户选题材

#### Scenario: 代理环境可辨可指引

- **WHEN** TUN fake-ip 环境签名 URL 下载失败
- **THEN** 失败原因 `proxy_fake_ip`，弹窗给代理指路文案与重试出口，不出现内部术语

#### Scenario: 同步整层替换

- **WHEN** 某题材同步完成
- **THEN** 该题材只读层与新包一致；其他题材行与用户层零变化（按题材替换取代整层替换）

#### Scenario: 老客户端吃新包

- **WHEN** 新版某题材文件包含本端尚不支持的条目
- **THEN** 同步成功并落层本端支持的子集，未识别条目沿用旧层/计入 skipped，其余照常可用

#### Scenario: 整包代际不兼容

- **WHEN** 某题材文件所有条目均无法被本端识别
- **THEN** 该题材同步判失败并保持旧层（不落空层），状态可重试

#### Scenario: 发布前硬闸

- **WHEN** 内容仓条目未过硬闸自检（结构标记/撞句/槽位错/审计侧车）
- **THEN** 打包发布被 CI 拒绝

#### Scenario: 代理环境下同步失败可辨可指引

- **WHEN** 用户处于 TUN fake-ip 代理环境，签名 URL 下载失败
- **THEN** 同步判失败且保持旧层，失败原因为 `proxy_fake_ip`；弹窗呈现代理指路文案（无内部术语）与重试出口

### Requirement: merged 视图与消费

写法块选择器与知识库页 SHALL 消费 merged 视图：基线层（排除隐藏、套用覆盖）∪ 用户自有
条目，来源标签「官方精选」随基线层呈现。启动补偿/登录钩子/会话内周期复查 SHALL 只做
**免费探测**（pointer+manifest），SHALL NOT 自动下载题材、SHALL NOT 静默扣额度，SHALL NOT
弹窗；失败 SHALL 进知识库页可重试状态，SHALL NOT 阻断写法块主链（该题材未同步＝写法块
不出现该题材官方条目）。用户手动同步单题材 SHALL 幂等；已同步同内容 SHALL 零写。

#### Scenario: 未同步完成不阻断

- **WHEN** 书的题材尚未同步（首装/失败/撤回）
- **THEN** 写法块不出现该题材官方条目、知识库其余功能照常；知识库页/写作工作台给
  「去同步」入口，不产生错误弹窗

#### Scenario: 周期复查只探测

- **WHEN** 应用常驻且距上次探测过一个周期
- **THEN** 只刷新 pointer/manifest 与配额，不下载题材、不替换层；用户下次打开知识库页
  看到可更新题材

#### Scenario: 手动同步单题材幂等

- **WHEN** 用户对同一题材重复点同步且内容未变
- **THEN** 第二次返回 current，零写、零 ticket

#### Scenario: 周期复查静默应用新版

- **WHEN** 应用常驻且距上次探测过一个周期
- **THEN** 周期复查只刷新 pointer/manifest 与可用题材/配额，不替换层、不弹窗；用户手动选题材同步后才落层

### Requirement: 更新探测与触达

知识库页 SHALL 通过 `GET /api/kb/baseline/probe`（免费）获知：已同步版本、release latest、
每个题材的 manifest 元数据与本机已同步状态、今日剩余额度、`resume_baseline`。
`update_available` SHALL 表示存在 sha256 不同或未同步的题材；探测 SHALL NOT 下载题材、
SHALL NOT 扣额度；失败 SHALL 返回稳定 reason，不抛错。

界面 SHALL 以**题材清单**触达：每行显示已同步/可更新/未同步与「同步/重新同步」动作；
顶部显示今日还可同步的题材数（用完时说明明天恢复）。每次点击只同步一个题材，S 端扣 1 次。
同步结果 SHALL 诚实呈现：429 说明今日次数用完、403 说明套餐不含、401 说明需登录、
404 说明该版本无此题材、405/older 说明本机已更新不降级；失败给重试出口；SHALL NOT 把
skipped 谎报成功。update 模式关闭 SHALL 记 release 版本锚（同版不自动重弹）。

写作工作台 SHALL 在书的题材未同步/可更新时给非阻断提示「去同步本题材」（携该题材开
弹窗）；SHALL NOT 静默下载/扣额度。

#### Scenario: 探测信封

- **WHEN** GET /api/kb/baseline/probe（已登录）
- **THEN** 返回 `{installed, latest, update_available, genres, installed_genres, updates, quota, resume, reason?}`；
  `genres` 缺失时前端显示暂时拿不到清单

#### Scenario: 按题材可更新

- **WHEN** release 中某题材 sha256 与本地不同或本地没有
- **THEN** `updates` 含该题材，清单行显示「可更新/未同步」并提供同步按钮

#### Scenario: 额度用完

- **WHEN** 今日 used ≥ limit
- **THEN** 清单按钮禁用并显示「今天的题材同步次数用完了（N/N），明天恢复」；429 时同样
  提示且不落成功态

#### Scenario: 套餐不含

- **WHEN** S 端 `entitlement.kb.enabled=false`
- **THEN** 同步返回 403；界面说明当前套餐不包含官方知识库，不弹成功

#### Scenario: 写作提示

- **WHEN** 打开某书写作工作台且该书题材未同步
- **THEN** appbar 出现「去同步本题材」；点击打开题材清单并高亮该书题材；不静默下载

#### Scenario: 暂不同步锚

- **WHEN** 用户关闭 update 模式弹窗
- **THEN** 记 release 版本锚；同版本再进知识库页不自动弹，版本变化后恢复

#### Scenario: 撤回恢复

- **WHEN** 探测到 `resume=true`
- **THEN** 清单顶部说明官方知识已恢复；用户可逐题材同步，仍不自动下载

#### Scenario: 探测端点同版

- **WHEN** GET /api/kb/baseline/probe 且 release latest 与本地已同步内容一致
- **THEN** 返回 `update_available: false`，`genres/installed_genres/quota` 照常可读

#### Scenario: 探测端点发现新版

- **WHEN** release 中某题材 sha256 与本地不同或本地未同步
- **THEN** 返回 `update_available: true`，`updates` 含该题材

#### Scenario: 探测端点失败不打扰

- **WHEN** S 端不可达或 pointer/manifest 验签失败
- **THEN** 返回 `{update_available: false, reason: "<原因>"}`，不抛错、不触发题材下载

#### Scenario: 层缺失时登录/校验钩子补装

- **WHEN** 登录或 check-auth 成功且本地从未同步过基线（或该题材层为空）
- **THEN** 后台只做 pointer/manifest 免费探测，不自动下载题材、不扣额度；失败不阻塞登录

#### Scenario: 已装用户钩子零外呼

- **WHEN** 登录或 check-auth 成功且本地已有题材基线
- **THEN** 只做免费探测（不发 genre ticket、不扣额度）；不自动替换层

#### Scenario: 知识库页自动弹更新窗

- **WHEN** 知识库页挂载探测到 update_available 且该 release 版本未被「暂不更新」锚压制
- **THEN** 自动弹出题材清单（每行已同步/可更新/未同步＋同步按钮＋今日剩余额度），不是单版本确认

#### Scenario: 暂不更新同版不重弹

- **WHEN** 用户点了「暂不同步」后再次进入知识库页且 release 仍为同一版本
- **THEN** 不再自动弹窗；版本号变化后恢复自动弹

#### Scenario: 立即更新落层

- **WHEN** 用户在清单里点某题材的「同步」
- **THEN** 只同步该题材（S 端扣 1 次/天），完成后该题材层为新版；其他题材与用户覆盖零变化；失败可重试

#### Scenario: 手动检查入口

- **WHEN** 用户点击知识库页头部「官方知识 vN」入口
- **THEN** 打开题材清单（携页内探测快照）；有可更新/未同步题材时逐行提供同步；无则说明已是最新

#### Scenario: 测试闸不受影响

- **WHEN** 环境变量 KB_BASELINE_SYNC=0（测试/诊断态）
- **THEN** 登录钩子与周期复查都不发起探测/同步；既有启动同步闸语义不变

#### Scenario: 周期复查发现新版自动落层

- **WHEN** 应用常驻且周期复查发现 release 高于本地某题材
- **THEN** 只刷新可用状态并提示该题材可更新，不自动落层；用户手动同步后才替换该题材（原「自动整层落层」由按题材手动同步取代）

#### Scenario: 周期复查失败缩短重试

- **WHEN** 某次周期复查探测失败（S 端不可达/验签失败/网络抖动）
- **THEN** 保持旧层，并在分钟级间隔后重试（短于常规周期）；重试成功或跳过后回到常规周期

#### Scenario: 同步跳过不谎报成功

- **WHEN** 用户点某题材同步，S 端返回 skipped（额度用完/档位不含/未登录/撤回/格式代际/版本已更新）
- **THEN** 界面不显示成功态、不 toast 成功；按原因给 info 说明（用完/套餐/登录/暂未开放/新版客户端/已是最新）

#### Scenario: 跳过的版本不再反复弹窗

- **WHEN** 某 release 版本被用户「暂不同步」或跳过
- **THEN** 不再自动弹出同一版本的清单；版本号变化后恢复自动弹
