# volume-chapter-index Specification

## Purpose
TBD - created by archiving change 005-index-db-base. Update Purpose after archive.

## Requirements

### Requirement: volumes table

- The system SHALL create a `volumes` table with columns: `id` (String(36) PK, default uuid4), `project_id` (String(36) FK → projects.id, NOT NULL, indexed), `volume_no` (Integer, NOT NULL), `title` (String(200), NOT NULL), `summary` (Text, NOT NULL, default `''`), `chapter_count` (Integer, NOT NULL, default 0), `created_at` / `updated_at` (DateTime, server defaults, `updated_at` on-update), matching development-plan §5.1.
- The table SHALL enforce a UNIQUE constraint on `(project_id, volume_no)`.
- `Volume` SHALL declare a `chapters` relationship with `cascade="all, delete-orphan"` back-populated to `Chapter.volume`.

#### Scenario: Table is created on startup
- Given the backend starts with a fresh SQLite database
- When `Base.metadata.create_all` runs in the lifespan
- Then a `volumes` table exists with the specified columns, and `(project_id, volume_no)` is unique

#### Scenario: Deleting a volume cascades to chapters
- Given a volume with chapters in the database and `PRAGMA foreign_keys=ON`
- When the volume row is deleted
- Then its chapter rows are deleted with it

### Requirement: chapters table

- The system SHALL create a `chapters` table with columns: `id` (String(36) PK, default uuid4), `project_id` (String(36) FK → projects.id, NOT NULL, indexed), `volume_id` (String(36) FK → volumes.id with `ondelete="CASCADE"`, NOT NULL, indexed), `chapter_no` (Integer, NOT NULL), `ref` (String(64), NOT NULL), `title` (String(200), NOT NULL), `status` (String(20), NOT NULL, default `'outline'`), `word_count` (Integer, NOT NULL, default 0), `has_prose` (Boolean, NOT NULL, default False), `outline_status` (String(20), NOT NULL, default `'unfilled'`), `confirmed_at` / `archived_at` (DateTime, nullable), `ladder_exit` (String(300), nullable — 章末落点，提示词前情与新章起点消费), `created_at` / `updated_at` (DateTime, server defaults), matching development-plan §5.2.
- The table SHALL enforce a UNIQUE constraint on `(project_id, ref)` and an INDEX on `(project_id, volume_id, status)`.
- `Chapter.volume_id` SHALL be guarded by both the FK `ondelete="CASCADE"` and the ORM relationship cascade (double insurance).

#### Scenario: Chapter rows are uniquely keyed by ref

- Given two chapters with the same `ref` under the same project
- When both rows are inserted
- Then the second insert fails on the `(project_id, ref)` unique constraint

#### Scenario: Existing database gains ladder_exit via idempotent DDL

- Given a pre-existing chapters table without `ladder_exit`
- When the backend starts and the lifespan runs the migration
- Then the column exists (nullable) and startup is not blocked if it already exists

### Requirement: projects.index_status column

- The system SHALL add an `index_status` column (String(20), NOT NULL, default `'none'`) to the `projects` model, with value domain `none` / `done`.
- The lifespan SHALL issue `ALTER TABLE projects ADD COLUMN index_status TEXT DEFAULT 'none'` idempotently (try/except, same pattern as `source` / `backfill_status`), so existing databases gain the column without error.
- `Project` SHALL declare a `volumes` relationship with `cascade="all, delete-orphan"` back-populated to `Volume.project`.

#### Scenario: Existing database gains index_status via ALTER
- Given a pre-existing projects table without `index_status`
- When the backend starts and the lifespan runs the ALTER
- Then the column exists with default `'none'`, and startup is not blocked if the column already exists

### Requirement: volume repository

- The system SHALL provide `repositories/volume_repo.py` with: `list_by_project(db, project_id)` (ORDER BY `volume_no`), `get_by_ref_or_number(db, project_id, ref_or_no)` (tolerating a trailing `.yaml`), `get_by_volume_no(db, project_id, volume_no)`, `max_volume_no(db, project_id)` (returns 0 when no rows), `upsert(db, project_id, volume_no, *, title, summary="")` (matched by the `(project_id, volume_no)` unique key), and `count_by_project(db, project_id)`.

#### Scenario: volume upsert inserts then matches
- Given a project with no volume rows
- When `upsert` is called for volume 1 and then again for volume 1
- Then exactly one row exists for that project/volume, and the second call returns the existing row

#### Scenario: ref lookup tolerates yaml suffix
- Given a volume stored as `vol-1`
- When `get_by_ref_or_number` is called with `vol-1.yaml` and with `vol-1`
- Then both return the same row

### Requirement: chapter repository

- The system SHALL provide `repositories/chapter_repo.py` with: `list_by_project(db, project_id)` (single query, for in-memory grouping without N+1), `get_by_ref(db, project_id, ref)`, `has(db, project_id, ref)`, `upsert(db, project_id, volume_id, *, chapter_no, ref, title, status="outline", word_count=0, has_prose=False, outline_status="unfilled", confirmed_at=None, archived_at=None)`, `delete(db, chapter_id)`, `max_chapter_no(db, project_id, volume_id)`, `count_by_project(db, project_id)`, and `count_archived(db, project_id)` (status `'archived'`, used by `gate_archived`).

