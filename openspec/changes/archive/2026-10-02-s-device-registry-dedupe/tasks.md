# Tasks: s-device-registry-dedupe

## 1. 注册竞态回落（#643 已合 main=d797f262）

- [x] 1.1 pg_http client 新增 `is_unique_violation()`（网关 `DATABASE_<pgcode>` 判 23505＋`duplicate key` 兜底）
- [x] 1.2 `PgHttpDeviceRepo.upsert` 撞 23505 回落 `_update_existing`（读回真实行 id/bound_at）；非约束错误上抛
- [x] 1.3 `SqlDeviceRepo.upsert` 撞 `IntegrityError` 回滚后重查更新（`_find_row`/`_apply_update` 提取）；happy path 加 `flush()` 令约束在写入期生效
- [x] 1.4 测试：PG 仓 23505 回落/22P02 上抛（MockTransport）、SQL 仓竞态回落（monkeypatch 竞态窗口）；S端 全量 472 绿＋ruff==0.16.3 干净

## 2. 容器身份钉死＋生产清理（运维）

- [x] 2.1 base compose client-backend 挂 `${CLIENT_MACHINE_ID:-./.docker-data/client/machine-id}:/etc/machine-id:ro`；一次性容器实测身份=宿主垫片、指纹=sha256(文件)
- [x] 2.2 本机 macOS 垫片创建（`.docker-data/client/machine-id`=IOPlatformUUID）；缺文件降级路径（目录挂载→OSError→回落）经代码路径核verify
- [x] 2.3 生产 `device_registry` 清理（网关 REST，按每用户保留最新一行）8→2 行；唯一约束探针 409 `DATABASE_23505` 实锤存在（`uq_device_registry_ufp`），免 DDL 免杀连接
- [x] 2.4 操作单＋执行记录＋垫片配方落 `docs/ops/device-registry-dedupe.md`

## 3. Specs sync

- [x] 3.1 新立 capability `device-registration`（注册去重 upsert＋竞态回落两条 Requirement）并 sync 入 `openspec/specs/device-registration/`
