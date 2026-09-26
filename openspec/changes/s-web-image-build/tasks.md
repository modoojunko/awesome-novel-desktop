## 1. 构建链修复

- [ ] 1.1 `docker-compose.yml`：`server-frontend.build.additional_contexts` 增加 `repo=.`
- [ ] 1.2 `server/frontend/Dockerfile`：build 阶段补 `COPY --from=repo LICENSE /LICENSE`
- [ ] 1.3 `server/frontend/scripts/copy-eula.mjs`：LICENSE 读不到时报错信息带上解析路径（`repoRoot=…`），便于未来再排查

## 2. 验证

- [ ] 2.1 `docker compose build server-frontend` 成功；启动临时容器核对 `/usr/share/nginx/html/legal/eula.html` 内容与仓库根 LICENSE 逐字一致（防双源破坏）
- [ ] 2.2 4 服务栈 `docker compose up -d` 全部健康；`GET /legal/eula.html` 返回 200 且内容含「软件许可协议（EULA v2026.09）」
- [ ] 2.3 本地非 docker 构建 `npm run build`（server/frontend）行为不变
