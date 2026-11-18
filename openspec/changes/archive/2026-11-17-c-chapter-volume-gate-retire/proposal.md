# c-chapter-volume-gate-retire — 建章撤掉「主线末端门禁」

## Why

用户实测（v0.47.9，2026-11-17 用户反馈）：拆书建书按「章卷结构」产物预建了第 2 卷（空卷），作者在第 1 卷写完两章（归档）后，想续建第 3 章被 409 拦死（「写作位在第2卷——这一卷还没轮到」）；删掉第 2 卷才恢复。根因是建章的「主线末端门禁」按卷号一刀切：凡被它拦下的场景，目标卷的章按 frontier 定义必然已全部归档，此时在卷尾追加只会让新章成为新写作位，排队模型毫发无损——闸拦到的全是无辜操作，而真正「排后面轮不到写」的往后续卷建章反而放行。boss 拍板（2026-11-17）：作家有先建卷、再写章的习惯，**章和卷的规则不冲突才对**——建章永远不该因卷序被拦。

## What Changes

- **BREAKING（行为翻转，spec 钉死场景随之改写）**：撤掉建章/拆章入口的「主线末端门禁」——后端 `create_chapter` 不再按「目标卷号 < 写作位卷号」返回 409；建章语义统一为「排到目标卷末尾（卷内 MAX+1）」，任何卷都放行。新章之前的章已全部归档时，新章即成为新写作位；写作位之后的既有拟定章/草稿照常排队。**写正文侧的排队门禁（先完成前面的章节）不受影响**。
- 前端同步撤闸：本卷章节页签「拆下一章」「在本卷新增一章」不再按卷序置灰/隐藏；右栏「拆下一章（AI）」撤卷序拦截（卷纲空门槛、档位锁保留不动）。
- 建章失败提示透出后端具体原因：三处 catch（卷页新增、左树/书主页 `createChapter`）不再以笼统「创建章失败」吞掉后端 4xx 中文 detail；「排上」弹窗已透出，不动。
- 拆书建书预建空卷从此不再是雷：空卷不再把写作位「抢走」导致旧卷锁死（占位显示位置不动，显示层自行随建章刷新）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `chapter-plan-ai`：Requirement「三入口归属（两手写一 AI）」——主线末端门禁 bullet 改写为建章放行；Scenario「非末端卷入口置灰」改写为「全归档后旧卷可续拆（空卷不拦）」；其余 bullets/scenarios 全量保留。
- `volume-outline`：Requirement「本卷章节页签」——「在本卷新增一章」恒可用（不再要求写作位在本卷）；「拆下一章」入口门禁沿用口径撤掉；Scenario「新增入口门控」「拆章入口末端门禁呈现」随之改写；新增「建章失败透出原因」口径。

## Design Impact

- 受影响端：**C端**（桌面应用）。
- 受影响屏/弹层：卷工作台·本卷章节页签（「拆下一章」按钮与提示段、「在本卷新增一章」入口与说明文案、建章失败 toast）；右栏卷助手·章节页签（「拆下一章（AI）」行 desc/hint/disabled）；左树卷行「＋添加章节」与书主页卡（仅失败 toast 文案）。
- 对象状态：撤掉「卷序置灰」状态——「拆下一章」按钮只剩 档位锁／卷纲空门槛／检查中 三种禁用态（均为既有状态语言，无新增形态）；toast 语气沿用 err。不触碰两端共享段；无原型先行需求（纯撤闸＋文案收敛，版式零变化）。
- 设计工件：实现侧自查（对照 docs/ux/design-language.html §13 文案口径；按钮词保持动词，提示不出现内部术语）。

## Impact

- 后端：`client/backend/chapters/service.py`（create_chapter 撤 409 门禁段）；测试 `tests/test_chapter_plan_ai_t3.py`（门禁用例翻转）＋ 新增空卷回归用例。
- 前端：`workbench/VolumeWorkspace.tsx`（splitBlocked/canAdd 撤除＋吞错修复）、`workbench/VolumeAssistPanel.tsx`（卷序拦截撤除）、`hooks/useWorkbench.ts`（createChapter 吞错修复）；测试 `__tests__/volumeWorkspace.test.tsx`、`__tests__/volumePlanCoverage.test.tsx`；e2e `e2e/chapter-plan.spec.ts`「非末端卷」用例翻转。
- 无 API 契约变化（同一端点，撤一条 409 分支）；无数据迁移。
- **归档排队注记**：在途 change `tier-plan-four-tiers` 对同一 Requirement「三入口归属（两手写一 AI）」也有一份 MODIFIED delta，其内容与当前主 spec 逐字相同（已被吸收、无净新增）——本 change 归档后该 delta 即过时（若日后原样归档会把门禁带回来）。本 change 不动它的工件（非本 scope），此处挂账给归档扫尾时一并清点。
