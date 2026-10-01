## Tasks

1. 构建期烘焙与断言
    - [x] 1.1 `client/backend/scripts/release_json_generate.py`：`generate()` 增产 `public_server_api`（env `RELEASE_PUBLIC_SERVER_API`）与 `portal_url`（env `RELEASE_PORTAL_URL`）两键，加入既有 `https://` 断言循环
    - [x] 1.2 `client/backend/scripts/release_json_assert.py`：冒烟断言覆盖 S端 地址族四键（`server_api_base`/`server_api_fallback`/`public_server_api`/`portal_url`）存在且 `https://` 形态
    - [x] 1.3 `.github/workflows/client-package.yml`：Generate release.json 步骤注入 `RELEASE_PUBLIC_SERVER_API: ${{ vars.CLIENT_PUBLIC_SERVER_API || 'https://www.awesomenovel.com/api' }}` 与 `RELEASE_PORTAL_URL: ${{ vars.CLIENT_PORTAL_URL || 'https://www.awesomenovel.com' }}`
2. 运行期注入与对齐
    - [x] 2.1 `client/backend/config.py`：`RELEASE_OVERRIDE_KEYS` 白名单补 `portal_url`（`public_server_api` 已在）
    - [x] 2.2 `client/packaging/build/pywebview_app.py`：`_env_with_release("PORTAL_URL", "portal_url", "")`（缺省空串，紧邻 `PUBLIC_SERVER_API` 注入行）
    - [x] 2.3 `client/backend/auth_local/service.py`：`load_or_create_config` 增 portal_url 对齐分支（env `PORTAL_URL` 显式设置且与 config 不一致即对齐落盘，镜像 server_api 同款并同款注释）
3. 测试
    - [x] 3.1 `tests/test_release_json_generate.py`：env fixture 补两新键；正例断言两键烘入且值正确；负例覆盖缺 env 报错、非 https 断言红
    - [x] 3.2 `tests/test_release_json_ci_assert.py`：happy path fixture 补地址族四键；负例覆盖缺键与非 https
    - [x] 3.3 config/auth_local 侧单测：portal_url 对齐正例（env 设置→config 残值被改写落盘）＋负例（无 env→既有默认与手工值不动）
4. 门禁与验证
    - [x] 4.1 `openspec validate c-package-public-endpoints --strict` 通过
    - [x] 4.2 pytest 定向（release_json 两个测试文件＋auth_local 相关）全绿；ruff 检查所有改动文件（防 S110/BLE001 类新增违规）
    - [x] 4.3 本地 dry-run：`RELEASE_*` env 齐备跑 `release_json_generate.py 0.25.1 -o /tmp/release.json` 后接 `release_json_assert.py` 全绿，核对两新键值
5. 收尾
    - [ ] 5.1 PR→CI→合并 main（Lint 存量红按挂账先例处理，PR 打包验证必须绿）
    - [ ] 5.2 打 v0.25.1 tag（附注首行进 latest.json.notes），流水线出双包上 CDN
    - [ ] 5.3 下载新包验实物：release.json 含四键且值正确；`v0.25` Release 页补已知问题说明并指向 v0.25.1
