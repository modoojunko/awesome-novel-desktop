# c-silent-relaunch-runner · 任务

> 实现已随 PR #903 合入 main（bca44e13，2026-10-20，CI 绿），本清单回收已完成项。

## 1. 壳层 runner 形态

- [x] 1.1 `_install_runner_script`：等尸段（Wait-Process 有界 60s）→同步执行安装器→
      留痕行（wait_ms／parent_alive_after_wait／installer_exit／install_seconds）
- [x] 1.2 `_spawn_install_runner`：detached PowerShell（WINDIR 全路径优先，缺失回落
      PATH 名）＋`-EncodedCommand`（UTF-16LE base64）下发
- [x] 1.3 `apply_pending_update` 接线：四闸不变，Popen 安装器改 spawn runner；
      spawn 失败上抛（attempts 不递增、pending 存活）

## 2. 后端配套

- [x] 2.1 auto-skip 清理保留 `installer-runner.log`（与 installer.log 同为诊断面）

## 3. 测试与门禁

- [x] 3.1 runner 编码命令解码对拍（等尸段/安装器 argv 全量/留痕字段/`exit $code`）
- [x] 3.2 WINDIR 全路径选路两臂（在场取全路径／缺失回落 PATH 名）
- [x] 3.3 存量暗病修复：`test_non_windows_leaves_pending` 假 sha 在指纹闸提前返回，
      从未到达平台闸——改真 sha 并钉平台闸日志
- [x] 3.4 packaging 14 绿＋update_check 46 绿＋CI 钉版 ruff（0.16.3）绿＋PR CI 绿

## 4. 收尾

- [x] 4.1 评审两轮：review-agent 首轮 1×P3（等尸段无留痕）已修复，复审 No findings
- [ ] 4.2 真机验收（随下一发版）：新版点重启→弹回即新版；`installer-runner.log`
      出现 `installer_exit=0`；异常臂（占住 exe）→ 无人拉起、重开后 pending 重试升版
