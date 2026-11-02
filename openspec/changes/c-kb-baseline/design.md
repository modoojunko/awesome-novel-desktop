# c-kb-baseline · Design（v2，双角色评审后重写）

设计核心＝**overlay 双层存储**（boss 定案）：官方基线＝只读 lower 层（不可变、整层替换式
更新），用户知识＝可写 upper 层；一切「修改/删除基线」都是 upper 层写时复制（CoW），
基线原件永不改变。本版吸收后端/架构师双评审 30+ 发现，四项 P0 全部闭环进设计。

## D0 关键裁定（评审 P0 收口，先于一切实施）

1. **确定性代理主键（后端 P0-2/架构师 P0-2 同源）**：kb_baseline_entries 物理主键＝
   `uuid5(KB_BASELINE_NS, src_key)` 确定性派生——跨包/跨设备/跨备份恢复稳定；
   kb_match_items/kb_prefs/kb_entry_tags 键空间不变（仍是 uuid）；src_key 保留为唯一
   业务键（overlay join 与「官方有新版」比对用）。基线 id 与用户条目 id 同为 uuid 形态，
   键空间无混用。
2. **run 重建双表解析（后端 P0-1/架构师 P0-2 的链路面）**：首生成落 items 后，重建/
   续写/同素材复用路径按代理 id 从 merged 域（kb_entries ∪ 基线层）双表解析条目文本；
   纯基线 run 的二次生成/续写字节一致进 A5 用例。「写法块链零改动」措辞废弃——
   **打分配额链零改动，重建解析器扩双表**。
3. **冷启动回退域（架构师 P0-1，拍板选 b）**：零绑定账号 `_binding_domain` 增基线回退域
   （genre=书题材、concepts=手法/文风/文笔、fingerprint 由 pack_version 派生）——
   基线就绪即出块，不要求先建库绑定；有绑定的账号仍走作家库域（现行为不变）。
   delta 补正向场景「基线就绪＋零绑定＝写法块出现」。
4. **Ed25519 签名（架构师 P1-8 提级）**：基线条目 instruction 原文直拼生成提示词，
   CDN 写权限＝全作家生成链注入面——sha256 只防损坏不防篡改，违背 c-silent-upgrade
   判例。latest+manifest 复用 manifest_crypto 同一 Ed25519 信任根（客户端烘焙公钥，
   publish 侧 UPDATE_SIGNING_PRIVATE_KEY CI secret）；加包体 size 上限（16MB）与
   https＋可信域＋拒非公网 DNS 的 SSRF 防线（照 prompt_pack 七道校验）。
5. **格式版本闸**：manifest 自 v1 带 format_version＋min_client_version；高于本端支持
   → 静默跳过保持旧层（与 backup「弹错拒绝」语义不同，显式写清）；失败/跳过均保持旧层
   ＋failed 可重试。
6. **下架孤儿提升（架构师 P1-5 选 a）**：官方下架条目的用户 edit 副本**提升为用户自有
   条目**（用户资产不蒸发——写时复制的副本本就是用户的话）；hide 记录同步事务末尾
   机会主义清理。
7. **双哈希「官方有新版」（后端 P1-4）**：kb_baseline_entries.content_sha256（同步时算）
   ＋kb_baseline_overlays.base_content_sha256（edit 物化时对当时原件算）；读时比对即知
   官方是否修订，零写放大；基线行缺失跳过提示。

## D1 双层模型

- **lower 只读层**：kb_baseline_entries（uuid5 代理主键＋src_key 唯一＋content_sha256＋
  选择链投影列 genre/concept/scope/slot/when_json/payload_json 一等列物化——禁 JSON 全扫
  §12 铁律＋pack_version）。同步＝delete＋executemany 批插＋记 pack_version 单事务
  （<100ms 量级；重入照 prompt_pack _syncing＋排队先例）。updated_at 取包发布时间
  （整层替换不重置新鲜度）。
- **upper 可写层**：用户自有条目（kb_entries 零改动）＋ kb_baseline_overlays
  （(user_id, src_key) 主键＋action∈{hide,edit}＋content＋base_content_sha256）。
  overlay 单行语义：action 转换矩阵显式定义（edit→hide 保留 content 供还原），进 B5 测试。

## D2 同步管线（含信任模型）

Ed25519 验签 latest+manifest → format/min_client 闸（高于本端＝静默跳过保旧层）→
size 上限 → manifest sha256 校验 → 整层替换单事务 → overtures 孤儿清理（hide）/提升
（edit→用户条目，按 D0-6）。版本策略：**允许回退**（整层替换天然安全；tombstone 随版本
走，回退复活已下架条目但有 hide overlay 的仍隐藏）；版本发布即不可变（build 拒绝已存在
版本）；publish 仅 CI 从 validated commit 触发。

## D3 merged 查询与分页

基线段按一等列过滤（genre/concept/scope/slot），跨表分页＝两段各按 id 游标取页 Python
归并（基线 ≤1000 行）；题材栏计数含基线口径；搜索 contains 覆盖两段。「官方精选」标签
随层派生——kb_entries.src_kind SHALL NOT 落 baseline 值（knowledge-base delta 明确）。

## D4 反馈与边界注记（可直接引用的口径）

1. vs #998：AI 整理候选域恒为 kb_entries，基线条目结构性不可达（organize.py 只扫
   kb_entries），无需 skip 代码；未来合表必须补显式 skip 闸。
2. vs 书级副本（形态）：开书复制＝对 merged view 的一次性**值快照**（含基线条目当时
   内容＋src_key 溯源列）；官方升级不回灌既有书。
3. vs 书级副本（写路径）：书内改写落书层 SHALL NOT 写回 overlay；overlay 只属账号层。
4. vs 书级副本（反馈）：书层对基线源自条的反馈经 src_key 溯源聚合，作基线修订依据。
5. vs P1 LLM 选择器：候选摘要域＝merged digest；输出 id 带层标记；基线不设特殊配额。
6. vs 库/快照域：本变更不扩 KbLibraryItem 与启用快照域（回退域方案 b 不动库语义）。
   「入约」（把基线条目并入自有库成员）按此条裁撤：库成员与 merged 域是两套取数口径，
   并存必打架，且与 D0-3 冷启动回退重复。基线条目只经 merged 域消费。
7. 同槽冲突合并（场景覆盖官方）归组装器，另立任务或随 P1。

## D5 明确不做

merge 判定（overlay 已消解）；基线加密/档位门；统一 resources.json 收敛（阶段2 独立
变更）；AI 整理写入基线层。

## D6 内容仓发布管线硬化（架构师 P1-9）

build 拒绝已存在版本（版本＝不可变标签）；publish 仅 CI 从 validated commit 触发
（先跑 validate）；版本目录 immutable＋latest 短 TTL；validate 从「3 条哨兵抽样」扩为
与 C 端闸门同集（共享 fixture 双端 parity——固定文案/词表导出双端消费，同口径从口号变
parity 测试）。
