## Why

2026-09-17 works.html 原型（docs/design-c/drafts/works.html）给登录后首屏「我的作品」定了新形态：书卡四态徽章（设定中/写作中/**待完本/已完结**）、分状态页脚（待完本＝回看＋完本、已完结＝完结于＋查看）、待完本提示条、完本清单弹窗（伏笔留白勾选→完结→撤完本）。现实现只有三态（设定中/写作中/已归档，纯前端派生），**没有任何完结概念**——现「已归档」实为原型的「待完本」，而「已完结」需要完本动作落库。用户 2026-09-19 拍板对齐原型。

## What Changes

- **阶段模型三态→四态（含落库）**：`novelStage` 单源扩为 `setting | writing | ready | done`；新增完结状态 `novels.finished_at`（完本动作写、撤完本清）；派生规则＝finished→已完结、主线章全归档未完结→待完本、无章→设定中、其余→写作中。现「已归档」标签更名「待完本」（语义对齐：全归档＝可以完本了），「已完结」成为新的第四态。
- **完本链路（后端）**：`POST /novels/{id}/finish`（守卫：主线章全归档且未完结，否则 409）与 `POST /novels/{id}/reopen`（守卫：已完结才可撤，否则 409）；list/detail 下发 `finished_at`。**不建书级「全书收尾」后台任务**（拍板：完本清单第三行按既有章级收尾提案口径呈现，文案引导到书内「操作」页签；书级收尾另行立项）。
- **书架卡片分状态页脚**：待完本＝「全书 N 章已归档」＋`回看`（落预览视图）＋`完本`（开弹窗）；已完结＝「完结于 X」＋`查看`；写作中/设定中维持「更新于＋继续创作」。四态徽章上卡（`.b` 家族新增 `ready` 档，`done` 档语义更名已完结）。
- **待完本提示条**：书架页对首本待完本书常驻提示「《X》主线已收齐 · N 章全部归档 · 可以完本了」＋`去完本`＋`知道了`（会话内记忆，不落 localStorage）。
- **完本清单弹窗（新 FinishModal）**：三行检查——①章节已全部归档（列表数据派生）②伏笔（`hooksApi.list` 取 active 逐条列出「第 N 章埋下」，可切「留白/未收」**仅弹窗内辅助确认不落库**（拍板））③归档收尾都已清；`完结这本书`→finish 端点→卡片转已完结；已完结态显示完结信息＋`撤完本 · 继续写`（→reopen）。弹窗/toast 文案对齐现实口径（「收尾提案在『操作』页逐条确认」，不提不存在的后台任务）。
- **已完结书的撤完本入口**：卡片 ⋯ 菜单对已完结书增「完本信息 · 撤完本」项（打开弹窗 done 态）——原型无撤完本入口，产品化补口（ADJUSTMENTS 登记）。
- **回看落点**：`回看`/已完结卡`查看`落预览视图（现状口径）；待完本卡本体点击仍落写作（与卡片标签同结论）。落点覆盖走 location state 一次性认领（`useWorkbench` 现无深链机制，小改）。
- **原型晋级**：works.html 晋级为 `prototypes/list.html` 基线换代（书架屏 parity 事实源），ADJUSTMENTS.md 新章登记全部偏差；parity books 场景扩四态＋新增完本弹窗场景。

## Capabilities

### New Capabilities
- `works-finish-flow`：完结状态落库与 finish/reopen 端点、书架四态徽章与分状态页脚、待完本提示条、完本清单弹窗、撤完本入口。

### Modified Capabilities
- `novel-workspace`：「Four-state workspace view machine」阶段判据从三态扩四态（`stageFromChapters(total, archived, finishedAt?)`）——finished→已完结、全归档未完结→待完本（落点改**写作**，不再直接落预览；预览改由卡片`回看`/`查看`显式进入）；卡片与落点同结论口径保持；新增「回看一次性落点覆盖」场景。
- `design-system`：登记 C端 书架阶段徽标（`.b` 家族）四态档位——`ready`（accent 底，行动召唤）、`done` 语义更名已完结（ok 底不变）；语气词仍限 info/ok/warn/err，无新胶囊形态。

## Impact

- **后端（client/backend）**：`models/project.py`（novels 加 `finished_at TIMESTAMP NULL`）、`main.py`（lifespan `ALTER TABLE ADD COLUMN` 守卫模式补列，无用户不做兼容层）、`novels/router.py`（list/detail 下发 `finished_at`＋finish/reopen 两端点与守卫）。
- **前端（client/frontend）**：`lib/novelStage.ts`（四态＋标签＋落点）、`pages/NovelListPage.tsx`（四态徽章、分状态页脚、提示条、⋯菜单撤完本入口、弹窗接线）、新 `components/novel/FinishModal.tsx`（design/Modal 基座）、`hooks/useWorkbench.ts`（落点 effect 认领一次性 location state 覆盖）、`lib/api.ts`（finishNovel/reopenNovel）、`design/list.css`（`.b.ready`/`.foot-acts`/`fin-*` 家族，业务层零 base.css 改动）。
- **原型与登记**：`docs/design-c/prototypes/list.html` 换代（自 works.html 晋级，drafts 原样留存）；`ADJUSTMENTS.md` 新章登记（⋯菜单与撤完本入口、留白不落库、文案对齐、排序仍按 updated_at、知道了会话内、Banner 群 parity 态隐藏等）；`e2e/design-parity.spec.ts` books 场景扩四态＋完本弹窗场景。
- **测试**：后端 pytest（两端点＋守卫＋字段下发）；vitest（novelStage 四态＋NovelListPage 交互）；e2e 新增 finish-flow spec＋存量回归；design:lint / design:check 全绿。
- **迁移影响**：加列即可，无数据回填；存量全归档书自动呈现「待完本」（预期行为）。

## Design Impact

- 受影响端：**仅 C端**（client/frontend + client/backend 本机 SQLite）。S端 无涉及；不触两端共享段（base.css 令牌与基础组件类零改动，全部落业务层 list.css 与弹窗组件）。
- 受影响屏/弹层：书架屏（卡片页脚/徽章/提示条）＋完本清单弹窗（新弹层，design/Modal 基座宽卡）；appbar/控制中心/状态条零改动（原型同构已达标）。
- 对象状态（对照 design-language §5 状态语言总表）：`.b` 徽标家族新增 `ready` 档（accent 底＝可行动召唤，对应「待完本」）、`done` 档语义更名「已完结」（ok 底不变）；提示条复用 `notice info`；无第四种胶囊、无新语气词（info/ok/warn/err 纪律不破）。
- 是否需要原型先行：**原型已就绪**——works.html 为设计事实源，本 change 晋级入 prototypes/ 并换代 list.html 基线；偏差逐条登记 ADJUSTMENTS.md。
- 设计工件由谁产出：实现侧自查（全部为既有语言的新档位与重排；无新视觉形态）。
