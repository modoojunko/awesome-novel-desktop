## Context

见 proposal.md「Why」。纯界面重组（零 API/存储/提示词改动），受三条现状约束：

1. **右栏数据通道被多处消费**：`OgStats`（reqOk/planWords/plotCount/castCount/missingLabels）经
   `ChapterWorkspace` 的 `onRailData` 上抛，右栏七个页签消费不同子集。撤章纲统计卡≠撤通道——
   reqOk 仍供操作页签、planWords 仍供正文页签、missingLabels 仍驱动「还缺」清单与「补全缺失字段」
   禁用态。
2. **render-loop 前科**：`onRailData` effect 依赖里塞进「每渲染都换身份」的对象曾致 e2e 空转烧 CPU
   （09-26 事故）。头部徽章的统计若走「每渲染新建的 memo → 进 effect 依赖」会复发同型循环。
3. **prose 常驻挂载**：`ProsePane` 以 `hidden` 切换常驻，`fs/lh` 是它的排版 props；头部 seg 撤除后
   这条数据流不能断。

## Goals / Non-Goals

**Goals**

- 四条拍板逐一落位，且头部徽章口径与原右栏统计卡**逐值一致**（同 ogGaps 分母、同 wt→targetWords 兜底）。
- 零 render-loop 风险：不改 `onRailData` effect 的依赖面与身份语义。
- e2e 与单测同批钉住新落位，防回潮。

**Non-Goals**

- 原型 `book.html` 同步改版与 parity 基线重录（ADJUSTMENTS 已登记，待原型同批更新）。
- 其余页签右栏统计卡、卷视图头部。

## Decisions

- **D1 统计计算双处各算、口径注释互指**：头部徽章在 `ChapterWorkspace` 渲染体内直接算（`gaps`/
  plotCount/castLines/wtParsed），`onRailData` effect 保持原有内联计算不动。不抽共享 memo——
  memo 依赖若含「每渲染换身份」的中间量（如外层 `gaps`）会让 effect 每渲染重跑 → setState →
  父重渲 → 死循环（09-26 事故同型）。两处逻辑各 4 行，以注释互指口径同源。
- **D2 `OgStats` 类型不收缩**：plotCount/castCount 在右栏已无展示位，但随数据通道保留（删字段要连
  动 rewriteFlow 等测试夹具，收益为零）；接口注释逐字段标明消费方。
- **D3 排版偏好收 `typo` 单一 state**：`fs/lh` 两个 state＋两个 setter 收为一个对象 state；setter 仅
  剩切书 effect 使用（只读回显）。`prefs.ts` 的 `setBookFontSize/setBookLineHeight` 从本文件摘除
  （BookPrefsModal 仍在用），`FontSizePref/LineHeightPref` 类型导入同步摘除。
- **D4 归档卡对旧稿支线不渲染**：头部旧按钮对 ghost 章可见（仅 archived/空章禁用）——ghost 是只读
  支线副本，归档无语义且无任何流程依赖；与重写/回退卡的 `!ghostOf` 口径拉齐。
- **D5 版本历史按钮进 `role=tablist` 行内**：语义上非页签件，以 `.ch-history`（btn-ghost btn-sm＋
  `margin-left:auto`，three-col 下 `align-self:center`）视觉区分；e2e 按 accessible name 定位不受影响。
- **D6 e2e S_API env 化**：`settings-forms`/`free-writing-flow`/`chapter-rewrite`/`modals-pr5` 四处
  `const S_API = "http://127.0.0.1:19000/api/web"` 改 `process.env.E2E_S_API || 原默认`——
  ai-assist/chapter-plan 早是此约定；不设 env 时行为不变（CI nightly 兼容）。

## Risks / Trade-offs

- 〔workbench parity 漂移〕头部/页签行/操作页签与原型不再逐像素一致 → ADJUSTMENTS 登记，基线待
  原型同批更新后重录；design:check 为本地门禁，不影响 CI。
- 〔归档入口变深一层的发现性〕高频归档用户需多一次页签点击 → 换来头部常年干净；右栏正文页签
  「已达成目标 · 可以归档本章了」提示文案保留指路。
- 〔头部徽章在 ogLoading 窗口闪默认值〕EMPTY_OG_FORM 下先显示 0/2 等 ~100ms——与原右栏统计卡
  同款时序，非新退化。

## Migration Plan

纯前端同批切换，无数据迁移、无兼容窗口（零真实用户口径不变）。
