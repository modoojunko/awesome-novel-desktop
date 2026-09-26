## 1. YAML 护栏

- [ ] 1.1 两条 workflow 各加 `concurrency` 组（`group: ${{ github.workflow }}-${{ github.ref }}`，`cancel-in-progress: true`）。验证＝同分支连续推两次，旧跑被取消（Actions 页面状态 cancelled）
- [ ] 1.2 后端 CI 的 ruff 步骤改 `ruff check --extend-select F811,F821,F841 .`（--extend-select 在默认规则集 E4/E7/E9/F 之上追加；用 `--select` 会整体替换默认集，丢掉 E4/E7/E9——c-og-slim-v2 提案里写错了，此处修正）。验证＝构造一个 F821 的临时提交在分支上触发红灯（或本地 `ruff check --select F821` 对拍）
- [ ] 1.3 push 触发收窄：两条 workflow 的 `on.push.paths` 保留、`on.push.branches` 收窄为 `main`；`pull_request` 触发不变。验证＝分支推不改门禁相关路径时不触发

## 2. 启用与验收

- [ ] 2.1 GitHub API 启用两条 workflow（`PUT /actions/workflows/{id}/enable`），核对 state 回 `active`。验证＝`gh api /actions/workflows` 两条 state=active
- [ ] 2.2 main 上 dispatch 双条件，预期双绿（main 树 ＝ 已验证分支树逐字节一致，本机三件套全绿）。若红且签名属 runner 层（steps=0/日志 404），重跑一次区分
- [ ] 2.3 PR 链路冒烟：开一个只改 `client/backend` 注释的试验 PR，确认后端 CI 触发且绿，合并后关闭
- [ ] 2.4 额度核对：恢复后查 GitHub 额度页（Billing and licensing → Actions），记录本批消耗；如额度报尽，按先例重新禁用并在 memory 登记，不阻塞合并

## 3. 记录

- [ ] 3.1 memory 更新「七条 CI 被人为禁用」条目：C端 两条已恢复（日期＋验证结论），S端 两条/打包/Docker/e2e-scheduled 仍禁用待额度
