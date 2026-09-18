## Why

归档条目名 = `{chapter_ref}-{slug(标题)}.md`，slug 公式在仓库有**两份手抄副本**（`archive/router.py::_slugify:28`、`archive/service.py:55` 内联），且**零安全过滤**（`title.replace(" ", "-").lower()[:50]`）。实证影响（本机最小复现）：

| 标题 | 包内条目 | 后果 |
|---|---|---|
| `上/下` | `archives/vol-1-ch-1-上/下.md` | 条目嵌套一层；导入端 `title=Path(name).stem` → 标题被分隔符**截断为「下」** |
| `上/../下` | `archives/vol-1-ch-1-上/../下.md` | 路径段含 `..` → 导入端 `validate_paths` 拒绝 → **一个标题让整个备份包不可导入** |
| `第1..2章` | `…-第1..2章.md` | 包可通过校验，但 `_parse_archive_filename` 拒 `..` 子串 → `GET /archives/{filename}` **不可寻址**（列表有、打不开） |
| `"a"*49+"."` | `…-{49a}.md` | **截断边界**：slug 以点结尾与 `.md` 拼接出 `..` 子串 → 同上不可寻址（评审补充反例） |

来源：`c-backup-archive-dedup` PR #409 后端评审 P2-6 实测登记（当时显式列为 Non-Goal 待单开），本 change 即其跟进。前端对归档接口零消费（归档阅读页已退役），损害集中在**备份包往返**与**接口契约面**。

## What Changes

- **命名单源化 + 安全字符规则**：抽 `archive/naming.py`（`slugify` / `archive_filename` / `parse_archive_filename` 三件，规则单源），`archive/router.py` 与 `archive/service.py` 两处副本改经它（router 保留 `_archive_filename`/`_parse_archive_filename` 两个别名以防外部导入断裂——`backup/export.py`、`novels/router.py` 各自 import）。规则：路径分隔符（`/`、`\`）→ `-`；连续点收敛为单点；**截断后**剥首尾点（防截断边界与 `.md` 拼接出 `..` 子串）。
- **写接口与列表同源**：`service.py` 的 `archive_path` 改用 `archive_filename(chapter_ref, title)`（原按 vol/ch 数字内联拼，形与列表一致但公式不同源）——POST 归档响应与列表 filename 自此恒等。
- 契约化（backup-restore 新增「归档条目名安全字符集」）：条目名无分隔符、无 `..`（段与子串两义）、恒可被归档解析器解析；恢复后 title SHALL 等于完整条目名 stem 且 SHALL NOT 因分隔符/`..` 被截断；不含危险字符的标题命名逐字节不变。
- 无用户可见界面改动；无 DB 迁移（文件名逐次派生，无持久化引用）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `backup-restore`: 新增「归档条目名安全字符集」需求（锁定上表四行的回归口径 + 写接口/列表同源）。

## Impact

- 代码：新增 `client/backend/archive/naming.py`；`archive/router.py`（三函数改薄别名）、`archive/service.py:55`（删内联副本）；消费方 `backup/export.py:83`、`novels/router.py:618/700` 经别名零改动。
- 测试：`naming` 单元参数化（四行实证 + 截断边界反例 + 普通标题零漂移）；端到端（危险标题书导出 → 条目名安全 + `validate_paths` 通过；导入后 title 语义断言）；`test_archive_free.py` 的 archive_path 反查用例回归。
- 兼容性：普通标题（不含 `/`、`\`、不以 `.` 开头/结尾、无连续点）命名逐字节不变；含危险字符标题的名字变化仅存于逐次派生面（无持久引用）。

## Non-Goals（显式排除）

- **导入端「真标题保真」**（读 `archives/manifest.yaml` 的 title 而非 `Path(stem)`）不在本 change：现状 title=条目名 stem 是既有语义（`test_backup_roundtrip` 有注释断言），本 change 只保证「不再被分隔符/`..` 截断」；该改进另行立项。
- 不做 Windows 保留字符（`:*?"<>|`）全量清洗（非路径穿越面，会引入无关命名漂移）。
- slug 以 `r[0-9a-f]{8}-` 开头时会被导入端 `belongs_to_ref` 误判为旧稿支线而**静默丢弃**（评审发现，另单跟进）；emoji/组合字素的截断仅外观，不处理。
- 不删旧整库包中已写坏的条目名（历史包一次性产物，无重写通道）。
- `archive/service.py:144` 的 `last_chapter = vol-{chapter数据}/ch-{chapter数据}` 同类「按数据拼名」残留（幽灵章丢 `-r{8hex}` 后缀）不在本 change——其 consumer 是 threads.yaml 语义面，另单跟进（评审登记）。
