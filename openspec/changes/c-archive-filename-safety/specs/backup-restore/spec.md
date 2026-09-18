## ADDED Requirements

### Requirement: 归档条目名安全字符集

归档条目名 SHALL 为 `{chapter_ref}-{slug}.md` 形态，其中 slug SHALL NOT 含路径分隔符（`/`、`\`）、SHALL NOT 使全名出现 `..` 序列（路径段与子串两义皆禁；含截断边界——拼接 `.md` 后仍不得出现）。导出实现 SHALL 保证包内每条 `archives/*.md` 条目名通过导入端路径校验（无 `..` 路径段），且产出的 `filename` 恒可被归档文件名解析器解析（`GET /archives/{filename}` 的规范地址可寻址）。

- 归档写接口返回的 `archive_path` 的 basename SHALL 与列表接口的 `filename` 相等（命名规则单源，不得存在第二份手抄公式）。
- 恢复后归档 title SHALL 等于完整条目名 stem（既有语义），且 SHALL NOT 因路径分隔符或 `..` 被截断。
- 不含危险字符且**截断窗口（前 50 字）不以点结尾**的标题命名 SHALL 逐字节保持不变（无历史命名漂移）；截断窗口尾点者按安全规则剥除（有意漂移，防拼接 `..`）。

#### Scenario: 危险标题的书导出包可导入且不再被分隔符截断

- **WHEN** 一本含归档且标题带 `/` 与 `..` 的书执行备份导出并导入空库
- **THEN** 包内条目名无路径分隔符、无 `..` 序列（路径校验通过）；恢复后该归档 title 等于完整条目名 stem（含 ref-slug 全名——既有语义），与修复前「被分隔符截断为尾段」不同

#### Scenario: 截断边界不产生 `..`

- **WHEN** 标题为 `"a" * 49 + "."` 形（slug 截断后以点结尾）执行导出
- **THEN** 条目名中不出现 `..` 子串，`_parse_archive_filename` 可解析（修复前该形态列表有、GET 404）

#### Scenario: 写接口与列表同源

- **WHEN** 对某章执行归档写操作
- **THEN** 响应 `archive_path` 的 basename 与随后列表接口返回的该归档 `filename` 逐字节相等

#### Scenario: 普通标题命名零漂移

- **WHEN** 标题不含 `/`、`\`、连续点且不以 `.` 开头/结尾
- **THEN** 产出的条目名与既有实现逐字节相同
