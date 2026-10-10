# c-assist-statusnote-prop — 设计判据

## 根因形制：JSX children 位置的「伪 prop」

开标签闭合（`>`）之后写 `prop={expr}` 是**合法 JSX**：`prop=` 解析为纯文本节点、`{expr}` 解析为相邻的独立表达式容器——编译期 tsc/Babel/eslint 全部放行，运行期静默把 `prop=` 渲染成字面文本。本例 `statusNote=` 与表达式节点之间还隔着 JSX 注释，视觉上与「写在标签里的 prop」无异，极难肉眼识别。防回归只能靠行为断言（字面量不得出现），类型/lint 门禁兜不住。

## 判据

- **「prop 没传」不是「少个文案」**：`statusNote` 槽位是 `zhuque-workbench` 主 spec 的 SHALL（开关关→副行注明），漏传＝spec 违约，与卡面字面量同根同修。排查此类问题时先 grep prop 在调用点的落位（开标签内还是 children 区），再看渲染结果。
- **静态 children 的泄漏面是全页签**：字面量写在 children 里不随 `tab` 分支，任何章页签恒见——用户在章纲页签报障不代表根因在章纲分支。
- **共享检出竞态再现**：`gh pr create` 在主检出跑会拿当前分支（彼时被并行会话切到 `c-char-batch-import`，报「该分支已有 PR #808」）——归档/发 PR 一律在独立 worktree 里跑并显式 `--head`；推后 `git ls-remote` 验远端 head。
- **测试断言形态**：负钉用 `queryByText(/statusNote/)`（字面量不得出现），正钉按 `getByText("朱雀检测已关闭 · 其余可用")` 精确匹配；prose 页签懒取数的状态更新收进 `await act(async () => {})` 防轮询类 act 噪音。
