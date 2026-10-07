## 1. 原型先行（硬性流程第一刀）

- [x] 1.1 `docs/design-c/prototypes/list.html`（toast 设计事实源）：toast 示例尾部补 × 关闭钮（原型局部样式 `.toast-x`，可含 hover/焦点态，`aria-label="关闭"`），× 用图形（close path）不用文本「×」字形；toast 演示函数同步补 × 节点，并把演示自动移除时长 2400→3000 对齐新基线；核对 toast-in 动画与既有 `.toast` 布局不被 × 撑破（长文案＋撤销链接＋× 三元素同行）。验证：浏览器开 list.html 触发 toast，× 可点可收、3 秒自消、布局不溢出。
  - 回执：✅ 已落（list.html：.toast-x 样式＋close path 图形＋aria-label；演示函数 2400→3000＋× 可点）；布局为 CSS 追加不撑破，design:check 6 绿含书架屏基线。
- [x] 1.2 `docs/design-c/prototypes/ADJUSTMENTS.md` 登记三处：① toast 新增 × 关闭钮（list.html 基线）＋默认 3 秒自动消失；② 实现侧 × 走内联样式（先例＝toast 内撤销按钮），不入共享段/不新增全局类，且**无 hover 变色**（与内联 action 按钮同口径），键盘焦点走全局 `:focus-visible`；③ 演示时长以 3 秒为基线。验证：登记条目含 change 名 c-toast-dismiss 与偏差原因。
  - 回执：✅ 已登记（三处：× 基线／实现侧内联无 hover、焦点走全局 :focus-visible／演示时长 3 秒为基线）。

## 2. 实现（C端 `client/frontend`，后端零改动）

- [x] 2.1 `src/lib/toast.tsx`：自动消失 4000→3000；`Toaster` 每条尾部渲染 ×（`Ico d={P.close}`＋`aria-label="关闭"`，点击 `toast.dismiss(t.id)`，内联样式对齐既有 action 按钮法，无 hover 态）；删除 `sticky` 类型字段、`addToast` 分支与 `toast.*` options 签名中的 `sticky`。可选收紧（默认不做，做了注明）：晚到 timer 过滤前后长度不变则跳过 `notify()`，或 dismiss 时 `clearTimeout`。验证：`npx tsc --noEmit` 干净（残留 sticky 调用点会编译报错）。
  - 回执：✅ tsc --noEmit 干净（exit 0）；晚到 timer 未收紧（默认不做，按 tasks 备注留原样）。
- [x] 2.2 `src/components/novel/workbench/ChapterWorkspace.tsx`：plot 采纳回执去 `sticky: true`（`plotReceiptRef`/`killPlotReceipt`/撤销逻辑保留）；同步清理「常驻到下次编辑，拍板②」过时注释（581 行一带）。验证：相关 vitest 全绿。
  - 回执：✅ plotFlow vitest 绿；581 注释已更新。
- [x] 2.3 `src/hooks/useCastReview.ts`：cast 写入回执去 `sticky: true`（弹窗 `done-notice` 全文回执不动）；同步清理文件头注释与 `markWritten` docstring 里的「toast sticky」字样（7、121 行一带）。验证：`npx tsc --noEmit` 干净。
  - 回执：✅ tsc 干净；7/121 两处注释已更新。

## 3. 测试

- [x] 3.1 新增 `src/__tests__/toast.test.tsx`，盖 `toast.tsx` 四项 100%（`error`/`info` 形态类名与图标臂、action 有/无两臂、空态提前 return 全覆盖）。写法钉死：`beforeEach(vi.useFakeTimers)`＋`afterEach(act(vi.runAllTimers) 清场再 useRealTimers)`（模块级 `_toasts` 无 reset API，靠跑完所有挂起 timer 归零）；**先 render `<Toaster/>` 再发 toast**（`useToasts` 初值不回放挂载前 toast，反序假绿）；推进时间必须 `act(() => vi.advanceTimersByTime(...))` 包裹。核心断言：2999ms 仍在/3000ms 消失、× 点击立收且不影响他条、多条叠放各自计时。验证：`npx vitest run src/__tests__/toast.test.tsx --coverage` 中 toast.tsx 四项 100%。
  - 回执：✅ toast.test.tsx 6 用例；vitest run --coverage 中 toast.tsx 语句/分支/函数/行 四项 100%。
