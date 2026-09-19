## 1. 后端：完结状态落库与端点

- [ ] 1.1 `models/project.py`：novels 加 `finished_at`（TIMESTAMP 可空）
- [ ] 1.2 `main.py`：lifespan 补 `ALTER TABLE novels ADD COLUMN finished_at TIMESTAMP` 守卫块（列存在检查）
- [ ] 1.3 `novels/router.py`：list/detail 下发 `finished_at`；新增 `POST /{id}/finish`（守卫：未完结＋主线章数>0＋主线归档数==主线章数，否则 409）与 `POST /{id}/reopen`（守卫：已完结，否则 409）；完结写/撤完本清＋updated_at 常规更新
- [ ] 1.4 pytest：finish 成功/重复 409/未全归档 409（含 ghost 支线不计入）/reopen 成功与 409/list-detail 字段下发

## 2. 前端：阶段模型四态

- [ ] 2.1 `lib/novelStage.ts`：`NovelStage` 加 `ready`；`stageFromChapters(total, archived, finishedAt?)` 四态派生；`STAGE_LABEL`（done=已完结、ready=待完本，已归档退役）；`landingViewFor`（ready→workbench、done→archives）
- [ ] 2.2 `__tests__/novelStage.test.ts` 四态＋落点全分支
- [ ] 2.3 `lib/api.ts`：`finishNovel`/`reopenNovel`
- [ ] 2.4 grep `stageFromChapters`/`STAGE_LABEL` 全部消费方补参（NovelListPage、useWorkbench；useProject 数据链补 `finished_at`）

## 3. 前端：书架页 UI

- [ ] 3.1 `design/list.css`：`.b.ready` 档、`.foot-acts`、`fin-*` 弹窗清单家族（业务层，零 base.css）
- [ ] 3.2 新 `components/novel/FinishModal.tsx`：两态（待完本三行检查/已完结撤完本）；hooks 取 active＋留白本地 state；finish/reopen 接线＋409 toast
- [ ] 3.3 `NovelListPage.tsx`：四态徽章上卡；分状态页脚（待完本＝回看＋完本、已完结＝完结于＋查看）；待完本提示条（去完本/知道了会话内）；⋯菜单已完结书「完本信息 · 撤完本」；完结/撤完本后本地列表更新
- [ ] 3.4 `hooks/useWorkbench.ts`：落点 effect 认领一次性 `location.state.landingView`（白名单＋认领即清 state）
- [ ] 3.5 design-vocab：`.b.ready` 若被白名单拦截则两端同批登记；docs/ux §5 状态语言总表补两行
- [ ] 3.6 vitest：NovelListPage（徽章/页脚/提示条/⋯菜单/弹窗开合与完结交互）

## 4. design-c 管线

- [ ] 4.1 `prototypes/list.html` 换代（works.html 晋级：四态 SEED、分状态页脚、ready-notice、finish modal、fin-* 样式；update-strip 保留）
- [ ] 4.2 `ADJUSTMENTS.md` 新章登记：⋯菜单与撤完本入口、Banner 群 parity 态隐藏、留白不落库（弹窗内重置）、文案对齐（不提后台任务）、排序仍按 updated_at、知道了会话内、待完本卡点落写作
- [ ] 4.3 `e2e/design-parity.spec.ts`：FIXED_NOVELS/PROTO_BOOKS 扩四态（补 finished_at/stage 字面）；books 场景含 ready 提示条；新增 finish 场景（stub hooks）
- [ ] 4.4 `npm run design:lint` + `npm run design:check` 全绿（<0.2%）

## 5. e2e 与回归

- [ ] 5.1 新 `e2e/works-finish-flow.spec.ts`：种书→待完本徽章/页脚/提示条→弹窗（伏笔行＋留白切换）→完结→已完结页脚→⋯菜单撤完本→回待完本
- [ ] 5.2 存量回归：creation-flow/statusbar/update-notice/modals-pr5/shelf-request-budget/v01-acceptance＋全量 e2e（本机 docker 栈，按 c-client e2e runbook）
- [ ] 5.3 `tsc --noEmit`、vitest 全量、后端容器 pytest

## 6. 收尾

- [ ] 6.1 PR（worktree feat/c-works-finish-flow → main），CI 绿后合并
- [ ] 6.2 openspec 归档（archive＋specs sync 走 PR）
