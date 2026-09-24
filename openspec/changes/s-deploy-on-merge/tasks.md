## 1. 双端影响判定

- [x] 1.1 双端影响判定：纯 CI 发布基建（新工作流），无产品代码/界面改动——Design Impact「不适用」，skip_specs

## 2. 工作流实现

- [x] 2.1 新增 `.github/workflows/s-web-test-deploy.yml`：push main（paths 过滤）→ 生产同款配方构建 → `tcb app deploy novel-s-web-ai-novel-test --env-id d1ghsr86ra814c12c`——diff 贴进 change 目录
- [x] 2.2 YAML 语法校验（actionlint 或 python yaml.safe_load）——结论贴进 change 目录
- [ ] 2.3 首跑验证：test 站 URL 打开为 main 前端（主文案/备案号/探测同生产）——**待合并后首次触发**，结论回填（未完成前任务保持未勾也可按 2.1-2.2 先合）

## 3. 回归

- [x] 3.1 生产发布工作流（s-server-deploy.yml）零改动——git diff 实证记录贴进 change 目录
