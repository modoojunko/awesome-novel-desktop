# c-kb-baseline · Tasks（v2 双评审后重排）

## 批0 文档对齐（先行）

- [x] proposal.md 重写为 overlay 双层口径；knowledge-base delta 补 MODIFIED（来源扩展/表边界/同步复验）＋原场景保全
- [x] design.md v2：D0 关键裁定（uuid5 代理键/回退域/双哈希/Ed25519/格式闸/下架孤儿提升/升级演练）＋路线边界注记

## 批A 只读层与同步（后端）

- [ ] A1 建表：kb_baseline_entries（uuid5 代理主键＋src_key 唯一＋content_sha256＋投影一等列＋pack_version）＋kb_baseline_overlays（(user_id,src_key) 主键＋action＋content＋base_content_sha256）＋kb_baseline_tags（同步物化，照 entry_tags 可重建先例）
- [ ] A2 同步器：Ed25519 验签→format/min_client 闸→size 上限→manifest sha256→整层替换单事务（delete＋executemany 批插＋记 pack_version；重入排队去重）
- [ ] A3 启动补偿挂接（不要求登录态——纯 CDN；失败静默可重试；异常不挡启动）
- [ ] A4 单测：坏哈希/断网/新格式三失败保旧层且 pack_version 不变/同版本 0 DELETE/升级演练（mismatch→带回→重同步→overlays 空 but valid）/双账号隔离

## 批B merged 换源＋操作面（后端＋前端）

- [ ] B1 merged 查询：基线段（排除 hidden、edit 套副本）∪ 用户段——digest_candidates 换源＋跨表分页归并＋题材栏计数＋搜索覆盖
- [ ] B2 run 重建双表解析器（代理 id 从 merged 域回读）——纯基线 run 二次生成/续写字节一致钉
- [ ] B3 冷启动回退域：零绑定账号 _binding_domain 基线回退（fingerprint 由 pack_version 派生）＋正向场景测试
- [ ] B4 覆盖/隐藏/恢复端点（写时复制＋过 C 端闸门回显）＋action 转换矩阵＋「官方有新版」双哈希比对
- [ ] B5 备份登记：overlays 进 export/importer/config_preview 三处（roundtrip 钉）
- [ ] B6 前端：知识库页基线条目只读操作面＋来源筛选「官方精选」＋入约＋组件测试
- [ ] B7 AI 整理边界钉：整理查询域不含基线（结构性不可达的回归钉）

## 批C 内容与发布（内容仓＋boss 侧）

- [ ] C1 validate 扩为与 C 端闸门同集（共享 fixture 双端 parity）
- [ ] C2 build 拒绝已存在版本＋publish 仅 CI 触发＋版本目录 immutable
- [ ] C3 打样扩量（玄幻/都市补齐＋新增 1-3 题材）＋基线包 v1 发布
- [ ] C4 真机走查：同步/出块/标记/升级整层替换保 overlays/回退
