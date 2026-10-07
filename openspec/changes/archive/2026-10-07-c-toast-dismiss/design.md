## Context

见 proposal.md（Why）：两条 `sticky` 回执 toast 永不消失且无关闭出口，用户投诉。`lib/toast.tsx` 是
模块级单例状态（`_toasts` 数组＋监听者集合），`Toaster` 为唯一渲染面；全站唯一提前收口 API 是
`toast.dismiss(id)`。拍板（2026-10-07）：默认 3 秒自动关闭＋× 手动关闭，sticky 整体退役。

## Goals / Non-Goals

**Goals**

- 全站 toast：默认 3 秒自动消失；每条带 ×；`sticky` 机制（类型＋分支＋调用点）删净。
- 两处回执调用点（plot 采纳、cast 写入）降为普通 toast，行为与 specs delta 一致。
- 不触两端共享段、不新增 CSS 类；parity 基线零漂移。

**Non-Goals**

- api-config `UndoToast`（8 秒软删除窗口，标准 §12 L4）与 `HooksSettingForm` 面板回执——面板内自管，不动。
- S端 toast 运行时（私有仓）——本轮零改动；若日后对齐 × 基线，另立 S端 change。
- toast hover 暂停计时、进度条、手动队列上限等增强——投诉不源于此，不扩面。

## Decisions

1. **× 走内联样式，不动 `base.css`。** 先例＝toast 内撤销按钮（`Toaster` 里 action 按钮已是 inline style）。
   `.toast` 已有 `pointer-events:auto`（共享段注释明言为可交互 toast 而设），× 可点性零新增 CSS。
   备选（原型侧同款 `.toast-x` 类下沉共享段）被否：会触发双端同批义务＋design-cross 基线变动，收益为零。
   原型侧仍补 `.toast-x`（list.html 局部样式）作视觉基线，ADJUSTMENTS.md 登记「实现侧内联、不入共享段」。
2. **退役 `sticky` 而非保留待用。** 死代码＋诱惑陷阱（cast 回执正是照抄 plot 先例踩进来的）。删类型＋分支后，
   编译器兜底任何残留调用点。
3. **plot 回执生命周期骨架保留。** `plotReceiptRef`/`killPlotReceipt`（编辑即收、切章即收）保留为提前收口；
   toast 已自动消失后 `dismiss(id)` 过滤空数组＝无害 no-op。撤销逻辑本身（`handlePlotUndo` 借 3 秒自动保存回写）
   原样——只是入口只活 3 秒窗口（拍板接受，spec 已翻转口径）。
4. **3 秒为全局统一默认，不做 per-call 时长参数。** 当前无差异化需求；真需要时再加 `duration` 选项，
   不预铺机制（避免半截 API）。
5. **文案/无障碍：** × 的 `aria-label`＝「关闭」（动词，§13），图形用 `Ico d={P.close}`（同文件 error 图标
   先例，跨字体渲染稳、不引入新 token），不用文本「×」字形；不新增可见文案；`role="status"`/
   `aria-live="polite"` 容器不变（× 与既有 action 按钮同口径，其可访问名随 live region 播报可接受）。
   action 按钮点击**不**统一加 dismiss——拍板只覆盖 3 秒＋×，规格措辞已对齐（点动作照常生效，
   未主动收的按基线自动收口）；要做 action-点击即收属新行为，另拍板另立。

## Risks / Trade-offs

- [plot 撤销窗口 4s→≈3s 实际缩短一半] → 拍板接受；spec 口径已翻转并在 design-system 立「撤销入口随 toast
  存活」总基线；若内测再反馈点不到，走「面板内自管回执」路线（§12 L4 同款）而非恢复常驻。
- [e2e 点撤销对 3 秒窗口敏感] → plot.spec.ts 现形状在「回执可见→点撤销」之间夹了 `expect.poll`
  真实落库轮询（plot.spec.ts:208-215，timeout 12000）——3 秒窗口内不可靠，scheduled e2e 随负载随机红。
  tasks 3.4 定为必改：断言回执可见后**立即**点撤销，中间轮询删除/后移（末尾轮询已传递性证明
  「采纳落库＋撤销＋自动保存回写」全链），复跑 3-5 遍；并顺手补「回执 3 秒自动消失」e2e 断言
  （新基线目前 e2e 零覆盖）。不给产品代码加测试后门。
- [多条长文案 toast 各自 3 秒，阅读时间偏紧] → cast 回执全文在弹窗 `done-notice`（aria-live）持久在场，
  toast 只是补充可见性；不为此破例延长。

## Migration Plan

纯前端，一次提交落地；无数据迁移。回滚＝revert 单提交。

## Open Questions

（无）
