# c-chtab-confirm-bubbles — 任务

## 1. 原型先行（本地资产，不入 PR）

- [x] 1.1 `docs/design-c/prototypes/book.html`：页签行「设定／角色关系」加 `<span class="pill pill-count pill-accent">N</span>`、「伏笔」加 `<span class="pill pill-count pill-warn">该收 N</span>`（补 title；演示已归档待确认态；同步登记：默认 parity 种子不出现泡泡，book 屏存量红归 c-book-parity-rebaseline）
- [x] 1.2 `docs/design-c/prototypes/ADJUSTMENTS.md` 新增 `## c-chtab-confirm-bubbles` 条目：泡泡词汇组合（pill-count×accent/warn）、微信红→accent 的 N6 裁决、章档 tab 存量 IA 不在本批处理、动效口径（挂载 pop）
- [x] 1.3 `docs/ux/design-language.html` §5.1 状态语言总表新增「待确认（AI 产出等裁决）」行（accent 计数泡泡·清零自消；台账节奏＝warn 计数泡泡），并跑 `npm run design:lint` 确认原型改动不触档位禁令

## 2. 数据层（工作台）

- [x] 2.1 `ChapterWorkspace.tsx`：`rearchive` 效果扩展——guard 增 `archiveJob?.state === "done"`，state 增 `settingsPending`/`relationsPending`（rows 现地过滤，口径＝设定三域／关系域 pending）
- [x] 2.2 `DOSSIER_CHANGED_EVENT` 监听（project/chapter 匹配才重拉；照 RelationsGraphPane 先例；清理函数随 effect 返回）
- [x] 2.3 「该收了」判定抽共享纯函数（落既有 hooks lib，HooksPane 改调用；页签侧 `useMemo(ledgerHooks, chapterNo)` 派生该收数）；核对 coverage-contract 无新文件

## 3. 展示层

- [x] 3.1 页签渲染：cnt 元组扩展 `pill`/`title` 字段，设定/关系＝accent 裸数字、伏笔＝warn「该收 N」，testid `chtab-bubble-settings/relations/hooks`
- [x] 3.2 `book.css`：`.chtab .pill` 尺寸微调（对齐 28px 页签行高）＋挂载 pop `@keyframes`（屏级作用域）

## 4. 测试

- [x] 4.1 vitest：提取完成出泡（mock dossierApi rows）／逐条确认后事件触发递减／清零隐藏／未归档无泡／该收计数与 HooksPane 同规则（共享函数单测）
- [x] 4.2 e2e（章档链路既有 spec）：归档完成后 `chtab-bubble-*` 出现与数值断言、全部采纳后消失
- [x] 4.3 `openspec validate --change c-chtab-confirm-bubbles --strict` 通过

## 5. 回归

- [x] 5.1 门禁实跑并记录结论：`npm run design:lint`／`npx tsc --noEmit`／vitest 全量／相关 e2e；design:check 之 book 屏为存量红（c-book-parity-rebaseline 专户），本批不新增门槛——结论写入 PR 描述
- [x] 5.2 共享段判定复核：确认 base.css 零改动、`.pill` 家族零新增类（免 design-cross，依据＝proposal Design Impact）
- [x] 5.3 设计资产随 PR 入库（实勘：三份均为 git 跟踪文件，早前『本地资产』判断系 ls-files 截断误读；主检出 pull 即得，无并行覆盖问题）
- [ ] 5.4 推分支＋PR（描述含：拍板口径、N6 配色裁决、门禁结论、遗留＝book 屏 parity 归 rebaseline）
