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
- `get_volume` SHALL return volume detail: 新卷纲字段集（主旨/结构模板/章数目标/核心矛盾/整体目标/预期结局/登场人物行集/关键剧情节点行集/埋下伏笔/揭露信息）＋ `chapters` 行集（**主线过滤**，逐行含 `ref/volume/chapter/title/status/word_count/has_prose/outline_status/archived/outline_summary`）＋ `ghost_count`（本卷旧稿支线章数）；旧代字段键 SHALL NOT 再出现。
- `update_volume` SHALL 把卷纲全字段（含行集整体替换）落 DB 真表——DB 为卷纲唯一事实源；运行时 `volumes/vol-N.yaml` 双写随数据全量入库退役（YAML 仅由导出链派生），`chapters` 派生快照清除口径（§4.3 dedup）随之失去对象、同步退役。
- `delete_volume` SHALL delete the DB row (CASCADE deletes chapter rows), then delete `volumes/vol-N.yaml`, `chapters/vol-N-ch-*.yaml`, `versions/vol-N-ch-*/`, and `archives/vol-N-*.md`; SHALL decrement `project.total_volumes` by 1 and `project.total_chapters` by the deleted chapter count in the same transaction.

#### Scenario: volume update splits DB vs YAML fields
- Given a volume with title, summary, and a structure-template field
- When `update_volume` is called with a new title, summary, and structure template
- Then the DB row reflects all three (structure template lands in the volumes table), and 运行时不再写任何 YAML 镜像——`volumes/vol-N.yaml` 仅由导出链派生（行名保留，语义已随数据全量入库切换为「DB 全字段 / YAML 零运行时写入」）

#### Scenario: volume detail is mainline-only
- Given a volume with 3 mainline chapters and 1 ghost (rewrite) chapter
- When `GET /volumes/vol-1` is called
- Then `chapters` contains the 3 mainline rows (each with `outline_summary`), `ghost_count` is 1, and no legacy outline keys appear

#### Scenario: delete cascades chapters and files
- Given a volume with two chapters
- When `delete_volume` is called
- Then the volume DB row and both chapter rows are gone, the vol/chapter/version/archive files are removed, and `total_volumes`/`total_chapters` reflect the deletion

#### Scenario: ref tolerates yaml suffix
- Given a volume stored as `vol-1`
- When `GET /volumes/vol-1.yaml` and `GET /volumes/vol-1` are called
- Then both return the same volume

### Requirement: chapter service — create_chapter + POST /volumes/{ref}/chapters

- The system SHALL provide `chapters/service.py` with `create_chapter(db, project, volume_ref, title, plot=None, challenge=None, ending=None, acts=None, stage=None)` locating the volume via `volume_repo.get_by_ref_or_number` (tolerating `.yaml`), computing `chapter_no = max_chapter_no + 1`, `ref = f"vol-{vol.volume_no}-ch-{chapter_no}"`.
- 章 SHALL 以 **DB 行为唯一所有者**（本块同时修正此前规格残留的 YAML 双主表述：建章 SHALL NOT 写任何章 YAML 文件；读取即真相，不存在"从文件自愈"路径）。Creation SHALL insert the DB row (`status='outline'`, `word_count=0`, `has_prose=False`, `outline_status='unfilled'`) → `vol.chapter_count += 1` and `project.total_chapters += 1` in the same session/commit.
- 拆章排上（请求体四段非空时）SHALL 在**同一事务**内经既有装配写回（`store.apply_chapter_data`——其 SHALL NOT 自行 commit）写入：本章剧情→`summary`、本章结尾→`ladder_exit`、挑战→`challenge`、阶段→`plot_stage`（c-og-slim-v2：「本章行动」`chapter_acts` 退役，键被服务端忽略）；SHALL NOT 出现"章已建、关键剧情字段为空"的中间态。SHALL NOT 为四段新写第二套标量写入路径。
- 请求校验 SHALL 在 API schema 层**先于建章**：`stage` 越出六档闭集、`acts` 超 4 行或单行超 60 字、任一字段超 DB 列宽 → 422 且 SHALL NOT 建章。
- 重复提交 SHALL 幂等：`(novel_id, ref)` 唯一约束冲突 SHALL 被捕获、重读既有行并按成功返回（两响应指向同一章），SHALL NOT 冒 500（#457 卷上同类事故只修了前端的服务端补课）。
- Creation SHALL **no longer write the embedded `chapters` list in `volumes/vol-N.yaml`**（卷 YAML 内嵌清单路径已随数据全量入库退役——卷详情即真相）。
- The system SHALL keep `POST /api/novels/{id}/volumes/{ref}/chapters` as the only creation path and **remove the legacy `POST /api/novels/{id}/chapters`** (404/405, no dual-track).

#### Scenario: chapter created under a volume increments counters
- Given a project with one volume that has one chapter
- When `POST /volumes/vol-1/chapters` is called
- Then a matching DB row exists with `chapter_no=2`, `chapter_count`/`total_chapters` increment, and no chapter YAML file is created

#### Scenario: 拆章排上一次写全
- **WHEN** `POST /volumes/vol-1/chapters` 携带 `{title, plot, challenge, ending, acts, stage}` 被调用
- **THEN** 返回的章同时带齐四段（剧情/挑战/结尾/阶段），任一环节失败 SHALL 回滚且不留章

#### Scenario: 重复提交幂等
- **WHEN** 同一请求在极短时间内到达两次
- **THEN** 两响应指向同一章，库中只有一行，SHALL NOT 返回 500

#### Scenario: 阶段越界拒绝且不留章
- **WHEN** 排上请求携带 `stage`＝「高潮」（不在六档）
- **THEN** 返回 422 且 SHALL NOT 建章

