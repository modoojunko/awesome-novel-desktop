## 1. 原型先行（C端 用户可见改动）

- [x] 1.1 逐屏判定受影响原型：设定·主线卡、完本确认弹窗、空书架卡/空书落点卡、提示词总览页；有对应原型文件（如 `book.html`/`home.html`/`foreshadow-settings.html` 等）的补失败态与置忙态，无对应原型的登记「无原型基线」——`docs/design-c/prototypes/ADJUSTMENTS.md` 登记项贴进 change 目录
- [x] 1.2 文案按 design-language.html §13 口径自查（动词按钮、无内部术语、补救语句带可点击出口）——自查结论贴进 change 目录

## 2. 主线卡加载失败不得整卡覆盖

- [x] 2.1 `useStoryArc` 增加 error 态：加载失败不再 `snapshotLoaded(EMPTY_ARC)`——diff 贴进 change 目录
- [x] 2.2 `StoryArcForm`/`SettingsView` 失败态呈现（err 语气 + 重试出口）并禁用保存——diff + 截图路径贴进 change 目录
- [x] 2.3 单测：加载失败后保存入口禁用且不发起 PUT；重试成功后回显可保存——`npx vitest run` 相关用例绿

## 3. 完本核对清单失败必须显式

- [x] 3.1 `FinishModal` 伏笔清单失败态（err 语气 + 重试）并禁用完本确认钮；卷章树失败同样显式——diff + 截图路径贴进 change 目录
- [x] 3.2 单测：失败态下确认钮禁用；成功且为空时文案为「无进行中伏笔」且可确认——vitest 绿

## 4. 建卷建章入口防重复提交

- [x] 4.1 `createVolume`/`createChapter` 加 in-flight 闸（`creatingRef` 范式）——diff 贴进 change 目录
- [x] 4.2 六处入口（`NovelWorkspace.tsx:834,1061,1068,1100,1143,1150`）提交中置忙禁用——diff 贴进 change 目录
- [x] 4.3 e2e：双击空书架卡「新增一卷」只产生一卷、无 500 提示——e2e 用例结论贴进 change 目录

## 5. 权益缓存随登出与换号失效

- [x] 5.1 `cachedVerify` 收进带 `reset()` 的缓存单例，`lib/auth.ts` logout 调用；Provider 登录态下降沿兜底重置——diff 贴进 change 目录
- [x] 5.2 单测：登出后缓存被清；换号登录首次判定用新快照；同会话节流不变——vitest 绿

## 6. 章提示词总览取数纪律

- [x] 6.1 后端新增批量只读端点（按书/卷返回各章提示词存在性，`GROUP BY chapter_id` 聚合）＋pytest 覆盖——`pytest client/backend/tests` 相关用例绿
- [x] 6.2 前端总览改批量取数（去掉逐章串行循环）——diff 贴进 change 目录
- [x] 6.3 骨架/单章查看失败态（err 语气 + 重试），不再显示为空——diff + 截图路径贴进 change 目录
- [x] 6.4 e2e/性能口径：多章书打开总览的请求数有界（不随章数串行）——结论贴进 change 目录

## 7. 回归

- [x] 7.1 `npm run design:lint`、`npm run design:check`（C端）输出结论贴进 change 目录
- [x] 7.2 `tsc --noEmit`（C端）与 `pytest client/backend/tests` 输出结论贴进 change 目录
- [x] 7.3 `npx vitest run`（全量）输出结论贴进 change 目录
- [x] 7.4 定向 e2e（空书建卷/完本/提示词总览/设定主线）在隔离 docker 栈通过——结论与截图路径贴进 change 目录
