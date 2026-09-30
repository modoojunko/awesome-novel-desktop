# Design: c-retire-local-file-storage

## Context

设定层存储结构（origin/main + #619 worktree 实勘，两路独立评审复证）：

- `CompositeStorageBackend`（`composite_storage.py`）按 `route_relative_path`
  分派：settings 路径（PATH_TO_KEY 7 键 + `threads.yaml` + `style-quant.yaml` +
  `character:` 前缀，`paths.py:47-57`）→ `DatabaseFileBackend`（KV 表，content
  恒 JSON）；其余路径 → `LocalFileBackend`（盘上文件）。卷/章/正文/版本/归档/
  提示词自 PR①-⑤ 起全走各自 DB 表，不过 storage 抽象。
- 死活实证：生产代码全部 `get_storage()` 的 yaml/md/list/delete 调用点路径
  实参均命中 DB 路由（无动态路径/getattr/字符串拼装分派；scripts 自建 fixture；
  打包保留 `reference/` 供种子；e2e 走 API 层）。`read_md`/`write_md`/
  `delete_root` 全仓零业务调用；`LocalFileBackend` 唯一 import 方是 composite。
- 三个建书入口（评审 P1 补全）：新书 `novels/service.py:44`、拆书导入
  `import_persist` `novels/router.py:863`（`os.path.join(DATA_ROOT, slug)` +
  makedirs + rmtree 回滚）、备份导入 `backup/importer.py:586`（已合规）。
- 事故背景与读边界防线见 PR #619；本 change 为根治配套，基于 #619 合入后
  的 main 实施（两改同碰 `tests/test_db_storage.py` 相邻区）。

## Goals / Non-Goals

**Goals**

1. 删掉生产零可达的盘上存储机器，使「书数据只存 DB」在代码结构上不可逆。
2. storage 层终态收敛：`get_storage()` → `DatabaseFileBackend`，一层、名实
   相符；孤儿方法（delete_root/has_key）同批清。
3. root_path 三个建书入口统一 `./data/{slug}`（单源 helper），消除 docker
   绝对路径烙库。
4. 修正全部会骗人的陈旧注释（以 grep 门禁可过为准）。

**Non-Goals**

- 不改 `.yaml` KV 键名、不改 `read_yaml`/`write_yaml` 函数名（键值迁移 ×
  备份布局 × specs 三联动，零功能收益；误导已由 #619 docstring + 注释缓解）。
- 不动备份/导出 YAML zip 布局、种子模板、迁移引擎 `LEGACY_YAML_MARKER`。
- 不迁移存量 root_path 行（新旧键互不影响，各书独立分区）。
- 不做删书清理存量空目录的追溯脚本（存量空目录无害，留在原处）。
- **获准留存的盘面读写**（防止误读为「应用不能写文件」）：备份导出、成稿
  下载、loginless 导出（三者在各自域内直写盘，不经 storage 抽象）；
  `novel-samples/` 读取（`settings/style_quant_router.py:87`、
  `settings/ai_router.py:1747`，缺目录时优雅降级为空样例表）。

## Decisions

**D1. 终态形状：删 `LocalFileBackend` + `StorageBackend` Protocol +
`CompositeStorageBackend` 三者；`get_storage()` 直接返回
`DatabaseFileBackend`。**
两路评审一致否决「保留 composite 空壳」：改造后的 composite 是 5 方法纯
转发，名不副实（什么都不 composite）；Protocol 仅一个实现者。下一个可能的
演进都不需要这条缝——逐书加密是 DatabaseFileBackend 内的编解码问题、云同步
暂存/导出早已在域内直写盘（`backup/export.py:450`、
`manuscript/service.py:104-137`）、S端存储是独立服务不经 C端 `get_storage`。
方法名不变（read_yaml/write_yaml/delete_file/list_dir），76 个调用点零改动；
`init_skeleton` 从接口退役，建书流程改为直呼 `seed_settings_to_db` +
mkdir（D3）。备选「保留 composite 改名」与「Protocol 断言守护」均被否：
给零调用方的分支留壳/留接口，成本同为删代码却留下认知负担。

**D2. 非路由路径的语义：维持 DB 后端现状（读 `{}`、写静默 no-op），
不新加 raise。**
`DatabaseFileBackend.read_yaml/write_yaml` 对 `route_relative_path` 为 None
的路径本就返回 `{}`/no-op（`db_storage.py:65-77`）。本 change 是纯清理，
不引入新行为；调用了不该调的路径属于实现错误，由「盘上机器已删」在代码
评审层面自然暴露。初稿「非 settings 路径调 storage 即 AttributeError」的
fail-fast 契约与 D1 直通矛盾（评审 P2），作废。

