# 导入自有书 A 路 · 回滚/备份演练记录（2026-10-19）

## 结论

**数据层演练通过**：新库新增列不改变旧列语义；用 SQLite 在线备份 API 可得到一致备份；旧代码只读已知列可正常读取；回填只写 `origin/import_kind/imported_at`，`status` 不变。
**未做**：用真实旧版本安装包启动旧库（需要发布包/旧二进制）；本记录作为发布前数据库演练，发布时补一条真机记录。

## 环境

- 隔离栈：私有 worktree `ai-novel-wt-import-direct`，后端 8104、临时 `DATA_ROOT`。
- 库：`$DATA_ROOT/novel-dev.db`，含一次 42 章 A 路导入（168 章来自多轮 e2e 种书）。
- 备份：`/tmp/import-e2e-rollback.db`。

## 实际输出

1. **直接 cp 主库文件不可用（WAL 数据未落主文件）**：`cp novel-dev.db backup.db` 后备份只有 4KB，`chapters` 表为空。→ 不能把「复制 .db」当备份。
2. **SQLite 在线备份 API 得到一致备份**：

```text
backup tables: 39
old-column select sample: [('86bb0c60-...', 'draft', 'import'), ...]
status counts: [('draft', 168)]
origin counts: [('import', 168)]
```

3. **旧列可读**：`select id,status,origin from chapters` 正常返回；旧代码只读 `id/status` 等已知列时，新增 `origin/imported_at` 会被忽略，不会报错。
4. **回填不改 status**：`test_import_backfill` 断言旧导入书回填后 `status` 保持 `draft/archived` 原值，只写 `origin=import`、`import_kind=legacy`、`imported_at`。
5. **恢复路径**：停止应用 → 用备份文件替换 `novel-dev.db`（同时删除 `-wal/-shm`）→ 启动旧版本；旧版本看到的是旧列集合，status 未变。新库若直接给旧版本读，多出的列被忽略；不建议长期双版本共用。

## 发布前补做

- 用上一版安装包启动一份旧库（含旧导入书），确认可打开、可读、可继续写。
- 用新版本打开同一旧库并执行 carry→backfill，确认续写落 N+1、预览标原文。
- 记录真实版本号、备份文件哈希、恢复耗时。
