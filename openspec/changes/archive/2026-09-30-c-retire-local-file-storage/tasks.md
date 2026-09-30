# Tasks: c-retire-local-file-storage

前置：PR #619 先合入 main，本 change 从其后的 main 切出（同碰
`tests/test_db_storage.py` 相邻区，见 design.md 排序约束）。

## 1. storage 层终态收敛（D1/D2）

- [x] 1.1 删 `LocalFileBackend` 整类 + `StorageBackend` Protocol + `CompositeStorageBackend` 整档（`client/backend/filesystem/storage.py`、`composite_storage.py`）；`storage.py` 仅留 `get_storage()`（直接构造/缓存 `DatabaseFileBackend`，返回类型注解同步）；验证：`grep -rn "LocalFileBackend\|CompositeStorageBackend\|StorageBackend" client/backend --include='*.py'` 仅剩本组新注释中「已退役」的历史注记（如有），零代码引用
- [x] 1.2 `DatabaseFileBackend` 清孤儿：删 `delete_root`、`has_key`（`filesystem/db_storage.py:116-126`），模块头 docstring 去「本地骨架委托 LocalFileBackend」句；验证：grep `delete_root\|has_key` 零代码引用（测试同批改，见 3.x）
- [x] 1.3 `filesystem/init.py` 删 `_init_project_skeleton_local`；`REFERENCE_DIR`/`TEMPLATE_DIR`（种子模板）保留；验证：grep `_init_project_skeleton_local` 零命中

## 2. 建书入口三处统一 root_path（D3/D4）

- [x] 2.1 `config.py` 新增 `book_root(slug) -> str`（返回 `f"./data/{slug}"`，docstring 注明「KV 分区键，环境无关相对方案」）；`config.py:23` 模板计数注释 5→3；验证：单测断言返回值
- [x] 2.2 `novels/service.py` 建书流程：`root_path = book_root(slug)`；原 `get_storage().init_skeleton(root_path)` 改 `await seed_settings_to_db(root_path)` + `os.makedirs(root_path, exist_ok=True)`（注释：novel-samples 文风蒸馏样例的唯一磁盘锚点）；相邻旧注释「导入后文件系统会由 /import/persist 写入完整内容」同步修正；验证：pytest 建书用例 + 新书行 `root_path` 以 `./data/` 开头
- [x] 2.3 `novels/router.py` import_persist：`:863` 改 `book_root(slug)`、删 `:867` `os.makedirs`、删 `:939-942` rmtree 死回滚（回滚改为仅清 DB 行，维持现有软删/清理口径）；验证：pytest 导入用例全绿 + 导入书行 `root_path` 以 `./data/` 开头
- [x] 2.4 `backup/importer.py:586` 改 `book_root(slug)`（单源收编，行为不变）；验证：pytest backup 全量

## 3. 测试改造（D5）

- [x] 3.1 `tests/test_db_storage.py`：非路由路径契约改写为「读 `{}`、写 no-op」（D2，弃 fail-fast 断言）；删 local 落盘/卷 yaml 断言；删 `test_delete_root_clears_rows_and_dir`；`test_init_skeleton_seeds_db_not_disk` 改测 `seed_settings_to_db`（has_key 断言改 read_yaml）；composite import 全部去除；验证：该文件全绿
- [x] 3.2 `tests/test_volume_chapter_crud.py:30,35,95,270-273`、`tests/test_dual_write.py:32,40,176-179,240-243`：删 LocalFileBackend import/实例化，按 3.1 同款契约改写；验证：两文件全绿
- [x] 3.3 `tests/conftest.py:164` 注释「仍走文件种子」改 KV 种子口径；grep `read_md|write_md|delete_root|has_key|init_skeleton|LocalFileBackend` 全测试/脚本清剩余引用（`upgrade_drill.py`/`up16_real_data_drill.py` 的自建 yaml fixture 不动）；验证：grep 仅剩 export/import 备份域与历史注记

## 4. 注释修正（D6，grep 门禁可过为验收）

- [x] 4.1 `filesystem/paths.py:3,43`：「其余路径路由 LocalFileBackend」→「`.yaml` 是文件时代键名，仅作 KV 键、永不落盘；非路由路径读 `{}` 写 no-op」；`prompt/store.py:47` 去 read_md 对齐语；验证：grep `read_md\|LocalFileBackend` 零残留
- [x] 4.2 前端纯注释：`lib/api.ts:257,260`、`components/novel/settings/GenreSettingForm.tsx:3,8,94`、`lib/themeCatalog.ts:16,25` 的 story.yaml 口径改 KV 键表述；验证：C端 `tsc --noEmit` 过（注释级，无 vitest 断言引用）

## 5. 回归门禁

- [x] 5.1 全量 pytest（`client/backend` venv 解释器，基线 = #619 合入后的全量绿）；ruff 清
- [x] 5.2 全量 e2e（隔离栈，E2E_BASE_URL 指向本会话环境；按「每对话独立环境」纪律起栈）；验证：数量不减于基线
- [ ] 5.3 真机快验（换包后）：建一本新书 + 走一次拆书导入——书架两本都在、设定页 world/story 各保存一次；`SELECT root_path FROM novels` 两行均以 `./data/` 开头；新书目录存在且仅含 `novel-samples/` 锚点语义（空目录）；导入书无盘上目录
