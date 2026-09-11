# auth-page-direct-entry Design

## Context

三方联合评审（PM/UI/FE）已定性：`/api/auth-page` 是后端手写内联 HTML（authorize.py:21-99），正牌页 AuthPage.vue（/auth 路由）功能为超集但零流量，根因是 C端 `service.py:335` 硬编码拼 `{public_server_api}/auth-page`。用户已裁定：无存量用户需兼容，直接改 C端 指向 `/auth`，后端内联页删除（不走 302 垫片）。

关键事实：
- `public_server_api` 形如 `https://www.awesomenovel.com/api`（带 `/api` 后缀）；web_origin 需剥后缀获得
- `encode_device_profile` 用 URL-safe Base64 且去 padding（字母表 `A-Za-z0-9_-`），query 原样拼接无编码失真风险
- AuthPage.vue 已读 `route.query.pc_hash/device_profile`，仅 pc_name 未消费；apiAuthorize 第 4 参固定传 undefined
- S端 合 main 不自动部署（s-server-deploy 只认 tag v*/workflow_dispatch），合并与部署天然解耦
- C端 打 tag v* 发版（Release+资产一条龙），同一 v* tag 会触发 s-server-deploy——**打 tag 即部署后端删除，这是顺序约束的根源**

## Goals / Non-Goals

**Goals:**
- 设备授权全量流量落到 S端 前端 /auth 正牌页
- 后端删除内联页实现单一事实源，杜绝再次漂移
- 自有设备零 404 窗口（发版顺序保证）

**Non-Goals:**
- 不做 302 重定向垫片（用户裁定）
- 不改 POST /api/authorize、GET /api/check-auth 契约
- 不动 AuthPage.vue 的视觉/布局（仅 pc_name + autocomplete 两个非视觉小修；PM/UI 复审若发现问题另立后续）
- 不改 C端 轮询节奏（2s × 60 次，登录窗口限定，无常驻心跳）

## Decisions

**D1：web_origin 推导 = public_server_api 去尾 `/api`，不新增配置项。**
`public_server_api` 与 `SERVER_API_BASE` 同源（config.json / env / 兜底链），剥 `/api` 后缀即 web origin。备选「新增 public_web_origin 配置」被否：多一个配置项多一份漂移面，且现有取值链已保证 `/api` 后缀存在（`_normalize_server_api` 保证）。实现需容忍尾斜杠（先 rstrip("/") 再 endswith("/api")）。

**D2：后端删除而非保留。** AUTH_PAGE_HTML + 路由 + HTMLResponse 导入整体删除；备选「保留路由但刷 CSS」被否（双实现永续漂移），「保留 302」被用户裁定否（无存量）。删除后 GET /api/auth-page 自然 404，契约测试改写为 404 断言，把「内联页不得复活」固化为契约。

**D3：pc_name 在 AuthPage.vue 侧闭合。** `onMounted` 一并读 `route.query.pc_name`，提交时作为 apiAuthorize 第 4 参传入。备选「C端 从 URL 删掉 pc_name」被否：设备名是控制台设备列表的展示锚点，该传就该被消费。

**D4：autocomplete 走 AppInput 既有通道。** LoginPage 已传 autocomplete 的惯例（password manager 正确填充 + 密码可见切换依赖 AppInput 内建能力），AuthPage 对齐即可，不新造组件。

**D5：测试策略 = 删除断言 + 404 契约固化 + C端单测补 URL 构造。**
- server 侧：test_web_api / test_api_path_normalize 中 auth-page 200 HTML 断言删除；contract/test_c端_contracts.py（冻结契约）改写为「GET /api/auth-page 返回 404」+ 注明页面实体迁至 S端 前端 /auth
- client 侧：为 service.py 的 auth_url 构造补单测（web_origin 剥离、query 三参、pc_name urlencode）

## Risks / Trade-offs

- [打 v* tag 同时触发 C端 发版与 S端 后端部署，用户旧包（v0.15.1）在此窗口内点登录将 404] → 顺序约束：PR1（C端+前端小修）先合，用户安装新包确认可用后，再合 PR2（后端删除）；PR2 合并后的下一次 tag 前用户已在 v0.16+。风险仅存在于用户自己的设备，接受。
- [未来 C端 若把 public_server_api 指到无 SPA 的裸域（直连兜底场景），/auth 将落空] → 与现状同病（旧内联页在裸域同样错位），属配置约束；在 service.py 注释注明。
- [vue-router 与 URLSearchParams 对 query 边界字符解析差异] → device_profile 为 URL-safe Base64 无 padding，字母表不含 `+/=`，理论无差异；以 e2e 演练（真实设备档案走通授权）实证兜底。

## Migration Plan

1. PR1 合并（C端 service.py + AuthPage.vue 小修 + client 单测 + S端 e2e 确认绿）——此时线上行为无任何变化（AuthPage 已在线上，pc_name 原本就被后端忽略）
2. 打 tag 发 C端 新版 → 用户安装并完整演练一次设备授权（发起 → /auth 授权 → 轮询进主界面）
3. PR2 合并（后端删除 + 测试改写）→ 随下一次 v* tag 或 dispatch 部署 S端 后端
4. 回滚策略：PR2 回滚即恢复内联页（代码在 git 历史）；C端 侧回滚 = 用户装回旧包（旧包指向 /api/auth-page，依赖 PR2 未部署）

## Open Questions

（无——三评审 agent 的实现红线（相对路径/query 透传/勿用 301）随「删除而非重定向」的裁定一并消解）
