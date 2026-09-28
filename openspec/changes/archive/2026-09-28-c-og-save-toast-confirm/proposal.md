# c-og-save-toast-confirm（补录归档）

> 补录说明：本 change 为 PR #550 合入后（2026-09-28）的补录归档（先例：#487 补录 #484），
> 实现先于 change 目录存在。真机事故排查中用户指令链：排查按钮置灰 → 确认根因 → 修复 → 合入 → 归档。

## Why

编辑态点「保存草稿」时，只要必填两项（必须完成的变化、主情绪，c-og-slim-v2 四改二口径）齐全，
`handleSaveDraft` 就自动调用 `confirmChapter` 确认章纲（设计稿行为），但 toast 恒弹「草稿已保存」。
2026-09-28 真机事故：作者保存后被带回查看态，见「确认章纲」按钮置灰（confirmed=true 的正常表现），
误判按钮坏了来报障——提示文案与实际状态错位是根因，按钮置灰本身是正确行为。

## What Changes

- **`handleSaveDraft` toast 分口径**（ChapterWorkspace.tsx）：`confirmChapter` 后以 `reloadStatus`
  回读的服务端 status 为准（与「确认章纲」按钮 `handleConfirm` 同款核对方式）——自动确认成功弹
  「已保存并确认章纲」；有必填缺口的纯存草稿维持「草稿已保存」。
- **两条 e2e 断言跟改**：outline-ai-draft「空章纲」（AI 起草回填后保存＝自动确认路径）断言改新文案；
  workbench-features 章纲用例断言同改，并修正其过时注释（必填四改二后该用例两项都填齐，实际一直走
  自动确认路径，旧文案掩盖了这一点）。
- **非目标**：不改确认机制本身、不动「已确认章再保存仍弹草稿已保存」的既有边界（后经用户确认维持）；
  specs 无漂移——workbench/spec.md 799-800 只锁「保存链机制不变」，未钉 toast 文案，机制未动故零 delta。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

（无——行为链未变，仅提示文案分口径，specs 不涉及）

## Impact

- 实现：#550（squash = a1842947，2026-09-28 admin 合入——CI 全仓基建秒挂按先例，本地门禁绿）
- 验证：tsc 0 错；vitest 934/934；演示栈（novel-demo）真机 e2e 两条复验绿后扩为两 spec 文件全量 19/19 绿
- 部署：演示栈 client-frontend 已重建（bundle 指纹自证含新文案），client-backend 代码本就最新
  （容器内 grep 实证含 #549/#545），override 指纹标签同步 a1842
