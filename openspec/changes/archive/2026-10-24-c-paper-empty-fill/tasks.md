# tasks — c-paper-empty-fill

## 1. 前端（C端纯 CSS）

- [x] 1.1 `book.css`：「填屏」flex 链 wrap／纸两级上移 base——`.editor-wrap` 恒纵向 flex＋`.editor-wrap > .prose-paper { flex: 1 0 auto; }`；编辑态专属 host/editor 两级保留；注释记录 10-24 反馈与「连续纸下限」口径；验证＝e2e 三态几何断言
- [x] 1.2 `[hidden]` 守卫核实：`.editor-wrap` 恒 flex 后页签显隐仍由 base.css `[hidden]{display:none!important}` 压住；人味边注层 absolute 不受 flex 影响；验证＝renwei 存量单测绿＋e2e 页签切换正常

## 2. e2e

- [x] 2.1 新增 `e2e/paper-fill.spec.ts`：三态几何断言（空章查看态/编辑态纸撑满＝可视高−纸外距 92px ±2；短章撑满不塌；长章纸长过可视区＋滚动到底可达）；验证＝撤补丁红（实测空章纸高 177px≠应有 240px）、上补丁绿
- [x] 2.2 编辑器重相关存量回归：free-writing-flow / thinking-display / chapter-rewrite / workbench-features / large-screen / zhuque；验证＝红集合与 origin/main 同栈 A/B 完全一致（3 红全为存量环境红，与本改动无关）

## 3. 回归（实际输出结论记录在 PR/归档总结）

- [x] 3.1 前端全量单测＋tsc；验证＝vitest 1781/1781 绿、`tsc --noEmit` 零错
