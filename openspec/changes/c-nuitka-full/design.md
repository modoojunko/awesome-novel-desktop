# Design — c-nuitka-full

## Context

spike（2026-10-07，worktree 实测）已实证：Nuitka 4.2.2＋clang 21 可编译全栈
（`spike_nuitka.sh`，日志与编译报告随仓留档）。三个引擎语义差已踩实：
①`--macos-create-app-bundle` 蕴含 standalone，不能与 `--mode=` 并用；
②hiddenimports 死条目（`filesystem.composite_storage`、`threads`）PyInstaller 容忍、
Nuitka FATAL——单源清单必须诚实；
③`--include-module` 全量显式列出比依赖 follow 更稳（prompt_pack 懒导入先例）。
compile_native.py 已有「PyInstaller 前置原生化＋`--scan` 红门」机制。

## Goals / Non-Goals

**Goals:**
- 双引擎并存，默认不变，一键回滚；清单单源，分叉即测试红。
- Nuitka 产物形态与 PyInstaller 交付等价（installer.iss 不分叉）。
- 扫描门双语义，强度不降（Nuitka 模式整树零 .py/.pyc/.pyo＋NATIVE 在位）。

**Non-Goals:**
- 不退役 PyInstaller（全量验证一个发布周期后另立）。
- 不做 onefile（启动慢，正式分发一直是 onedir）。
- 不动 UPX（Nuitka 产物不做 UPX 压缩，体积差接受并记录）。
- 不动启动链代码（v0.28.2 刚验收的启动体验是保护对象，本 change 只换打包引擎）。

## Decisions

1. **单源抽取 `bundle_manifest.py`**：`DATAS`（含 release.json 可选标记）与
   `HIDDEN_IMPORTS` 两个普通列表；build.spec 与 build_nuitka.py 共同 import。
   附带清理两个死条目（本 change 顺手的诚实修正）。parity 测试断言两引擎命令
   组装包含同一集合。
2. **build_nuitka.py 从 spike 脚本产品化**：清单从单源读；release.json 存在才打
   （对齐 build.spec 条件）；Windows 旗标（`--windows-icon-from-ico`、
   `--windows-version-file`）平台分支；输出 `.dist` 目录改名 `AI Novel` 对齐
   installer.iss 期望——选「构建后 rename」而非改 iss Source（iss 不分叉的代价最小）。
3. **compile_native 先行不变**：NATIVE 三模块在 Nuitka 前原生化（.so/.pyd 作为
   extension 被 Nuitka 收进 dist）；`--scan` 加引擎参数分语义，Nuitka 模式验
   整树零 .py/.pyc/.pyo＋NATIVE 在位＋`--include-data-file` 无敏感源码误入。
4. **CI 灰度**：client-package.yml 读 `BUILD_ENGINE`（仓库 Variable，默认空=
   pyinstaller）；tag 构建先灰度一版观察，PR 构建不启用（分钟数纪律）。
5. **构建指纹**：build_nuitka.py 写 `build-engine.json`（engine/nuitka 版本/时间）
   进资源根，启动自检日志可自证（排障与「装的是哪版」判据）。

## Risks / Trade-offs

- **启动链回归风险（最大）**：Nuitka 换掉整个引导路径，v0.28.2 刚验收的启动体验
  可能被打破——缓解＝Windows 真机全冒烟作为发版硬门槛（spec 场景钉死），macOS 绿
  不算数；首次灰度只上 tag 构建，出问题 `BUILD_ENGINE=pyinstaller` 一键回退发版。
- **体积与编译时长**：Nuitka 产物通常略大（不做 UPX）、构建 30–90 分钟——CI 分钟数
  与本地出包时间都要预算；macOS spike 实测时长回填 tasks。
- **pywebview Windows 后端（pythonnet/clr）**：macOS spike 未覆盖，Windows 首编译
  可能暴露 clr 相关缺件——预案：`--include-module` 补齐或 pywebview 插件旗标，
  在 Windows 演练轮消化。
- **双维护窗口**：两引擎并存期间清单改动要两引擎都验——parity 测试＋单源把漂移面
  压到最小；窗口期一个发布周期，尽快收敛。

## Open Questions

无——引擎选择与灰度口径用户已拍板（「拉个worktree，搞全量」）。
