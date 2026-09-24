## Context

- 生产发布：`s-server-deploy.yml`（tag v*/dispatch）→ cloudrun 部署后端＋`tcb app deploy novel-s-web` 部署前端；前端构建配方＝VITE_API_BASE（TCB_BACKEND_DOMAIN 归一化）＋备案 secrets 写 `.env.production.local`（云端会重建、读包内 .env 烘焙）。
- test 云环境 `d1ghsr86ra814c12c`：已托管 `novel-s-web-ai-novel-test`（S web 静态站，portal.ts/升级弹窗的兜底 URL）与 C端 更新源 CDN。与生产 env 相互独立。
- 凭据：`tcb login --cloudbase-api-key` 为账号级，同一 secret 可操作 test env。

## Goals / Non-Goals

**Goals:**

- 合 main → S 前端自动发布 test 站，main 前端改动立即可见可验。

**Non-Goals:**

- **后端自动发布（含发生产）不做**——真栈集成测试只在 nightly，main 每提交直上生产风险过高；此政策若要收紧待用户明确拍板。
- 不动 C端 更新源 CDN（latest.json 由 client-package 流程管理）。
- 不新建云资源。

## Decisions

**D1：构建配方与生产逐字相同**（同一 VITE_API_BASE/备案 secrets）——test 站语义＝「main 前端预览（生产 API）」，所见即将发布之物。
**D2：应用标识按既有 URL 取 `novel-s-web-ai-novel-test`＋env `d1ghsr86ra814c12c` 直接写死**（带注释）；如平台标识不同，首跑报错即可见、改一行。备选（已弃）vars 化——需要用户先去 GitHub 配置，违背「纯增量零配置」目标。

## Risks / Trade-offs

- [main 前端直连生产 API] → 与生产行为一致（merge 前已经 PR＋CI＋nightly 验证）；数据面风险与正常发布相同。
- [应用标识猜错首跑失败] → 失败可见无害（非生产）；修一行重跑。
- [每次 main push 都构建部署（含 docs-only 之外的噪音）] → paths 过滤已限前端相关目录。

## Open Questions

- test 站的精确应用标识（`novel-s-web-ai-novel-test`）需首跑确认——失败不影响生产。
- 后端是否也要 test 实例（需新建 cloudrun＋DB），成本高、暂缓，待拍板。

## Migration Plan

工作流合入即生效（下一次 main push 触发）；回滚 = 删除工作流文件。
