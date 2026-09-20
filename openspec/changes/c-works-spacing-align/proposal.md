# 书架屏垂直节奏对齐 works.html 原型

## Why

c-works-finish-flow（#440）把 `drafts/works.html` 草稿晋级为 `prototypes/list.html` 基线时，只并入了四态内容家族（`.b.ready`／`.foot-acts`／`fin-*`／待完本提示条），**漏抄了草稿改动的垂直间距三值**——parity 是「原型 vs 应用」比对，两侧同错故四场景照样全绿，缺口被遮蔽。用户实测 5174 登录后书架与 works.html 原型整体不一致（同数据逐像素比对差异 5.06%，卡片区整体下移 31px）。用户裁定：**以原型为准**。

## What Changes

- 书架屏（/novels）垂直节奏对齐 `drafts/works.html`，三值：
  - `.main` 顶距 48px→**40px**（＋8px）；
  - `.page-head` 下缘距 36px→**26px**（＋10px）；
  - `.page-head .sub` 下缘距 `1em`→**0**（＋13px）。三者合计卡片上移 31px。
  - 窄屏（≤480px）断点同步：`.main` 32→**28px** 顶距、`.page-head` gap 16→**14px**／mb 28→**22px**。
- 实现走**屏级作用域** `.pg-works`（照 model-config `.pg-config` 先例：各屏节奏本就不同——list/backup-restore 48/36、model-config 44/28、works 40/26），`base.css` 全局壳零改动，其余屏不受影响。
- `.sub` 的 `1em` 下缘距考古结论：系 #181 像素复刻旧 list.html 时，把**未被重置的 UA 默认 `p` margin-bottom 显式写死**（旧原型无 `p{margin:0}` 重置）；works.html 草稿已加 `p{margin:0}` 全局重置归零。本 change 仅在书架屏归零，其余屏（与其原型「意外一致」）不动。
- `prototypes/list.html`（parity 基线）同批采用同值；ADJUSTMENTS.md 换代节补第 12 条登记。
- **不改**：⋯ 卡片菜单（换代节 #4 已登记的有意偏差）、更新提示条按钮组（notes_url 数据驱动）、状态栏版本号（真实版本）——排查中已排除的三项非缺陷。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `works-finish-flow`: 新增「书架屏垂直节奏」requirement——把 works.html 的屏级间距口径（含窄屏断点与屏级作用域约束）钉进规格；既有四态/完本链路 requirement 不动。

## Design Impact

- **受影响端**：C端 单端（S端 无对应屏，零改动）。
- **受影响屏/弹层**：书架 /novels 一屏；无弹层变化（完本弹窗等不动）。
- **对象状态**：不新增——四态徽章语言不变，无新状态/语气词。
- **是否触碰两端共享段**：否。改动全部落在 `list.css` 屏级作用域与 `NovelListPage` 挂类，`base.css` 令牌与基础组件类零改动，故无需双端同批、免 design-cross。
- **是否需要原型先行**：是——`prototypes/list.html` 三值＋窄屏断点先改，ADJUSTMENTS.md 登记（design-system「Prototype-first flow」既有流程约束）。
- **设计工件产出方**：实现侧自查——`drafts/works.html`（2026-09-17）即设计真值，本 change 是把它漏抄的部分补进晋级基线，无新设计决策。

## Impact

- 代码：`client/frontend/src/pages/NovelListPage.tsx`（`<main className="main">`→挂 `.pg-works`）、`client/frontend/src/design/list.css`（屏级间距块）。
- 设计线：`docs/design-c/prototypes/list.html`（三值＋移动端断点）、`docs/design-c/prototypes/ADJUSTMENTS.md`（换代节补登记）。
- 门禁：`design:lint` → C端 `design:check` 四场景（books/empty/quota/finish，像素差须回 <0.2%，需先把新构建烘进主栈容器）→ `tsc --noEmit` → 相关 vitest。无 API/数据/依赖变化。
- 注：`docs/ux/design-language.html` §「main 内容宽…padding 48/32/80」描述的是通用基线，各屏屏级差异以原型＋ADJUSTMENTS 登记为准（model-config 44/28 先例），标准正文不动。
