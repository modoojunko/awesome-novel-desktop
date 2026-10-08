## 1. 实现（打包链三文件，后端业务零改动）

- [x] 1.1 `.github/workflows/client-package.yml`：`RELEASE_SERVER_API_BASE` 默认值翻转 `https://www.awesomenovel.com/api`；兜底默认保持直连域并注释同址会被判红。验证：YAML 解析（CI 演练即验）。
  - 回执：✅ 已落（ba240daa）；演练 run 37725343702 Generate 步绿。
- [x] 1.2 `client/packaging/build/build_release.ps1`：本地 Windows 入口同款翻转（三入口漂移判例：与 workflow 必须同批）。
  - 回执：✅ 已落；评审 P2 整改时注释同步「生成步即判红」（59010df9）。
- [x] 1.3 `release_json_assert.py`：主/兜底同址判红闸＋零依赖单源 `normalize_server_base`（复刻 `auth_local._normalize_server_api`：尾斜杠 rstrip＋裸域名补 `/api`，urlsplit 属 stdlib）。验证：ruff 0.16.3 干净。
  - 回执：✅ 初版同址闸（ba240daa）；评审 P3 整改改归一化比较（59010df9）；ISC004/I001 各修一轮。
- [x] 1.4 `release_json_generate.py`：生成期同闸（评审 P2 整改）——同址形态 Generate 步即红，不待双平台打包烧完；import 归一化单源复用。
  - 回执：✅ 已落（59010df9）；dry-run 负例（同址＋尾斜杠变体）rc=1 且信息点名归一化后同址。

## 2. 测试

- [x] 2.1 `test_release_json_ci_assert.py`：夹具改主≠兜底（生产拓扑）＋同址负例（产物闸）＋生成期同址负例＋尾斜杠/裸域名归一化变体负例＋归一化语义直测。验证：五套件全绿。
  - 回执：✅ `test_release_json_ci_assert`/`test_config_release`/`test_server_api_sync`/`test_server_api_fallback`/`test_auth_url` 共 71 例绿（10-08 本地实跑）；PR CI 绿。
- [x] 2.2 本地 dry-run 正/负例：生产拓扑值（BASE=自定义域名、FALLBACK=直连）生成 rc=0 且产物断言过；同址（含尾斜杠变体）生成期 rc=1。验证：逐条实跑。
  - 回执：✅ 两例均如预期。
- [x] 2.3 打包 dispatch 演练（打包链改动判例）：双平台 Generate＋Assert 步绿、release job 正确 skipped（非 tag 不发版）。验证：run 37725343702＋37731967625 两轮。
  - 回执：✅ 两轮全绿（整改前/后各一轮）。
- [x] 2.4 产物核验（「容器里的东西确实是自己的构建」判例）：演练 dmg 挂载读实烘 release.json 逐键核对＋构建指纹（branch/commit）自证。验证：八键全对、base=自定义域名、fallback=直连。
  - 回执：✅ dmg（`AwesomeNovel_mac_vc-server-api-base-defaults.dmg`）实烘值逐键吻合，指纹 `c-server-api-base-defaults/ba240`。

## 3. 运维与收尾

- [x] 3.1 仓库 Variables 补配：`CLIENT_SERVER_API_BASE=https://www.awesomenovel.com/api`＋`CLIENT_SERVER_API_FALLBACK=<直连域>`。验证：`gh variable list`。
  - 回执：✅ 10-08 已落（显式配置恒胜默认，与代码默认值双保险）。
- [x] 3.2 两域名实勘：`/api/check-auth` 均通且返回一致（`{"code":1,"msg":"缺少 pc_hash"}`），自定义域名 `/api` 分流正常。
  - 回执：✅ 均通。
- [x] 3.3 实现 PR #735 合 main（squash＝9fffd6b6，评审 P2/P3 整改同 PR，分支已删）；主检出 ff 至新 main。
  - 回执：✅ 全落。
- [x] 3.4 遗留挂号：存量 v0.29.x 已装包无自救路径（烘焙值恒胜、启动回滚手改），须下个发版（如 v0.29.2）把用户侧换到自定义域名——发版时机待拍板（不在本 change 范围）。
  - 回执：✅ 已在 PR 描述与记忆挂号。
