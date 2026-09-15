# volume-chapter-service Specification

## Purpose
TBD - created by archiving change 006-volume-chapter-service. Update Purpose after archive.

## Requirements

### Requirement: volume service — list_volumes（DB 全量树）

- The system SHALL provide `volumes/service.py` with `list_volumes(db, project)` querying the DB (`volume_repo.list_by_project` + `chapter_repo.list_by_project` fetched once, grouped in memory by `volume_id` to avoid N+1), returning full volume+chapter tree metadata `{ref,title,summary,chapter_count,chapters:[{id,ref,volume,chapter,title,status,word_count,has_prose,outline_status,archived}]}` — each chapter entry SHALL carry its DB `id` (uuid) so downstream consumers (e.g. the foreshadow chapter picker) can reference chapters by id instead of parsing refs.
- `GET /api/novels/{id}/volumes` SHALL be wired to `list_volumes` (replacing the file-scan response). It SHALL return the full tree with `has_prose` / `outline_status` / `archived` and SHALL NOT filter out empty chapters (N1 — filtering is the frontend's job). This is a breaking change, migrated same-commit in the frontend `useWorkbench.loadVolumes`.

#### Scenario: GET /volumes returns the DB tree

- Given a project whose volumes/chapters have DB rows
- When `GET /api/novels/{id}/volumes` is called
- Then it returns the full volume+chapter tree with `has_prose` / `outline_status` per chapter, without filtering empty chapters and without scanning files

#### Scenario: chapter entries carry DB id

- Given a project with at least one chapter
- When `GET /api/novels/{id}/volumes` is called
- Then every chapter entry includes its DB `id`, and the value equals `chapters.id` for that row
### Requirement: volume service — create_volume（MAX+1 + 双写）

- The system SHALL provide `create_volume(db, project, *, title, summary="")` computing `volume_no = max_volume_no + 1` and **ignoring / rejecting any `body.vol_num`** (B9/P2-N — prevents UNIQUE collisions).
- The gate SHALL run through `tier_or_gate(db, project, gate_settings_complete)` (free tier passes).
- Creation SHALL double-write: write `volumes/vol-N.yaml` → insert the DB row → `project.total_volumes += 1` (the current `= vol_num` overwrite is a bug) → same transaction commit; `update_phase("outline")` runs idempotently.
- `POST /api/novels/{id}/volumes` SHALL be wired to this service. DB write failure SHALL degrade without 500 (try/except + warning; YAML already written, DB row self-healed on read path).

#### Scenario: create ignores body.vol_num
- Given two existing volumes in a project
- When `POST /volumes` is called with `vol_num: 99`
- Then the new volume gets `volume_no = 3` and `total_volumes` increments by 1

#### Scenario: create double-writes YAML and DB
- Given a valid project
- When `create_volume` runs
- Then `volumes/vol-N.yaml` exists and a matching `volumes` row exists with the same title

### Requirement: volume service — get/update/delete + {ref} .yaml tolerance

- The system SHALL provide `get_volume(db, project, ref)`, `update_volume(db, project, ref, body)`, and `delete_volume(db, project, ref)`, wired to `GET / PUT / DELETE /api/novels/{id}/volumes/{ref}`.
- All three SHALL tolerate a trailing `.yaml` suffix on `{ref}` (`strip_suffix`), so legacy `vol-1.yaml` calls work unchanged.
- `update_volume` SHALL double-write `title`/`summary` to both the DB row and the YAML; all other keys (PRO outline fields: structure template / core conflicts / emotional beats / information gaps / conflict ladder / scene cards) SHALL be written to YAML only; `chapters` SHALL be popped from the YAML before writing (clears the derived snapshot, §4.3 dedup).
- `delete_volume` SHALL delete the DB row (CASCADE deletes chapter rows), then delete `volumes/vol-N.yaml`, `chapters/vol-N-ch-*.yaml`, `versions/vol-N-ch-*/`, and `archives/vol-N-*.md`; SHALL decrement `project.total_volumes` by 1 and `project.total_chapters` by the deleted chapter count in the same transaction.

#### Scenario: volume update splits DB vs YAML fields
- Given a volume with title, summary, and a PRO structure-template field
- When `update_volume` is called with a new title, summary, and structure template
- Then the DB row and YAML both reflect the new title/summary, the structure template is only in the YAML, and the YAML's embedded `chapters` list is cleared

#### Scenario: delete cascades chapters and files
- Given a volume with two chapters
- When `delete_volume` is called
- Then the volume DB row and both chapter rows are gone, the vol/chapter/version/archive files are removed, and `total_volumes`/`total_chapters` reflect the deletion

#### Scenario: ref tolerates yaml suffix
- Given a volume stored as `vol-1`
- When `GET /volumes/vol-1.yaml` and `GET /volumes/vol-1` are called
- Then both return the same volume

### Requirement: chapter service — create_chapter + POST /volumes/{ref}/chapters

- The system SHALL provide `chapters/service.py` with `create_chapter(db, project, volume_ref, title)` locating the volume via `volume_repo.get_by_ref_or_number` (tolerating `.yaml`), computing `chapter_no = max_chapter_no + 1`, `ref = f"vol-{vol.volume_no}-ch-{chapter_no}"`.
- Creation SHALL double-write: write `chapters/{ref}.yaml` (template defaults) → insert the DB row (`status='outline'`, `word_count=0`, `has_prose=False`, `outline_status='unfilled'`) → `vol.chapter_count += 1` and `project.total_chapters += 1` in the same session/commit (prevents read-modify-write races).
- Creation SHALL **no longer write the embedded `chapters` list in `volumes/vol-N.yaml`** (§4.3 — single owner, not mirrored).
- The system SHALL add `POST /api/novels/{id}/volumes/{ref}/chapters` (body `{title}`) and **remove the legacy `POST /api/novels/{id}/chapters`** — a breaking change migrated same-commit in `tests/test_readiness.py`, `tests/test_workflow_api.py`, and the frontend `useWorkbench.createChapter`. The removed endpoint SHALL no longer exist (404/405, no dual-track).

#### Scenario: chapter created under a volume increments counters
- Given a project with one volume that has one chapter
- When `POST /volumes/vol-1/chapters` is called
- Then `chapters/vol-1-ch-2.yaml` and a matching DB row exist, `chapter_count`/`total_chapters` increment, and the vol YAML embedded list is unchanged

#### Scenario: legacy POST /chapters is gone
- Given the legacy endpoint has been replaced
- When `POST /api/novels/{id}/chapters` is called
- Then it returns 404/405 and the new `POST /volumes/{ref}/chapters` is the only creation path

### Requirement: chapter service — save / save_prose + refresh_chapter_meta（双写一致性核心）

- The system SHALL provide `save_chapter(db, project, ref, data)` calling `engine.save_chapter` (YAML write + version snapshot) then `refresh_chapter_meta` (second write step).
- The system SHALL provide `save_prose(db, project, ref, prose)` reading the YAML, setting `data["prose"]=prose`, calling `engine.save_chapter`, then `refresh_chapter_meta` (dedicated to editor autosave).
- `refresh_chapter_meta(db, project, ref, data)` SHALL: if the DB row is missing, first run `ensure_volume_row` (lazy backfill, change 005); then **derive values from a re-read YAML and overwrite only the changed fields** — `title=data.get("title", row.title)`, `word_count`/`has_prose` from the re-read prose via `count_chars`, `status`/`outline_status` derived from the YAML (`confirmed`→`confirmed`; non-empty summary/task→`in_progress`; else `unfilled`); it SHALL NOT overwrite the whole row with payload defaults. DB failure SHALL degrade without 500 (try/except + warning; YAML is already written, row self-healed on read path).
- `PUT /api/novels/{id}/chapters/{ref}` SHALL be wired to `save_chapter` + `refresh_chapter_meta`; the system SHALL add `PUT /api/novels/{id}/chapters/{ref}/prose` (body `{prose}`).

#### Scenario: save_prose refreshes DB metadata from YAML
- Given a chapter with prose saved via `PUT /chapters/{ref}/prose`
- When the DB is queried
- Then `word_count` equals `count_chars(prose)`, `has_prose` is True, and the YAML remains the content owner (no prose stored in DB)

#### Scenario: DB failure degrades without 500
- Given `refresh_chapter_meta` raises an exception
- When `save_chapter` / `save_prose` is called
- Then the endpoint still returns 200 (YAML written), a warning is logged, and a later `GET /chapters/{ref}` self-heals the row

### Requirement: chapter service — read-path self-heal + confirm + delete + versions restore

- `GET /api/novels/{id}/chapters/{ref}` SHALL merge YAML content with DB metadata (`word_count`/`outline_status`/`status`/`confirmed_at`/`archived_at`); if the DB row is missing, it SHALL self-heal via `ensure_volume_row` (volume row first) then insert the chapter row from the YAML, without 500.
- `POST /api/novels/{id}/chapters/{ref}/confirm` SHALL run `gate_chapter_ready` through `tier_or_gate` (free passes, change 002), write YAML `status='confirmed'`, and set DB `status='confirmed'` / `outline_status='confirmed'` / `confirmed_at=now` in the same transaction; SHALL no longer modify the vol YAML embedded list.
- `DELETE /api/novels/{id}/chapters/{ref}` SHALL delete the YAML, the DB row, and `versions/{ref}/`, and decrement `vol.chapter_count` / `project.total_chapters` in the same transaction; SHALL no longer modify the vol YAML embedded list.
- `chapters/versions.py::restore_version` SHALL call `refresh_chapter_meta` after `save_chapter`, so restored prose refreshes `word_count`/`has_prose`/`status`/`outline_status`/`confirmed_at`.

#### Scenario: GET self-heals a deleted DB row
- Given a chapter whose DB row was manually deleted
- When `GET /chapters/{ref}` is called
- Then it returns the YAML content plus DB metadata, recreating the volume and chapter rows, and a second call is stable

#### Scenario: confirm writes both YAML and DB
- Given a chapter that passes the ready gate
- When `POST /chapters/{ref}/confirm` is called
- Then YAML `status` is `confirmed` and the DB row has `status='confirmed'`, `outline_status='confirmed'`, and a `confirmed_at` timestamp, with the vol YAML embedded list untouched

#### Scenario: restore refreshes DB metadata
- Given a chapter restored from an older version
- When `restore_version` completes
- Then the DB `word_count`/`has_prose` match the restored YAML

### Requirement: build_project_tree reads the DB（GET /tree 结构不变）

- The system SHALL rewrite `novels/service.py::build_project_tree` (`GET /api/novels/{id}/tree`) to query the DB, returning the response shape `{project_id, volumes:[{ref,title,summary,chapter_count,chapters:[{id,ref,chapter,title,status,word_count,...}]}]}` — chapter entries SHALL additionally carry DB `id`; the rest of the shape stays compatible so the frontend `useOutline.refetchTree` change is additive only.
- `word_count` SHALL use the `count_chars` semantics (B5 — fixing the current `len(prose)` whitespace drift).
- If no DB rows exist for a project (e.g. pre-backfill), the function SHALL fall back to the file-scan shape so nothing 404s.

#### Scenario: GET /tree returns DB-derived structure unchanged

- Given a project with volumes and chapters
- When `GET /api/novels/{id}/tree` is called
- Then it returns the same structure as before (frontend unchanged), with `word_count` computed via `count_chars`

#### Scenario: chapter entries carry DB id

- Given a project with volumes and chapters
- When `GET /api/novels/{id}/tree` is called
- Then every chapter entry includes its DB `id`, and the value equals `chapters.id` for that row
