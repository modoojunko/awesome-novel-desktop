# s-contract-live-check Specification

## Purpose
S web 前端↔S 后端之间的契约必须有活体检查：一组不打桩的冒烟用例在真后端上验证关键页面可用，且共享契约端点的响应形状以 fixture 单源、两端对拍——后端删路由/改字段不再是「全绿通过、线上才发现」。

## Requirements

### Requirement: 真后端活体冒烟档

S web e2e SHALL 包含一组不打桩（不挂 auto mock）的活体冒烟用例，经 vite proxy 打真后端验证关键页（落地页、登录成功进入控制台、备案页）可用；环境变量 `S_LIVE_BASE_URL` 未设置时整组 SHALL 跳过（不误连共享栈）；nightly 工作流 SHALL 设置该变量真跑本组。

#### Scenario: 活体冒烟真跑

- **WHEN** nightly 起真后端并设置 `S_LIVE_BASE_URL` 后运行 S web e2e
- **THEN** 活体组真执行（非 skip），落地页/登录进控制台/备案页断言通过

#### Scenario: 本地未设变量不误跑

- **WHEN** 开发者本地未设置 `S_LIVE_BASE_URL` 运行 S web e2e
- **THEN** 活体组整组 skip，其余 mock 用例不受影响

### Requirement: 共享契约响应以 fixture 单源

C↔S 共享契约端点（check-auth、devices/current）的响应形状 SHALL 以 `docs/contracts/` 下 JSON fixture 为单源，S端与 C端两侧各有对拍测试断言实现响应与 fixture 一致；fixture 演进 MUST 两侧同批。

#### Scenario: check-auth 契约对拍

- **WHEN** S端 check-auth 契约测试与 C端消费侧对拍测试分别运行
- **THEN** 两侧断言的响应键集/类型与同一 fixture 一致；一侧漂移即测试失败

#### Scenario: 字段新增两侧同批

- **WHEN** 契约新增可选字段并更新 fixture
- **THEN** 两侧对拍测试同批通过，旧消费方不受影响（加键兼容）
