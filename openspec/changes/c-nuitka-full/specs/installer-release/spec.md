## ADDED Requirements

### Requirement: 构建引擎可切换与双引擎并存

- 打包链 SHALL 支持构建引擎选择：`BUILD_ENGINE=nuitka|pyinstaller`，默认
  `pyinstaller`；两引擎产出的交付形态 SHALL 等价（Windows onedir 目录＋Inno 安装器
  可直接消费、macOS .app 可直接打 DMG），安装器脚本 SHALL NOT 因引擎分叉出两套。
- Nuitka 模式 SHALL：入口与 PyInstaller 同为 `pywebview_app.py`；烘焙清单
  （hiddenimports/datas）与 PyInstaller 模式同一单源（分叉即失真）；release.json
  烘焙、品牌资源、EULA/第三方声明随包行为与 PyInstaller 模式逐项一致。
- 引擎切换 SHALL 可一键回滚（不删 PyInstaller 链路）；CI 灰度期 SHALL 仅 tag 构建
  启用 Nuitka，PR/手动构建默认 PyInstaller（Actions 分钟数纪律）。
- Nuitka 模式发版前置验收 SHALL 包含 Windows 真机启动全冒烟（启动页→后端就绪→
  提示词包同步→AI 功能一条链→退出干净），macOS 验证 SHALL NOT 替代该门槛。
- 引擎选择的实现 SHALL 打上构建指纹（产物内可自证「哪个引擎、哪个版本构建」）。

#### Scenario: 默认引擎不变

- **WHEN** 本地或 CI 未设置 BUILD_ENGINE 出包
- **THEN** 走 PyInstaller 链路，产物与既有版本形态一致

#### Scenario: Nuitka 出包可被安装器直接消费

- **WHEN** `BUILD_ENGINE=nuitka` 构建 Windows 交付
- **THEN** 产出的 onedir 目录（改名 `AI Novel`）可直接被 installer.iss 打出安装包，
  无需手工搬运文件

#### Scenario: 一键回滚

- **WHEN** Nuitka 出包链路故障时设置 `BUILD_ENGINE=pyinstaller`
- **THEN** 打包恢复既有链路，无需代码改动

#### Scenario: Nuitka 灰度只上 tag 构建

- **WHEN** PR 或手动 dispatch 触发打包流水线且未显式设置引擎
- **THEN** 构建 walk PyInstaller 模式；仅 `v*` 标签构建走 Nuitka 灰度开关
