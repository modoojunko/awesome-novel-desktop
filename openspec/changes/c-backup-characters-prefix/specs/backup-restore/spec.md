## ADDED Requirements

### Requirement: 多书包每书段落位置（prefix 纪律）

资产包内全部书级段落（`project.yaml`、`story.yaml`、`threads.yaml`、`settings/`、`chapters/`、`versions/`、`prompts/`、`archives/`、`characters/`、`hooks/`）SHALL 位于各书 `projects/{slug}/` 前缀下。**多书包导出实现 SHALL 经统一 prefix 机制写入**（不得有段落硬写包根）；prefix 为空（包根布局）SHALL 仅用于单书交付导出（`kind=single`）与 `GET /novels/{id}/export` 两个单书端点。导入端 SHALL 逐书按 `{book_dir}` 前缀读取，SHALL NOT 跨书混用或回退到包根取值。

- 本条款为既有布局契约的显式化与实现对齐（`_dump_characters` 曾漏传 prefix，整库包多书角色文件写包根互相覆盖且导入端读不到）。

#### Scenario: 两书角色段各归其位

- **WHEN** 两本各有角色的书执行整库备份导出
- **THEN** 包内 `projects/{slugA}/characters/characters.yaml` 与 `projects/{slugB}/characters/characters.yaml` 均存在且内容互异（各自书内角色），包根不出现 `characters/` 目录

#### Scenario: 整库包恢复角色逐书对拍

- **WHEN** 上述整库包导入空库
- **THEN** 每本书恢复后的角色数与关系数与源库逐书一致（非「最后一本的发给每本书」，也不是全部丢失）

#### Scenario: 单书导出布局不变

- **WHEN** 单书交付导出执行
- **THEN** 角色段仍位于包根 `characters/characters.yaml`（prefix 为空），与既有单书包逐字节同构