- [x] 3.2 `src/lib/toast.tsx` 追加进 `src/coverage-contract.ts` 的 COVERAGE_CONTRACT_FILES（CI 跑 `vitest run --coverage`，契约锁本批交付动过的文件）。验证：`npx vitest run --coverage` 全绿（含既有契约文件）。
  - 回执：✅ coverage-contract.ts 已追加 toast.tsx；全量 --coverage 107 文件/1254 用例全绿（契约含新增文件全过）。
- [x] 3.3 更新 `src/__tests__/chapterWorkspace.plotFlow.test.tsx` 与 `src/__tests__/castReviewFlow.test.tsx`：`sticky: true` 断言改普通 toast 断言（消息文案不变）；清理「回执常驻（sticky）」类头注/注释。验证：`npx vitest run src/__tests__/chapterWorkspace.plotFlow.test.tsx src/__tests__/castReviewFlow.test.tsx` 全绿。
  - 回执：✅ plotFlow/castReview 改单参断言＋头注清理；两文件 vitest 绿（cast 26/26）。
- [x] 3.4 e2e `e2e/plot.spec.ts` 必改时序：断言回执可见后**立即**点「撤销」，中间的落库 `expect.poll`（208-215 行）删除或后移——末尾对恢复后 `plot_items` 的轮询已传递性证明「采纳落库＋撤销＋自动保存回写」全链；「常驻回执撤销恢复」用例名改为不再含「常驻」；顺手补「回执 3 秒自动消失」断言（新基线 e2e 零覆盖）。验证：隔离栈跑该 spec 连续 3-5 遍全绿（隔离栈起栈配方见记忆 e2e-isolated-stack-config-path）。
  - 回执：✅ 隔离栈（假 S 19187＋裸 uvicorn 8187＋临时 vite 5187，特征串 /@fs 自证 AUTO_DISMISS_MS×2）：plot.spec 3/3 绿；采纳用例合计 4 遍全绿（13.2/13.2/13.0/12.9s）；cast-review.spec 顺带 6/6 绿；用例名与 :9 头注已去「常驻」。

## 4. 门禁回归（「回归」小节须贴实际输出结论）

- [x] 4.1 `npm run design:lint`（C端）零违例；`npm run design:check` 各场景像素差 <0.2%（toast 瞬态浮层不入 parity 页集，× 不触共享段 CSS——预期零漂移）。把各场景像素差百分比贴在本条下方。
  - 回执：✅ design:lint exit 0 零违例；design:check 8 场景 6 绿 2 红＝书架屏 empty+quota——A/B 实证存量红（还原 pristine list.html 后同样两红，quota 2.693% 与记忆存量光栅漂移一致），与本改无关；base.css 零改动未触发 design-cross。
- [x] 4.2 `npx tsc --noEmit` 干净；`npx vitest run --coverage`（对齐 CI，勿裸跑漏覆盖率门禁）绿；新增/改动用例清单附本条下方。
  - 回执：✅ tsc --noEmit exit 0；vitest run --coverage 107 文件/1254 用例全绿；新增 toast.test.tsx（6）＋改动 plotFlow/castReview 断言。
- [x] 4.3 共享段判定复验：`git diff --stat src/design/base.css` 为空（零改动 ⇒ 不触发 design-cross 双端义务）；proposal Design Impact 的「不触共享段」结论成立。
  - 回执：✅ git status/diff --stat base.css 为空；不触共享段结论成立（× 内联样式）。
- [ ] （待真机）4.4 真机抽检（章工作台）：剧情抽卡采纳回执 3 秒自消、× 可提前收、窗口内撤销可用；人物精盘写入回执同口径；弹窗内 done-notice 全文仍在。走查结论记本条下方。
