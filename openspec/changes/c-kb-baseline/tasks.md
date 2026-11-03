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
  - D0-6 已补：孤儿 edit 副本在整层替换时提升为账号自有条目（src_kind=manual／src_novel_name=「官方精选（已下架）」／标签同事务物化），随后删覆盖记录；hide 孤儿照旧清理
- [x] B5 备份登记：overlays 进 export/importer/config_preview 三处（roundtrip 钉）
  - 导入按 (user_id, src_key) upsert（自增 id 不能走通用按 id 去重循环）
- [x] B6 前端：知识库页基线条目只读操作面＋来源筛选「官方精选」＋入约＋组件测试
  - 已做：来源筛选四档、官方精选/我的副本/官方有新版三徽章、抽屉「隐藏这条／恢复官方版」、kbApi 两方法＋组件/API 测试
  - 补规格「未同步完成不阻断…状态行可重试」：GET /api/kb/baseline/status ＋ POST /api/kb/baseline/sync ＋ 官方精选空态「重新同步」
  - 「入约」裁撤：与 design D4-6「本变更不扩 KbLibraryItem 与启用快照域」冲突——基线不进自有库成员，出块走 merged 域（见 design D4 补注）
- [x] B7 AI 整理边界钉：整理查询域不含基线（结构性不可达的回归钉）
- [x] B8 评审修复（11-02，七条）：
  - P1 隐藏可逆：`src=已隐藏` 列表回读 hide 白名单＋抽屉「恢复默认」（原实现隐藏后拿不到 id）
  - P2 图谱聚合并入基线格子（原来只有题材节点计数含基线，纯基线账号图谱空白）
  - P2 书未设题材不跨题材回退（空 genre 在 digest 里＝不过滤，会把别题材基线混进来）
  - P3 覆盖写入撞 (user_id,src_key) 唯一索引→回滚后改更新赢家行（不再 500）
  - P3 下架提升后再上架：给该用户补 hide，用户副本与复活原件不重复显示
  - P3 edit→hide 保留的副本正文在官方下架时不再被整条删除
  - P3 同步失败/跳过不再提示「暂时没有新版本」；筛选态空集不再提示「没同步下来」；parity 内容仓相对路径 parents 修正
- [x] B10 第二轮评审修复（11-03，三条）：
  - P2 备份重复导入幂等：提升件按 `evidence_json.promoted_from` 查亲（`find_promoted_copy`），
    命中即跳过——不再二次造条目，层已同步时也不再补建覆盖行造成两份显示
  - P3 编辑副本失败原样透传后端闸门 message（原来固定文案吞掉具体原因）＋草稿 maxLength=240 与字数
  - P3 旧包无 `base_meta` 的孤儿副本不再静默：导入摘要新增 `orphaned` 计数（覆盖行保留，等未来重上架）
- [x] B9 评审补修（11-02，三条）：
  - P2 编辑存副本：抽屉「存为我的副本」入口（草稿预填官方原文→过同套闸门→落用户副本），
    补上 CoW Requirement 里原本只有 API、UI 不可达的「修改」场景；文案改为「不能删除，想改就存副本」
  - P2 孤儿副本可恢复：导出给覆盖行带 `base_meta`（概念/题材/标题/载荷/条件/原文），
    导入端对不上当前基线层（官方已下架/本机包更新）就地提升为账号自有条目，不留隐形孤儿
  - P3 烘焙钥 parity：`_PROD_PUBKEYS_JSON` 与打包常量 `PROD_PACK_PUBKEYS` 同源钉（漂移＝同步恒失败）

## 批C 内容与发布（内容仓＋boss 侧）

- [x] C1 validate 扩为与 C 端闸门同集（共享 fixture 双端 parity）
  - C 端单源 `kb.gates.check_baseline_entry`（同步 `_parse_entries` 直接调用）＋内容仓 `tools/validate.py` 同序同码
  - fixture `tests/fixtures/kb_baseline_gate_cases.json`（23 例＋四张封闭词表）两仓同一份；C 端 parity 测试含「两仓 fixture 一致」「内容仓条目全过 C 判据」
  - 实锤：内容仓原有 1 条 when.scene=「对决」（非封闭值）——已改「打斗」，此类条目在旧口径下永远匹配不上
- [x] C2 build 拒绝已存在版本＋publish 仅 CI 触发＋版本目录 immutable
  - build：先过闸→版本目录已存在即拒→Ed25519 签 manifest＋latest（canonical 与 C 端 manifest_crypto 同源）＋自签名回验；`--unsigned` 调试包不可发布
  - publish：未签名拒发／非 CI 且无演练目录拒发／同版本同内容幂等、不同内容拒绝覆盖；`KNOWLEDGE_CDN_DIR` 支持本地演练目录
  - `tests/selftest_tools.py` 7 项（签名复验/不可变/发布闸/幂等/未签名拒收/非 CI 拒发/fixture），CI validate.yml 已挂
- [ ] C3 打样扩量（玄幻/都市补齐＋新增 1-3 题材）＋基线包 v1 发布
  - 打样扩量已做：13 → 53 条（玄幻/都市补齐，新增 仙侠/修真、悬疑；全过双端闸）
  - 分发面已改走**既有静态托管**（不新建 CDN）：`www.awesomenovel.com/knowledge/baseline/`，
    publish 走 `tcb hosting deploy`；C 端 URL/验签钥已烘焙（**与提示词包共用 `pack-k1`**、
    主域失败切兜底域）
  - **v1 发布待内容仓 Settings 填既有值**（不新造凭据）：`TCB_API_KEY`(secret)＋
    `TCB_ENV_ID`(variable)＝与 desktop 发布同一套；`PACK_SIGNING_KEY`(secret)
    ＝awesome-novel-prompts 同名 secret 同一值（PEM，pack-k1）
- [ ] C4 真机走查：同步/出块/标记/升级整层替换保 overlays/回退
  - 本地全链已过（`tests/test_kb_baseline_fullchain.py`）：内容仓真实 build→publish→本地 HTTP→真实 httpx 同步→merged 选择→hide 生效→同版本零下载
  - **Mac 本地应用走查已过（2026-11-02，pywebview 应用后端 + 打包前端 dist + 本地签名包）**：
    启动补偿自动同步 v1（53 条/234 标签）→ 知识库页「官方精选」列表/徽章 → 隐藏 → 「已隐藏」找回 →
    恢复默认回到精选 → 发布 v2 重启后整层替换升到 v2 且 hide 覆盖保留（「线索·重复动词」仍隐藏）；
    拆书发派页双卡/默认智能维（已选 5/10，切全书拆 10/10，切回 5/10）在 c-deconstruct-knowledge 构建上验过
  - 余：真实 CDN（`www.awesomenovel.com`）＋真实签名包上线后的装机走查（依赖 C3 凭据）
