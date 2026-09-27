# volume-chapter-service

## MODIFIED Requirements

### Requirement: volume service — create_volume（MAX+1 + 双写）

- The system SHALL provide `create_volume(db, project, *, title, summary="")` computing `volume_no = max_volume_no + 1` and **ignoring / rejecting any `body.vol_num`** (B9/P2-N — prevents UNIQUE collisions).
- The gate SHALL run through `tier_or_gate(db, project, gate_settings_complete)` (free tier passes).
- Creation SHALL double-write: write `volumes/vol-N.yaml` → insert the DB row → `project.total_volumes += 1` (the current `= vol_num` overwrite is a bug) → same transaction commit; the phase marking SHALL run **idempotently and leniently（只进不退）**——same-phase is a no-op, a legal transition (`settings→outline`、`archive→outline` 新循环) advances, a legacy `init` row advances straight to `outline`, and an illegal backward jump (e.g. `write→outline` / `prompt→outline` while re-planning a volume mid-writing) SHALL be skipped leaving the phase unchanged. The volume write SHALL NOT fail with 500 because of the phase machine.
- `POST /api/novels/{id}/volumes` SHALL be wired to this service. DB write failure SHALL degrade without 500 (try/except + warning; YAML already written, DB row self-healed on read path).

#### Scenario: create ignores body.vol_num
- Given two existing volumes in a project
- When `POST /volumes` is called with `vol_num: 99`
- Then the new volume gets `volume_no = 3` and `total_volumes` increments by 1

#### Scenario: create double-writes YAML and DB
- Given a valid project
- When `create_volume` runs
- Then `volumes/vol-N.yaml` exists and a matching `volumes` row exists with the same title

#### Scenario: create volume at write phase does not 500
- Given a project whose `current_phase` is `write` (or `prompt`) and no volume rows
- When `POST /volumes` runs（抽卡「确认这一套，成卷」落库）
- Then the volume is created (`volume_no = 1`), `current_phase` stays unchanged (只进不退), and no ValueError/500 is raised

#### Scenario: create volume at init marks outline
- Given a legacy project whose `current_phase` is `init`
- When `create_volume` runs
- Then `current_phase` becomes `outline`（新建书创建即 `settings`，`init` 仅存量行捷径）

#### Scenario: legal transitions still advance
- Given a project whose `current_phase` is `settings` or `archive`
- When `create_volume` runs
- Then `current_phase` becomes `outline`
