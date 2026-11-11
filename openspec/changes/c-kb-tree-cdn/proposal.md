# c-kb-tree-cdn · 知识树改走 CDN——C 端包内零 taxonomy，空树明确不可用

## Why

boss 2026-11-11 拍板：**C 端不能有初始化的知识，所有知识都要从 CDN 获取**。官方基线条目本就
只走 CDN（knowledge/baseline，2026-11-11 已整体撤回）；唯一随包的知识资产是
`kb/data/taxonomy.json`（知识树＋字段模板）。且线上 tree 仍是 v1（少 `文风|tone`/`文笔|tic`
两个映射）——随包树与 CDN 树已经漂移，「随包内置」让树的更新必须发客户端版本，违背
「知识是数据」的北极星。

## What Changes

- **C 端包内零 taxonomy**：删 `kb/data/taxonomy.json` 与 `bundle_manifest` 的 `kb/data`
  datas 条目；打包门禁负向断言（与 prompts 同款红线）。
- **新增 `kb/tree_sync`**：从 CDN `knowledge/tree` 拉签名树，落 `{DATA_ROOT}/kb-tree/`
  （receipt＋v{N}/taxonomy.json 原始字节＋meta.json＋highwatermark）。指针验签用内容仓
  `tree_publish.py` 的 **legacy 三字段格式**（与 manifest_crypto 不同，专用 verifier）；
  下载体 sha256/size/结构（单根/父可解析/slot_map 指向存在/无环）三重校验；staging 原子
  安装、receipt 最后写；**低版本一律拒绝**（回退保护）；同版本缓存损坏＝修复重下；
  `KB_TREE_SYNC=0` 关启动钩；`KNOWLEDGE_TREE_CDN_BASE` 覆盖。
- **`kb/taxonomy` 改缓存读取**：`KB_TAXONOMY_PATH`（测试/dev）→ tree_sync 缓存 →
  规范化空树；`_load` total（缺失/损坏只 log 不抛）；`reload()` 供同步后失效；
  `nodes/node_for/parent_chain` 用 `.get` 安全化。
- **空树＝明确不可用**：`run_summarize`/`run_refine` 返回 `tree_not_ready`（不再回落
  硬编码「写作知识→其他」、不再「完成但 moved=0」空转）；`maybe_auto_summarize` 整体跳过；
  `graph/tree` 返回 `tree` 元数据（ready/version），排序降级不 500；旧 DB 根行（用户数据）
  仍展示。
- **API/UI**：`GET /api/kb/tree/sync-status|probe`、`POST /api/kb/tree/sync`；前端
  `kbApi.graphTree` 类型加 `tree`、新增 `treeSyncStatus`；树面板区分「树未同步」与
  「还没有知识点」；「知识提炼」按钮在未同步时禁用。
- **CDN tree v2 先行**：发布当前 25,770B 树为 v2（含那两个映射），再发带本改动的客户端。

## Impact

- 后端：kb/tree_sync.py（新）、kb/taxonomy.py、kb/summarize.py、kb/refine.py、
  kb/router.py、main.py（启动钩）、packaging/bundle_manifest.py、tests/conftest.py、
  tests/test_kb_tree_sync.py（新）、tests/test_kb_tree_not_ready.py（新）、
  tests/fixtures/taxonomy/taxonomy.json（新）、test_bundle_manifest.py
- 前端：src/lib/kbApi.ts、KnowledgeTreePanel.tsx、KnowledgeBasePage.tsx（最小改动）
- 内容仓：tools/tree_publish.py 发布 v2（不改代码）；tests/selftest_tools.py 补 tree
  指针验签用例
- spec：knowledge-base「知识编辑器与种子」（随包内置 → CDN 下发）
