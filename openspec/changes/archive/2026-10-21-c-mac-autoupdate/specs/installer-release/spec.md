## ADDED Requirements

### Requirement: macOS bundle 版本元数据

macOS .app 产物的 bundle 元数据 SHALL 携带真实版本：`Info.plist` 的
`CFBundleShortVersionString` 与 `CFBundleVersion` MUST 与同次构建的发布版本同源
（tag 去 `v` 前缀；本地构建取 APP_VERSION env > git describe > 0.0.0 兜底，与 Windows
版本资源共用同一版本单源，SHALL NOT 出现第二份取值逻辑）。发版流水线 MUST 在打包期
断言 plist 版本字段与本次发布版本逐字一致，断言不过 MUST 使流水线失败（坏包不上
真机）；MUST NOT 以运行时自报版本（release.json 烘焙）替代 bundle 元数据——两者
口径一致但载体独立，Finder「显示简介」等系统读取面依赖后者。

#### Scenario: tag 构建 plist 版本同源

- **WHEN** 发版流水线以 `v*` 标签构建 macOS DMG
- **THEN** .app 的 `CFBundleShortVersionString`/`CFBundleVersion` 等于去 `v` 前缀的
  标签版本，且流水线断言通过

#### Scenario: plist 版本不符流水线判红

- **WHEN** 打包产物 plist 版本字段与本次发布版本不一致（如注入链断裂回落默认值）
- **THEN** 流水线断言步骤失败，DMG 不进入发布段
