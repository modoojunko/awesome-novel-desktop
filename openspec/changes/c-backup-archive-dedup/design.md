## Context

`client/backend/backup/export.py::dump_book_into` 遍历卷写入 `volumes/`、逐章写入 `chapters/versions/prompts/`，**卷循环体内**还包含一段书级归档查询（`select(Archive).join(Chapter).where(Chapter.project_id == project.id)`，含 `content` 大 TEXT 列）与 zip 写入。归档数据与单卷无关，放卷循环内属实现笔误：N 卷书每条归档写 N 次（zip 允许同名重复条目并发 `Duplicate name` 警告）、书级全量 SELECT 被每卷重拉一次、`manifest_archives` 被追加 N 遍。现有导出用例的种子或零卷（`test_backup_export.py` 零卷零归档）或单卷（`test_backup_roundtrip.py` 1 卷 1 归档、只断 `[0]`），单卷不触发重复，缺陷静默。

## Goals / Non-Goals

**Goals:**
- 归档查询与写入提升到卷循环之后（书级执行一次、带显式排序），产物形状达到 specs 新条款。
- 多卷书回归用例锁定条目唯一性与 manifest 计数（先红后绿，断言形态见下）。

**Non-Goals:**
- 不改归档渲染内容、`_archive_filename` 命名（含 `/` 标题的路径缺口另行跟进，见 proposal Non-Goals）、manifest 字段集与 `format_version`。
- 不动导入端：zip 同名重复条目此前由「read 取最后一条」语义掩盖，重复条目内容等值，修复后导入结果逐字节一致。
- 不处理卷/章循环本身的逐章查询效率（既有形态，非本缺陷）。

## Decisions

**1. 平移而非重写：仅把归档块移出循环，变量与命名保持，查询补排序。**
`archives` 查询（补 `.join(Volume).order_by(Volume.volume_no, Chapter.chapter_no)`）、`for arch in archives:` 写入、`manifest_archives` 追加整体下移到卷循环之后；`put`/`put_yaml` 闭包沿用（实测其只捕获 `zf`/`prefix`，无循环变量依赖）。manifest 落盘本就在循环外，平移后仍「先条目后 manifest」。实测修复后 manifest 顺序 = 修复前去重序，无跨版本顺序回归；补排序使其确定（不再依赖 SQLite 计划）。

**2. 回归测试断言形态（实测钉死，防写歪）。**
zipfile 同名 `writestr` **保留重复**：`namelist()` 计数保留（修复前 4 / 后 2），`set()` 会塌成 2——**必须用 list 计数**；`archives/` 下还有 `manifest.yaml`，过滤要带前缀与 `.md` 后缀（整库包前缀 `projects/{slug}/`）。修复前真机复现：2 卷 × 每卷 1 归档 → `.md` 条目 4、manifest 4 条。断言样例：

```python
arch = [n for n in zf.namelist()
        if n.startswith(f"projects/{slug}/archives/") and n.endswith(".md")]
assert len(arch) == 2 and len(set(arch)) == 2          # 修复前 len=4 → 必红
man = yaml.safe_load(zf.read(f"projects/{slug}/archives/manifest.yaml"))["archives"]
assert len(man) == 2 and len({m["filename"] for m in man}) == 2   # 修复前 4 → 必红
assert set(man[0]) == {"filename", "ref", "title", "summary", "archived_at"}
```

「单卷书行为不变」scenario 对接到新增 1 卷 1 归档用例（条目名/条目字节/manifest 字段集），既有 `test_backup_roundtrip.py` 层 7 也可扩断言。

替代方案：写入处按 `name` 去重——被否，两条硬事实：① `manifest_archives` 的 N 倍追加是独立语句，写入处去重修不到（需第二道去重）；② 书级全量 SELECT（含 content 大 TEXT）的 N×A 次放大原样保留。

## Risks / Trade-offs

- [依赖 zip 同名重复语义的隐藏消费方] → 实查零消费方：importer 用 `set(namelist())` 去重、`read()` 取最后一条且内容等值（修复后逐字节一致）；前端无 zip 解析；pytest 全量回归兜底。
- [多卷书种子构造成本] → 复用既有 fixture 模式，新增约 40 行测试（先红后绿已验证可红）。
- [边界形态] → 实测备查：0 卷但有归档不可达（`Chapter.volume_id` NOT NULL + FK CASCADE；修复后此类假想书反而会导出，单向变好）；ghost 章有 volume_id 正常随卷导出；一章至多一条归档（`models/archive.py` 唯一约束 + upsert）；`_archive_filename` 在 ref 语法与 `uq_chapters_project_ref` 下同书不可能碰撞。

## Migration Plan

单函数内代码块平移＋查询补排序＋测试，一次 commit；随下次发版带出（备份包为本地灾备资产，无线上数据迁移）。回滚 = revert 该 commit（旧包含重复条目导入端行为不变），无状态残留。

## Open Questions

无。
