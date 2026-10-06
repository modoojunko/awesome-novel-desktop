## ADDED Requirements

### Requirement: 验签公钥随包烘焙与校验（发布链）

- 发布构建 SHALL 在 `release.json` 烘入**必选键** `pack_pubkeys`：内容为
  `{"<signer_key_id>": "<base64(32 字节 Ed25519 公钥)>"}` 的 JSON 字符串（与
  release.json 各键统一为字符串值的既有形态一致）。签名私钥 SHALL NOT 出现在任何
  仓库、产物或构建日志中；仅公钥随包分发。
- 生成期（`release_json_generate`）SHALL 硬要求 `RELEASE_PACK_PUBKEYS` env 并做形态
  校验：缺失或形态非法即构建失败，SHALL NOT 产出缺键/坏键产物。
- 产物侧冒烟断言（`release_json_assert`）SHALL 将 `pack_pubkeys` 列为必选键并严格
  校验：合法 JSON 映射／非空／每个值合法 base64／恰 32 字节；任一不满足断言失败、
  流水线转红。形态校验实现 SHALL 单源（生成侧与产物侧复用同一实现）。
- 打包应用启动后端时 SHALL 经 release.json 注入 `CLIENT_PACK_PUBKEYS`（键名与同步器
  读取一致）；release.json 缺该键（如本地直打）时 SHALL 回落生产发布公钥常量——
  SHALL NOT 以空钥集运行（空钥集＝恒拒装）。
- 三条打包路径（CI workflow 内联兜底 / Windows 本地 ps1 默认 / pywebview 常量）
  的默认公钥 SHALL 逐字一致，且 SHALL 由测试钉死（漂移＝某条路径烘出验不了包的钥）。
- 轮换签名钥 SHALL 支持多 kid 并存：`pack_pubkeys` 允许同时携带新旧公钥；新包用新
  kid 签发、旧包按已装版本继续可验——SHALL NOT 一对一替换式轮换（会致已装包验签
  失败）。

#### Scenario: 发布构建烘入公钥
- **WHEN** tag／PR 构建执行 `release.json` 生成步骤
- **THEN** 产物内 `pack_pubkeys` 存在且为合法 `{kid: base64(32B Ed25519)}` 映射，
  冒烟断言通过

#### Scenario: 缺烘或坏形态在构建期拦截
- **WHEN** 生成期缺 `RELEASE_PACK_PUBKEYS` env，或产物的 `pack_pubkeys` 为空/非 JSON/
  非映射/坏 base64/非 32 字节
- **THEN** 生成或冒烟断言失败、流水线转红，坏产物 SHALL NOT 发布

#### Scenario: 运行时注入与回落
- **WHEN** 打包应用启动后端
- **THEN** `CLIENT_PACK_PUBKEYS` 等于 release.json 的 `pack_pubkeys` 值；release.json
  缺该键时等于生产发布公钥常量（恒非空）

#### Scenario: 跨入口默认一致
- **WHEN** 检查三条打包路径的默认公钥
- **THEN** 三者逐字一致且形态合法（测试守卫；漂移即红）

#### Scenario: 多 kid 轮换不破已装包
- **WHEN** 发布方轮换签名钥并在 `pack_pubkeys` 中同时保留新旧公钥
- **THEN** 旧版本已装包继续可验（按旧 kid），新包按新 kid 验签，用户无感
