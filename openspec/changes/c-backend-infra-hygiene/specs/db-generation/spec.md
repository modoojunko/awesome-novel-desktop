## ADDED Requirements

### Requirement: 迁移端点入参必须经白名单与参数化

免登迁入端点全家（start/preview/dismiss/cleanup/retention）的 `source_filename` 入参 SHALL 经同一白名单校验（候选形状白名单＋`resolve()` 收敛在数据目录内＋非活跃库），MUST NOT 存在未过校验即读文件/复制/ATTACH 的路径。拼接进 SQLite 语句的路径 SHALL 做字面量转义或参数化，MUST NOT 依赖「文件名碰巧不含引号」。

#### Scenario: start 与 dismiss 同源校验

- **WHEN** start/preview 收到 `../x.db`、子目录路径或含引号的文件名
- **THEN** 返回 400 级可读拒绝，不发生任何读文件、复制或 ATTACH

#### Scenario: 含引号文件名不破坏语句

- **WHEN** 数据目录内出现名字含 `'` 的文件并尝试搬运
- **THEN** ATTACH 语句仍为合法 SQL（转义生效），不产生注入面
