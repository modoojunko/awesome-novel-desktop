## MODIFIED Requirements

### Requirement: C端 顶栏外跳入口

C端 SHALL 在控制中心面板「支持」组提供「联系客服」菜单项，新窗口打开 S端 `/support` 页（`target="_blank"` 锚点，禁用编程式 window.open）；列表屏顶栏与工作台顶栏的「联系客服」常驻按钮 SHALL 移除（顶栏动作区收敛为头像唯一入口）。未登录的静态首页/登录页 MUST NOT 出现该入口（官网落地页页脚已覆盖）。外跳地址 SHALL 复用 C端 既有 portal_url 单一来源（后端 `/auth/config` 下发，`lib/portal.ts` 体系含安全校验），MUST NOT 在 C端 再硬编码一份 S端 域名。

#### Scenario: 已登录用户从列表屏跳转

- **WHEN** 已登录用户在列表屏打开控制中心面板并点击「联系客服」
- **THEN** 系统默认浏览器新窗口打开 `<portal_url>/support`，应用窗口不离开当前页面，面板关闭

#### Scenario: 已登录用户从工作台跳转

- **WHEN** 已登录用户在工作台顶栏打开控制中心面板并点击「联系客服」
- **THEN** 行为与列表屏一致，新窗口打开 `<portal_url>/support`

#### Scenario: 门户地址未取到时的降级

- **WHEN** portal_url 请求失败或返回空（如后端不可达）
- **THEN** 面板「联系客服」项不渲染，MUST NOT 出现指向测试兜底域名或空 href 的死链

#### Scenario: 不硬编码第二域名

- **WHEN** 检索 C端 实现中客服外跳地址的来源
- **THEN** 地址由 portal_url 追加 `/support` 路径派生，代码库内无独立于 portal 体系的第二个 S端 域名常量
