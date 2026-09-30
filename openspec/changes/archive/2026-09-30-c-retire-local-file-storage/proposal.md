# Proposal: c-retire-local-file-storage —— 退役盘上 YAML/MD 存储死代码

## Why

设定层自存储 ADR 起「业务数据全量入库」，盘上不再承载任何书数据；但整套
`LocalFileBackend` 盘上存储机器（YAML/MD 读写、列目录、删文件、删根目录）
仍留在代码里。2026-09-30 的 world 行裸 YAML 500 事故复盘证明：这层「文件
时代」的命名与机器是事故土壤——手修数据的人按接口名（read_yaml /
world-setting.yaml）误以为 content 列存 YAML。该机器已被两路独立评审复证
**生产零可达**（全部 read_yaml/write_yaml 调用点的路径实参均命中
`route_relative_path` 的 DB 路由：PATH_TO_KEY 7 键 + threads + style-quant +
character: 前缀；卷/章/正文/提示词/归档走各自 DB 表；无任何动态路径、
打包、脚本、e2e 触达）。

用户拍板（2026-09-30）：库内数据不再有任何 YAML 存储，备份/导出（对外交换
格式）除外。

## What Changes

- **删 `LocalFileBackend` 整类 + `StorageBackend` Protocol + `CompositeStorageBackend`**
  （`filesystem/storage.py`、`filesystem/composite_storage.py`）：三路评审后
  采纳「再塌一层」——composite 改造后只是 5 方法纯转发、名不副实（什么都不
  composite），Protocol 仅一个实现者；`get_storage()` 单例门面保留，直接返回
  `DatabaseFileBackend`（方法名不变，76 个 read_yaml 调用点零改动）
- **`DatabaseFileBackend` 同批清孤儿**：`delete_root`（唯一调用方是被删的
  composite）、`has_key`（仅测试调用）一并删除——「留空壳只会复活误用」
  对自己的后端同样成立
- **init_skeleton 拆解**：纯 DB 种子（`seed_settings_to_db`）移到建书调用点
  （`novels/service.py`）；**根目录 mkdir 保留**但移到同一调用点并注明存在
  理由——`novel-samples/`（文风蒸馏样例）是唯一获准读书目录的功能
  （`settings/style_quant_router.py:87`、`settings/ai_router.py:1747`），
  需要目录作为用户投样锚点
- **root_path 统一为 `./data/{slug}`，覆盖全部三个建书入口**：新书
  （`novels/service.py:44`）、**拆书导入 `import_persist`**
  （`novels/router.py:863`，评审 P1 实锤的漏网点——现为
  `os.path.join(DATA_ROOT, slug)`，docker 下烙绝对路径；同入口的
  `os.makedirs` `:867` 与死回滚 `rmtree` `:939-942` 一并删除）、备份导入
  （`backup/importer.py:586`，已合规，收编到共享 helper）。方案取环境无关
  相对路径（`config.py` 新增 `book_root(slug)` 单源）；root_path 仅为 KV
  分区键（API 响应/前端/备份 zip 布局零暴露，两路评审复证），存量行不迁
- **修正骗人注释**（grep 门禁可过为准）：`filesystem/paths.py:3,43`、
  `db_storage.py` 模块头、`prompt/store.py:47`、`tests/conftest.py:164`、
  `config.py:23`（模板 5→3）、前端 `lib/api.ts:257,260`、
  `components/novel/settings/GenreSettingForm.tsx:3,8,94`、
  `lib/themeCatalog.ts:16,25`

**不改**（有意保留）：`.yaml` KV 键名（改键 = 数据迁移 × 备份包布局 × specs
三联动，零功能收益）；`read_yaml`/`write_yaml` 函数名（76 调用点，#619 已落
「JSON dict 唯一正规形状」docstring）；`reference/*.yaml.template` 种子模板
（建书输入，非存储）；备份 zip 布局（用户口径明示除外）；
`migration/engine.py` 的 `LEGACY_YAML_MARKER`（老安装升级门禁，迁移窗口
关闭后另议）。**获准留存的盘面读写面**（明示以免误读为「应用不能写文件」）：
备份导出、成稿下载、loginless 导出、novel-samples 读取、种子模板——全部
不经 storage 抽象、位于各自域内。

**BREAKING**：无。零 API / 零 DB 行为变化（见 design.md 死活性论证与评审记录）。

## Capabilities

### New Capabilities

（无——纯死代码清理 + 内部键值口径统一，零 spec 级行为变化；`.openspec.yaml`
已置 `skip_specs: true`。两路评审独立复核 specs 全库：无任何 capability
requirement 钉住 LocalFileBackend/init_skeleton/盘上骨架/root_path 格式；
`db-generation` 对盘上 yaml 的引用是迁移门禁读取端，本 change 不触碰；
`creation-flow` 的 rename 不变式不受影响。）

### Modified Capabilities

（无。）

## Impact

- 代码：`client/backend/filesystem/`（storage.py、composite_storage.py 整档，
  init.py 一函数，paths.py/db_storage.py 注释）、`novels/service.py`、
  `novels/router.py`（import_persist 段）、`backup/importer.py` 一行、
  `config.py`（helper + 注释）、`prompt/store.py` 注释、`tests/conftest.py`
  注释；前端纯注释四处（api.ts、GenreSettingForm.tsx、themeCatalog.ts）
- 测试：`tests/test_db_storage.py`（与 PR #619 同文件相邻改动——**#619 先合，
  本 change 基于其后的 main 切出**）、`test_volume_chapter_crud.py`、
  `test_dual_write.py`（两处直接 import LocalFileBackend，评审 P2 补登）
- 事故背景：PR #619（read_yaml 读边界容错，在途）为复盘防线；本 change 是
  根治配套（把骗人的机器删掉，而不是只防住它）
