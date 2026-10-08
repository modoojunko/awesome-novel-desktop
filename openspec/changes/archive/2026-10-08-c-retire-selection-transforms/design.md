## Context

选区加工三卡（去AI味/场景扩写/压缩啰嗦段落）中的扩写与压缩退役，去AI味保留。继 #669（AI 续写退役）后同一拍板方向的第二批裁撤。

**并发 change 地形（开发团队评审勘误，实勘 origin/main @ 830f91f1）**：main 上现有三个未归档 change 改相邻 requirement——#668 c-archived-readonly（解锁链退役，22:48 合入）、#669 c-retire-continue-writing（AI 续写退役，本会话）、本 change。主 spec 的「三卡折叠」scenario 已随 #667（density 归档）sync 进 :1003-1007，**不是** #669 工件专属（初版 D3 前提勘误）。

退役面：
- 后端：`POST /write/expand`（router.py:520）→ `expand_text`（auxiliary.py:213）；`POST /write/compress`（router.py:457）→ `compress_text`（auxiliary.py:178）；两模板。`polish_text`（:132）与 `/write/polish` 保留；`build_auxiliary_context` 保留。
- 前端：AiAssistPanel 段落加工组（:422 区三卡折叠、分组行 `ai-para-group` :451）→ 去AI味单卡（`testid=ai-polish`）；`expandLoading`/`compressLoading`（AiAssistPanel props＋ProsePane `ProseAIState` :50-66 字段＋INITIAL 常量）；ProsePane `runTransform` 两分支＋`ProseHandle` expand/compress（:77-79/:672-673）＋preview footer「已应用扩写/压缩」分支（:867-871）；Rail/NovelWorkspace mode 类型（六处声明点全落在方案面）；`lib/ai.ts` `compressText`:186/`expandText`:200；`ContrastPreviewModal` mode（:9/:56/:76）。
- 测试：`test_write_transform_modes.py` TestCompress 3 用例（:91/:121/:126）删除，TestPolish 保留，**无 TestExpand**；`AiAssistPanel.test.tsx` :94-136 整用例（未选中置灰断言＋压缩卡两段）；`NovelWorkspace.test.tsx:602-605`（ai-para-group 存在＋ai-polish null＋场景扩写 null）；e2e `workbench-features.spec.ts:680-684`（折叠行 disabled＋ai-polish count 0）。
- 原型：book.html 场景扩写卡 :1095、压缩卡 :1096、脚注 :1104（按卡片文案锚点定位，行号随 #668 改动漂移）。

## Goal / Non-Goals

- Goal：扩写/压缩全链退役，右栏收敛为「生成正文＋去AI味＋朱雀检测」；specs 四处条款校准。
- Non-Goals：去AI味（polish）全链不动；卷域 `volumes/ai/expand` 不动（`desk-expand` 事件名同理）；朱雀检测不动。

## Decisions

### D1. 纯删除＋契约反向钉

同 #669 判例。**契约测试实况勘误**：sibling 子路径清单从不含 `/compress` `/expand`（#669 后为 `/prompt`、`/prompt/polish`、`/quality-check`、`/polish`）——无「去清单」动作，仅照 `test_continue_route_retired` 形制新增两条缺席反向钉。`test_write_transform_modes.py` 删 TestCompress 时同步清 docstring（「/write/compress…」）与 `AITimeoutError` import（其唯一使用者在 TestCompress 超时用例）。

### D2. 段落加工组单卡化，折叠机制退役

单卡 `testid=ai-polish`（显式带 testid：NovelWorkspace.test:604 的 `ai-polish` null 断言翻转为存在性/置灰断言，e2e :684 同步）。三卡折叠分组头（`ai-para-group`）退役。`aiState.hasSelection` 门控保留为置灰判定。

### D3. 三方归档撞车：终态化 #669 工件＋归档顺序硬约束

main 三个未归档 change 改相邻 requirement，处理如下：
- **#668（解锁链）**：本 change 552 终态块直接采用 #668 口径（归档章 disabled＋hint 指路「重写本章」）——#668 归档位次不限，覆盖幂等。
- **#669（续写＋prompt-crafting）**：工件已终态化修订（本次评审落地）——其 workbench 552 块改写为本 change 同款单卡终态、ADDED 密度重排块删「右栏段落卡按选区折叠」scenario、两条枚举（「去AI味/扩写」「去AI味/扩写/压缩」）去尾、「去AI味/扩写辅助链」→「去AI味辅助链」。至此 #669 与本 change 的 552/prompt-crafting 块语义一致，**任一归档顺序均收敛，无顺序回归**。
- **980 requirement（三卡折叠 scenario 在主 spec :1003-1007）**：由 #669 的 REMOVED+ADDED 在归档时带走（其 ADDED 已无段落卡场景）。**归档顺序硬约束：#669 先于本 change 归档**（两归档 PR 同批发、#669 在前；否则主 spec 在窗口期持续要求已退役的三卡折叠）。本 change 不出 980 delta（避免同构 REMOVED 在 #669 归档后目标缺失）。
- **scenario 标题历史名**：「未选段时段落动作折叠为分组行」标题在 MODIFIED 同名约束下保留（改名会被 validate 判场景缺失），正文已是单卡置灰语义；归档 sync 后可在后续 chore 中改名。

### D4. 计量与历史数据

`operation=expand/compress(/_fail)` 历史行留存（stats 泛型 group_by 透出、无门禁消费——评审核验）；无数据迁移。

## Risks / Trade-offs

- 用户失去「选中扩写成一场景」与「一键压缩」，替代路径＝整章重新生成或去AI味（删冗余）——产品拍板接受。
- parity 基线必红（右栏卡片数变化）——基线重录随 design:check（#669 同判例）；`design-parity-book.spec.ts:245` 注释「扩写」字样随重录顺手清。
- 零残留自证 grep 必须 `grep -E`（BSD grep 字面 `|` 会假绿——评审 P2 实锤）。
- 归档顺序依赖（D3）：两归档 PR 同批发、#669 在前；单用户产品无归档竞争，可控。

## Open Questions

- 无。范围由用户拍板；三方撞车与 specs 漏面经开发团队三视角评审补齐。
