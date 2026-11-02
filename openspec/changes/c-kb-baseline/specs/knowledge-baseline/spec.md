## ADDED Requirements

### Requirement: 基线包分发

官方基线知识 SHALL 以版本化数据包经 CDN 分发：包目录含 manifest（版本、条目计数、逐文件 sha256）、entries.jsonl（全量条目）与 tombstones.json（下架清单）；latest.json 薄指针指向当前版本。分发 SHALL NOT 加密、SHALL NOT 设档位门（基线为全档冷启动底座）。条目 SHALL 携带固定 src_key（baseline:<题材>:<slug>），版本迭代 SHALL 只增不覆盖：用户改过/删过/标记过的同 key 条目 SHALL 保持用户状态。包内条目 SHALL 先过与 C 端同口径的硬闸自检（单行、无结构标记、无块首字样、与固定文案及跨条目撞句 <8 字）方可发布。

#### Scenario: 首次同步落库

- **WHEN** 客户端首次启动同步基线包
- **THEN** 按 manifest 校验逐文件哈希后，全部条目以 src_kind="baseline" 幂等写入账号库（缺失 key 插入，已存在 key 跳过），知识库页来源标签显示「官方精选」

#### Scenario: 用户资产优先

- **WHEN** 新版本基线包包含用户已修改或已删除的同 key 条目
- **THEN** 该条目保持用户当前状态不被覆盖；仅用户未触碰的条目按包更新

#### Scenario: 条目下架

- **WHEN** 新版本 tombstones 清单声明某 src_key 下架
- **THEN** 用户未触碰的该条目从账号库移除；用户触碰过的转隐藏（不再进写法块与默认视图，用户可手动清）

### Requirement: 同步触发与状态

基线包同步 SHALL 在启动补偿点静默执行（与既有提示词包同步同点），SHALL NOT 弹窗打断；同步失败 SHALL 进入可重试状态并在知识库页状态行呈现，SHALL NOT 阻断知识库其余功能与写法块主链（未就绪＝写法块不出现，同级降级）。重复同步 SHALL 幂等。

#### Scenario: 同步失败不阻断

- **WHEN** CDN 不可达导致基线同步失败
- **THEN** 知识库页状态行显示可重试，写法块与知识库其余功能照常；下次启动补偿重试
