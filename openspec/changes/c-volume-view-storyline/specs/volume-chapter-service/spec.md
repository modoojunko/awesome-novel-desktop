## MODIFIED Requirements

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
