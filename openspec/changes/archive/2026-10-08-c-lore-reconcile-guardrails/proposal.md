# c-lore-reconcile-guardrails

## Why

真机实锤（演示栈《我在夜晚打吸血鬼》写两章）：归档收尾 lore 通道把 13 条 AI 条目灌进世界设定——人物进了势力格（银铎，角色卡另有一份，双重记账）、同一条款跨格双落（停战条款第三条在 history 和 factions 各一份）、同一条教规两个名目双落（「染血即焚」vs「教团验心规」）、第 2 章情节拍点被当世界要素（验心提前）、主角身体特征进更多细节（旧咬痕），第 1 章一批 8 条全数入账。势力格 6/6 已满（FACTIONS_MAX=6），下一条带新势力的提案采纳会整批转失败。作者结论：「势力越多，冲突越难聚焦，建议 2-3 个」——而势力格引导语「先立两三个」（WorldSettingPanel.tsx:590）从未进提炼口径。伏笔通道的同类事故（首章提 11 条）已在 c-hooks-advance-ledger 整改（真伏笔判据＋每类 ≤3＋台账对账），lore 是唯一没装护栏的提炼通道。

## What Changes

- **lore 收尾 prompt 加判据与口径**（`archive/reconcile.py` lore 段）：只提「后续章节还要引用的恒定世界事实」，一次性情节事件、人物状态/外貌、一次性场景 SHALL NOT 提；每批 ≤4 条、宁缺勿滥；势力聚焦——现有势力 ≥3 时不再提新势力，势力相关变化并进既有势力条目；人物一律不提（含未登记人物，人物归角色域）。
- **提案侧代码护栏**（确定性，不依赖模型自觉）：解析后过滤——候选名目命中本章出场角色名单（outline.characters，两侧同口径归一化）→ 丢弃；现有势力 ≥3（只统计有名目条目）时 set=factions 的新名目 → 丢弃；过滤后整批为空 → 不落行也不覆盖既有未决行。排重注入源从「世界设定现值」扩为「现值＋**本书其他章**待确认提案名目」（独立成块只列名目；排除本章——同章重复由覆盖语义兜住，混入会自吞未决提案，评审 P0-2）。
- **采纳侧归并＋复检**（评审 P1-1/2/3）：同批内归一化同名目先去重（保留首条）；归一化名目（沿用伏笔 planted 查重的 `_norm` 口径）命中 history/extra/factions 既有条目 → 用既有条目的**字面** key/origin/set 改写为更新（保留原格与原 origin（若该格条目带 origin）、替换 value/note），跨章同名目 SHALL NOT 重复新增、同键 SHALL NOT 跨格双落；constraints（作者手写铁律）不进归并目标；每条采纳前复做出场人物判定（兜存量未决行与章纲漏填）。
- 零前端改动；零 DDL；`chapter_reconcile` 行结构、逐条采纳/驳回交互、PRO 门控、满员整批转失败的诚实语义全部不动。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `world-settings`: 「lore-keeping 随归档生长（提案制）」Requirement 增加产出护栏（恒定事实判据、每批上限、势力聚焦、人物排除、排重源扩展）与归并语义（归一化同名目更新既有条目，跨章/跨格 SHALL NOT 双落）；保留原三场景，新增护栏场景。归并语义单源落本 Requirement（`archive-reconcile` 的采纳条款是委托式表述「lore→lore-apply 幂等合并」，无需随之改，防双家漂移）。

## Impact

- 代码：`client/backend/archive/reconcile.py`（lore prompt 段、解析后过滤、`apply_accept` lore 分支归并）；`settings/world_model.py` 只复用常量与 `_norm` 口径，不改通用 `lore_apply_entries` 语义（设置页右栏建议路径不受影响）。
- 测试：pytest 新增 lore 过滤/归并单测；改 prompt 前对齐桩锚点（评审 P0 实勘）：lore 段首句「识别新出现或变化的世界要素」是 e2e 桩路由子串（`reconcile.spec.ts:66`）与 pytest 断言（`test_reconcile.py:719`）双重锚点，重写逐字保留；禁复用 dossier 桩第一分支子串「只输出一个 JSON 对象，四键齐全」；hooks 段冻结。
- 非目标：存量脏数据清理（演示栈本书 13 条已入账＋1 条 pending，另行手动执行、作者逐条拍板）；「为无卡人物提案立角色卡」新通道（另立项）；势力软上限按书可配（另立项）。