#### Scenario: chapter upsert preserves fields
- Given a chapter row created by `upsert` with title and word_count
- When `get_by_ref` retrieves it
- Then all supplied fields are returned unchanged

### Requirement: ensure_volume_row lazy backfill entry

- The system SHALL provide `ensure_volume_row(db, project_id, volume_no, *, title=None)` in `repositories/volume_repo.py` as the single lazy-backfill entry point: if the volume row is missing, it SHALL upsert the volume (title falling back to 「导入卷 N」); if the volume row exists, it SHALL return it directly.
- It SHALL be reusable by the change-006 double-write path and by read-path self-healing; chapter rows are created by the backfill scan after the volume row is ensured.

#### Scenario: missing volume row is created with fallback title
- Given a project with no volume row
- When `ensure_volume_row` is called with a title
- Then the volume row exists with that title, and a second call returns the same row without inserting a duplicate

#### Scenario: existing volume row is returned as-is
- Given an existing volume row for volume 2
- When `ensure_volume_row` is called for volume 2
- Then it returns the existing row and does not modify it

### Requirement: count_chars unified word-count semantics

- The system SHALL provide `count_chars(text: str) -> int` in `novels/service.py` computing `len(re.sub(r"\s+", "", text or ""))`, matching the frontend `countChars` (whitespace-stripped char count, B5).

#### Scenario: whitespace is stripped before counting
- Given the text `"  你好 世界 \n abc"`
- When `count_chars` is applied
- Then it returns 7 (`你好世界` + `abc`), matching the frontend count

### Requirement: idempotent volumes/chapters backfill

- The system SHALL provide `filesystem/index_volumes_chapters.py` with `index_volumes_chapters()`, `reindex_project(project_id)`, and a shared `_scan_project(root)`.
- The backfill SHALL enumerate all project root paths (reusing the `filesystem/migrate.py` pattern, including imported projects) and, per project, scan `volumes/vol-N.yaml`: INSERT-if-missing the volume row (title from YAML, falling back to 「导入卷 N」), then walk the embedded `chapters` list with `ref=f"vol-{vol_no}-ch-{chapter}"`.
- Per chapter, the SHALL source of truth is `chapters/{ref}.yaml`: read title/status/prose from it, compute `word_count=count_chars(prose)`, `has_prose=bool(prose.strip())`, and derive `outline_status` (status `'confirmed'` → `'confirmed'`; non-empty prose → `'in_progress'`; else `'unfilled'`). A chapter referenced in the volume list but missing its YAML file SHALL still get a placeholder row (title from the embedded list, `word_count=0`).
- The backfill SHALL self-heal orphan chapter files (DB has no row and no volume row exists): reverse-lookup the `volume_no`, create a placeholder volume row, and insert the chapter row.
- The backfill SHALL self-heal redundant counters: set `project.total_volumes` / `project.total_chapters` to the actual COUNTs.
- The backfill SHALL be run-once: skipped when `project.index_status == "done"`, and sets it to `"done"` after scanning (both the guard and INSERT-if-missing provide double insurance so restarts are idempotent).
- The backfill SHALL only ever insert, never delete: orphan DB rows whose YAML files were removed by the write path SHALL NOT be cleaned up.
- `reindex_project(project_id)` SHALL force a rescan of a single project (not gated by `index_status`) for the import scenario.

#### Scenario: running backfill twice is idempotent
- Given an existing project with volume and chapter YAML files
- When `_scan_project` runs twice against the same project
- Then the row counts in `volumes` and `chapters` are unchanged after the second run

#### Scenario: embedded word_count is corrected from the chapter file
- Given a volume YAML whose embedded chapter list reports `word_count: 0`, and a `chapters/vol-1-ch-1.yaml` that actually contains prose
- When the backfill scans the project
- Then the chapter row reports the true whitespace-stripped character count and `has_prose=True`

#### Scenario: orphan chapter file is adopted by a placeholder volume
- Given a `chapters/vol-2-ch-1.yaml` whose volume YAML does not exist
- When the backfill scans the project
- Then a volume row for volume 2 and the chapter row are both created

#### Scenario: completed projects are not rescanned
- Given a project whose `index_status` is already `"done"`
- When `_scan_project` runs (non-forced)
- Then no new rows are inserted

### Requirement: lifespan mount and import reindex

- The system SHALL call `index_volumes_chapters()` from the lifespan, after the settings migration and near the tone backfill, wrapped in try/except with a warning so a failure does not block startup.
- `novels/router.py::import_persist` SHALL call `reindex_project(project_id)` after writing YAML files and creating the project record, so an imported project's tree is queryable immediately without a restart.

#### Scenario: import makes the tree queryable immediately
- Given a project is imported (YAML files written and project record created)
- When `import_persist` completes
- Then the volume and chapter rows exist, so the tree is queryable without a restart

