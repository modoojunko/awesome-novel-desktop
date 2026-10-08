# c-httpx-socks-fallback

## Why

2026-10-08 用户实机实锤（app.log）：VPN 客户端把 SOCKS 代理注册成 Windows 系统代理时，
打包产物缺 `socksio`（requirements 只装 httpx 本体），后端全部出网 httpx 调用在
构造期抛 `ImportError`——`/api/auth/check-auth`、`/api/update-check`
整端点 500。表现为「浏览器 OAuth 登录成功、客户端永远检测不到登录」：浏览器走自己的
网络栈（SOCKS 正常）登录成功，桌面端轮询每轮 500、前端 catch 静默吞。波及全部出网
构造点（grep 实锤 9 处：`AsyncClient`×7 ＋ `prompt_pack/sync.py` 同步 `httpx.Client`×2）
与 openai SDK 内部 httpx——登录检测、更新检查、设备激活、提示词包同步、朱雀检测、
连接探针、AI 生成在该网络环境下全链不可用。

## What Changes

- 依赖：`requirements.txt` 的 `httpx>=0.27.0` → `httpx[socks]>=0.27.0`（+socksio，
  纯 Python 零传递依赖）。这是把 VPN 用户全链修活的主刀——openai SDK 内部的 httpx
  一并受益（工厂兜底包不住它）。
- 新增共用工厂（sync/async 双入口）：封装出网客户端构造，构造期异常（`ImportError`
  等）→ 降级 `trust_env=False` 直连重建；留痕只记代理 scheme＋host:port（剔除
  userinfo，代理 URL 可能内嵌凭据）。9 处构造点换用工厂
  （auth_local/service.py `call_server_api`、auth_local/router.py `devices/current`
  两处、update_check.py、zhuque/client.py、api_configs/connection.py 两处——
  以上 `AsyncClient`×7；prompt_pack/sync.py 同步 `httpx.Client`×2 走同步入口）。
- 行为守恒：无代理路径（构造成功即返回）与 HTTP 代理路径零变化——无 VPN 用户与
  Clash HTTP 系统代理用户不受影响；仅 SOCKS 代理场景从「崩溃 500」变为「正常走代理，
  依赖缺失时降级直连」。
- 打包产物自证：httpx 是运行时才 `import socksio`，静态分析有漏收风险，socksio 钉入
  `bundle_manifest.py` 的 HIDDEN_IMPORTS 单源（PyInstaller/Nuitka 双引擎共同消费；
  只改单一引擎配置会让另一引擎产物静默漏收），并解包产物抓特征串确认真进了包
  （c-prompt-pack-hardening 判例：抓产物特征串，别只看构建命令返回成功）。

## Capabilities

### New Capabilities

- `outbound-http-client`: C 端后端出网 HTTP 调用对本机代理配置的韧性——代理可用则
  走代理（含 SOCKS 系统/环境代理），代理配置异常则降级直连，代理配置问题绝不把
  业务端点打成 500；无代理路径行为不变。

### Modified Capabilities

（无——`openspec/specs/` 57 个 capability 零 socks/代理覆盖，grep 实锤；本改动是
新增横切能力，不修改任何既有需求。）

## Impact

- 代码：`client/backend/requirements.txt`；新增共用工厂模块（sync/async 双入口）；
  9 处构造点替换（`AsyncClient`×7 ＋ 同步 `httpx.Client`×2）。
- 依赖：新增 `socksio`（httpx[socks] extra，零传递依赖、不影响既有依赖树）。
- 打包：双引擎（PyInstaller/Nuitka）产物新增 socksio 模块（HIDDEN_IMPORTS 单源
  钉入），须产物特征串自证；Windows/macOS 双包走 dispatch 演练（打包链改动判例）。
- 测试：新增 SOCKS 代理场景回归（代理可用走代理 / 构造失败降级直连 / 无代理路径
  不变三分支）+ 既有 pytest 全量回归。
- 用户面：VPN（SOCKS 系统代理）用户登录检测、更新检查、AI 全链恢复可用；无 VPN
  用户零行为变化（两刀均为惰性路径）。
