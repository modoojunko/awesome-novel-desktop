# c-chtab-confirm-bubbles — 设计

## Context

- 数据面：`dossierApi.get()` 返回 `rows[]`（每行自带 `domain`+`status`）与 `progress` 聚合；页签内分区组件（`SettingChangesSection`/`RelationChangesSection`）各自拉一份数据并计算 pending。工作台已有 `rearchive` 轮询（deps 含 `showArchive/archived/store.archiveJob?.state/chapterRef`）在归档态拉同一端点。
- 事件面：本章变化行动作后已有 `DOSSIER_CHANGED_EVENT` 广播（detail 含 projectId/chapterRef），`RelationsGraphPane` 已有监听先例。
- 伏笔面：工作台已挂 `useHooksLedger`（`ledgerHooks`/`ledgerChapters` 在手）；「该收了」判定目前内联在 `HooksPane`（基准章号：章态＝当前章）。
- 视觉面：页签行每项已渲染 `.cnt` 计数位（og/prose 在用，其余传空串）；`.pill` 家族（base.css:156-164）含 count role 与 ok/warn/err/accent 软底 tone。原型与 ux 标准为本地资产（不入 PR），design-parity-book 为存量红（`c-book-parity-rebaseline` 专户）。

## Goals / Non-Goals

**Goals:**
- 三枚页签泡泡：设定/关系＝三域/关系域 pending（accent），伏笔＝「该收 N」（warn）。
- 实时感：提取完成即现、确认即时递减、清零自消——全部骑在既有管线（job 终态 effect／DOSSIER_CHANGED_EVENT／useHooksLedger）上，不新增轮询。
- 「该收了」判定抽共享单源，HooksPane 与页签泡泡共用，杜绝第二套规则。

**Non-Goals:**
- 不改后端、不动 dossier API 形状（rows 现地过滤足够）。
- 不新增任何共享段类/语气档/胶囊形态；不做实底红。
- 不处理 book.html 存量 IA 漂移（章档 tab 等归 `c-book-parity-rebaseline`）；不在页签行外新增任何入口。

## Decisions

1. **计数来源＝工作台现地过滤 rows，不新增端点**：扩展现有 `rearchive` 效果，保留 `pending/accepted/rows` 同时派生 `{ settings: rows.filter(domain≠relations ∧ status=pending), relations: rows.filter(domain=relations ∧ status=pending) }`。效果 guard 扩为 `showArchive || archived || archiveJob?.state === "done"`（覆盖「提取刚收口、树尚未翻转 archived」的窗口，泡泡不迟于 toast 出现）。
2. **递减＝监听 `DOSSIER_CHANGED_EVENT` 重拉**：detail 的 projectId/chapterRef 与当前匹配才重拉（照 `RelationsGraphPane` 先例）。不在事件里传增量——行数小，全量重取最简且天然幂等。
3. **该收计数＝复用既有共享判定 `ogHookHints().mres`**（`lib/hookHints.ts` 纯函数，注释即注明与 HooksPane dueBaseChNo 同法），工作台已在算 `hookHints`，泡泡取 `mres.length` 即可——零新函数、零新文件。配套补一条台账变更广播：`hooksApi` create/patch/remove/restore 成功后派发 `HOOKS_CHANGED_EVENT`，`useHooksLedger` 监听重取（detail.projectId 匹配）——页签泡泡与 HooksPane 台账行都免切章刷新。
4. **渲染＝页签 cnt 元组扩展**：`[key, text, cnt]` 的 `cnt` 增加可选 `pill: "accent" | "warn"` 与 `title`；渲染分支输出 `<span className={"pill pill-count pill-" + tone} title={title}>{text}</span>` 或回落既有 `.cnt`。testid＝`chtab-bubble-settings/relations/hooks`（e2e 钩子）。
5. **pop 动画＝book.css 屏级**：`.chtab .pill` 挂载动画（scale+fade 220ms，`@keyframes` 新定义于 book.css，先例＝`.ai-streaming .pulse`）；不进 base.css、不做递减 bump（数字变化本身可见，避免 effect 记账复杂度）。
6. **视觉词汇＝`.pill.pill-count.pill-accent`（设定/关系，裸数字）／`.pill.pill-count.pill-warn`（伏笔，「该收 N」）**。初议微信红按 N6 改判 accent（proposal Design Impact 已登记）；「该收了」行内 `.hp-due` 维持不动。
7. **原型先行（本地资产）**：`book.html` 页签行加三枚泡泡（演示已归档态；默认 parity 种子为未归档态不出现，book 屏存量红归 rebaseline 专户）＋`ADJUSTMENTS.md` 登记＋`design-language.html` §5.1 新增「待确认」行。三份均为本地单拷贝：在 worktree 内编辑，收官时同步回主检出正本（覆盖前 diff 防并行会话改动）。

## Open Questions

（无——配色、口径、范围均已拍板。）
