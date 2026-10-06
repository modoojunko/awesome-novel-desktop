## 1. 真签名钥对与留档

- [x] 1.1 生成 Ed25519 签名钥对（kid=`pack-k1`）：私钥落发布机 `~/.awesome-novel/pack-signing-ed25519.pem`（chmod 600，永不入仓/入产物/入日志）。验证＝文件存在且权限 600、仓库全库 grep 无私钥内容
- [x] 1.2 公钥与指纹留档（公钥 `UaJFasM5PBIB3Tg1o03cjG6Opeq5CaKtPv2ooLyNPPM=`；指纹 `ca374b4f2c6c5783`）进 design.md D1/D6。验证＝发布前可重算指纹比对

## 2. 烘焙链三触点

- [x] 2.1 `config.RELEASE_OVERRIDE_KEYS` 加 `pack_pubkeys`（含注释：漏登记＝注入静默断链）。验证＝`test_config_release.py::test_pack_pubkeys_roundtrip`
- [x] 2.2 `release_json_generate.generate()` 烘入 `pack_pubkeys`：env 缺失 KeyError 转红、形态非法生成期即拦（复用单源校验）。验证＝生成侧正例＋两条可归因负例
- [x] 2.3 `release_json_assert` 必选键严格校验（JSON 映射/非空/合法 base64/恰 32 字节），实现单源 `validate_pack_pubkeys`。验证＝产物侧正例＋六条负例参数化＋单源校验器直测
- [x] 2.4 `pywebview_app` 注入段加行（`PROD_PACK_PUBKEYS` 常量＋`_env_with_release`）。验证＝`test_config_release.py::test_pywebview_injects_pack_pubkeys_env`（真源码行实跑，含回落分支）

## 3. 两处构建入口默认值

- [x] 3.1 workflow Generate 步骤注入 `RELEASE_PACK_PUBKEYS: ${{ vars.CLIENT_PACK_PUBKEYS || '<生产公钥 JSON>' }}`。验证＝YAML 解析后表达式内 JSON 完好且等于生产公钥（本地实跑）
- [x] 3.2 `build_release.ps1` 步骤 2 加默认（与另两处逐字一致）。验证＝跨入口漂移守卫测试
- [x] 3.3 漂移守卫测试（三份文件真源码互证＋单源校验器验形态）。验证＝`test_pack_pubkeys_defaults_consistent_across_entrypoints`

## 4. 回归与门禁

- [x] 4.1 相关测试全绿：`test_release_json_ci_assert.py`＋`test_config_release.py`＋`test_packaging_shell_startup.py`＋`test_prompt_pack*.py`（本地 77＋64 通过）
- [x] 4.2 `ruff==0.16.3` 改动文件零判（含 CI 同口径 F821 检查 pywebview 入口）
- [x] 4.3 真钥回环实跑：真公钥 env → generate → assert 通过，产物 `pack_pubkeys` 解出 32 字节
- [x] 4.4 合入 main 后重跑打包验证构建（workflow_dispatch 两平台 37434081689 双 success）：`Assert release.json baked into bundle`＋零 .prompt 断言在 main 真实产物通过

## 5. 归档前

- [x] 5.1 发布链彩排已全通：真钥出包 v2026.10.6-1/-2（现行 -2，min_client=0.28 配 v0.28.1）→ CDN 上传逐字节对拍 → 四档 CEK 生产登记（两版共存）→ latest 已翻 → 生产字节离线验签 ALL PASS → 生产全链 smoke ALL PASS（含 403 降档/篡改拒装/幂等）
- [ ] 5.2 归档：spec delta 同步 `prompt-pack-delivery`；本 change 的 D1/D6（指纹与轮换程序）留在 design 记录
