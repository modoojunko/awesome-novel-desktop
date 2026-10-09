# tasks — c-og-cast-role-hover

> 用户口径（2026-10-09）：「章纲界面出场角色胶囊，每个角色要有标记 ta 是主角、反派、配角的标记。鼠标放上去可以看到 ta 的基本信息，人设」。

## 1. 原型先行

- [x] 1.1 `docs/design-c/prototypes/book.html`：`og-char-picker` 胶囊补身份小标（`.cast-role` 四档示例——沉舟[主角]/老陆[配角]/银铎[反派]/老周[路人]/魏七[配角＋「新」]，别名同标；没卡名「秦伯」维持「没卡」标不出身份标），并补悬停身份卡 demo（文件尾 `CAST_DEMO`：正名＋身份标/别名行/一句话人设/基础档案行/首次出场脚注，空格不出行）；局部样式沿既有 token 与字号档（10/11/11.5/12/12.5/13.5px），无裸色值、无 emoji。**验证 ✓** `node scripts/design-lint.mjs`：严格扫描 31 文件零违规。
- [x] 1.2 `docs/design-c/prototypes/ADJUSTMENTS.md` 登记 `c-og-cast-role-hover` 小节（5 条：身份标四档形制与角色类型色语言／悬停卡原型就地 demo vs 实现 portal+fixed＋panelAnchor zoom 折算／role 四档同标的理由／别名归卡／不进 parity 截图的依据）。**验证 ✓** 条目与原型、实现逐字对得上（类名、demo 种子、字号档、浮层对策）。

## 2. 前端实现

- [x] 2.1 新组件 `client/frontend/src/components/novel/workbench/CastHover.tsx`：`CastInfo` 类型＋`RoleTag`（四档小标，`.rg-node.role-*` 同名修饰词）＋`CastHover`（悬停/聚焦出身份卡：createPortal＋fixed、`htmlZoom()` 折算、下方放不下翻转向上的 `bottom` 锚定、横向视口夹取、max-height 限高、开 150ms/关 150ms 宽限、卡内悬停不收、Esc 收、滚动/resize 重锚、卸载后残留定时器 `!el` 守卫兜底）；卡内容空格不占位、长值行内折 2 行；effect 挂在提前 return 之前（info 翻转不炸钩序）。**验证 ✓** `npx tsc --noEmit` 零错。
- [x] 2.2 `ChapterWorkspace.tsx`：`refreshCharacterNames` 既有循环顺手产出 `castInfos`（正名与每个别名各一键 → 同一张卡摘要，哨兵名不入），新可选 prop 下发 `OgPane`；角色接口失败路径逐字不变（纯名字退化）。**验证 ✓** tsc 零错＋既有 vitest 全绿。
- [x] 2.3 `OgPane.tsx`＋`design/book.css`：查看态逐名胶囊与编辑态 `og-char-picker` 候选胶囊两态挂 `RoleTag`＋`CastHover`（有卡才包；没卡名维持「没卡」标与建卡入口）；CSS 新增 `.cast-role`（四档）/`.cast-hover`＋`chc-*` 一族＋「选中 chip 底 accent-soft 时小标改 surface 底」一条，只用既有 token（浮层阴影沿 `.mp-panel` 的 `--shadow-card` 先例）。**验证 ✓** tsc 零错＋`npm run design:lint` 全绿。

## 3. 测试

- [x] 3.1 vitest 新用例 `src/__tests__/castChipRoleHover.test.tsx` 10 例全绿：两态同貌身份标（主角/反派，别名归卡）／悬停卡内容（人设全文＋别名行＋性别·年龄·种族合一行＋已填档案＋首次出场，空格不出行）／没卡名无标无卡／castInfos 缺失退化纯名字／编辑态聚焦出卡且正名位显卡上正名／空人设/未出场/无别名不出行／开关时序（开延迟内移出取消、开着再入短路、卡内悬停不收、非 Esc 不收、Esc 收、卸载后定时器不炸）／下方放不下翻转 bottom 锚定／闭集外 role 不出标／castInfos 从缺到有不炸钩序。**验证 ✓** `npx vitest run src/__tests__/castChipRoleHover.test.tsx` 10/10；**判例**：React 的 `onMouseEnter` 须 `fireEvent.mouseOver` 触发；fake timers 下推进定时器须包 `act`，否则 React 19 调度不冲刷。
- [x] 3.2 覆盖率契约：`CastHover.tsx` 入 `COVERAGE_CONTRACT_FILES`。**验证 ✓** `npx vitest run --coverage`＝115 文件 / 1375 例全绿、零阈值报错，`CastHover.tsx` 四列全 100%；`coverageContract.test.ts` 5 例过。
- [x] 3.3 e2e 复核：出场角色相关断言（`workbench-features.spec.ts` 走 `#wf-chars` textarea 直填、`reconcile.spec.ts` 只匹配提示词文本、`cast-review.spec.ts` 只碰 `claim-name` 输入框）均不依赖胶囊内部结构。**验证 ✓** 无需更新；胶囊内新增小标不改这些选择器的命中面。

## 4. 回归

- [x] 4.1 前端全量：`npx tsc --noEmit` **零错**；`npx vitest run --coverage` ＝ **115 文件 / 1375 例全绿**（含新增 10 例）、覆盖率四闸零报错。后端零触碰（`charactersApi.list` 既有字段，无契约变更）→ 不涉 pytest。
- [x] 4.2 设计门禁：`npm run design:lint` 全绿（严格 31 文件零违规）。`design:check`（DESIGN_PARITY=1，本会话隔离 vite 5199，E2E_BASE_URL 指向自己）：预览屏 **1/1 通过**；书架屏 **6/7**（`quota` 存量红＝判例在册，失败集与在册判例逐字相同）→ 本次零新增漂移。
- [x] 4.3 双端影响判定（proposal Design Impact）：单端（C端）、不触 `base.css` 令牌与 `pill/notice/sk/panel/f-err` 共享段 → 不跑 `node scripts/design-cross.mjs`（依据：新类落 `book.css` cast-* 作用域族，只组合既有 token；S端 无对应面）。
- [x] 4.4 `openspec validate c-og-cast-role-hover --strict` ＝ **valid**；`openspec validate --specs` 全过（见 5.1 实测输出）。
- [x] 4.5 （基线诚实）`design-parity-book` workbench 场景 A/B 对拍（同机隔离 vite，同一 spec 双跑）：**pristine `origin/main`（/tmp 临时 worktree，12.193%）vs 本改（12.265%）**，增量 +0.072pp＝出场角色胶囊行身份标本身；两版差异图逐块目检，除胶囊行外逐字一致 → 该场景存量深红（查看态 vs 原型编辑态建模差，判例在册）之上零新增漂移。临时 worktree 与 5299 服务已拆。

## 5. 环境收尾

- [x] 5.1 `openspec validate c-og-cast-role-hover --strict` ＝ `Change 'c-og-cast-role-hover' is valid`；`openspec validate --specs` ＝ **61 passed, 0 failed**。隔离栈已拆：vite 5199（本改侧）与 5299（A/B 侧）逐口 kill，`/tmp/an-baseline-ogcast` worktree 已 remove；主检出（`fix/log-file-visible` 检出）与共享 docker 栈零触碰。
