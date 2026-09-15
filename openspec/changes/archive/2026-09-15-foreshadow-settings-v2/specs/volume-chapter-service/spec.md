# volume-chapter-service 变更（增量）

## MODIFIED Requirements

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
