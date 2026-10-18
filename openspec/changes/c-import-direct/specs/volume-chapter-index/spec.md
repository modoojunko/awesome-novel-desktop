## ADDED Requirements

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

- 系统 SHALL 在数据 carry 完成后按 `app_meta.import_backfill_v1` 标记幂等执行旧书回填；SHALL NOT 只在首次启动无条件跑一次。
- 回填规则：`projects` 中 `source='import'` 且 `import_kind` 为空/authored 的书 → `import_kind='legacy'`；其所有章 `origin='import'`、`imported_at=created_at`；章 `status` SHALL NOT 被改写。
- 回填 SHALL 可重复执行且结果一致；失败 SHALL 不写标记，下次启动重试。

#### Scenario: 旧导入书迁移
- **WHEN** 旧库中的导入书被 carry 到新库并执行回填
- **THEN** 该书 import_kind=legacy，其非归档章 origin=import、status 保持原值，续写落 N+1

#### Scenario: 重跑回填不改结果
- **WHEN** 回填因中断重跑
- **THEN** 已标记的书不重复写入，章 origin/status 与第一次结果一致
