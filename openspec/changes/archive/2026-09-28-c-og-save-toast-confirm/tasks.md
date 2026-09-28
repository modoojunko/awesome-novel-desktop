# Tasks（补录——实现已于 #550 完成，此处回填执行记录）

## 1. 排查定因

- [x] 1.1 定位按钮禁用条件 `confirmed || gaps.length > 0 || saving`（OgPane.tsx 查看态）与
  `confirmed = ogStatus === "confirmed"`（ChapterWorkspace.tsx）；排除工作区 4 个在途后端文件
  （开篇期位置标注，与本链路无关）；验证：机制链闭环——handleSaveDraft 无缺项自动确认＋toast 恒弹「草稿已保存」
- [x] 1.2 后端口径核对：`gate_chapter_ready` 与前端 `ogGaps` 同为两项（必须完成的变化、主情绪），
  确认必成功、状态停 confirmed；验证：gates.py 通读

## 2. 修复

- [x] 2.1 `handleSaveDraft` 分口径：`autoConfirmed = (await reloadStatus()) === "confirmed"`，
  toast 按真值弹「已保存并确认章纲」/「草稿已保存」；验证：tsc 0 错
- [x] 2.2 e2e 断言跟改两处：outline-ai-draft:174（自动确认路径→新文案）、workbench-features:192
  （断言同改＋过时注释「仍有必填缺口」修正为自动确认口径）；验证：grep 全仓无残留旧断言
  （源码侧旧文案保留于 else 分支属正确）

## 3. 门禁与合入

- [x] 3.1 vitest 全量 934/934 绿（5.86s）；验证：本地全量跑
- [x] 3.2 分支 fix/c-og-save-toast-confirm → PR #550 → CI 全仓基建秒挂（与改动无关的
  CodeQL/build/release 全 2-3s 挂，同 #549 先例签名）→ admin squash 合入 = a1842947；验证：
  gh pr view 550 = MERGED，origin/main 头提交即修复提交

## 4. 部署与真机复验

- [x] 4.1 演示栈 client-frontend 重建（`-p novel-demo` build＋up --no-deps）；验证：bundle 文件名
  变更＋包内抓到「已保存并确认章纲」特征串＋5174 回 200
- [x] 4.2 真机 e2e 复验：先两条用例绿（期间根治 server-backend 重启循环并补发 19000——独立事项，
  详见 s-demo-stack-usersnew-orphan-fix 记忆），后扩为两 spec 文件全量 19/19 绿（1.4min）；验证：
  演示栈真机跑，e2e-cleanup 残留清扫、真书无损
