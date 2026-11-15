# c-kb-tree-cdn · Tasks

## 1. C 端 tree_sync

- [x] 1.1 `kb/tree_sync.py`：缓存布局（receipt/v{N}/原始字节/meta/highwatermark）、
      legacy 三字段 verifier、下载体 sha/size/结构校验、staging 原子安装、低版本拒绝、
      同版本损坏修复、`KB_TREE_SYNC=0`、启动 schedule
- [x] 1.2 `kb/taxonomy.py`：缓存读取（KB_TAXONOMY_PATH → tree_sync 缓存 → 空树）、
      `_load` total、`reload()`、`is_ready()`、helper `.get` 安全化
- [x] 1.3 空树行为：summarize/refine `tree_not_ready`；`maybe_auto_summarize` 跳过；
      graph/tree `tree` 元数据＋排序降级
- [x] 1.4 API：`/tree/sync-status|probe|sync`
- [x] 1.5 打包：删 kb/data/taxonomy.json；bundle_manifest 去 datas；负向断言
- [x] 1.6 测试：夹具树＋conftest 播种；test_kb_tree_sync（18 例）；test_kb_tree_not_ready
- [x] 1.7 前端：kbApi.graphTree.tree＋treeSyncStatus；树面板未同步空态/降级横幅；
      提炼按钮禁用；测试 mock 接线

## 2. 内容仓

- [ ] 2.1 发布 CDN tree v2（当前 25,770B 树，legacy 签名，pack-k1）
- [ ] 2.2 selftest_tools 补 tree 指针验签用例（发布后验证）

## 3. 验收

- [x] 3.1 后端全量 pytest 绿（3053 passed；2 个 content-repo-withdrawn 环境红与
      main 相同，非本改动引入）
- [x] 3.2 前端 tsc/vitest --coverage（四项阈值）/build 全绿
- [ ] 3.3 真机走查：新装首启同步树；断网启动树空提示；CDN 篡改保旧层
