# Ops：device_registry 同机重复行清理＋唯一约束核查

> **执行记录（2026-10-02，经网关 REST 完成免控制台）**：生产全表 8 行 → 2 行。
> 删 6 行＝`modoojunko` 名下 demo 栈 C端 容器的历史行（hostname 为容器 ID，
> 09-19～09-24 每次容器重建注册一台），保留当前在跑容器（`e7ec6af7d987`，
> 与 `docker ps` 容器 ID 对拍一致）＋`demo_mercenary` 唯一行。
> 唯一约束**已实锤存在**：同 `(user_id, fingerprint)` 重复插入被拒
> HTTP 409 `DATABASE_23505`，约束名 `uq_device_registry_ufp`（与 ORM 声明的
> `uq_user_fingerprint` 不同名，同列，行为等价）→ 无需补 DDL、无需杀连接。

> **复发源与已实施方案**：本地 demo/隔离栈 C端 跑在容器里时，`/etc/machine-id`
> 与 `/var/lib/dbus/machine-id` 均缺失 → 身份回落容器 hostname（容器 ID），每次
> 重建容器＝新指纹＝新设备行（还须浏览器重新授权一次）。已按拍板实施**宿主身份
> 挂载**：base `docker-compose.yml` 的 client-backend 增加
> `${CLIENT_MACHINE_ID:-./.docker-data/client/machine-id}:/etc/machine-id:ro`。
> 宿主垫片配方（一次性）：
> ```sh
> # macOS（写入 IOPlatformUUID → 容器与原生 C端 同指纹、同设备）：
> ioreg -rd1 -c IOPlatformExpertDevice \
>   | sed -nE 's/.*"IOPlatformUUID" = "([^"]+)".*/\1/p' \
>   > .docker-data/client/machine-id
> # Linux 宿主机更直接：CLIENT_MACHINE_ID=/etc/machine-id
> ```
> 垫片文件缺失时 Docker 造出同名目录，采集器按 OSError 静默降级回旧行为，
> 不阻断启动。注意切换身份后**首次浏览器重新授权**会注册出新的稳定行，届时
> 按 §2 清掉旧的 hostname 身份行即可。真机桌面版身份是硬件 UUID，不受影响。

> 背景：设备列表出现「同一台设备注册了多次」。根因是 #430（2026-09-19）之前的
> 指纹算法退化为 `sha256(主机名)`（macOS 无 wmic、异常静默吞掉），主机名随网络
> 环境漂移 → 每次漂移都注册出一台「新设备」。#430 修的是**算法**（改硬件 UUID
> 单一身份源），**没有清历史行**——旧幻影行会一直躺在 `device_registry` 里。
>
> 影响评估：幻影行 `last_active_at` 停留在最后一次旧客户端登录，激活位按
> `last_active_at` 降序取前 N，幻影行沉底**不抢激活位**；危害是设备列表脏、
> `total_count` 虚高、需要手动清理。属数据卫生问题，非紧急。

## 操作入口

生产 PG 无迁移链（表结构带外手工维护，见
`docs/postmortem/2026-08-31-s-server-pg-schema-drift-and-gateway-plan-cache.md`）。
网关（PostgREST）只能单表 CRUD，跑不了本页 SQL——用腾讯云 PostgreSQL 控制台
的 SQL 窗口（或带外直连）执行。

## 1) 诊断：看清重复形态

```sql
SELECT user_id, fingerprint, hostname, os,
       to_char(created_at,     'YYYY-MM-DD HH24:MI') AS created,
       to_char(last_active_at, 'YYYY-MM-DD HH24:MI') AS last_active
FROM device_registry
ORDER BY user_id, created_at DESC;
```

判读：

- **同 `hostname`/`os`、不同 `fingerprint`** → 主机名哈希时代的幻影行（本页主目标）。
- **同 `fingerprint` 多行** → 唯一约束缺失＋先查后插竞态（做第 3 步补约束）。
  设备仓加固后（pg_http/sql 两仓 upsert 撞 23505 自动回落更新）同指纹竞态
  不会再留重/报 500。

## 2) 清理：保留每用户最新一行

每用户当前真机的行永远是最新一条（每次登录都会刷新 `last_active_at`）；
其余行在 #430 后客户端侧已不可能再被更新，删掉后无需迁移。

```sql
WITH ranked AS (
  SELECT id,
         ROW_NUMBER() OVER (PARTITION BY user_id
                            ORDER BY last_active_at DESC) AS rn
  FROM device_registry
)
DELETE FROM device_registry
WHERE id IN (SELECT id FROM ranked WHERE rn > 1);
```

副作用（可接受，先读再跑）：某用户若有多台真机、且某台超过 30 天没登录，
它的行也会被删——该机下次浏览器重新授权一次即重新登记（`device_grants`
里的令牌不受影响，本地作品无感知）。只删个别幻影行也可以按第 1 步查出的
`id` 逐条 `DELETE ... WHERE id = '...'`。

## 3) 唯一约束核查＋补建

ORM 声明了 `uq_user_fingerprint (user_id, fingerprint)`，但生产表是带外建的，
08-31 复盘修复单里「重建 UNIQUE/FK/索引」是否执行过未留证——必须实测：

```sql
SELECT conname FROM pg_constraint
WHERE conrelid = 'device_registry'::regclass AND contype = 'u';
```

没有 `uq_user_fingerprint` 就补上（有重复行会直接报错，先跑第 2 步）：

```sql
ALTER TABLE device_registry
  ADD CONSTRAINT uq_user_fingerprint UNIQUE (user_id, fingerprint);
```

## 4) 收尾（复盘铁律）

任何 DDL/约束变更后**杀连接刷网关连接池**，否则预编译计划缓存可能让
`/api/device/my` 等 500：

```sql
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid();
```

等十几秒 503（`DATABASE_PGRST001`）自愈后，浏览器登 S端 设备页复核：
重复行消失、当前设备在列且 activated。
