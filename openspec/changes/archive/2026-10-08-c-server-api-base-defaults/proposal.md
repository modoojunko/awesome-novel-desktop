## Why

用户 app.log 报 `s_api_call_error base=https://novel-s-server-297265-7-1468883265.sh.run.tcloudbase.com/api endpoint=check-auth error=`（2026-10-08）。定诊：打包工作流的 `CLIENT_SERVER_API_BASE` / `CLIENT_SERVER_API_FALLBACK` 仓库 Variables **从未配置**，v0.29.x 全部已发包按 CI 默认值把**主基址**烘成云托管直连域，且兜底默认与主基址同值——`call_server_api` 对基址列表去重后只剩一个基址，兜底形同虚设，主基址一次网络抖动即业务不可用且无第二次尝试；授权页用的 `public_server_api` 默认本就是自定义域名，掩盖了 API 走直连的事实。

## What Changes

- 打包主基址默认值（workflow `client-package.yml` 与本地 Windows 入口 `build_release.ps1` 两处）翻转为自定义域名 `https://www.awesomenovel.com/api`；兜底默认＝云托管直连域——未配置仓库 Variables 时默认拓扑即正确，fork 构建开箱可用性质不变。仓库 Variables 已同批补配（显式配置恒胜默认，双保险）。
- 主/兜底**同址判红双闸**：生成侧（`release_json_generate.generate()`）与产物冒烟（`release_json_assert.check_release_json`）共用同一道闸——同址形态在 Generate 步即红，不待双平台打包烧完才在冒烟步暴露；产物闸继续兜底手改产物。
- 同址比较用**归一化形**：新增零依赖单源 `normalize_server_base`（复刻 `auth_local._normalize_server_api` 语义：尾斜杠 rstrip＋裸域名补 `/api`，自定义子路径不动）——运行时 `call_server_api` 去重对象是归一化基址，原始串比较会让尾斜杠/裸域名变体绕过守卫。
- **不动**（明确出界）：运行时兜底切换链（`call_server_api` 主/兜底自动切换）、`public_server_api`/`portal_url`/下载地址族默认（本就指向自定义域名）、pywebview 本地开发占位（无 release.json 的 dev 态）、`client_update_url` 地址族。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `installer-release`：「release.json 烘焙版本与检测地址」requirement MODIFIED——`server_api_base` 默认值翻转（直连域→`https://www.awesomenovel.com/api`，仓库 Variable `CLIENT_SERVER_API_BASE` 可覆盖）、`server_api_fallback` 默认值改为云托管直连域（原「与主基址一致」，仓库 Variable `CLIENT_SERVER_API_FALLBACK` 可覆盖）；主/兜底归一化后同址 MUST 生成/产物双闸判红。「S端 公开地址族随包烘入」场景同步改默认值口径，并新增「主/兜底同址判红」场景。

## Impact

- 代码：`.github/workflows/client-package.yml`（BASE 默认值＋注释）、`client/packaging/build/build_release.ps1`（同款翻转）、`client/backend/scripts/release_json_assert.py`（同址闸＋归一化单源）、`client/backend/scripts/release_json_generate.py`（生成期同闸）；后端业务代码零改动。
- 运维：仓库 Variables 补配 `CLIENT_SERVER_API_BASE=https://www.awesomenovel.com/api`＋`CLIENT_SERVER_API_FALLBACK=<直连域>`（10-08 `gh variable set` 已落）。
- 测试：`test_release_json_ci_assert.py` 夹具改主≠兜底＋同址/尾斜杠/裸域名归一化变体负例＋生成期同址负例＋归一化语义直测；相关五套件 71 例绿；ruff 0.16.3（CI 钉版）干净；本地 dry-run 正/负例实证；打包 dispatch 演练两轮双平台绿，dmg 实烘 release.json 逐键核对（构建指纹自证）。PR #735 CI 全绿。
- 生效面：合入（squash＝9fffd6b6）后任何打包构建即烘正确拓扑；**存量 v0.29.x 已装包无自救路径**（烘焙值恒胜、启动会把 config.json 手改回滚），须下个发版（如 v0.29.2）把用户侧换到自定义域名——发版时机另拍板。

## Design Impact

- 受影响端：仅 C端 打包/发布链（workflow＋打包脚本＋后端 scripts）；S端 与前端零改动。
- 受影响的屏/弹层：无 UI 变化；行为变化仅「安装包连哪个 S端 域名」（终端用户零感知，主基址抖动时新增一次兜底尝试）。
- 用到/新增的对象状态：零新增状态档位；release.json 键集不变（八键原样），仅两键默认值与校验规则收紧。
- 是否触碰两端共享段：否。
- 是否需要原型先行：不需要。
- 设计工件由谁产出：无。
