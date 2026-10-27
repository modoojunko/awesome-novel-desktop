# c-relaunch-version-selfreport · 设计

## Context（2026-10-27 真机定诊）

- v0.43 灰度跳：换装/收账/盘上 bundle 全对（0.43），拉起实例自报 0.42；`applied.json`
  正确写 0.43（reconcile 直读 release.json 不吃 env）与 boot 行 env-first 并存＝定诊
  分叉点。
- 传染链（mac 实证）：`_env_with_release("CLIENT_VERSION",…)`（pywebview_app.py
  :808-812，存量 env 优先仅补缺）→ 旧实例 os.environ 带上 0.42 → runner
  `env={**os.environ}`（:1821）→ `open` 传播 → 新实例 :1356-58 env 优先 ⇒ 0.42。
- Windows 同链理论成立（Popen 无 env= 隐式继承 → Inno → [Run]）；是否被 Inno
  中转洗掉待徽章采证——修法平台无关，双平台同批覆盖，采证只影响历史解读。

## Decisions

- **D1 冻结态烘焙恒优先（单点根治）**：`_env_with_release` 开头加 frozen 分支——
  `frozen = getattr(sys, "frozen", False) or "__compiled__" in globals()`（与
  get_install_dir 同判别式）时 `os.environ[name] = release.get(key) or fallback`
  强制覆盖后 return。dev/非冻结走原两段补缺逻辑（env 覆盖与「dev」回退全保留）。
  该函数是 SERVER_API_BASE(_FALLBACK)／PUBLIC_SERVER_API／PORTAL_URL／
  CLIENT_VERSION／CLIENT_UPDATE_URL(_FALLBACK) 七个烘焙键的唯一注入点——单点改＝
  徽章、update-check.current、后端子进程 env 全部一次性纠正。
- **D2 boot 版本行冻结不信任 env**：main() `client_version_at_boot`（:1356-58）在
  frozen 下不再读 `os.environ["CLIENT_VERSION"]`（否则启动日志在 server setup 覆写
  env 之前仍打旧值——诊断面不能说谎）。
- **D3 runner 剥 baked 键（双保险）**：模块级 `_BAKED_ENV_KEYS = frozenset({...7 键})`
  ＋`_without_baked_env(env) -> dict`（拷贝并剔除，其余键原样保留——PATH/SystemRoot
  等系统键不动）；mac spawn 的 env dict 与 Windows spawn（补 `env=` 参数）都过它。
  即使 D1 失守（未来新键忘了进 frozen 分支），执行体链也带不出旧版本值。
- **D4 测试口径**：`_without_baked_env` 纯函数三臂直测（剥 baked／保留系统键／空
  dict 安全）；`_env_with_release` 是闭包不可导入——冻结/非冻结两臂用源码形状断言
  （frozen 分支串在场）；Windows spawn 补 env= 用形状断言（与 #952/#953 同口径）。
- **D5 非目标**：单实例锁、apply 闸≥放行、runner 等安装器退出码（0.44 桶另三件）；
  不改换装算法与 runner 三段留痕契约。

## 测试设计

- `_without_baked_env`：含 7 键＋PATH 的假 env → 7 键被剥、PATH 保留；空 dict →
  空 dict 不抛。
- 形状断言：源内含 `frozen` 分支（`_env_with_release` 强制覆盖行）、
  `_without_baked_env(os.environ)`（mac spawn）、`env=_without_baked_env(`
  （Windows spawn）、boot 行 frozen 不读 env 的判别串。
- 回归：后端全量 CI 口径；ruff 闸内全绿；壳层 A/B 对拍无新增账（新增 except 为零——
  本 change 不引入新 try/except）。

## 风险

- 冻结态强制覆盖后，若未来出现「要在打包产物上用 env 临时改端点」的运维需求将被
  拒——当前无此场景（lab 走构建期烘焙），登记为已知取舍。
- Windows 徽章采证若证明同病，本修复即治；若幸免，剥键属无害加固。
