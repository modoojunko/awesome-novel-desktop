## 1. 原型先行（design-system 流程硬性要求）

- [x] 1.1 `docs/design-c/prototypes/list.html` 三值对齐 works.html：`.main` padding 48px→40px、`.page-head` margin-bottom 36px→26px、`.page-head .sub` 显式补 `margin-bottom: 0`；≤480px 媒体查询同步：`.main` 32px 16px 64px→28px 16px 64px、`.page-head` gap 16px→14px／mb 28px→22px。验证：浏览器打开 file:// 原型，measure `.main` padTop=40、`.page-head` mb=26、page-head 高 73（sub 下无 13px 空隙）。
  - 证据（ph.mjs 实测）：page-head h=73 mb=26px、child[0] y=158 h=73、sub y=211 h=20——与 works.html 完全同值（改前 166/86/219）。
- [x] 1.2 `docs/design-c/prototypes/ADJUSTMENTS.md` 换代节（「list.html 书架屏换代」）补第 12 条登记：间距随草稿补齐晋级（三值＋窄屏断点）；`.sub` 1em 考古结论（旧原型 UA `p` margin 显式复刻，works.html 已 `p{margin:0}` 归零）；屏级作用域理由（model-config 44/28 先例）；已知微差豁免：`.update-strip` 窄屏 padding 属全局壳层不入本批。验证：文件内可见新条目且含豁免说明。

## 2. 实现侧

- [x] 2.1 `client/frontend/src/design/list.css` 追加 `.pg-works` 屏级间距块（desktop 三值＋≤480px 断点两值，形状见 design.md 决策 3，注释注明 works.html 口径与 `.pg-config` 先例、级联顺序依赖）。验证：`npm run design:lint` 无新违规。
  - 证据：`npm run design:lint` exit=0（裸 hex 5 文件系 ADJUSTMENTS #11 登记的 main 存量，非本批新增）。
- [x] 2.2 `client/frontend/src/pages/NovelListPage.tsx` 根元素挂类：`<main className="main">`→`<main className="main pg-works">`，其余零改动。验证：`npx tsc --noEmit` 绿；`grep -c pg-works NovelListPage.tsx` = 1。
  - 证据：`npx tsc --noEmit` exit=0。

## 3. 门禁与回归

- [x] 3.1 烘镜像进主栈（works-finish-flow 收官配方）：重建 `ai-novel-client-frontend` 镜像并按容器名重启，使 5174 服务新构建。验证：`curl -s localhost:5174` 取新 bundle，grep 到 `pg-works`。
  - 证据：`docker build … -t ai-novel-client-frontend:latest` 成功；`docker compose up -d client-frontend` 换容器（中途裸 `docker run` 未接 compose 网络已废弃改走 compose）；新 bundle `assets/index-DTdNH-37.js`（旧 `index-BrB8chnF.js`）grep `pg-works`=1。
- [x] 3.2 C端 `npm run design:check`：lint＋parity books/empty/quota/finish 四场景全绿（像素差 <0.2%，预期双侧同值回 0 差量级）。输出摘要（各场景差异百分比＋baselines 三图路径）追加在本 checkbox 下。
  - 证据：`5 passed (16.8s)`——design:lint exit 0 ＋ parity 书架 books/empty/quota/finish 四场景 ✓（阈值 0.2%，绿即达标）＋ preview 场景 ✓；对比图已落 `docs/design-c/baselines/list.{books,empty,quota,finish}.{proto,app,diff}.png`。
- [x] 3.3 `npx tsc --noEmit`＋NovelListPage 相关 vitest（`npx vitest run NovelList` 如有用例）绿；相关 e2e（works-finish-flow.spec.ts）绿。输出结论追加在本 checkbox 下。
  - 证据：`npx tsc --noEmit` exit=0；`npx vitest run src/__tests__/` 73 文件 674 用例全绿（含 novelListPage.test.tsx）；`npx playwright test e2e/works-finish-flow.spec.ts` 4 passed (7.8s)。
- [x] 3.4 人工对照：/tmp/works-parity/compare.mjs 同数据双侧重跑，差异回 ~0%（排除登记偏差项 ⋯ 菜单后肉眼一致），截图留档 change 目录 `evidence/`。
  - 证据：同数据（四态各一）works.html vs 5174 逐像素差异 **5.062%→0.457%**；分带定位剩余差异仅两处登记项——y0-100 更新条（草稿演示字面 v0.19 vs stub v0.13，ADJUSTMENTS #9 登记不采用）、y550-600 第二行卡片 ⋯ 菜单钮（换代节 #4 登记保留）；`.main`/`.page-head`/`.cards`/卡片矩形全部同值。截图与 DOM dump 留档 `evidence/{proto,app,diff}.png`＋`*.dump.txt`。

## 4. 收尾

- [x] 4.1 清理 /tmp/works-parity 临时脚本（一次性诊断件，不入库）；确认无 stray 改动（`git status` 干净除 change 目录与四文件）。
  - 证据：`/tmp/works-parity`＋临时 bundle/log 已删；本批改动面＝`list.css`／`NovelListPage.tsx`／`prototypes/list.html`／`ADJUSTMENTS.md` 四文件＋openspec change 目录（evidence 含本批对比图）。
  - **共存提示**：工作区另有 4 个**非本批**的已修改文件（`ChapterWorkspace.tsx`/`VolumeWorkspace.tsx`/`workbench-features.spec.ts`/`book.css`）——系另一会话「章/卷页签同位＋衬垫修复」的未提交改动（见记忆 workbench-tab-position-fix），提交本批时**勿裹挟**。
