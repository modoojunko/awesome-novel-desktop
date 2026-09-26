## Context

#498 把 EULA 生成挂进 `server/frontend` 的 build 脚本（`copy-eula.mjs`），脚本以「脚本位置 ＋ 三级向上」反推仓库根读 `LICENSE`。本地全量检出下解析正确；docker 构建上下文只有 `./server/frontend`（`COPY . .` 到 `/app`），`/app/scripts/../../..` 解析为 `/` → 读 `/LICENSE` ENOENT，`docker compose build server-frontend` 必失败。受影响：4 服务本地栈（S端 前端缺位）、`docker-build-ci.yml`（disabled_manually，恢复即炸）。`s-web-test-deploy` 在 GitHub runner 全量检出下构建，不受影响。

EULA 单源契约（/legal/eula.html 由仓库根 LICENSE 生成、严禁手编）不变。

## Goals / Non-Goals

**Goals**
- `docker compose build server-frontend` 恢复成功，且产物内 `/legal/eula.html` 内容与仓库根 LICENSE 逐字一致。
- 4 服务本地栈可完整启动（S端 前端回位）。
- 构建脚本在 LICENSE 缺失时给出可定位的报错。

**Non-Goals**
- 不改 EULA 内容与单源机制；不给 `copy-eula.mjs` 加多来源/可配置化。
- 不动 `s-web-test-deploy` 与 `docker-build-ci.yml` 的触发/禁用状态。

## Decisions

**D1 命名上下文 `repo=.`（compose 侧注入），不在脚本里加回退链。**
compose 的 `server-frontend.build.additional_contexts` 已有 `brand=./brand` 先例；再加 `repo=.`，Dockerfile 一行 `COPY --from=repo LICENSE /LICENSE` 落到容器内脚本反推的 `/LICENSE` 位置——脚本零改动、本地与容器两种构建路径语义一致。
备选被否：① 脚本加「向上找不到就沿 fallback 链找」（多一条隐性来源路径，破坏单源可审计性）；② 提交生成产物 `public/legal/eula.html` 进 git（与「严禁手编」的防双源机制冲突）。

**D2 `docker-build-ci.yml` 与 compose 共用 compose 文件构建，自动受益，不改。**

## Risks / Trade-offs

- [构建上下文携带仓库根 LICENSE] → LICENSE 内容（EULA 全文）进入镜像 build 层；仅在 build stage，不进最终 nginx 镜像层（serve stage 只 COPY dist 与 nginx.conf），无泄露面。
- [compose 之外裸 `docker build server/frontend` 仍失败] → 属既有边界（brand 注入同样依赖 compose），不新增破坏。

## Migration Plan

单 commit；合入后 `docker compose build server-frontend` 即恢复。回滚＝revert 该 commit。

## Open Questions

（无）
