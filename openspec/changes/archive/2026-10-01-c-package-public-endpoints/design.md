## Context

打包端 S端 地址解析链（现状，2026-10-01 实勘）：

- **构建期**：`.github/workflows/client-package.yml` 的 Generate release.json 步骤以 env `RELEASE_SERVER_API_BASE`／`RELEASE_SERVER_API_FALLBACK`／`RELEASE_DOWNLOAD_BASE`／`RELEASE_DOWNLOAD_FALLBACK_BASE` 传入 `release_json_generate.py`；`generate()` 只产出 7 键（server_api_base／server_api_fallback／client_version／client_update_url／client_update_url_fallback／components／可选 build info），其中 `server_api_base`/`server_api_fallback` 已烘焙但任何 spec 未立规。仓库无 `CLIENT_SERVER_API_BASE` Variable，实际生效的是 workflow 硬编码默认（云托管直连域）。`RELEASE_OVERRIDE_KEYS`（`config.py`）白名单已含 `public_server_api`，但 generate() 不产出该键——白名单形同虚设。
- **运行期**：`pywebview_app.start_server` 以 `_env_with_release` 把 release.json 键注入 env（`SERVER_API_BASE`／`SERVER_API_FALLBACK`／`PUBLIC_SERVER_API`／`CLIENT_VERSION`／…），注释明示「server_api 字段 env 恒胜——启动会把 config.json 对齐到本值」。
- **取值链**：`auth_local/service.py` `_get_public_server_api()`＝config `public_server_api` → env `PUBLIC_SERVER_API` → 回落 `_get_server_api()`；`_build_auth_url()` 剥尾部 `/api` 得 web origin 开 `/auth`。打包端因 release.json 缺键 → 回落 API 基址 → 云托管直连源 `/auth` 404（实测）。`portal_url` 只在 `load_or_create_config` 默认值（`DEFAULT_PORTAL_URL`＝test 环境 webapps 常量）与 config.json 存量值两处取值，无 env 通道。
- **消费方**：授权页 URL 仅 `browser_auth` 非静默分支构造、`LoginPage` 原样 `window.open`（无兜底转换）；`portal_url` 由 `/auth/config` 端点下发给前端 `lib/portal.ts`（会员页 `MemberBlockPrompt`、客服页 `support.ts`）。

约束：`device-auth-page` spec 已钉死授权页地址契约（`{public_server_api 剥 /api}/auth`），本 change 只补打包链取值源，不碰契约本身；生产域名事实源＝`https://www.awesomenovel.com`（`TCB_BACKEND_DOMAIN` Variable、`WXPAY_NOTIFY_URL`、`www/auth` 200 实测三重印证）。

## Goals / Non-Goals

**Goals**

- 打包端新装用户能完成首次登录：授权页 URL 落在承载 `/auth` 的 S端 web 源（www）。
- 打包端会员页/客服页跳转指向生产门户源，且能治老包写入的 config 存量残值。
- 键族全部进 spec＋冒烟断言，杜绝「白名单有键、烘焙缺行」的静默断链（本次事故形态）。

**Non-Goals**

- 不改 `device-auth-page` 授权页地址契约与 `_build_auth_url` 实现。
- 不动 S端（www 路由、云托管）任何行为。
- 不改 demo/本地开发 env 注入拓扑（compose override 已显式生产地址）。
- 不处理 `DEFAULT_PORTAL_URL` 常量本身（dev/demo 默认值保持原样，仅打包端经 env 覆盖）。

## Decisions

1. **键名与 env 口径沿用既有家族**：release.json 键 `public_server_api`／`portal_url`；构建 env `RELEASE_PUBLIC_SERVER_API`／`RELEASE_PORTAL_URL`；仓库 Variable `CLIENT_PUBLIC_SERVER_API`／`CLIENT_PORTAL_URL`（未配置走 workflow 默认值）——与 `RELEASE_SERVER_API_BASE`/`CLIENT_DOWNLOAD_BASE` 完全同构，`generate()` 内对两新键加与既有三键相同的 `https://` 断言。
2. **portal_url 运行时语义镜像 server_api**：`pywebview_app` 增 `_env_with_release("PORTAL_URL", "portal_url", "")`（缺省空串，dev 无感）；`load_or_create_config` 增「env 显式设置且与 config 不一致即对齐落盘」分支（与 c-server-api-sync 同款）。选对齐而非「仅缺省时取默认」，因 v0.23–v0.25 已把 test 域名写进用户 config.json，仅靠默认值取不到效。
3. **默认值钉 www**：`public_server_api` 默认 `https://www.awesomenovel.com/api`（同源承载 /auth＋/api→云托管，与本地 5173 角色同构）；`portal_url` 默认 `https://www.awesomenovel.com`。云托管直连域继续承担 `server_api_base`/`server_api_fallback`（API 面现状不动）。
4. **冒烟断言扩两键**：`release_json_assert.py` 校验地址族四键存在且 `https://` 形态（`components` 校验逻辑不动）。PR 构建同口径——键值与 tag 构建一致（地址族与版本无关）。

## Open Questions

（无——键名/默认值/对齐语义均沿用仓内既有先例，无需用户拍板项）
