## 1. 设计确认（原型先行豁免：用户 2026-10-04 拍板「不改整页原型，独立演示页确认特效」）

- [x] 1.1 特效以独立演示页确认（/tmp/prose-stream-demo.html，应用内浏览器实机播放，用户拍板「就这个」）：呼吸灯 accent 光环 2s 起伏（0%/100%＝环 18%＋晕 6%，50%＝环 55%＋晕 20%）、页签行徽章「AI 正在生成…＋停止」；`docs/design-c/prototypes/book.html` 保持不动，ADJUSTMENTS.md 无原型登记项；演示页参数即验收基准（已回填 design.md 决策 4）

## 2. 保底收尾：切章/卸载保留半截（ProsePane）

- [x] 2.1 `ProsePane.tsx`「卸载/切章」effect cleanup 改为先 `abortRef.current?.abort()` 再 `finishStream(streamReceivedRef.current, false)`（照抄 `stopWriting` 收尾；删除裸 `streamingRef.current = false`），并**立即 `store.flush()` 落盘**——实勘发现 useChapterData 的 release 兜底按声明序先于本 cleanup 执行（那时还没脏），防抖定时器在 release 后成孤儿，1.5s 内关窗即丢，必须显式 flush（flush 自带 isDirty 门：无流时零开销），验证：单测「流式中回主页确认中断→半截内容经 PUT /prose 落旧章」「流式中切章→`streaming`/`aiState.streaming` 复位、编辑器锁定恢复」过（NovelWorkspace.test.tsx 现场保护组）
- [x] 2.2 单测补「生成已正常结束后切章→cleanup no-op 不二次收尾」（finishStream 幂等守卫由 `streamingRef.current` 条件覆盖，正常收尾用例与二次收尾路径全量回归无回归红），验证：`npx vitest run` 全量 1160/1160 绿

## 3. 生成状态可视：呼吸灯＋徽章提升页签行

- [x] 3.1 `book.css` 为 `.editor.generating` 加 box-shadow 呼吸 `@keyframes stream-breath`（2s 周期，`var(--accent)` + color-mix，零裸 hex，不动 base.css 共享段），验证：`npm run design:lint` exit 0；演示页实机目检动效起止与流式同步（用户拍板截图三张）
- [x] 3.2 `ChapterWorkspace.tsx` 将「AI 正在生成…」徽章＋「停止」从 `editor-status`（`hidden={chTab !== "prose"}` 作用域）移出，改为流式期间条件渲染在页签行（`data-testid="ai-streaming-badge"`，版本历史按钮之前）；正文页签下状态条内不再重复渲染，验证：单测「章纲页签下徽章可见可用且全文档仅一处」过
- [x] 3.3 同批 grep e2e 断言（`ai-streaming`/`正在生成`/`停止`）：**零命中**，现有 e2e 无徽章定位与流式中切树流程，无需更新；验证：grep 输出空

## 4. 危险口子锁定：左栏树生成中锁定

- [x] 4.1 `NovelWorkspace.tsx` 左栏 `col-tree` 壳层加 `ai-lock` 类＋`title` 指路＋`onClickCapture` 捕获拦截（树内 button/.vol-head/.ch 全拦，OutlineTree 组件零改动）；book.css 加 `.col-tree.ai-lock` 置灰/禁用手感/hover 抑制，验证：单测「流式中点另一章→不加载该章＋锁定态在场」「停止后→树恢复可切（ch-2 加载）」过
- [x] 4.2 顶栏「写作」回书主页既有确认弹窗回归不动；页签切换与切设定/预览在流式中不受影响，验证：既有 e2e「AI 流式中点『写作』先确认」等 4 文件 23 用例全绿（隔离栈实跑）

## 5. 回归门禁（实际输出结论回填）

- [x] 5.1 门禁实跑结论：`design:lint` exit 0；`design:check` 7/8 场景绿，唯一红＝书架屏 empty 像素差 0.291%（阈值 0.2%）——与 2026-10-01 记录的存量光栅漂移同签名（本 change 零触书架屏代码，非本改引入）；`tsc --noEmit` 0 错；`npx vitest run` 1160/1160 绿（101 文件）；受影响 e2e 4 文件（prompt-pipeline / ai-write-route / modals-pr5 / workbench-features）在隔离栈（worktree c-prose-stream-guard-e2e + compose.e2e-iso，bundle 特征串 `ai-streaming-badge` 自证）23/23 绿，跑后栈已销毁。不触共享段无需 design-cross（判定依据见 proposal Design Impact）
- [ ] 5.2 真机走查四场景：①正文页签生成中呼吸灯＋徽章；②切章纲页签徽章仍在、生成继续；③流式中左栏点章被挡；④回主页确认中断后重开该章半截内容在、无残留锁定——待用户在配好模型的真书环境验收（隔离栈无模型 Key，无法真流式）
