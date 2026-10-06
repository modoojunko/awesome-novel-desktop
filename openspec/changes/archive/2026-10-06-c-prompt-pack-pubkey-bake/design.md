# c-prompt-pack-pubkey-bake — 设计

## D1 公钥是项目常量，不是环境变量

Ed25519 签名钥对代表**发布方身份**（谁签的包），不随环境（dev/prod）变化——只有一个发布方，故只有一把签名钥。推论：

- 公钥可以、也应该**硬编码**在三条打包路径的默认值里（与 `CLIENT_SERVER_API_BASE` 等地址族默认值同构）；GitHub Variable `CLIENT_PACK_PUBKEYS` 只作**轮换覆盖**用，不是配置项。
- 私钥（`.pem`）只在发布方离线保管，任何仓库、任何产物、任何 CI 日志里都不得出现。本期落在发布机 `~/.awesome-novel/pack-signing-ed25519.pem`（600）。
- 现场核对手段：`ssh-keygen` 风格的指纹留档（本期 `ca374b4f2c6c5783`），发布前重算比对，防「拿错钥签包」。

## D2 为什么是必选键而不是可选键（fail-loud）

可选键的形态（缺省容忍）在此场景是错的：缺烘不会造成任何显式错误，只会让**所有**用户的 AI 恒「未就绪」——排障要从客户端一路查到 CDN 与打包产物，代价极高（地址族缺烘致授权页 404 的判例已经付过一次这个代价）。

故 `release_json_assert` 把它列为**必选键**，且判据尽可能严：JSON 映射、非空、每个值合法 base64、恰 32 字节（Ed25519 公钥长度）。生成侧同时硬要求 env（缺＝KeyError 转红），两层拦截保证「产物里没有它」这件事在构建期就不可发生。

## D3 形态校验单源（生成侧与产物侧共用）

`validate_pack_pubkeys(raw) -> str` 定义在 `release_json_assert.py`，`release_json_generate.py` import 复用（生成侧通过时直接写入规范化原串）。理由：两处各写一套校验是漂移的温床，而漂移的表现形态（坏钥进产物）只有上线后才可见。该模块只 import 后端零依赖叶子（`backup.format`/`schema_version`），仍满足「生成步骤跑在 Install deps 之前」的约束。

不做的事：不在 `load_release_overrides` 里校验（config 层保持哑透传，校验留在发布链），不在运行时模块里校验（`sync._pubkeys()` 已有自己的容错路径，坏钥在运行时只表现为空集＋拒装，不影响用户数据）。

## D4 运行时注入与回落

```
release.json.pack_pubkeys ──(白名单)──> load_release_overrides
        └─(pywebview_app 注入段, 键名 CLIENT_PACK_PUBKEYS)——┬─ 有烘焙值 → 用它
                                                            └─ 无 → PROD_PACK_PUBKEYS 常量
                                                                     └─> sync._pubkeys() 解析 {kid: b64}
```

回落到生产常量而不是空串：本地直打的 .app（如 `build_mac.sh` 不产 release.json）也应有钥可验，否则本地产物会出现「同步成功但永远拒装」的假故障。空串回落在发布路径已由必选键断言排除，无兜底价值。

## D5 三入口默认一致＝承诺的可验证化

三条打包路径的默认公钥必须逐字相同（pywebview 常量 / workflow 内联 / ps1 默认）。这不是洁癖：任一处漂移的后果与「缺烘」完全同类（验不了包），而现场没有任何线索区分它们。测试直接解析三份文件的真源码并互证＋用单源校验器验证形态，防「三处一致地写错」。

## D6 轮换程序（运营，非本期执行）

换签名钥＝四步同批：① 新私钥离线生成并留指纹；② S端 发布侧（prompts 仓 publish 链）切新私钥签发；③ `vars.CLIENT_PACK_PUBKEYS` 改新公钥＋三处默认同批改（本 change 的漂移守卫会红，正是提醒）；④ 客户端侧**向后兼容**：`{kid: pub}` 是映射，轮换期可**双钥并存**（新旧 kid 各一条），旧包按已装版本继续可验，新包用新 kid 签——故禁止「一对一替换」式轮换。

## 验证与证据

- 单测：`tests/test_release_json_ci_assert.py`（正/负例族＋生成侧可归因负例＋两个静态守卫＋跨入口漂移守卫）、`tests/test_config_release.py`（白名单往返＋注入段真源码行实跑，含回落分支）。
- 真钥回环（本地实跑）：真实公钥 env → `release_json_generate` → `release_json_assert` 通过；产物内 `pack_pubkeys` 解出 32 字节。
- YAML 解析验证：workflow 该行以 plain scalar 解析后，`${{ vars.CLIENT_PACK_PUBKEYS || '<json>' }}` 表达式提取出的 JSON 完好且等于生产公钥（防表达式内引号被 YAML 吃掉）。
- 端到端：合入后重跑打包验证构建（workflow_dispatch，两平台），证明严格断言在真实产物上通过。
