## 1. 原型先行（ADJUSTMENTS 登记替代）

- [x] 1.1 `docs/design-c/prototypes/ADJUSTMENTS.md` 新增本 change 段：登记「卷态角色关系并入剧情边（随时对齐本卷最新已确认关系）」的语义变化与依据（卷视图事实源 storyline.html 已下线、不入 parity 基线；数据投影语义变化、零样式改动；设计工件＝实现侧自查）。完成证据＝登记段落入库 diff。

## 2. 卷态并入剧情边（RelationsGraphPane.tsx）

- [x] 2.1 `ChapterMeta` 增 `archived: boolean`（卷树扁平化时带上；`parseChapterRef` 解析卷号已有先例）；卷态数据分支：scopeKey ＝ `chapterRef ?? \`vol:${volumeScope}\``，卷树未就绪（新增 `chaptersReady`）前不发请求；就绪后取本卷末章 ref 调 `dossierApi.preview`（本卷零章则跳过）＋范围内未归档章逐章 `dossierApi.get` 取已采纳关系行（kind "evo"、ref＝章 ref），preview 行在前（design D3）。完成证据＝tsc 干净＋单测断言 preview 以本卷末章 ref 调用。
- [x] 2.2 加载门控对齐章态：`loadedForRef` 初始判定含卷态；渲染门 `scopeKey && loadedForRef !== scopeKey` →「加载中」；树/投影失败静默退回开书设定边（finally 落 loadedForRef）。完成证据＝单测：失败态退回开书边、不白屏。
- [x] 2.3 文案：卷态 aria-label「角色关系图（截至第 N 卷末剧情投影）」；图例附「（含剧情演变 X 条）」（X>0 时）；文件头注释同步（撤「不并入剧情边」旧口径）。完成证据＝单测断言文案；grep 文件内无旧口径残留。

## 3. 测试

- [x] 3.1 `workbenchExtras.test.tsx` 卷态用例重写＋新增：①卷态并入剧情边（preview 以本卷末章 ref 调用、evo 边上图同向覆盖开书边、图例文案）；②跨卷边不显示（vol-2 来源被投影过滤）；③未归档章已采纳行并入（get 按未归档 ref 调用、pending 不上图）；④投影失败静默退回开书边＋加载门控；⑤章态/缩放存量用例适配（aria-label 变更、TREE 补 archived）。完成证据＝vitest 全绿。
- [ ] 3.2 e2e `chapter-dossier.spec.ts` ③″ 后插卷态投影断言：切卷视图「角色关系」页签，断言已采纳剧情边上图、待确认不上图、图例含「截至第 1 卷末」。完成证据＝隔离栈 e2e 该文件全绿。

## 4. 门禁与交付

- [x] 4.1 门禁：`npm run design:lint`（零 CSS 变更，design-cross 不适用）＋ `tsc --noEmit` ＋全量 vitest。完成证据＝各命令实际输出结论。
- [ ] 4.2 隔离栈 e2e 重跑 `chapter-dossier.spec.ts`（per-session 隔离环境配方）。完成证据＝全绿输出。
- [ ] 4.3 `openspec validate --strict` 全绿；PR（标题不带硬编码 PR 号）；合并后按归档流程 sync specs（workbench MODIFIED）。
