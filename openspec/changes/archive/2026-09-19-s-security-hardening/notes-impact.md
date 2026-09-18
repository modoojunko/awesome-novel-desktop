# 双端影响判定（任务 1.1）

> s-security-hardening 实施前判定（2026-09-18，实施中随实际落地更新）

## 四项结论

1. **受影响端**：S端 后端（主）+ S端 门户（两处纯文案）；C端 仅本机后端 `client/backend/auth_local/`
   逻辑适配。**C端 前端零改动**（硬约束：本机 check-auth 响应形状保持带 token，见 proposal）。
2. **屏/弹层清单**：无布局、无组件、无令牌变化；新增两处可见文案——
   ①S端 授权页 challenge 缺失/不合法时的兜底提示（复用既有 `notice warn` + 可点击出口）；
   ②S端 注册页用户名列 hint（design-language §13 上限可见）。两处按既有组件与文案口径产出。
3. **对象状态**：无新增或变化（仅复用既有 warn 语气；对照状态语言总表）。
4. **共享段**：不触碰（`@cross` 段、base.css 令牌、语义类家族零改动）→ 免原型先行、免 design-cross。

## 实施期校正（实测驱动，2026-09-18）

- **限流修复机制**：设计写的"反向排列 add_middleware"在本仓 venv（Starlette 1.6.0 + 当前 FastAPI）
  实测不成立（`user_middleware` 实际嵌套与"后 add 者在外层"假设不符，反向排列后行为不变）；
  改为限流器内部两形态归一（`_sensitive_filter`），与注册顺序解耦。design D3 已同步。
- **注册页 hint 与授权页兜底提示**：属任务 6.3（配对改造同批），尚未落地——实施进度见 tasks.md。
