# c-og-badge-archived-confirm

## Why

写作页「写作 X/Y 章纲」徽标把归档章排除在确认计数之外：后端章 `status` 是单列生命周期（outline→draft→confirmed→archived），归档落库把 `confirmed` 覆写成 `archived`，前端 `deriveOutlineStatus` 只认 `status==="confirmed"`——用户拆章规划 4 章、写完正文全部归档后徽标反而显示 0/4（实机复现，2026-10-01 报告）。#613（c-og-draft-no-autconfirm）退役「存草稿自动确认」后，不带确认一路写到归档成为常态路径，徽标对已完成的书长期显示 0/N。三路评审（前端/后端/架构师）已定稿修复包。

## What Changes

- **前端投影（主修）**：`useOutline.ts` 的 `deriveOutlineStatus` 把归档章（`meta.status === "archived"`）视为已确认——判据置于 chapterData 判定之前。写作徽标、章树三态 dot、删除盘点 chips 三面共用此函数，单点修＝三面全修；`allConfirmed` 随之变对。
- **后端守卫（同批堵洞）**：confirm 端点拒已归档章（409「本章已归档，恢复编辑后再确认章纲」）。现状 OgPane 确认按钮对归档章可点，误点会把 `archived` 翻回 `confirmed`：树 archived 标志翻转、frontier 退回、`total_archives` 永久虚高（unarchive 回减判据此时判 false，不可逆）。**此 hunk 与在途分支 c-og-confirm-gates（bc0a4380 已提交）逐字同形**——两侧同文同位，git 自动归并，谁先合都零冲突；PR 描述注明去重。
- **e2e 桩修真**：design-parity-book、design-parity-preview（chapter 工厂＋chapterDetail）、manuscript-download 三文件把归档章桩从 `status:"confirmed"+archived:true` 改为真实后端形态 `status:"archived"`，断言一律不动。桩与主修必须同批——否则夹具在反向静默说谎（parity 是活体对拍且不进 CI，没有任何门禁会拦住说谎的桩）。
- **原型同批对齐（硬流程）**：`book.html` 的徽标计数/dot/删除盘点/续写定位四处判定补「或已归档」，与实现新口径一致；ADJUSTMENTS.md 登记条目。种子数据（c2=已归档＋已确认）下新旧规则像素零差，design:check 不受影响。
- **测试钉**：vitest（归档→confirmed／loadChapterData 后仍 confirmed 的分支顺序钉／负钉不看 outline_status／unarchive 回落）＋NovelWorkspace 徽标「4/4 章纲」钉（本修唯一硬回归门禁——parity 不进 CI）＋pytest 四例（免费档 409／PRO 档 409-非-400 排序钉／归档-恢复-重归档全环 total_archives 恒 1／树契约 `archived:True`，均带状态不变式断言）。

### 不做（评审定案）

- 数据迁移：备份导入的书 status 保留 archived，前端投影天然覆盖。
- 树接口 `outline_status` 归一：前端不读该列（死载荷）。
- 后端归档保留 confirmed：`status=="archived"` 是树 archived 标志/frontier/unconfirm/unarchive/`resolve_prev_ending` 的承重墙。
- OgPane 按钮禁用：c-og-confirm-gates 有正式门禁 UX 设计（锁定横幅＋引导层），勿做两遍；后端 409＋toast 已兜底。
- versions.py restore_version 同族洞、写入口 CAS：跟进票，不进本包。

## Capabilities

### New Capabilities

（无——本 change 声明 `skip_specs: true`，先例 c-book-parity-rebaseline。）

### Modified Capabilities

（无。）confirm 端点拒归档章的 requirement **归 c-og-confirm-gates 所有**（其 proposal「章纲状态机守卫」条目＋workbench/chapter-dossier delta 已覆盖），本 change 只提前落码，不制造第二个 spec delta；modnav 徽标计数语义无既有 spec 钩子（前端投影属实现细节，不构成 capability 变更）。

## Design Impact

- 受影响端：**C端**（S端 零改动）。
- 受影响屏：写作页模块导航「写作 X/Y 章纲」徽标（计数口径变化）；章树三态 dot（归档章黄点→绿点，与既有「已归档」tag 并存）；删除盘点 chips（归档章「章纲草稿」→「章纲已确认」）；工作台右侧无改动。
- 对象状态：无新增状态、无新增语气词、无第四种胶囊——归档章复用既有 confirmed 态的 ok 词汇（dot-ok／「章纲已确认」），与状态语言总表一致；「已归档」文字 tag 照旧承载归档信息（信息无损）。
- 共享段：不触碰 base.css 令牌与组件类，双端同步条款不触发，design-cross 不涉及。
- 原型先行：是——`book.html` 四处判定规则先改并登记 ADJUSTMENTS.md，实现随后同批对齐；种子数据下像素零差。
- 设计工件：实现侧自查（规则对齐类改动，无新视觉形态）。

## Impact

- 代码：`client/frontend/src/hooks/useOutline.ts`（主修＋测试）；`client/backend/chapters/router.py`（confirm 守卫，与 c-og-confirm-gates 同形）；`docs/design-c/prototypes/book.html`＋`ADJUSTMENTS.md`；e2e 三文件桩数据；前后端测试文件。
- 行为面：全归档书的徽标 0/N→N/N；`allConfirmed` 变 true（无生产消费方，已核实 transitionToPrompt 零 UI 调用方）；unarchive 恢复编辑后徽标回落 N-1/N（符合「恢复编辑需重新确认」语义）；对归档章调 confirm 从静默腐化改为 409。
- 兼容：备份导出/导入 round-trip 保留 status，新旧行为一致；无 API 契约变化（409 为新增错误分支，前端 api.ts 原样透传 toast）。
- 风险：与 c-og-confirm-gates 的 router.py 同位 hunk——逐字同形保零冲突；其测试改动（conftest helper、既有归档测试加确认步）与本包新增测试不同 hunk，可干净合流。
