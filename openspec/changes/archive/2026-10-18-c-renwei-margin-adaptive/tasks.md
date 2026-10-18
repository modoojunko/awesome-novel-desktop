# Tasks: c-renwei-margin-adaptive

## 1. 实现（已随 PR #894 合入）

- [x] 1.1 纵向边注 top 按 `htmlZoom()` 折算回布局 px，消除大屏 zoom 二次放大漂移
- [x] 1.2 横向改为贴正文：边注列左缘＝正文栏实测右缘＋16px，列宽 clamp 120~224px 吃掉右侧留白
- [x] 1.3 `ResizeObserver` 观察正文与 `.editor-wrap`（正文宽度不变、位置随栏宽移动也重算）；滚动/resize 重算保留
- [x] 1.4 悬停详情卡右侧留白足够时朝右展开；窄栏放不下最小列宽时收成段侧 severity 圆点
- [x] 1.5 回归钉：zoom=1.25 下 top/left 折算、窄栏兜底类（`renweiCheck.test.tsx`）

## 2. 验证

- [x] 2.1 真 Chromium A/B（2560×1440，zoom 1.28）：未修漂 78/233px，修复后 ≤0.28px；1440×900 横向间距 16px
- [x] 2.2 正文栏 680→500（无窗口 resize）边注跟随；2560 强制滚动仍对齐；窄栏 850px 圆点不越界
- [x] 2.3 前端全量 1693 passed；`tsc`、`npm run build`、`design:lint` 通过
- [x] 2.4 PR [#894](https://github.com/modoojunko/awesome-novel-desktop/pull/894) CI 绿（1m52s），squash 合入 main＝`dfd5b496`

## 3. 归档

- [x] 3.1 `renwei-check` 主 spec「正文左右分边注与覆盖层」按本 change 同步
- [x] 3.2 `openspec validate --specs` 通过
