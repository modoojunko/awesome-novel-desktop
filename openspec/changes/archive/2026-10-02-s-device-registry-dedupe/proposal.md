# Proposal: s-device-registry-dedupe

## Why

S端 设备列表出现「同一台设备注册了多次」。排查（2026-10-02，实勘生产 + 代码考古）定性为两案叠加：

1. **历史幻影行**：#430 之前的指纹算法在容器/macOS 场景退化为 `sha256(主机名)`——生产 `device_registry` 里 `modoojunko` 名下 7 行全是 demo C端 容器行（容器内 `/etc/machine-id` 缺失 → 身份回落容器 hostname，每次重建容器注册一台新设备）；#430 修了算法但没清历史行，也没有任何机制阻止容器场景复发。
2. **现行竞态缺口**：两仓（pg_http/SQLite）的设备 upsert 是「先查后插」，find→insert 间隙被并发请求抢先插入同 `(user_id, fingerprint)` 时，唯一约束存在（生产实锤 `uq_device_registry_ufp`，探针 409 `DATABASE_23505`）则第二个请求 500，缺失则留下重复行。

注册去重语义此前无任何 spec 覆盖（`devices` 只钉路由命名、`device-fingerprint` 只钉 C端 采集契约），本 change 补录立约并归档。

## What Changes

- **注册竞态回落**：pg_http client 新增 `is_unique_violation()`（网关错误码 `DATABASE_<pgcode>` 判 23505）；pg_http/SQLite 两仓设备 upsert 撞唯一约束自动回落为对该键行的更新——不 500、不留重复行；非约束错误原样上抛；约束缺失的部署上插入照常成功（安全退化为旧行为）。
- **容器身份钉死**：base compose 的 client-backend 挂载 `${CLIENT_MACHINE_ID:-./.docker-data/client/machine-id}:/etc/machine-id:ro`，容器内身份不再回落容器 hostname；垫片文件缺失时 Docker 造同名目录，采集器按 OSError 静默降级回旧行为。macOS 宿主垫片写入 IOPlatformUUID（容器与原生 C端 同指纹同设备），配方落 `docs/ops/device-registry-dedupe.md`。
- **生产清理（带外已执行，记录在案）**：经网关 REST 按「每用户保留最新一行」删 6 行历史容器行（8→2）；唯一约束探针实测存在（免 DDL 免杀连接）。操作单（诊断/清理 SQL＋约束核查＋杀连接收尾）入 `docs/ops/device-registry-dedupe.md`。
- **明确不动**：设备激活策略（ActivationPolicy 按 last_active 降序取前 N）、授权/配对契约（device-auth-page）、指纹采集链（device-fingerprint）、路由命名（devices）零改动。

## Capabilities

### New Capabilities

- `device-registration`: authorize 设备注册的去重与竞态契约——以 `(user_id, fingerprint)` 为去重键 upsert（复用保留 id/bound_at），并发撞唯一约束回落更新不 500 不留重，非约束错误上抛，约束缺失安全退化。

### Modified Capabilities

（无——指纹采集链契约不变，容器身份钉死属部署拓扑，落 ops 文档不立 requirement）

## Impact

- **代码（#643 已合 main=d797f262）**：S端 `server/app/infrastructure/repositories/pg_http/{client,device_repo}.py`、`sql/device_repo.py`＋测试 3 条（S端 全量 472 绿，ruff==0.16.3 干净）；根 `docker-compose.yml` client-backend 挂载一行；`docs/ops/device-registry-dedupe.md` 新增。
- **运维**：生产数据已清理（8→2）；demo C端 容器身份切换后首次浏览器重新授权将注册出稳定新行，届时按 ops §2 清旧行 `e7ec6af7d987`。
- **风险**：无破坏性——回落路径在约束缺失部署上退化为旧行为；挂载缺文件静默降级。
