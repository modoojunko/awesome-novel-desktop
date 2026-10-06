# c-prompt-pack-pubkey-bake — 验签公钥随包烘焙：真钥对＋三触点＋严格断言

## Why

c-prompt-pack-client 立了「内置信任钥集合按 signer_key_id 验 manifest 签名」的契，但**公钥怎么进包**没有实现路径——发布窗口前的实勘发现整条烘焙链是断的：

1. `config.RELEASE_OVERRIDE_KEYS` 白名单无 `pack_pubkeys` 键 → 即使 release.json 写了也会被 `load_release_overrides` 丢弃；
2. `pywebview_app` 注入段无 `CLIENT_PACK_PUBKEYS` 行 → 冻结产物里 `sync._pubkeys()` 恒返回空集；
3. `release_json_generate` 无该键的烘入、`release_json_assert` 无该键的断言 → 缺烘不会在构建期转红。

合起来＝**打包端永远验不了任何包**：同步器七道校验第一道就失败，现场只表现为「AI 永久未就绪」，没有任何线索指向打包链（与 v0.23–v0.25 地址族缺烘致授权页 404 是同一类静默断链）。且此前只有一把**测试用**的临时钥（e2e harness 生成），生产签名钥对尚未生成。

## What Changes

- **真钥对落地**：生成 Ed25519 签名钥对（kid=`pack-k1`），私钥离线保管在发布方（`~/.awesome-novel/pack-signing-ed25519.pem`，600，永不入仓/入产物），**仅公钥**（`UaJFasM5PBIB3Tg1o03cjG6Opeq5CaKtPv2ooLyNPPM=`，指纹 `ca374b4f2c6c5783`）随包分发；指纹留档于 design.md。
- **烘焙链三触点补齐**：白名单加键（config）→ 生成期烘入（release_json_generate，缺 env 即红）→ 产物侧严格断言（release_json_assert，**必选键**：JSON 映射/非空/合法 base64/恰 32 字节）；形态校验实现单源复用，生成侧与产物侧不得两套。
- **运行时注入**：`pywebview_app` 注入段加 `_env_with_release("CLIENT_PACK_PUBKEYS", "pack_pubkeys", PROD_PACK_PUBKEYS)`——release.json 有则用烘焙值，没有（本地直打）回落生产发布钥常量。
- **三入口默认一致**：pywebview 常量 / workflow 内联兜底 / build_release.ps1 默认三处逐字一致，漂移由测试钉死（三条打包路径任一处烘错钥，现场同样只表现为「AI 恒未就绪」）。
- **测试**：产物侧正/负例族（缺键/空串/非 JSON/非映射/空映射/坏 base64/非 32 字节）、生成侧缺 env 与坏形态可归因负例、workflow 注入静态守卫、跨入口漂移守卫、pywebview 注入段真源码行实跑（含回落分支）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `prompt-pack-delivery`：新增 Requirement「验签公钥随包烘焙与校验（发布链）」——必选键、三入口默认一致、运行时注入与回落、轮换程序；与既有「提示词包获取与安装（C端）」的验签要求互为前提（无钥可验＝整条链不可用）。

## Impact

- `client/backend/config.py`（白名单）、`client/backend/scripts/release_json_generate.py`、`client/backend/scripts/release_json_assert.py`（形态校验单源）、`client/packaging/build/pywebview_app.py`（注入＋常量）、`client/packaging/build/build_release.ps1`、`.github/workflows/client-package.yml`（env 注入）；测试 `tests/test_release_json_ci_assert.py`、`tests/test_config_release.py`。
- 不触碰任何用户可见行为、无 UI 变化；对已发布旧版（无本键）无影响——本键随提示词包功能首发。
- 私钥保管与轮换是运营程序（design D3），不进仓库。

## Design Impact

- 无 UI/原型/共享段改动（纯发布链与运行时注入）。信任模型补一页：公钥＝随包常量（可入仓、可入产物），私钥＝离线保管（发布方签发用），轮换＝vars 覆盖＋三处默认同批改。
