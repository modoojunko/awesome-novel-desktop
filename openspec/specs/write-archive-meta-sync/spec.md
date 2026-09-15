# write-archive-meta-sync Specification

## Purpose
TBD - created by archiving change 007-write-archive-meta-sync. Update Purpose after archive.

## Requirements

### Requirement: SSE 初稿写完刷新 DB 章元数据

系统 SHALL 实现本条——`write_chapter` 的 SSE 流完成后（`_stream_chapter` `is_done`），已落盘 YAML 的章必须刷新 DB 章行（`refresh_chapter_meta`），使 `word_count`/`has_prose`/`outline_status` 与正文一致。

#### Scenario: SSE 初稿完成后 DB word_count 反映正文

- Given 一卷一章的项目，章 YAML `prose` 为空，DB 章行 `word_count=0`
- When `write_chapter` 流完成写入 prose「灯火在雨里摇晃」
- Then DB 章行 `word_count == 7`，`has_prose == True`，`outline_status == "in_progress"`
- And DB 写失败时不 500（YAML 已落，读路径自愈）

### Requirement: 续写完成后刷新 DB 章元数据

系统 SHALL 实现本条——`continue_writing` 的 SSE 流完成后（`stream_continue` `is_done`），合并后的 prose 必须刷新 DB 章行。

#### Scenario: 续写完成后 DB word_count 反映新正文

- Given 已保存 prose「abc」的章，DB `word_count=3`
- When 续写追加「def」流完成，章 prose 变为「abcdef」
- Then DB 章行 `word_count == 6`

### Requirement: 归档停写内嵌列表并同步 DB 章行 archived 态

系统 SHALL 实现本条——`archive_chapter` 不得再写 `volumes/vol-N.yaml` 内嵌 chapters 列表（§4.3 唯一属主非镜像，change 006 起停写）；`archive` 端点必须在归档后把 DB 章行置 `status='archived'` + `archived_at=now`。

#### Scenario: 归档后 DB 章行 archived 且内嵌列表不再更新

- Given 一卷一章项目，卷 YAML 内嵌 `chapters=[]`
- When 归档该章（`POST .../chapters/vol-1-ch-1/archive`，full_text ≥ 100 字）
- Then 卷 YAML 内嵌 `chapters` 仍为 `[]`（不写）
- And DB 章行 `status == "archived"`，`archived_at` 非空
- And `GET /volumes` 树该章 `archived == True`

#### Scenario: 归档文本过短仍拒绝

- Given 项目与章
- When `POST .../archive` body `full_text` 少于 100 字
- Then 返回 400，DB 章行状态不变

### Requirement: 项目详情响应补 genre 字段

系统 SHALL 实现本条——`GET /novels/{id}` 响应必须含 `genre`（题材库 id）与 `genre_name`（题材名）；未选题材时二者为 `None`。

#### Scenario: 已选题材的项目详情含 genre

- Given 项目已 `PUT /settings/genre` 选 `genre_id=urban-romance`
- When `GET /novels/{id}`
- Then 响应 `genre == "urban-romance"`，`genre_name` 为题材库名称（或 `None` 若题材已删）

#### Scenario: 未选题材的项目详情 genre 为 None

- Given 未设置题材的项目
- When `GET /novels/{id}`
- Then 响应 `genre == None` 且 `genre_name == None`，不 500

### Requirement: unarchive 恢复章为可编辑态

系统 SHALL 实现本条——`POST /chapters/{ref}/unarchive` 必须把归档章恢复为可编辑：章 YAML `status` 置 `draft`、清除 `archive_path`/`archive_summary`、保留 prose；DB 章行清 `archived_at`、`status` 置 `draft`。

#### Scenario: 归档章 unarchive 后树恢复非归档态

- Given 已归档章（YAML `status='archived'` + DB `archived_at` 非空）
- When `POST .../chapters/vol-1-ch-1/unarchive`
- Then YAML `status == "draft"`，无 `archive_path`/`archive_summary`
- And DB 章行 `archived_at is None`，`status == "draft"`
- And `GET /volumes` 树该章 `archived == False`

### Requirement: 归档联动写伏笔 mentioned 引用列

- 章节归档时，系统 SHALL 把「本章引入的活跃伏笔」的 mentioned_in_chapter_id 更新为当前章 id（单条 UPDATE，替代旧「整文件读改写 status:mentioned」的做法）。
- 伏笔 status 枚举（active/resolved/abandoned）SHALL NOT 被归档联动修改；mentioned_in_chapter_id 仅作归档留痕，不参与注入与门禁判定。
- 归档联动 SHALL 幂等：重复归档同一章不改变已写入的引用。

#### Scenario: 归档本章给引入伏笔打上引用

- **WHEN** 归档第 3 章，且某活跃伏笔的 introduced_chapter_id 指向第 3 章
- **THEN** 该伏笔的 mentioned_in_chapter_id 被置为第 3 章的 id，status 仍为 active

#### Scenario: 归档其他章不误伤

- **WHEN** 归档第 5 章，而某伏笔引入于第 3 章
- **THEN** 该伏笔的 mentioned_in_chapter_id 保持不变

#### Scenario: 重复归档幂等

- **WHEN** 同一章被归档流程执行两次
- **THEN** 相关伏笔的 mentioned_in_chapter_id 值不变，status 不变
