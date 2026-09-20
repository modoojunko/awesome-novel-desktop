## 1. 原型先行（design-system 流程硬性要求）

- [x] 1.1 晋级 `prototypes/list.html`：v2 正文并入（工具栏/分组/dot/分页/`bk-list` 等价结构＋`od.works.v1` 键＋`state/finishedAt` 字段＋数字 `createdAt/updatedAt` 归一化）＋**保留 v1 两块应用侧扩展**：quota 依赖块与 **first-run 三步引导块**＋`.book-card .foot` 三值随 v2 补抄。
  - 证据：/tmp/promote-v2.py 逐锚点断言替换成功（48.2KB）；五态 DOM 探针全过——①零书 first-run＋工具栏隐藏 ②筛选无果 bk-empty＋清除筛选 ③四态混排 rank 序（ready→writing→setting→done）④quota 锁卡/提示条/主按钮带锁 ⑤待完本分组头「1 本 · 主线已收齐＋去完本」。
- [x] 1.2 `ADJUSTMENTS.md` 新章「list.html 书架屏换代 v2」（10 条）＋改写前章 #6。
- [x] 1.3 新档位无条件登记（章内第 7 条：chip 30/12.5、search&sort 36、group-head 15 serif 等；注明 CSS 不在 lint 扫描面）。
  - 证据：`npm run design:lint` exit 0（存量统计不变）。
- [x] 1.4 `prototypes/CLAUDE.md` 屏说明同步 v2（工具栏/分组/分页/注入键）。

## 2. 实现侧

- [x] 2.1 `src/lib/shelfSort.ts` 纯函数＋单测。
  - 证据：15/15 绿（含比较器容错三态 ISO/null/缺失、created 证伪数据、rank 恒优先、组合过滤、分页切片）。
- [x] 2.2 `NovelListPage.tsx` 重构（filters 单对象/工具栏条件渲染/bk-list/分组/分页 IO 守卫/空态两分/删提示条四处/done 回看/data-od-id 全量）。
  - 证据：`npx tsc --noEmit` exit 0。
- [x] 2.3 `list.css` 新家族＋`.bk-chips .chip` 作用域化＋999px＋`.foot` 补抄＋`.b` nowrap。
  - 证据：`npm run design:lint` exit 0。
- [x] 2.4 既有测试随批更新（works-finish-flow.spec 四用例重写；novelListPage.test chips/回看歧义 within 收窄、提示条组替换、三步引导保留；新增工具栏单测）。
  - 证据：`npx vitest run` 74 文件 690 用例全绿。
- [x] 2.5 新增 e2e：`e2e/shelf-toolbar.spec.ts`（已完结 409 透出服务端 detail／清除筛选四复原／分页按钮程序触发＋IO 冒烟／回看落预览真实后端两入口）＋works-finish-flow 分组头用例。
  - 证据：shelf-toolbar 4 用例＋works-finish-flow 4 用例 8 passed；分页按钮点击竞态（滚动即触 IO）按 F23 口径改程序触发＋IO 独立冒烟；回看用例曝光 bind mount 上 rename 可见性抖动 → setupSession 改「真实 API 往返判据重试」（300ms×10）。
- [x] 2.6 骑手：FinishModal 双 catch 走 `errMessage`（409 透出服务端 detail）＋`lib/serverTime.parseServerTime` 补 Z（relTime/relDay 8h 时差）；app 侧补 v2「读者与编辑看到的状态是…」句。
  - 证据：tsc exit 0；e2e「已完结 409」用例断言服务端 detail 原样透出。

## 3. 门禁与回归

- [x] 3.1 parity 场景扩七＋注入契约换代。
  - 证据：`DESIGN_PARITY=1 playwright test e2e/design-parity.spec.ts` **7 passed**（books/group(ready)/empty-filter/empty/finish/quota/pagination）。修复两处：quota 场景 protoBooks 回退 bug（4 本 vs 1 本）；v2 更新条文字与弹窗「后台叙事」回归 → 基线回填 stub 字面＋现实口径（ADJUSTMENTS 章内第 12 条）。
- [x] 3.2 烘镜像进主栈（两轮：实现首版＋文案修订版），bundle `index-DP03gwsa.js` 含 `bk-toolbar`。
- [x] 3.3 C端 `npm run design:check` 全绿（lint＋全部 parity＋preview）。
  - 证据：`8 passed (25.6s)`——design:lint exit 0；书架 v2 七场景（books/group/empty-filter/empty/finish/quota/pagination）＋preview 场景全过（阈值 0.2%）；baselines 三图重出。
- [x] 3.4 `npx tsc --noEmit`＋全量 vitest（已 690 绿）＋**全量 e2e**（后台跑批）+相关回归（landing-view/landing 空态/shelf-request-budget/expiry/update-notice/statusbar/creation-flow）。
  - 证据：`npx tsc --noEmit` exit 0；**全量 e2e：166 passed / 17 skipped / 0 failed（7.9m）**（17 skipped＝parity 等 DESIGN_PARITY 条件场景，属正常）；全量 vitest 74 文件 690 用例绿。
- [x] 3.5 同数据双侧截图（works.html v2 vs 5174：books/group/empty-filter 三视图）留档 `evidence/`。
  - 证据：三视图逐像素差异 **0.104% / 0.101% / 0.096%**（余差＝草稿演示字面〔v0.19 更新条〕等登记项），`evidence/{books,group,empty-filter}.{proto,app,diff}.png` 六＋三图在案。

## 4. 收尾

- [x] 4.1 `git status` 改动面清点（仅本 change 路径）；临时脚本清理。
  - 证据：本批＝9 改（list.html/ADJUSTMENTS/CLAUDE.md/list.css/NovelListPage/FinishModal/design-parity.spec/works-finish-flow.spec/novelListPage.test）＋4 新（lib/shelfSort.ts、lib/serverTime.ts、__tests__/shelfSort.test.ts、e2e/shelf-toolbar.spec.ts）＋`openspec/changes/c-works-toolbar/`；baselines PNG 属 gitignore 本地资产。前轮共存的其他会话 4 文件已由其自行提交（现工作区无裹挟风险）。临时脚本（promote-v2/diag-*/show-states/probe/evidence 生成器）全部清除。
