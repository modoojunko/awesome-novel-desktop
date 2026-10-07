# Proposal: c-nuitka-full — C端 打包引擎全量切换 Nuitka（双引擎并存）

## Why

用户拍板（2026-10-07）上全量 Nuitka：①反逆向收口——安装包内不再存在任何可反编译的
Python 字节码（现状＝PyInstaller PYZ 可被 pyinstxtractor 秒抽，钥匙/解密虽已原生化但
组装逻辑、S端 协议、gates 判定仍可读）；②为将来「整体闭源形态」铺路。
macOS spike 已实证可行性（pywebview 全栈过 Nuitka standalone，C 编译链就位）。

## What Changes

- **双引擎并存**：打包链支持 `BUILD_ENGINE=nuitka|pyinstaller`（默认 pyinstaller 不变），
  Nuitka 模式产出同等交付形态（Windows onedir＋Inno 安装器、macOS .app＋DMG）。
  全量验证过一个发布周期后再议退役 PyInstaller（本 change 不退役）。
- **清单单源抽取**：build.spec 的 hiddenimports/datas 抽为 `bundle_manifest.py` 单源，
  双引擎共同消费（附 parity 发现：现清单含死条目 `filesystem.composite_storage`、
  `threads`——PyInstaller 容忍缺失，Nuitka FATAL，须清理）。
- **`build_nuitka.py` 产品化**：spike 脚本转正——release.json 条件烘焙、Windows
  icon/版本资源、输出布局对齐 installer.iss 期望（dist 目录改名 `AI Novel`）。
- **扫描门语义适配**：compile_native.py `--scan` 在 Nuitka 模式下改验「交付树零
  .py/.pyc/.pyo ＋ NATIVE 扩展在位」（Nuitka standalone 产物天然无字节码）。
- **验收门槛**：Windows 真机启动全冒烟（loading→后端就绪→拉包→AI 一条链→退出干净）
  为发版前置；CI 灰度＝仅 tag 构建启用 Nuitka（Actions 分钟数纪律）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `installer-release`：ADDED「构建引擎可切换」——双引擎并存契约、默认引擎、
  回滚开关、产物等价性要求（同一 installer.iss 可消费两种引擎产物）。
- `prompt-pack-delivery`：MODIFIED「本机提取防护强度与不承诺项」——零字节码断言的
  验证手段在 Nuitka 模式下的等价适配（强度不降：交付树零 .py/.pyc/.pyo＋NATIVE
  扩展在位＋特征串自证）。

## Impact

- `client/packaging/build/`：新增 `bundle_manifest.py`、`build_nuitka.py`；`build.spec`
  改消费单源＋清死条目；`compile_native.py` scan 分支适配；`build.bat`/`build_mac.sh`
  引擎开关；`requirements.txt` 增 nuitka/ordered-set。
- `installer.iss`：Source 路径兼容两种引擎产物目录（或前置 rename 步骤，二选一见 design）。
- CI：`client-package.yml` 增 `BUILD_ENGINE` env（tag 构建灰度启用）。
- spike 产物（`spike_nuitka.sh`、`spike-build.log`、`spike-report.xml`）随 change 留档后清理。
- 回归面：打包门禁（零提示词断言、验签公钥烘焙断言）在双引擎下都要绿。

## Design Impact

- 无用户可见界面改动（打包链变更）；原型/共享段/design:check 零触碰。
- 用户可感知面仅「安装包内部形态」（体积、启动特征），功能契约不变。