#### Scenario: backfill failure does not block startup
- Given a project whose scan raises an exception
- When the lifespan runs `index_volumes_chapters`
- Then startup continues with a warning logged, and other projects are still scanned

### Requirement: prompt-crafting chapter columns and sub-table

- `chapter_scene_cards` SHALL gain nullable columns `weight` (String(10); value domain `high`/`mid`/`low`) and `focus` (String(50); value domain 核心冲突/人物情绪/信息差), consumed by prompt material assembly for 笔墨分配.
- The system SHALL create a `chapter_micro_payoffs` table (读者获得/爽点) with columns: `id` (String(36) PK), `chapter_id` (String(36) FK → chapters.id `ondelete="CASCADE"`, NOT NULL, indexed), `sort_order` (Integer, NOT NULL), `kind` (String(50), NOT NULL — 类型枚举 info/relationship/emotion/clue/ability/resource/recognition), `description` (String(300), NOT NULL), `location` (String(20), NOT NULL, default 前段 — 前段/中段/后段).
- The table SHALL enforce a UNIQUE constraint on `(chapter_id, sort_order)` and cascade with chapter deletion (same `_ChapterChildMixin` pattern).
- All new columns/tables SHALL be applied to existing databases via idempotent startup DDL (存量库幂等，启动不因已存在而失败).

#### Scenario: New columns on a fresh database

- Given the backend starts with a fresh SQLite database
- Then `chapter_scene_cards` has `weight`/`focus` columns and `chapter_micro_payoffs` exists with the specified columns and unique constraint

#### Scenario: Existing database migrates idempotently

- Given a pre-existing database from before this change
- When the backend starts
- Then the scene-card columns and the micro-payoffs table are added without error, and a second startup is also a no-op success

#### Scenario: Deleting a chapter cascades to micro payoffs

- Given a chapter with micro_payoffs rows and `PRAGMA foreign_keys=ON`
- When the chapter row is deleted
- Then its micro_payoffs rows are deleted with it

### Requirement: 导入来源与导入会话 schema

- `chapters` 表 SHALL 增加 `origin`（String，NOT NULL，`server_default='authored'`，值域 `authored|import`）与 `imported_at`（DateTime，nullable）；SHALL NOT 新增 `status=imported` 值。
- `projects`（书）表 SHALL 增加 `import_kind`（String，NOT NULL，`server_default='authored'`，值域 `authored|direct|legacy`；`deconstruct` 由后续 change 追加）与 `import_token`（String，nullable，UNIQUE）。
- 系统 SHALL 新增 `import_sessions` 表：`id`、`manifest_json`、`source_path`、`source_sha256`、`encoding`、`char_count`、`expires_at`、`created_at`；用于第 1 步到落库/建任务之间复用解析结果，避免重复上传或重新解析。
- 所有新增 NOT NULL 字符串列 SHALL 带 `server_default`；迁移 SHALL 幂等、可重入；旧库升级后不得出现空字符串冒充 `authored/direct/legacy`。

#### Scenario: 旧库升级后列有默认值
- **WHEN** 一个旧库启动并执行 schema 升级
- **THEN** 旧章 origin 为 `authored`，旧书 import_kind 为 `authored`，不出现空字符串

#### Scenario: 导入会话过期
- **WHEN** 作者在第 1 步解析后超过 TTL 才提交
- **THEN** 返回可执行错误「请重新解析文件」，不创建半本书

### Requirement: 旧导入书 backfill

- 系统 SHALL 在数据 carry 完成后按 `app_meta.import_backfill_v1` 标记幂等执行旧书回填；启动期 SHALL 对同一保守规则补跑一次（升级用户可能无需 carry），carry 完成强制重扫。
- 回填规则：`projects` 中 `source='import'` 且 `import_kind` 为空/authored 的书 → `import_kind='legacy'`；只把与书 `created_at` 同窗（≤10 分钟）内创建的章标为 `origin='import'`、`imported_at=created_at`；章 `status` SHALL NOT 被改写。备份恢复书（书创建时间远早于章行）与导入后作者续写的章 SHALL 保持 `authored`，SHALL NOT 整书改写。
- 回填 SHALL 可重复执行且结果一致；失败 SHALL 不写标记，下次启动重试；没有可证明的旧导入书时 SHALL NOT 落标记。

#### Scenario: 旧导入书迁移
- **WHEN** 旧库中的导入书被 carry 到新库并执行回填
- **THEN** 该书 import_kind=legacy，其导入批次内的非归档章 origin=import、status 保持原值，续写落 N+1

#### Scenario: 导入后作者续写不被误标
- **WHEN** 旧导入书里存在导入完成之后作者新建的章
- **THEN** 该章保持 origin=authored，仍参与完本计数

#### Scenario: 备份恢复书不整书改写
- **WHEN** 一本作者书从备份包恢复（书创建时间远早于恢复出的章）
- **THEN** 所有章保持 origin=authored，回填不改写

#### Scenario: 重跑回填不改结果
- **WHEN** 回填因中断重跑
- **THEN** 已标记的书不重复写入，章 origin/status 与第一次结果一致
