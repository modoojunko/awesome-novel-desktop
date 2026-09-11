# auth-page-direct-entry

## Why

线上设备授权页 `/api/auth-page` 是后端手写内联 HTML（土棕金色系 #8b6914 等），与整站青绿 oklch 体系是色相级偏离；且它是用户输入密码的信任敏感页，观感割裂直接伤害可信度。而 S端 前端 `/auth`（AuthPage.vue，换装 #194 已对齐设计系统）功能是其超集（无效态、429 限频文案、成功态套餐/到期展示、注册入口、备案条）却从未被打开过——PM/UX/FE 三方联合评审定性为「正牌入口被旁路」。用户拍板：C端 直接改开 `/auth`，后端内联页整个删除（裁定无存量用户需兼容，不走 302 垫片）。

## What Changes

- C端 授权地址从 `{public_server_api}/auth-page` 改为剥掉 `/api` 后缀的 `{web_origin}/auth`，query 三参（pc_hash/pc_name/device_profile）不变；device_profile 本就是 URL-safe Base64 无 padding，无需额外编码
- S端 前端 AuthPage.vue 补读 `route.query.pc_name` 传给 apiAuthorize（闭合 C端 传了没人消费的契约洞）；两个 AppInput 补 `autocomplete`（username / current-password）
- S端 后端删除 `AUTH_PAGE_HTML` 内联页与 `GET /api/auth-page` 路由。**BREAKING**：已发布的旧版桌面包点「浏览器登录」将 404——按用户裁定无存量用户，且以「C端 新包先发、后端删除后部署」的顺序消解自有设备风险
- 同步更新 3 个后端测试文件中 auth-page 返回 200 HTML 的断言（删除或改写）

## Capabilities

### New Capabilities

- `device-auth-page`: 设备授权页入口契约——C端 桌面端 SHALL 打开 S端 前端 `/auth` 页完成设备绑定授权，授权页 SHALL 仅由 S端 前端承载；授权动作契约（POST /api/authorize）与轮询契约（GET /api/check-auth）不变

### Modified Capabilities

（无——不触碰令牌档位、组件词汇、状态语言，design-system 不动）

## Impact

- `client/backend/auth_local/service.py`：auth_url 构造（唯一 C端 改动点）
- `server/frontend/src/views/AuthPage.vue`：pc_name + autocomplete 两处小修
- `server/app/interfaces/client_api/authorize.py`：删 AUTH_PAGE_HTML（21-99 行）+ 路由 + HTMLResponse 导入，更新模块 docstring
- `server/tests/test_web_api.py`、`server/tests/test_api_path_normalize.py`、`server/tests/contract/test_c端_contracts.py`：断言同步
- 部署顺序：C端 打 tag 发版且用户安装新包后，再部署 S端 后端删除（S端 合 main 不自动部署，天然留出窗口）
- POST /api/authorize 与 GET /api/check-auth 契约零变更；C端 轮询链路（2s × 最多 60 次、登录窗口限定）不受影响

## Design Impact

- 受影响端：S端（/auth 页小修）；C端 仅改后端拼 URL，无界面变化
- 受影响屏/弹层：S端 `/auth` 设备授权页（升级为唯一正版页，承接全部真实流量）
- 对象状态：沿用既有状态语言（loading / notice 的 err、warn / ok 态、pill），无新增状态
- 是否触碰两端共享段：否（不改 base.css 令牌与基础组件类）
- 原型先行：纯 S端 改动免原型（AuthPage.vue 已存在且经换装 #194 对齐）；按约定在 change 目录附渲染截图对照
- 设计工件产出：实现侧自查 + PM/UI agent 切流量前复审（PM 验收标准逐项核对 + Open Design 合规终审，已并行进行）
