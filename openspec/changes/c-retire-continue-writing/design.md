## Context

AI 续写（从光标处流式续写正文）与整章生成职责重叠，且续写产物绕过断章口径（章末切点/章首接点只约束整章生成的素材与模板，续写从光标处自由生长），是断章质量的旁路。产品拍板全链退役。

退役面（开发团队评审后勘误版；**c-workbench-density 已于 2026-10-04 合入 main（c441ad38，#666），初版方案「density 未提交」的前提作废**）：
- 后端：`POST /write/{chapter_ref}/continue`（write/router.py:392）→ `stream_continue`（write/auxiliary.py:135，光标前 1500 字切片、continue_writing 模板渲染、写回 prose＋版本快照）→ `prompts/continue_writing.prompt`。`recent_context` 的 `prose[-1500:]` 填充唯一消费方是续写模板，随退役成死赋值（auxiliary.py:69），顺手删除。
- 前端：右栏「续写建议」卡（AiAssistPanel `cap("continue")`，:425）→ `onContinue` prop 链（Rail.tsx:135 → NovelWorkspace:1218 `onAiContinue`/:265 `AiAction` continue 分支/:282 `runAiAction` 分支）→ ProsePane `continueWriting`（:78/:680，`startStream(true, ...)`）→ `lib/ai.ts` `streamChapterContinue`（:61）。**文末续写块**（ProsePane:844-859 `tail-continue`，`onClick={() => startStream(true)}`，达标判定 prop `planWords` :104-107，ChapterWorkspace:1200 传参，book.css `.tail-cw`）随链退役。
- specs：初版侦察漏面已勘误——涉及 **4 个 capability**：intro-genre-settings（参数表两处）、workbench（动作清单/AI 入口唯一化/两态枚举三处＋密度重排 requirement 的文末续写块条款）、write-archive-meta-sync（整条「续写完成后刷新 DB 章元数据」）、prompt-crafting（辅助链清单）。

## Goal / Non-Goals

- Goal：AI 续写全链退役（后端端点/函数/模板＋前端入口/执行链/文末块＋specs 四 capability 校准），断章口径无旁路。
- Non-Goals：**顶栏/书主页卡「续写」按钮与「续写恢复」滚动信号不在范围**——那是导航功能（回到上次写到的章继续写作，09-16 用户拍板口径；ProsePane 的 resumeScroll/resumeSignal 消费链属导航，保留）；选区变换（去AI味/扩写/压缩）不动；`build_auxiliary_context` 主体不动（polish/expand/compress 共用；仅 recent_context 死赋值行随退役删除）。

## Decisions

### D1. 纯删除，不留兼容层

无外部 API 消费者（桌面应用前后端同包发布）、无存量用户（产品零基线拍板），端点直接移除不加 410/废弃标记。`chapter_versions` 历史续写快照保留不动（无 continue 类型标记，通用 JSON，无代码假设其存在——评审核验过）；`operation=continue` 计量历史行原样留存（stats 透出字符串、无门禁消费）。

### D2. 前端撤卡不撤骨架；删除范围精确到分支

AiAssistPanel 能力卡骨架（cap 行、streaming 门控）保留，只删 continue 一行＋`onContinue` prop 链（经 Rail.tsx 透传至 NovelWorkspace——评审勘误：初版清单漏了 Rail 与 NovelWorkspace 两个必改文件，`AiAction` union 的 continue 分支唯一生产者就是续写卡，随链删除）。ProsePane `startStream` 保留整章生成分支：**空文档垫段是共享逻辑**（整章生成对空章同样依赖，proseStream.test 复刻的就是该路径），删除范围精确到 continuation 分支（`cap.end` 偏移）；`textOffsetToPmPos` 因选区变换链（polish/expand/compress 的选区→PM 位置转换）仍在使用而保留，仅删续写分支的使用点；「续写恢复」信号消费属导航链保留。

### D3. 文末续写块由本 change 自己拆（评审勘误）

初版按「density 未提交、知会未来落地」处理——评审三视角一致证伪：c-workbench-density 已合入 main，文末续写块是活代码，tasks 2.2 删续写分支会当场编译失败/留死按钮。本 change 直接拆除块＋样式＋`planWords` prop 链。prop 的其他消费方（AiAssistPanel/SimModal 的完成度用法）保留。

### D4. 测试与基线面

- `tests/test_write_routes_contract.py` 子路径清单去 `/continue`，并**反向钉缺席**（`assert WRITE + "/continue" not in openapi_paths`，防端点回潮无报警——套件内已有 `test_double_write_path_absent` 先例）。
- 单测 pin：`__tests__/NovelWorkspace.test.tsx:602`「续写建议」按钮断言删除（:605-606 段落卡折叠断言保留）；AiAssistPanel.test.tsx 无续写钉位。
- e2e：AI 续写面零用例（唯一命中是 prompt-pipeline.spec.ts:156 的路由 glob 注释，顺手改写）；导航续写四用例全保留。`design-parity-book` 免费态截图以 book.html 为真值且右栏在比对范围——撤卡必红，**基线重录是确定性工作**（非或然）：book.html:1094 卡行删除、ADJUSTMENTS.md 登记、book.*.png 基线重录。
- 零残留自证词形（评审勘误：函数实名 `streamChapterContinue` 非 `streamContinue`）：`续写建议|/write/continue|streamChapterContinue|continueWriting|cap\("continue"|tail-continue`（前端）＋`stream_continue|continue_writing`（后端），注释级残留（auxiliary.py:266 等 docstring）随实现顺手清。

## Risks / Trade-offs

- 用户失去「从光标处让 AI 接着写」的能力，替代路径＝整章重新生成（带断章口径约束）或手写——产品拍板接受。
- 「续写」一词仍存在于顶栏按钮/e2e/文案（保留面）——自证 grep 须按 D4 词形区分退役面与保留面，避免误清导航功能。
- PRD `creation-flow-to-be-design.md`「正文 AI 五连」口径与本次拍板相反——不阻塞实现，归档时备注文档过期。

## Open Questions

- 无。范围（全链退役 vs 仅前端）已由用户拍板；评审 P0（density 已合入）已吸收。
