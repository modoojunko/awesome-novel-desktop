## Context

`load_or_create_config`（auth_local/service.py:203）在启动/读取时补默认值并持久化。其中 SERVER_API_BASE 的同步条件是 `… and not cfg.get("server_api")`——只在 config 为空时写入一次。此后 env 如何变更都不再生效（config 永远赢），而 S端 容器一旦停掉/迁移，地址即死。2026-09-18 本地实锤：`.env` 切生产后用户登录授权页能开（public 链走 env），凭证回传/校验打向 `server-backend:19000`（server 链走 config 残值）死地址，卡死登录页。

## Goals / Non-Goals

**Goals:**
- env `SERVER_API_BASE` 显式设置时，启动即把 config.server_api 对齐到 env（幂等、持久化）。
- 行为用例先红后绿（对旧逻辑必红）。

**Non-Goals:**
- env 未设置时不做任何事（不覆盖手工 config 配置，保留自定义子路径形态）。
- 不动 `public_server_api` / `server_api_fallback` 的读链（现无写入方，无遮蔽面）。
- 不删除 config.server_api 字段本身（packaged 端把它当持久化缓存，删除牵动迁移逻辑）。

## Decisions

**1. 对齐而非清空：env 显式设置且 ≠ config 时，config := env 并持久化。**
```python
env_base = os.environ.get("SERVER_API_BASE")
if env_base and cfg.get("server_api") != env_base:
    cfg["server_api"] = env_base
    changed = True
```
语义：「env 是部署真值，config 是它的缓存」。env 未设置（如开发者手工指定自定义地址）时 config 不被触碰。幂等：相等时 changed 不置位、不重写盘。

替代方案：删掉 config.server_api 读路径（env 唯一）——被否：`_normalize_server_api` 支持「自定义子路径」配置形态，且 packaged 端把该值当持久化缓存写入，硬删牵动迁移与升级面；对齐式修复 diff 最小。

**2. 测试：CONFIG_FILE 指 tmp + monkeypatch env，直接调 `load_or_create_config()`。**
用例：① env 变更 → config 对齐（先红：旧逻辑保持旧值）；② env 稳定 → 幂等不重写盘（mtime/内容不变）；③ env 未设置 → config 保留手工值；④ 全新空文件 + env → 首次即种子为 env 值。隔离手法沿用仓库惯例：monkeypatch `auth_local.service.CONFIG_FILE`（`_reset_config_cache` 清签名）。

## Risks / Trade-offs

- [手工配置被 env 覆盖] → 仅当 env 显式设置时发生；单用户产品无自托管部署面，env 即部署配置的唯一来源；docstring 注明。
- [每次启动重写 config.json] → 幂等：值相等时 changed 不置位、不落盘；不一致也仅一次写。

## Migration Plan

单函数内同步块改写＋用例，一次 commit。回滚 = revert，无状态残留（config 里多出的值与 env 一致，旧代码读它行为不变）。

## Open Questions

无。