#### Scenario: legacy POST /chapters is gone
- Given the legacy endpoint has been replaced
- When `POST /api/novels/{id}/chapters` is called
- Then it returns 404/405 and the new `POST /volumes/{ref}/chapters` is the only creation path

### Requirement: chapter service — save / save_prose + refresh_chapter_meta（双写一致性核心）

- 章保存 SHALL 走**统一写入口**（`chapters.store` 的装配写回族：读现行章 JSON → 合并 → 整表写回 → 派生元数据同事务刷新），**DB 行为唯一所有者**——本块同时修正此前规格残留的 YAML 双主表述（章文件、版本快照目录、读路径自愈均已随数据全量入库退役）。
- `PUT /api/novels/{id}/chapters/{ref}`（章纲整表回传）与 `PUT /api/novels/{id}/chapters/{ref}/prose`（正文自动保存）SHALL 复用同一写入口；保存 SHALL 刷新 `word_count`/`has_prose`/`status`/`outline_status` 等派生元数据；拆章写入的三列 SHALL 随整表回传保留（见 chapter-data）。
- 版本快照 SHALL 为 DB 表 `chapter_versions`（随保存落行）；恢复（restore_version）SHALL 经同一写入口回写并刷新派生元数据。

#### Scenario: save_prose refreshes DB metadata from YAML
- **WHEN** 正文经 `PUT /chapters/{ref}/prose` 自动保存
- **THEN** DB `word_count`＝本次字数、`has_prose`=True，拆章三列原样保留

#### Scenario: DB failure degrades without 500
- **WHEN** 派生元数据刷新抛异常
- **THEN** 接口不冒 500，告警落日志，行状态在下次读取时按 DB 现状返回

#### Scenario: 保存章纲保留拆章三列
- **WHEN** 对拆章排上的章保存章纲（整表回传）
- **THEN** challenge/plot_stage 原样保留，word_count/status 按本次内容刷新

#### Scenario: 拆章三列在任一保存路径均不丢失
- **WHEN** 正文自动保存与章纲保存先后发生
- **THEN** 先写入方的 challenge/plot_stage 在后一次保存后仍原样（无旧快照互抹窗口）

### Requirement: chapter service — read-path self-heal + confirm + delete + versions restore

- `GET /api/novels/{id}/chapters/{ref}` SHALL return the chapter from the DB row（行即真相）；DB 行缺失 SHALL 返回 404（章文件与"从文件自愈"路径已随数据全量入库退役，SHALL NOT 复活）。
- `POST /api/novels/{id}/chapters/{ref}/confirm` SHALL 经统一写入口在同一事务置 `status='confirmed'` / `outline_status='confirmed'` / `confirmed_at=now`（沿用既有档位门 `tier_or_gate`，免费放行）。
- `DELETE /api/novels/{id}/chapters/{ref}` SHALL 加**双重守卫**：仅当该章为**本卷最后一章**（`chapter_no`＝该卷当前最大）**且拟定且无正文**时可删；否则 409 并引导——非尾章→「先删其后的章节，或走重拆整卷」；有正文/已归档→「重写或归档」。SHALL NOT 删除有正文/已归档章及其正文/归档 CASCADE。守卫通过后 SHALL 删 DB 行（章纲子表/版本快照/归档/提示词经 FK CASCADE）并同事务递减 `vol.chapter_count` / `project.total_chapters`。
- 删尾章后章号 SHALL 自然复用（建章 MAX+1）：删除本卷最后一章后再次建章 SHALL 复用同一章号，卷内 SHALL NOT 出现"章数少于最大章号"的跳号形态。
- **重拆整卷** SHALL 按章号**降序**逐章删除（每一步都满足"尾章＋拟定＋无正文"），仅移除拟定且无正文的章；有正文或已归档的章 SHALL NOT 被移除。卷级删除（delete_volume）沿用既有级联语义，SHALL NOT 受单章守卫约束。
- `chapters/versions.py::restore_version` SHALL 经统一写入口回写版本内容并刷新派生元数据（`word_count`/`has_prose`/`status`/`outline_status`/`confirmed_at`）。

#### Scenario: GET self-heals a deleted DB row
- **WHEN** 请求一个 DB 行不存在的章 ref
- **THEN** 返回 404，SHALL NOT 由任何文件重建行——本场景显式替代原"文件自愈"断言（章文件已随数据全量入库退役）

#### Scenario: confirm writes both YAML and DB
- **WHEN** 一个通过就绪门的章 confirm
- **THEN** DB 行 `status='confirmed'`、`outline_status='confirmed'`、`confirmed_at` 同事务落库；YAML 侧已退役，本场景显式替代原"写 YAML"断言

#### Scenario: 有正文的章拒绝删除
- **WHEN** 对已有正文（草稿）的章调用 DELETE
- **THEN** 返回 409，正文、归档、版本均保留，提示走重写或归档

#### Scenario: 非尾章拟定章拒绝单删
- **WHEN** 卷内有拟定章第 2、3、4 章，对第 2 章调用 DELETE
- **THEN** 返回 409 并提示「先删其后的章节，或走重拆整卷」，SHALL NOT 留下章号空洞

#### Scenario: 删尾章后章号复用
- **WHEN** 卷内最新一章（拟定无正文）被删除后再次拆章
- **THEN** 新章复用同一章号，左树与顶栏不出现跳号

#### Scenario: restore refreshes DB metadata
- **WHEN** 从旧版本恢复一章
- **THEN** 经统一写入口回写后，DB `word_count`/`has_prose` 与恢复内容一致，`status`/`outline_status` 按派生口径刷新

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
