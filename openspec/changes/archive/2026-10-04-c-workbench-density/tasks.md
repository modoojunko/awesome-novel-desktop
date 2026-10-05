## 1. 刀一·头部压缩（ChapterWorkspace + ProsePane）

- [x] 1.1 `ChapterWorkspace.tsx` e-meta 删三枚重复徽章（计划字数/完成度/本书总字数；planWords/progressPct/bookWords 变量保留）；卷名 kicker 隐去（删节点，volLabel 变量随之删），验证：`chapterWorkspace.plotFlow.test.tsx` 断言改口径（not.toContain 三枚 + ch-progress 含完成度）后绿
- [x] 1.2 `ChapterWorkspace.tsx` 页签行版本历史左侧插 `<span class="ch-progress">完成度 X% · 总字数 X</span>`（testid ch-progress），验证：单测断言页签行含进度文本绿
- [x] 1.3 `ProsePane.tsx` 完工横幅并入编辑工具行：编辑态下工具行左侧加警示胶囊（testid qc-banner 迁到胶囊；qc-word/qc-self 迁入展开明细条 qc-detail；点胶囊切换 qcOpen；全部条件渲染），查看态不渲染，验证：e2e prompt-pipeline 阶段三改口径（胶囊可见→点击展开明细→再点收起）实跑绿；「知道了」关闭语义退役（胶囊常驻至下次生成）

## 2. 刀二·右栏再分配（book.css + AiAssistPanel）

- [x] 2.1 `book.css:69` grid 第三列 236px→300px（栅格纪律注释同步；916-918 设定域 236px 未动），验证：`npm run design:check` 7/8，唯一红＝书架屏 empty 0.291% 存量光栅漂移（与本改零交集）
- [x] 2.2 `AiAssistPanel.tsx` 正文页签三张段落级置灰卡在未选中时收成一行「段落加工」说明行（testid ai-para-group，disabled＋「先在正文选中一段」hint）；选中后展开三卡（testid ai-polish 等不变），验证：AiAssistPanel.test / NovelWorkspace.test 断言改口径后全绿；e2e workbench-features 改断言（ai-para-group disabled＋ai-polish count 0）实跑绿

## 3. 刀三·文末续写（ProsePane）

- [x] 3.1 `ProsePane.tsx` 编辑器滚动内容末尾加虚线续写块（testid tail-continue；editable 且非流式且 planWords>0 且 words<planWords*0.9 时渲染），点「续写」调 startStream(true)（continueWriting 同链），planWords prop 由 ChapterWorkspace 传入（章纲 wt→targetWords 兜底），验证：tsc 零错；渲染条件四项齐全（达标/无目标/流式/非编辑态均不出现）
- [x] 3.2 book.css 加 .tail-cw / .qc-pill / .qc-detail / .ch-progress 四类（accent/warn 令牌 color-mix，零裸 hex），验证：`npm run design:lint` exit 0

## 4. 回归门禁（实际输出结论回填）

- [x] 4.1 门禁实跑结论：`tsc --noEmit` 零错；`npm run design:lint` exit 0；`npx vitest run` 1160/1160 绿（含三处口径迁移：plotFlow e-meta、AiAssistPanel 折叠制、NovelWorkspace PRO 入口）；`npm run design:check` 7/8（唯一红＝书架屏 0.291% 存量漂移，非本改）；受影响 e2e 4 文件（prompt-pipeline / workbench-features / modals-pr5 / ai-write-route）隔离栈 **23/23 绿**（bundle 特征串 tail-continue 自证；插曲：container_name 跨项目复用 + teardown sweep 曾把栈搞没，按 [[compose-container-name-hijack]] 判例重建后过），跑后栈已销毁、worktree 已清
- [x] 4.2 演示页基准对照走查：5174 更新包后真机逐刀目检（第二章 1,930/2,500 编辑态）——①头部仅 5 徽章＋页签行「完成度 77% · 总字数 4,059」；②右栏 300px「段落加工」折叠行在场；③文末虚线续写块「还差约 320 字＋续写按钮」在场；截图四张留档（artifacts sess_430aaa00），与演示页基准逐项对上
