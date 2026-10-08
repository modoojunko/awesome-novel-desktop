## 1. 实现（C端 `client/frontend`，后端零改动）

- [x] 1.1 `src/design/book.css`：`.editor-wrap.editing` 加 `display:flex;flex-direction:column`＋`padding-bottom:36px`；`.editor-host`、`.editor` 各 `flex:1 0 auto`（wrap→host→editor 逐级传递）；注释带 `[hidden]` 全局守卫依据。验证：`npx tsc --noEmit` 干净（CSS 不进 tsc，作编译冒烟）；真机量测四项（见 3.2）。
  - 回执：✅ 三条规则＋注释已落（aade5066）；`padding-bottom` 覆盖 shorthand 生效（真机 computed=36px）。
- [x] 1.2 `src/components/novel/workbench/ProsePane.tsx`：`<EditorContent editor={editor} className="editor-host" />`（TipTap v3 透传 HTMLProps 到包装 div）。验证：`npx tsc --noEmit` 零错（className 是合法 prop）。
  - 回执：✅ 已落；tsc exit 0。

## 2. 测试

- [x] 2.1 相关 vitest 回归：`NovelWorkspace`/`chapterWorkspace.plotFlow`/`proseStream`/`proseDoc`/`features`（60 例）＋`castReviewFlow`/`zhuqueWorkbench`（40 例）。验证：全部绿。
  - 回执：✅ 7 套 100 例全绿（10-08 本地实跑）；PR #733 CI 全绿（check pass 2m21s）。
- [x] 2.2 真机（演示栈 5274，干净 worktree 构建 cad7848c 换包）：受控浏览器自动登录→第六章→编辑态，量 `.editor-host` computed display、`.editor` flex、`.editor-wrap` 底 padding；长文（2,334 字）截图呼吸框通到状态栏。验证：四项全中。
  - 回执：✅ hostDisplay=flex、editorFlex=`1 0 auto`、wrapPadBottom=36px、editorH=3707（内容超屏照常滚动）。
- [x] 2.3 短内容场景（真书无短章可安全复现，不动活书数据）：用 5274 下发的同一份编译 CSS（`index-8NAKszEt.css`）搭静态 harness（同构 DOM：edit-bar＋`editor-wrap.editing`＞`editor-host`＞`editor.generating`＋editor-status，3 段短文）。验证：绿框直通状态栏上方（底留白与顶对称）、量测 wrap=565/editor=492（=565−36×2）、框内空白可点击聚焦。
  - 回执：✅ harness 截图与量测全中（editor 恰撑满 padding 内区域）。

## 3. 门禁回归（「回归」小节须贴实际输出结论）

- [x] 3.1 `npx tsc --noEmit` 零错；`npm run design:lint` 不适用（未新增类/词汇，无新 CSS 类名）；`design:check` 不适用（parity spec 页集不含编辑态，本改无原型侧改动）。结论：无门禁面变化。
  - 回执：✅ tsc 干净；design 两门无需跑（proposal Design Impact 已论证零接触）。
- [x] 3.2 e2e 影响面对拍：全 e2e 无 `.editor` 高度/padding 断言、无 parity 用例进编辑态；滚动恢复用例（free-writing ⑦）`LONG`＝36 字×30 单段必溢出可视区，`scrollTop>0` 断言不受撑满影响。结论：e2e 零改动。
  - 回执：✅ grep 实勘（editor-wrap 仅 free-writing:365 一处 scrollTop 操作型使用）；PR #733 CI e2e 全绿。

## 4. 收尾

- [x] 4.1 实现 PR #733 合 main（squash＝aade5066，分支已删）；演示栈 5274 前端同源（cad7848c 构建）、后端徽标 override 同步 `main@aade5`（boot=current 零迁移）。
  - 回执：✅ 全落；5274 探活 200。
