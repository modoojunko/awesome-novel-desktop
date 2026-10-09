## Why

内测反馈（飞书反馈表 #4，跟踪 issue #784）：能力包未安装时「写作能力」引导弹窗在每次回到「我的作品」页都强制重弹——网络不通（如挂代理装不上 CDN 包）的用户永远装不上，弹窗就永远循环出现；关闭弹窗只有当次有效，没有任何「不再提示」记忆。网络层根因（SOCKS 系统代理出网崩溃）已由 c-httpx-socks-fallback（v0.30 首发）修复，但「网络暂不可用期间弹窗循环打扰」的 UX 缺口独立存在，升级不解决。

## What Changes

- 首装弹窗增加**持久化关闭记忆**：用户关闭首装引导弹窗（任意非锁定态出口）后，写 localStorage 标记；之后回到「我的作品」页不再自动弹首装窗，直至包装上为止（装上后标记清除自愈）。
- 更新弹窗的「暂不更新」同样持久化：记住关闭时所见的 CDN 版本号，**同一版本不再重复弹**；CDN 出现更新版本号时自动重新获得提醒资格（版本变了提醒才有意义）。
- 手动入口不受影响：账号面板「写作能力」菜单项（manual 模式）随时可开，是持久化关闭后的兜底路径；AI 功能报 `prompts_missing` 的既有文案指引不变。
- 弹窗队列入场约束（shell-dialog-queue）、进度期锁定、探测静默语义全部维持现状不变。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `prompt-pack-delivery`: 「写作能力引导弹窗（首装/更新/手动）」requirement 增加持久化关闭语义——首装关闭后不再自动弹（装上自愈）、更新暂不更新按版本号记忆重弹；MODIFIED 同时微调「暂不更新」场景的「下次再提示」为「同版本不再提示」。

## Impact

- 前端：`client/frontend/src/components/novel/license/PromptPackModal.tsx`（close/暂不更新处写标记＋装完清标记）、`client/frontend/src/pages/NovelListPage.tsx`（自动弹前查标记）、新增或就近放一个存取 helper（先例：`MigrationBanner` 永久关闭、`ExpiryNoticeBar` 按日记忆）。
- 后端：零改动（probe 契约不变；`latest_version` 已在 probe 返回里，作更新重弹的版本锚点）。
- 测试：NovelListPage 弹窗触发用例需补「已关闭不再弹／同版本不重弹／新版本重弹」；PromptPackModal 关闭写标记用例。存量 e2e 若依赖「未装必弹」需同步适配。
