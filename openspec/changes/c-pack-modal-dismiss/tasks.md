## 1. 关闭记忆存取

- [ ] 1.1 `lib/packProbe.ts` 增加关闭记忆读写 helper：`readPackDismissal()` / `writePackInstallDismissed()` / `writePackUpdateDismissed(version)` / `clearPackInstallDismissed()`，单 key JSON（`{"install":true,"updateVersion":"x"}`，design D1/D5）；单测覆盖读写/清除外/坏 JSON 容错
- [ ] 1.2 vitest：helper 用例全绿（`cd client/frontend && npx vitest run src/lib/__tests__/packProbe`，按现有测试落点）

## 2. 弹窗写入记忆

- [ ] 2.1 `PromptPackModal.close()`：包仍未装上（无 installed_version）时写首装关闭标记；安装成功（done/轮询到 installed_version）时清除标记（design D2）；vitest 断言 close 后标记在、成功后标记清
- [ ] 2.2 更新 confirm 页「暂不更新」与更新态关闭：写 `updateVersion`＝本次弹窗入场所用 probe `latest_version`（design D3）；vitest 断言「暂不更新」后标记值为当前版本

## 3. 自动弹拦截

- [ ] 3.1 `NovelListPage` 挂载 effect：`update_available` 分支先查 `updateVersion` 记忆（相同则跳过），install 分支先查 `install` 记忆（为真则跳过）；manual 入口与 `openPackModal` 本体不加闸（design D4）
- [ ] 3.2 vitest（NovelListPage）：首挂未装弹 install→关闭→再挂不弹；暂不更新 vM→再挂同版本不弹→probe 改 vK 再挂弹；已装用户路径不变（存量用例回归）

## 4. 收尾验证

- [ ] 4.1 前端全量 vitest＋tsc 绿；受影响存量 e2e（若有依赖「未装必弹」）同步改口径后过
- [ ] 4.2 `openspec validate --change c-pack-modal-dismiss` 通过；归档时按 sync 流程对拍 `prompt-pack-delivery` 主 spec（MODIFIED 块逐字对拍）
