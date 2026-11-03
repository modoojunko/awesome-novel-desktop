## MODIFIED Requirements

### Requirement: 基线只读层与整层替换

官方基线知识 SHALL 存于只读层（kb_baseline_entries）：基线包同步 SHALL 以整层事务替换完成
更新（清旧插新＋记 pack_version），SHALL NOT 对其做单条修改。条目 SHALL 携带固定 src_key
（baseline:<题材>:<slug>）与包版本号。分发包 SHALL 先过与 C 端同口径硬闸自检（单行、无
结构标记、无块首字样、撞句 <8 字）方可发布；分发 SHALL NOT 加密、SHALL NOT 设档位门。

同步 SHALL 向前兼容：本端不认识的条目（新概念、新适用维度等）SHALL 只跳过该条，SHALL NOT
因存在不识别条目而拒收整包；包级与条目级新增字段 SHALL 可被忽略而不影响解析。仅当整包
一条都不可识别时，同步 SHALL 保持旧层（SHALL NOT 落空层）。

格式代 SHALL **以引入它的客户端版本表达**（manifest.format_client，如 `0.45.0`），
SHALL NOT 维护与客户端版本脱节的独立编号；manifest 双写的整数 `format_version` 仅为
只认整数的老客户端提供等价读法（`0.45.0` ⇔ 1），SHALL 由映射表派生而非手工填写。
本端不认识的格式代 SHALL 静默跳过并保持旧层。`min_client_version` SHALL 仅用于产品级
要求，SHALL NOT 作为内容追加的默认门槛。

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
