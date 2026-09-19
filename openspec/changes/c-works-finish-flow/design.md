## Context

原型 works.html（555 行）已实勘完毕，现实现书架骨架与其同构（壳层/page-head/卡片骨架/新建导入弹窗全现成），增量集中在四态模型与完本链路。无存量用户（2026-09-18 确认），破坏性改动选干净方案。

## Goals / Non-Goals

- Goals：完结状态落库；书架四态呈现与分状态页脚；完本清单弹窗与撤完本；原型晋级 parity 全绿。
- Non-Goals：书级「全书收尾」后台任务（另行立项）；伏笔「留白」落库（弹窗内辅助确认）；已完结书的编辑封锁（撤完本可继续写，不做只读态）。

## Decisions

### D1 完结状态＝`novels.finished_at` 单列（而非 status 枚举）
- 完结是一个带时间戳的单向动作（撤完本清空），时间戳即「完结于 X」文案数据源；阶段仍派生而非存储，避免派生/存储双真。加列走 `main.py` lifespan 既有 `ALTER TABLE ADD COLUMN` 守卫模式（列存在检查后 ADD），无回填。
- 端点动词化：`POST /novels/{id}/finish`、`POST /novels/{id}/reopen`（不用 PATCH 泛改——完结守卫是业务门禁不是字段写）。守卫在 service 层查库判定：finish 要求 `total_chapters>0 且主线归档数==主线章数 且 未完结`，否则 409（detail 与 detail 中文案）；reopen 要求 `已完结`，否则 409。list/detail 下发 `finished_at`（ISO 字符串或 null）。

### D2 阶段派生单源扩参（向后兼容默认值）
- `stageFromChapters(total, archived, finishedAt?)`：`finishedAt` 非空→`done`；`total<=0`→`setting`；`archived>=total`→`ready`；其余→`writing`。第三参缺省 `undefined` 保持旧两参调用可编译（grep 确认调用点：NovelListPage、useWorkbench——两处都补传 finished_at）。
- 标签：`STAGE_LABEL`＝setting 设定中 / writing 写作中 / **ready 待完本** / **done 已完结**（「已归档」标签退役）。落点：`landingViewFor`＝ready→`workbench`（原型卡点＝storyline，与「卡片标签=写作中才落写作」同结论口径延续：待完本仍可加章/改稿）、done→`archives`（预览）、其余不变。
- useWorkbench 的落点 effect 从卷章树自算 total/archived（现状），finished_at 从项目数据取（useProject 已含 novels 行，detail 端点补字段即可）。

### D3 回看落点＝location state 一次性认领
- `useWorkbench` 落点 effect 现无深链机制。`回看`按钮 `navigate(\`/novel/${id}\`, { state: { landingView: "archives" } })`；落点 effect 开头认领 `location.state?.landingView`（合法值白名单：archives/advanced-settings/workbench/advanced-outline），命中则按其落点并 `navigate(location.pathname, { replace: true })` 清 state（防刷新重放）。与「用户显式选择不覆盖」同一语义（navigatedRef 同路）。

### D4 完本清单弹窗数据源
- 三行：①归档判定用书架列表已有聚合（`total_chapters/total_archives` 主线口径），零新请求；②伏笔 `hooksApi.list(projectId)` 过滤 `status==="active"`，行＝名称＋「第 N 章埋下」（planned_chapter_id→章号经卷章树换算太重，直接显示 hook 的 planted 章引用文本，取 hook 现有字段，缺省「—」）；「留白」勾选为弹窗内 `useState`，打开时重置；③收尾行静态呈现（章级收尾提案既有机制，文案引导书内「操作」页签）。
- 完结成功后本地更新：`setNovels` 置 `finished_at`（服务端时钟为准，用响应值），不整列表重拉。

### D5 待完本提示条与会话内记忆
- 从列表派生（第一条 ready 书），`知道了`＝页面 `useState` 布尔（挂载期内不重现），不落 localStorage——提示条语义是「当期可办的事」，持久关闭反而错过后续第二本待完本（ADJUSTMENTS 登记）。

### D6 ⋯菜单补撤完本入口
- 已完结卡 ⋯ 菜单增「完本信息 · 撤完本」→ 打开 FinishModal（done 态，主按钮`撤完本 · 继续写`）。原型只有 done 态弹窗无入口（演示稿程序可达），产品化补口登记 ADJUSTMENTS。

### D7 原型晋级与 parity
- `prototypes/list.html` 以 works.html 为底换代：SEED 换四态书（writing/setting/ready/done 各一＋提示条入图），完本弹窗标记与 fin-* 样式并入，update-strip 保留（parity 场景 stub 无更新态隐藏，同现状）；应用侧扩展（⋯菜单/Banner 群/骨架屏）不入图口径不变。
- parity 场景：`books` 扩为四态数据（app 侧 FIXED_NOVELS stub 补 `finished_at`，原型侧 PROTO_BOOKS 补 stage/stageLabel 字面）；新增 `finish` 场景（books 态＋打开弹窗，stub hooks 空数据＝第二行 ok 形态）。empty/quota 不动。
- 设计 lint：`.b.ready` 若被 design-vocab 白名单拦截，则两端 design-vocab.mjs 同批登记（docs/ux 标准正文 §5 状态语言总表补「待完本/已完结」两行）。

### D8 文案对齐现实（原型偏差登记）
- 弹窗 lead 与 toast 不提「全书收尾在后台跑」：完结 toast＝`《X》已完结 · 归档收尾提案可在书的「操作」页逐条确认`；弹窗③行描述＝`每一章归档后的写回提案都处理完了；未处理的在书的「操作」页逐条确认`。完本不做编辑封锁，撤完本后回到待完本/写作中（按章派生）。

## Risks / Trade-offs

- 「已归档」→「待完本」更名会让存量全归档书突然出现完本入口——预期行为（正是原型意图），无数据风险。
- finish 守卫用主线口径聚合（复用 list 的聚合 SQL 形态），与卡片判据同源，避免「卡片说可以完本、接口说不行」的劈叉；pytest 覆盖 ghost 支线不计入。
- location state 落点覆盖与「用户显式切视图不覆盖」并存：认领动作本身视同显式选择，只影响首次落点。

## Migration Plan

加列即用；无回填、无兼容层。存量全归档书首启即呈「待完本」。

## Open Questions

- 无（范围两拍板已在 proposal 记录：不建书级收尾任务；留白不落库）。
