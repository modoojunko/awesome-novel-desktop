# device-auth-page Specification

## Purpose
设备授权页入口契约：C端 桌面端发起设备绑定时在宿主浏览器打开的授权页由 S端 前端 `/auth` 唯一承载，后端不再提供手写内联授权页。授权动作（POST /api/authorize）与 C端 轮询（GET /api/check-auth）契约不变。

## ADDED Requirements

### Requirement: 授权页由 S端 前端 /auth 唯一承载

C端 桌面端 SHALL 构造授权页地址为 `{web_origin}/auth?pc_hash=<pc_hash>&pc_name=<urlencode(pc_name)>&device_profile=<device_profile>`，其中 `web_origin` 为 public_server_api 剥掉尾部 `/api` 后的源（如 `https://www.awesomenovel.com/api` → `https://www.awesomenovel.com`）；系统 SHALL NOT 提供后端内联授权页（GET /api/auth-page 返回 404）。

#### Scenario: C端 发起设备绑定打开正牌页

- **WHEN** 用户在 C端 登录页点击「浏览器登录」
- **THEN** 宿主浏览器打开 `{web_origin}/auth?pc_hash=...&pc_name=...&device_profile=...`，页面为 S端 前端设计系统授权页（含无效态/注册入口/限频文案/成功态套餐与到期展示）

#### Scenario: 旧内联授权页已删除

- **WHEN** 任意客户端请求 `GET /api/auth-page`
- **THEN** 返回 404，响应体不含任何授权表单 HTML

#### Scenario: device_profile 经 query 传递不失真

- **WHEN** C端 将 URL-safe Base64（无 padding）编码的 device_profile 拼入 query 打开 /auth
- **THEN** 授权页解析到的 device_profile 与 C端 原串逐字符一致，提交 /api/authorize 后设备档案完整入库

### Requirement: 授权页消费 pc_name

授权页 SHALL 读取 query 中的 `pc_name` 并随授权请求提交，使设备在控制台展示用户可见的设备名；`pc_name` 缺省时按空串处理，由后端既有兜底链（device_profile.hostname 优先）承接。

#### Scenario: 设备名随授权落库

- **WHEN** 用户在 /auth 页输入账密提交授权，URL 携带 `pc_name=Work-Mac`
- **THEN** /api/authorize 收到 pc_name="Work-Mac"，生成的设备记录以该名称展示

### Requirement: 授权与轮询契约零变更

授权动作 SHALL 仍为 POST /api/authorize（username/password/pc_hash/pc_name/device_profile），C端 轮询 SHALL 仍为 GET /api/check-auth?pc_hash=...（code 0 携带 token/username/tier/expires_at），本变更 SHALL NOT 修改两接口的请求响应契约。

#### Scenario: 授权全链路走通

- **WHEN** 用户在 /auth 页提交正确账密
- **THEN** 页面展示授权成功（含套餐 tier 与到期日），C端 在轮询窗口内经 check-auth 拿到 token 自动进入主界面
