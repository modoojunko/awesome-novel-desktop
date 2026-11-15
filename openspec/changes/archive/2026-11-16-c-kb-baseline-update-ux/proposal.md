# Proposal: c-kb-baseline-update-ux · 知识基线更新对齐提示词包

## Why

知识基线目前只在启动时拉一次 latest.json（`schedule_sync`，无周期轮询、无 UI 入口）：
官方发了新内容包（如 v4）后，用户不重启 app 永远拿不到，也**不知道有新版**。
提示词包已有一套成熟的更新方案（页面挂载探测→更新弹窗「当前 v→最新 v，立即/暂不」
＋暂不锚＋手动检查入口＋登录/校验钩子补装）。boss 拍板：知识基线**照抄这套方案**。

## What Changes

- **后端探测端点**：新增 `GET /api/kb/baseline/probe`——拉 CDN latest.json 验签，
  回 `{installed, latest, update_available}`；CDN 不可达回 `update_available:false`＋reason。
- **登录/校验钩子补装**：`browser_auth` 成功段（`maybe_after_auth` 旁）挂
  `kb.baseline.maybe_sync()`——纯本地早退（本地已有版本且层非空→零外呼），
  层空/从未同步才后台补装；受既有 `KB_BASELINE_SYNC=0` 闸管。
- **前端更新弹窗**（照 PromptPackModal 剪裁为两模式）：
  - update 模式：知识库页挂载探测到新版且未被暂不锚压制→自动弹
    「官方知识有更新｜当前 v3 → 最新 v4｜立即更新／暂不更新」；
  - manual 模式：知识库页头部小字入口「官方知识 vN」点开，展示当前版本与是否可更新。
- **同步反馈**：点「立即更新」→ await `POST /api/kb/baseline/sync`（既有端点、幂等）
  →成功 toast「官方知识已更新到 v4」；失败「更新没有完成，稍后可再试」。
- **暂不锚**：localStorage 记「暂不更新」时所见的 CDN 版本——同版不重弹、新版自动重臂
  （照抄 pack-modal-dismiss 机制）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `knowledge-baseline`: 新增需求「更新探测与触达」——探测端点、补装钩子、
  更新弹窗（update/manual）、暂不锚、更新完成反馈。

## Design Impact

- **受影响端**：C端（后端 kb/baseline、auth_local 挂点；前端知识库页＋新弹窗组件）。
- **受影响屏/弹层**：知识库页（KnowledgeBasePage，页头新增小字入口＋挂载探测）；
  新增居中弹窗 KnowledgeSyncModal（update/manual 两模式，经壳层弹窗队列 enqueueDialog）。
- **对象状态**：不新增状态语言对象——弹窗为即时交互层（open/closed＋busy 态），
  不入全局状态表；「暂不锚」为本机 UX 偏好（localStorage，同 pack-modal-dismiss 先例）。
- **共享段**：不触碰两端共享段；后端端点为 C端本地 API。
- **原型先行**：不需要——形态照抄既有 PromptPackModal（先例组件），无新视觉语言。
- **设计工件**：实现侧自查（对照 PromptPackModal／design-language §13 文案口径）。

## Non-Goals

- 不做 install 首装引导模式（启动＋补装钩子已静默自动装）。
- 不做 AcctMenu 入口（知识库有专属页面）。
- 不做 1s 轮询状态机（基线同步 await 直回、秒级）。
- 不动鉴权/COS 分发（后续另行立项）。
- 不动 f9ec49a3 已退役的隐藏管理/特权臂——只加「更新可见性」。
