# 任务：c-update-detached-ps-fix

## 1. 壳层执行体修复（client/packaging/build/pywebview_app.py）

- [x] 1.1 `_spawn_install_runner`：创建旗标 `DETACHED_PROCESS` → `CREATE_NO_WINDOW`
      （保留 `CREATE_NEW_PROCESS_GROUP`，argv 不变）。验证：新增旗标断言测试通过。
- [x] 1.2 `_install_runner_script`：在 `$log = …` 赋值之后、`$w0 = Get-Date` 之前插入
      `runner: started (runner_pid=$PID parent=…)` 首行（引用 $log/$parent，插早了会静默
      失败恒缺）；结束行格式不动。`_install_runner_script_macos`：`log()` 定义后、等待
      循环前补 `log "started (runner_pid=$$ parent=$UPD_PARENT)"`（同串 runner: started）。
      验证：两平台脚本形状断言（started 在等待段之前）通过。
- [x] 1.3 `_spawn_install_runner`：Popen 包 try，`OSError` 回退直接 detached Popen 安装器
      （argv 不变），落 fallback 日志，不再上抛。记账语义：仅当至少一个执行通道成功派发
      才递增 attempts，双失败不递增（下次退出重试）。验证：spawn 失败回退用例通过
      （第二次 Popen argv/flags＋日志行＋派发成功时 attempts 递增）。
- [x] 1.4 `_reconcile_pending` 版本不匹配分支：回读执行日志（取**最后一次**匹配：
      started 有无＋installer_exit，mac 按 install_ok 映射），落 startup.log 一行＋写
      `data/updates/last-install-attempt.json`（version/attempts/runner_started/
      installer_exit/recorded_at；tmp+rename 原子写）。版本匹配分支（成功）同步删除该
      文件，过期失败记录不常驻。验证：三形态对拍＋append 取末段＋成功清理用例通过。

## 2. 状态诊断字段（client/backend/update_check.py）

- [x] 2.1 状态聚合读取 `last-install-attempt.json` 并入公开状态只读字段
      `last_install_attempt`（文件缺失＝**键不出现**，非 null 占位——存量全等断言
      `assert st == {…}` 依赖；无新端点）。验证：状态端点单测覆盖三态＋缺失态（键不
      出现）＋升级成功后字段消失，存量全等断言保绿。

## 3. 测试（client/backend/tests/）

- [x] 3.1 `test_packaging_shell_apply.py`：新增旗标断言（含 CREATE_NO_WINDOW 位、不含
      DETACHED_PROCESS 位）＋两平台 started 首行断言（mac 回读解析含 install_ok 映射）；
      桩 `_FakePopen` 须扩展为同时捕获 kwargs（现桩只记 argv，creationflags 无处落脚）；
      存量 Windows/macOS 用例保绿不改钉。
- [x] 3.2 新增 `test_runner_spawn_failure_falls_back_to_direct_installer`（含双失败不递增
      attempts 臂）。
- [x] 3.3 对拍回读用例落 `test_packaging_shell_apply.py`（三形态＋append 两次尝试取
      末段＋成功清理）；
      `last_install_attempt` 状态字段用例落 `test_update_check.py`（三态＋缺失＋成功消失，
      与 2.1 同批）。

## 4. 回归与验收

- [x] 4.1 后端全量：`cd client/backend && python -m pytest`（存量 2470＋新增全绿；
      带覆盖口径与 CI 一致）。验证：退出码 0。
- [x] 4.2 门禁结论登记（无 UI 改动，design:lint/design:check/tsc 不涉——引用 proposal
      Design Impact 判定：无 React 屏改动、无共享段触碰）。
- [ ] 4.3 真机验收臂（0.39→0.40，现役验收台＝事故机 D:\AwesomeNovel）：点「重启更新」
      → 应用退出 → 新版自动拉起且版本前进；`installer-runner.log` 含 started 首行与
      installer_exit=0；数据目录零改动。（执行体创建失败的回退臂由 3.2 单测覆盖——
      System32 下 powershell.exe 属主 TrustedInstaller，真机不可改名模拟。）
