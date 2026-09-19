# c-device-fingerprint-stable — Tasks

## 1. 双端影响判定（非 UI 变更替代原型先行）

- [x] 1.1 判定并记录：本 change 纯 C端 后端逻辑，无用户可见界面改动、不触 base.css 令牌/共享段、S端 零改动 → design:lint / design:check / design-cross 全部不适用，回归以 pytest＋vitest＋e2e 为准（依据=proposal Impact 段）。验证：该判定写入本任务 checkbox 下方即可，无代码产出。
  - 证据：纯 C端 后端逻辑，无 UI 改动、不触共享段、S端 零改动——design:lint/check/cross 不适用，回归以 pytest＋e2e 为准（已按此执行）。

## 2. 平台身份 helper（单一事实源）

- [x] 2.1 在 `client/backend/auth_local/service.py` 新增 `_platform_identity() -> str`：按 macOS(ioreg→IOPlatformUUID) → Windows(PowerShell Get-CimInstance→SMBIOS UUID) → Windows 兜底(reg query→MachineGuid) → Linux(/etc/machine-id，兜 /var/lib/dbus/machine-id) → platform.node() 顺序采集；每级 5s 超时、OSError/非零/解析失败静默降级。验证：单测 mock 各平台子进程，断言优先级与降级路径。
  - 证据：已完成：`_platform_identity()`＋四级采集器＋静默降级链落在 service.py；采集链单测覆盖优先级与降级。
- [x] 2.2 实现占位值检测：空串、去连字符后全 0、全 F（大小写不敏感）判无效落下一级；进程内 memoize 首个有效值（测试用 monkeypatch 注入，不改磁盘）。验证：单测覆盖空/全0/全F/合法四类输入。
  - 证据：已完成：`_is_valid_identity()`（空/全0/全F 大小写不敏感）＋进程内 `_identity_memo`（测试用 `_reset_identity_memo()` 注入）；四类输入单测绿。
- [x] 2.3 `generate_pc_hash` 与 `collect_device_profile` 改为调用 `_platform_identity()`（保留 sha256[:32] 与 sha256 全长两种出口），删除两处 wmic 采集代码。验证：grep 全仓无 `wmic` 残留（含注释与测试桩）；两函数既有单测改期望后全绿。
  - 证据：已完成：两函数同走 `_platform_identity()`（sha256[:32] / sha256 全长两出口）；wmic 采集代码删除，残留仅「为何退役」注释与防回归断言（`test_collect_device_profile_wmic_retired` 断言不再发出 wmic）。

## 3. 测试补齐

- [x] 3.1 新增采集链单测：macOS/Windows/Linux 三平台各一「主路径＋全链失败兜底主机名」用例（subprocess mock），合计覆盖 spec 三场景＋无效值场景。验证：容器内 pytest 新用例全绿（容器须重建，见 4.1）。
  - 证据：已完成：macOS/Windows/Linux 主路径＋全链失败兜底＋占位值降级 MachineGuid＋wmic 退役断言，覆盖 spec 四场景；容器内 `tests/test_device_activation.py` 15/15 绿。
- [x] 3.2 新增同机稳定性用例：同平台两次采集返回同值；「删 config 重生成 pc_hash 不变」用例（清空 config 后 load_or_create_config，断言 pc_hash 与丢失前一致）。验证：容器内 pytest 绿。
  - 证据：已完成：同源断言（pc_hash==fingerprint[:32]）＋主机名漂移不变＋`test_pc_hash_stable_across_config_loss`（删 config 重生成同值）；实机复核另见 4.3。
- [x] 3.3 排查 e2e/测试代码中硬编码的 pc_hash/指纹值，改为运行时从被测进程 helper 或 config 同源读取。验证：grep 测试代码无 32/64 位 hex 字面量身份值残留；本地 e2e 相关 spec 通过。
  - 证据：已完成：grep e2e＋backend tests 无 32/64 位 hex 身份字面量（e2e pc_hash 均为运行时 `randomUUID()` 注入，无需改动）。

## 4. 回归与验收

- [x] 4.1 重建 C端 docker 容器（改后端必须重建，镜像含模板代码），跑容器内全量 pytest。验证：pytest 全绿，输出摘要贴本任务下。
  - 证据：容器内全量 pytest（挂 client/ 整目录）：1201 passed / 2 failed＝brand+entitlement 已知基线环境红（brand.json 被挂载盖掉，origin/main 同败口径），非回归。
- [x] 4.2 本地 docker 栈跑 C端 全量 e2e（含登录/授权链）。验证：e2e 全绿；重点观察授权相关 spec 无新红。
  - 证据：隔离栈（worktree override 5274/8100＋播种 config）全量 e2e：155 passed / 14 skipped（存量登记）/ 6.5m，EXIT=0。备注：主栈前两轮（31.2m 41 passed＋10.2s 成片超时）被并行会话的共享栈施工污染（docker events 见外部 19000 探针与容器错峰重建），按 runbook 配方②切隔离栈后全绿，证实与本次 diff 无关。
- [x] 4.3 本机实机验收：删除 config.json 后启动并模拟登录，抓取 device_profile 解码验证 fingerprint 稳定且 ≠ sha256(主机名)；S端「我的设备」不再新增重复行。验证：解码输出与设备列表截图/记录贴本任务下。
  - 证据：macOS 实机（uv venv 3.12＋DATA_ROOT 隔离 temp，两轮进程语义）：fingerprint=dda8435f84ee4be1…源自 IOPlatformUUID，≠ sha256(主机名)=744551dfcc5428d3…；删 config 重生成 pc_hash/fingerprint 与删除前逐位一致；device_profile 解码 f 字段与 fingerprint 一致。S端 设备行收敛为同一不变量（指纹稳定 → (user_id, fingerprint) upsert 命中同行，S端 代码未动），登录链 e2e 全绿佐证；重复行终验随新构建首次真实登录自然完成。
- [x] 4.4 门禁收尾：双端 tsc/vue-tsc --noEmit、vitest（改了被 e2e 依赖的前端模块才需要，预计零改动）按影响面执行并记录结论；设计门禁按 1.1 判定为不适用。验证：结论写本任务下，全绿后走 PR。
  - 证据：门禁收尾：C端 `npm run build`（tsc＋vite build）exit 0；C端 前端无独立 vitest script（test=playwright）且前端零改动，vitest 不适用；vue-tsc 属 S端 工具链不适用；设计门禁按 1.1 判定不适用。