**D3. init_skeleton 拆解：DB 种子与根目录 mkdir 移到建书调用点，mkdir 保留
并注明存在理由。**
初稿「书在盘上零足迹/无代码假设目录存在」被评审证伪：`novel-samples/`
（文风蒸馏样例，UI 暴露、测试钉住）按 `<root_path>/novel-samples/` 读盘，
是唯一获准读书目录的功能——目录是用户投样的锚点，删了会让新书用户手摸
DATA_ROOT 自建路径。故 `novels/service.py` 建书处：`await
seed_settings_to_db(root_path)` + `os.makedirs(root_path, exist_ok=True)`
（注释指向 novel-samples）；`_init_project_skeleton_local` 删除；
`import_persist` 的 mkdir/rmtree 删除（导入书不投样，需要时功能侧自建，
`os.makedirs(exist_ok=True)` 已是样例上传路径的既有行为口径）。存量空目录
不追溯清理。

**D4. root_path 统一 `./data/{slug}`，三个入口走 `config.book_root(slug)`
单源。**
新增 `config.book_root(slug) -> str`（config 是叶子模块无环）；三处替换：
`novels/service.py:44`、`novels/router.py:863`（import_persist，同入口删
`:867` makedirs 与 `:939-942` rmtree 死回滚）、`backup/importer.py:586`。
取相对方案的理由：同一份库文件跨环境（本机/docker/演示栈）搬运时 KV 分区
键不变；绝对方案在 docker 下烙 `/app/data/<slug>`，换机即成孤儿口径。
存量行不迁移：root_path 是逐书独立的不透明分区键，混排永不互相作用
（`novel_to_dict` 不含 root_path、前端零消费、zip 按 slug 分目录、rename
不变式只改 name——两路评审复证；`migration/engine.py:100-106` 的旧世代
探针对两种格式均正确解析且仅作用于无 project_settings 的旧库）。

**D5. 测试处置：改写而非保留。**
- `test_db_storage.py`：`test_composite_routes_settings_to_db_rest_to_local`
  的 local 半边改写为「非路由路径读 `{}` 写 no-op」契约（D2）；卷 yaml 落盘
  断言删除；`test_delete_root_clears_rows_and_dir` 删除（方法退役）；
  `test_db_roundtrip_and_delete` 去「非 settings 路径不落 DB」段；
  `test_init_skeleton_seeds_db_not_disk` 改为直接测 `seed_settings_to_db`
  + 建书调用点行为。
- `test_volume_chapter_crud.py:30,35,95,270-273`、`test_dual_write.py:32,40,
  176-179,240-243`：删 LocalFileBackend import/实例化，按 D2 契约改写
  （评审 P2 补登——漏改则 collection 即炸，5.1 门禁必红）。
- `has_key` 删除后，skeleton 测试改用 `read_yaml` 断言。
- `upgrade_drill.py`/`up16_real_data_drill.py` 自建 yaml fixture 模拟旧世代，
  不依赖被删类，不动。

**D6. 注释修正以「grep 门禁可过」为验收**（评审 P2：初稿白名单漏四处）：
`paths.py:3`（模块 docstring「其余路径路由 LocalFileBackend」）、
`paths.py:43`（route_relative_path docstring 同语）、`db_storage.py:1-6`
（模块头「本地骨架委托 LocalFileBackend」）、`prompt/store.py:47`（「对齐
read_md 缺文件返空串」）、`tests/conftest.py:164`（「仍走文件种子」）、
`config.py:23`（5→3）；前端 `api.ts:257,260`、`GenreSettingForm.tsx:3,8,94`、
`themeCatalog.ts:16,25` 的 story.yaml 口径同批。

## Risks / Trade-offs

- **隐藏触达**：两路独立评审的可达性扫描（动态路径/scripts/打包/e2e/
  alembic/桌面壳）均未发现第六方法的生产触达；若未来有人给非 settings
  路径调 storage，读 `{}` 写 no-op（D2）不会炸但也不落盘——与 DB 后端
  现状一致，无新增风险面。回归证据 = 全量 pytest + 全量 e2e（API 层）。
- **novel-samples 与根目录**：mkdir 保留（D3），功能无感；代价是书在盘上
  仍有一个（有用的）目录，接受。
- **新旧行共存**：同库内新书写 `./data/<slug>`、docker 旧导入行可能仍是
  `/app/data/<slug>`——互为独立分区键，功能无感；人工核对
  `SELECT DISTINCT root_path FROM novels` 一眼可辨。
- **排序约束**：PR #619 先合（同测试文件相邻 hunks，先合免 rebase 冲突）；
  本 change 从其后的 main 切出。`fix/char-tree-refresh-on-save`（仅
  CharacterManager.tsx）与本 change 零重叠，无排序约束；演示栈换包独立。

## Open Questions

（无——死活两路评审复证；D2/D3 两处初稿错误已按评审修正。）
