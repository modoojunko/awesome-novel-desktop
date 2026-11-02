# c-kb-baseline · Tasks（v2 双评审后重排）

## 批0 文档对齐（先行）

- [x] proposal.md 重写为 overlay 双层口径；knowledge-base delta 补 MODIFIED（来源扩展/表边界/同步复验）＋原场景保全
- [x] design.md v2：D0 关键裁定（uuid5 代理键/回退域/双哈希/Ed25519/格式闸/下架孤儿提升/升级演练）＋路线边界注记

## 批A 只读层与同步（后端）

- [x] A1 建表：kb_baseline_entries（uuid5 代理主键＋src_key 唯一＋content_sha256＋投影一等列＋pack_version）＋kb_baseline_overlays（(user_id,src_key) 主键＋action＋content＋base_content_sha256）＋kb_baseline_tags（同步物化，照 entry_tags 可重建先例）
- [x] A2 同步器：Ed25519 验签→format/min_client 闸→size 上限→manifest sha256→整层替换单事务（delete＋executemany 批插＋记 pack_version；重入排队去重）
- [x] A3 启动补偿挂接（不要求登录态——纯 CDN；失败静默可重试；异常不挡启动）
- [x] A4 单测：坏哈希/断网/新格式三失败保旧层且 pack_version 不变/同版本 0 DELETE/升级演练（mismatch→带回→重同步→overlays 空 but valid）/双账号隔离
  - 12 例见 `tests/test_kb_baseline_sync.py`；顺手修 A2 实现 P0（`db.execute` 漏 await → 「synced」但零行落库）、补 executemany、min_client 闸、坏行/重复键/超长 src_key 复验
  - 遗留：下架条目的孤儿 **edit** 副本「提升为用户条目」（D0-6）归 B4 与 action 矩阵同批做（当前保留 overlay 行，数据不丢）

## 批B merged 换源＋操作面（后端＋前端）

- [x] B1 merged 查询：基线段（排除 hidden、edit 套副本）∪ 用户段——digest_candidates 换源＋跨表分页归并＋题材栏计数＋搜索覆盖
  - 新模块 `kb/merged.py`（MergedEntry 与 KbEntry 读口径同形＋hide 走 SQL NOT EXISTS＋分页归并）；`kb/match.py` 短名单/取行并入基线；`kb/service.list_entries` 跨表分页、`genre_counts` 相加、详情端点基线回退
- [x] B2 run 重建双表解析器（代理 id 从 merged 域回读）——纯基线 run 二次生成/续写字节一致钉
- [x] B3 冷启动回退域：零绑定账号 _binding_domain 基线回退（fingerprint 由 pack_version 派生）＋正向场景测试
- [x] B4 覆盖/隐藏/恢复端点（写时复制＋过 C 端闸门回显）＋action 转换矩阵＋「官方有新版」双哈希比对
  - `PUT/DELETE /api/kb/entries/{id}/baseline-override`；edit 过 check_gates、edit→hide 保留副本文本；pref 端点放行基线条目
  - 遗留：官方下架条目的孤儿 edit「提升为用户条目」（D0-6）仍未做——当前 overlay 行保留（数据不丢），待单独定 shape（src_kind/概念映射/标签）
- [x] B5 备份登记：overlays 进 export/importer/config_preview 三处（roundtrip 钉）
  - 导入按 (user_id, src_key) upsert（自增 id 不能走通用按 id 去重循环）
- [x] B6 前端：知识库页基线条目只读操作面＋来源筛选「官方精选」＋入约＋组件测试
  - 已做：来源筛选四档、官方精选/我的副本/官方有新版三徽章、抽屉「隐藏这条／恢复官方版」、kbApi 两方法＋组件/API 测试
  - 补规格「未同步完成不阻断…状态行可重试」：GET /api/kb/baseline/status ＋ POST /api/kb/baseline/sync ＋ 官方精选空态「重新同步」
  - 未做：「入约」（基线条目加入自有库）当前口径未定义（库成员是手动圈选 P1），挂账待拍板
- [x] B7 AI 整理边界钉：整理查询域不含基线（结构性不可达的回归钉）

## 批C 内容与发布（内容仓＋boss 侧）

- [ ] C1 validate 扩为与 C 端闸门同集（共享 fixture 双端 parity）
- [ ] C2 build 拒绝已存在版本＋publish 仅 CI 触发＋版本目录 immutable
- [ ] C3 打样扩量（玄幻/都市补齐＋新增 1-3 题材）＋基线包 v1 发布
- [ ] C4 真机走查：同步/出块/标记/升级整层替换保 overlays/回退
