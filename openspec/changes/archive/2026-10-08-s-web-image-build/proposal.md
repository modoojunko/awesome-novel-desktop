# s-web-image-build — 修 S端 前端 docker 镜像构建（EULA 生成读不到 LICENSE）

## Why

自 #498（relicense-proprietary）起，`server/frontend` 的 docker 镜像构建必失败：`npm run build` 的第一步 `node scripts/copy-eula.mjs` 用「脚本位置 ＋ `../..//..`」反推仓库根读 `LICENSE`，而 Dockerfile 的构建上下文只有 `./server/frontend`（`COPY . .` 到 `/app`），反推结果落在文件系统根 `/LICENSE` → `ENOENT`，镜像 3 秒内构建失败。受影响面：4 服务本地栈只起得来 3 个（S端 前端缺位）、`docker-build-ci.yml` 恢复时同炸。同一次提交改了 build 脚本、没改 Dockerfile，属一次性遗漏，不是行为争议。`s-web-test-deploy` 走 GitHub runner 全量检出（`npm run build` 能找到根 LICENSE）不受影响。

## What Changes

- `docker-compose.yml` 的 `server-frontend.build.additional_contexts` 新增命名上下文 `repo=.`（与既有 `brand=./brand` 同模式）。
- `server/frontend/Dockerfile` build 阶段补一行 `COPY --from=repo LICENSE /LICENSE`——`copy-eula.mjs` 的仓库根反推（`/app/scripts/../../..`）恰好落在 `/`，从此读到真实 LICENSE。
- `copy-eula.mjs` 增加「LICENSE 读不到时显式报错并打印解析路径」的失败信息（现状 ENOENT 不带路径，排查多绕一圈）。
- **不改动**：EULA 单源契约（/legal/eula.html 由仓库根 LICENSE 生成、严禁手编）一字不动；`s-web-test-deploy`（runner 全量检出）不受影响也无需改。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

（无——构建链路修复，EULA 单源行为契约不变；故本 change 设 `skip_specs: true`。）

## Impact

- `docker-compose.yml`、`server/frontend/Dockerfile`、`server/frontend/scripts/copy-eula.mjs`。
- 验证＝`docker compose build server-frontend` 成功 ＋ 镜像内 `/legal/eula.html` 内容与仓库根 LICENSE 逐字一致（防双源破坏）＋ 4 服务栈可完整启动。
- `docker-build-ci.yml`（现为 `disabled_manually`）恢复时自动受益，无需改。

## Design Impact

- 纯构建链路（Dockerfile/compose/构建脚本），无用户可见 UI 变化；S端 不触共享段；无原型需求。
