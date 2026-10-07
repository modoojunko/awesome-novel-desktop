# Design: c-prompt-pack-onboard-modal

## Context

现状（v0.28.2，c-prompt-pack-client #686 + hardening #704 已上线）：

- 同步器 `client/backend/prompt_pack/sync.py` 四钩子（启动补偿 main.py lifespan／登录成功
  `browser_auth(silent=True)` code==0 分支／档位变化／手动 POST `/prompt-pack/check`），
  状态快照 `get_status()` 只有 phase（syncing/ready/missing/failed/tier_denied），无进度。
- 前端：四态卡 `PromptPackCard` 挂 AI 助手右栏（syncing/ready 不渲染＝全静默）；AcctMenu
  foot 小字行 `am-pack`（版本 + 小「检查」钮）；`/auth/verify` 的 `prompt_pack` 字段经
  LicenseProvider 消费；LicenseProvider 已有「路由进 /novels 或 /novel/* → check-auth 两
  跳刷新（60s 节流）」。
- 2026-10-07 定诊三洞：登录触发可被在途同步的 `_syncing` 锁吞掉（未登录启动同步先占锁
  挂在 S端 冷启动上）；失败后无近期自动重试；全静默设计让作家不知道发生了什么/去哪补。
- 探测现无「只查版本」路径：`maybe_after_auth` 在已装完好时早退（不查 CDN），手动 check
  会直接装新版——不满足「更新需确认」。

约束：用户可见名词统一「写作能力」；弹窗复用设计系统 `Modal`（`components/design/Modal`，
portal＋Esc/遮罩/焦点圈已具备）；存量 e2e（202 条 dev 态）零改动是硬门禁。

## Goals / Non-Goals

**Goals:**

- 首装：登录落地作品页即弹窗＋自动开始装包＋分步进度＋完成可关——作家无需知道任何
  内部概念。
- 更新：回作品页静默探测；有新版弹窗确认后安装（确认前旧版可用）；暂不更新不强制。
- 可靠性：登录触发不被吞、未登录不空跑（消掉首装竞态主成因）。
- 菜单入口从 foot 小字行升级为「数据」组完整菜单项。

**Non-Goals:**

- 不做后台定时轮询/强制更新/百分比进度环；不做下载断点续传（包 ~300KB）；
- 不改 S端 契约、包格式、七道校验、loader、加密布局；
- 四态卡与 BLOCK_TEXT 兜底机制保留（弹窗是主引导，卡是工作台内兜底）。

## Decisions

### D1 弹窗挂壳层单点 + CustomEvent 开启（沿用 legacy-migrate:open 先例）

`PromptPackModal` 单实例挂在应用壳层（与 RestoreModal/LegacyMigrateModal 同层），不挂在
`NovelListPage` 内——菜单项从任意页面（含工作台）都能打开它；开启通道 =
`window.dispatchEvent(new CustomEvent("pack-modal:open", { detail: { mode } }))`。
AcctMenu 的 RestoreModal 已验证该模式无双实例问题。
**为什么不在 NovelListPage 挂**：菜单入口在工作台也要能用；页面级挂载会在路由切换时
卸载中断轮询。

### D2 探测端点：GET `/api/prompt-pack/probe`（只探测不安装）

后端新增 `probe_latest()`：复用 `_candidate_urls`/`_fetch_json`/`_validate_outbound`/
`_verify_manifest_signature`/min_client 闸，取 latest 与 receipt 版本比较，返回
`{ installed_version, latest_version, update_available, reason?, source }`（无 phase——
探测不碰状态机，phase 由 /status 单源）。不打 S端、不下载、不写状态机（探测不得把
ready 抖成 syncing）；端点侧 `asyncio.to_thread` 包裹（同步 httpx 最坏 12s+，不得阻塞
事件循环——评审 P1-1）。dev 态（非强制包模式且包内目录可用、且无已装包）直接返回
`update_available=false, source=dev`（存量 e2e 零改动的关键；有已装包的 dev 机器仍走
真实探测——尊重真实安装态）。
**备选否决**：复用 POST `/check` 探测——它全自动安装，违背确认制；前端直连 CDN——
SSRF/验签纪律都在后端，不可复制到前端。

### D3 触发点选择：NovelListPage 挂载 effect（每次进入都探测）

- 挂载 effect：未登录不可能（路由有 AuthGuard）；逻辑＝先看本地包状态
  （`/prompt-pack/status`）：missing/failed → 开弹窗首装模式并 POST `/check`；否则
  GET `/probe`：`update_available` → 开弹窗更新模式；其余全静默。
- 「每次回到」＝每次路由挂载都探测（用户拍板字面执行）；同帧去重靠 effect 清理 +
  探测在途锁（模块级 in-flight 标记，避免 StrictMode 双挂载双打 CDN）。不加节流 TTL——
  latest.json 很小，且离开作品页往往意味着长时间不在。
- 首装检测为什么不用登录事件直连：登录完成后必然重定向 /novels，挂载点统一收敛在
  作品页，免去跨组件登录态联动的复杂度；重启后已登录未装包（上次失败）同样被覆盖。

### D4 进度面：`_state` 扩 `step` 字段（不新增端点）

`sync_once` 在关键节点写 step：`probe`（取 latest/闸门）→ `download`（含换钥等待）→
`install`（校验安装）→ 完成清空。`get_status()`/`/auth/verify` 自然带出，弹窗 1s 短轮询
`/prompt-pack/status`（沿用四态卡轮询先例，上限放宽到 180s——S端 冷启动 60s 口径）。
step 文案映射在前端：检查版本/正在下载/正在校验安装；换钥等待归入「正在下载」不单列
（「获取授权」是内部概念，作家无感）。
**为什么不做百分比**：包 ~300KB 下载秒级，慢的从来是 S端 冷启动等待——分步行是真实
瓶颈的诚实表达；百分比环暗示可预估，反而制造卡住焦虑。

### D5 触发可靠性：pending 重跑 + 未登录早退（定诊修复同批）

- `trigger_sync`：`_syncing` 为真时置 `_pending_tier`，工作线程循环消费 pending 直到
  空（评审 P2-1：重跑在途窗口的新触发同样不丢；后到覆盖先到、同步幂等兜底）。
- `maybe_after_auth`：本地无 token 直接 return（未登录换钥必 401，且 30-60s 冷启动占锁
  正是吞掉登录触发的窗口）。
- 失败自动重试**不引入定时器**：首装失败用户就在弹窗里（重新获取一键重试）；更新失败
  旧版仍可用，下次回作品页再探测——事件驱动已闭环，定时器是非必要复杂度。

### D6 菜单项与弹窗手动模式

- AcctMenu：「数据」组内、「模型配置 · API Key」之后加 `am-item`「写作能力」，hint 三态
  （已就绪 vX／未就绪／有新版本——数据源 `tier.pack` + 最近探测缓存）；点击 close() +
  CustomEvent 开弹窗。foot 的 `am-pack` 行与 `am-pack-check` 样式同批删除。
- 弹窗手动模式：展示当前版本与状态 + 「检查更新」按钮 → GET `/probe` → 有更新转确认
  UI，无更新 toast「已是最新」，未就绪转首装进度流。诊断复制从 AcctMenu 行迁入弹窗
  失败态（数据同源 `pack`）。

### D7 弹窗状态机（单组件内聚）

`mode ∈ {install, update, manual}` × `stage ∈ {confirm, running, done, failed}`：
- install：open 即 running（无 confirm），完成 done（「已就绪，可以开始写作」+ 关闭）。
- update：open 即 confirm（当前 vN → 最新 vM + 立即更新/暂不更新）；确认转 running。
- manual：open 显示状态 + 检查更新；按探测结果转 update-confirm 或 install-running。
- running（首装与确认更新后）**弹窗锁定**（用户拍板 10-07 二次：进度期不得提示可
  关闭——Modal locked 态 Esc/遮罩/X 全失效，完成才提示可关闭，失败解锁给重试）；
  confirm（更新确认）与 manual（手动）态不锁。同步本身仍是后台 daemon 线程。
- **文案明说（用户拍板 10-07 三次）**：进度与更新确认文案都直书「期间不能关闭此
  窗口」＋「预计 1 分钟左右，网络较慢时可能需要几分钟」；首装/更新（升级）同口径，
  运行态标题分诊（正在准备写作能力／正在更新写作能力）。
- **原子换版（同拍板）**：「不能边升级边换提示词」——安装本就 staging 全验后
  rename＋receipt 原子切换，在用模板集中途不变；staging 永不参与解析（pytest
  `test_update_keeps_old_set_until_atomic_swap` 钉）。
- tier_denied：沿用升级卡出口（member-block 事件），弹窗内呈现去升级。

### D8 原型先行与词汇同批

书架原型（list.html）加弹窗三模式变体 + 菜单项行；ADJUSTMENTS.md 登记；
design-language §5 状态总表加「写作能力弹窗」行；design-vocab.mjs 新词两端同批
（弹窗标题/进度行/完成行/失败行/菜单项三态 hint）。CSS 走既有 modal/am-item 类，新增
仅进度行样式（`.pm-steps` 族，前端 src 内）。

## Risks / Trade-offs

- [作品页挂载探测给 e2e/CI 增加 CDN 依赖] → dev 态探测恒 false（D2），强制包模式走假
  CDN 夹具（既有 PROMPT_PACK_MODE=force 机制），存量 spec 不受影响；新增场景组单独写。
- [探测每次挂载都打 CDN，频繁进出作品页请求放大] → latest.json 极小（静态托管无冷启
  动）；in-flight 去重 + StrictMode 双挂载保护；观察后如需再加 60s TTL（记 Open
  Question，不预做）。
- [弹窗自动弹出打扰] → 仅两类：未装包（不装就没 AI，弹窗是必要引导）与有新版（作家
  拍板要的提示）；无更新/跳过全静默。
- [pending 重跑与手动触发叠加造成双跑] → 重跑仅消费一级 pending、手动触发与自动触发
  共用同一 `_pending` 槽（后到覆盖先到），同步幂等（七道校验+版本闸）兜底。
- [更新确认前旧包与新客户端的 min_client_version 边界] → 探测沿用 latest 的
  min_client 闸（跳过＝无更新静默）；召回底线 min_pack_version 仍走安装时闸（既有语
  义，弹窗确认后的安装路径自然覆盖）。

## Migration Plan

纯 C端 前后端同版本交付，无数据迁移；回滚＝还原客户端版本（包目录/receipt/高水位布局
不变）。发布顺序无特殊要求（不依赖 S端 变更）。

## Open Questions

- 探测是否需要 60s 会话级节流（防极端频繁进出作品页）——默认不做，上线后看请求量再定，
  不影响契约（探测本就幂等静默）。
- 弹窗完成态是否加「开始写作」主按钮（现在只有关闭）——文案细节，实施时按原型评审定。
