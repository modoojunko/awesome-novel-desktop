## Purpose

（既有能力 world-settings 的增量：lore-keeping 提案制加产出护栏与采纳归并——真机实锤两章灌入 13 条 AI 条目、势力格 6/6 占满，Purpose 见主 spec。）

## MODIFIED Requirements

### Requirement: lore-keeping 随归档生长（提案制）

- 归档章节时系统 SHALL 产出世界要素建议，**经后台收尾提案制落 `chapter_reconcile` 待确认行（kind=lore）**——覆盖 history/extra/factions/constraints 条目集（`set` 归属随建议给出，缺失/非法回落 extra；规则戒律类 SHALL 归 constraints——姊妹模板与事故实勘：三选项口径是「同一教规两格双落」的成因之一）；段落型 01-03 SHALL NOT 被改写；人物变化 SHALL 由收尾的出场引用状态变化承载（char_states），不在本建议内。
- 建议 SHALL NOT 随归档响应即焚、SHALL NOT 进入任何面板暂存区：归档响应不再携带建议列表；采纳统一在「设定」页签的收尾提案区逐条确认（展示位置见 archive-reconcile「提案展示各归各的页签」）。
- 建议条目 SHALL 带章节来源 origin；采纳经 `POST .../reconcile/{id}/accept` 走 lore-apply 幂等合并（同一 origin 重复归档/重跑 SHALL NOT 产生重复条目，同章同类未决提案 SHALL 覆盖而非堆积）。
- lore 建议 SHALL 与「归档生成章节摘要」偏好互相独立（均只看会员门控）。
- 产出判据（c-lore-reconcile-guardrails）：建议 SHALL 只含「后续章节还会当既定设定引用的恒定世界事实」（正反判据成对：长期有效的规则/条约/戒律——哪怕本章才立下——SHALL 提；本章情节经过与拍点、人物状态与外貌、一次性场景细节 SHALL NOT 提）。prompt SHALL 注入现有势力名单（聚焦口径：势力先立两三个，已有 ≥3 不再提新势力，势力相关变化并进既有势力条目，且 SHALL NOT 把新势力改放 extra/history 变相提交）与**本书其他章**待确认提案名目——待确认提案 SHALL 独立成块、只列名目，SHALL NOT 混入「现有世界设定」块（未决提案不是既定设定）；排除本章：同章重复由覆盖语义兜住。排重源＝世界设定现值＋其他章待确认提案，SHALL NOT 只对现值排重。
- 产出护栏 SHALL 代码侧确定性执行（不依赖模型自觉）：单批候选超过 4 条时按模型给出顺序截取前 4 条；候选名目与出场角色名单两侧同口径归一化，命中 SHALL 丢弃；世界设定势力已 ≥3（只统计有名目条目）时 set=factions 的新名目候选 SHALL 丢弃（名目命中既有势力的候选不受限）；过滤后整批为空 SHALL NOT 落行、SHALL NOT 覆盖既有未决行；产出护栏同样作用于采纳时（存量未决行采纳前逐条复检）。
- 采纳归并：同批内归一化同名目先去重（保留首条）；归一化名目（口径同伏笔查重：小写化、去空白与标点，不做全角折叠）命中 history/extra/factions 既有条目时，采纳 SHALL 用该既有条目的**字面** key/origin/set 改写为更新（保留原格与原 origin——若该格条目带 origin——替换 value/note），SHALL NOT 因跨章来源或 `set` 归属不同而新增第二条或落入另一格；constraints 条目集 SHALL NOT 被归并改写（作者手写铁律 SHALL NOT 被 AI value 覆盖）。

#### Scenario: 归档产生提案行（不随响应即焚）
- Given 会员用户归档第 12 章且本书模型就绪
- When 后台收尾完成
- Then 世界要素建议以 kind=lore 的待确认行出现在该章「设定」页签；归档响应本身不含建议列表

#### Scenario: 采纳入账幂等
- Given 一条 kind=lore 待确认提案（origin=第 12 章）
- When 作者点「采纳」，随后同名目同来源的条目再次入账
- Then 世界设定仅一条该条目（(key, origin) 幂等），提案行标记已采纳

#### Scenario: 驳回不入账且留痕
- Given 一条 kind=lore 待确认提案
- When 作者点「驳回」
- Then 世界设定不变、后续写章不引用该条；提案行标记已驳回（留痕，不再出现待确认计数）

#### Scenario: 单批候选超限截断
- Given 收尾模型单批返回 6 条候选（真机实锤：首章一批 8 条全数入账）
- When 提案落待确认行
- Then 行内只保留按模型给出顺序的前 4 条，其余丢弃

#### Scenario: 出场人物名目被丢弃
- Given 本章出场角色名单含「银铎」，世界设定与角色名册均无该名目条目
- When 收尾返回 key=银铎 的候选（无论 set 归属）
- Then 该候选不出现在待确认行内容中（人物归角色域，无卡人物也不入世界要素）；若该批仅此一条（过滤后为空），本章不落世界要素待确认行、既有未决行不被覆盖

#### Scenario: 势力聚焦——三势力后不提新势力
- Given 世界设定已有 3 个势力条目（含手写）
- When 收尾返回 set=factions 且名目为现有势力之外的新候选
- Then 该候选被丢弃；set=factions 且名目命中既有势力的候选不受限（照常更新该势力）

#### Scenario: 整批过滤为空不落行
- Given 本章候选经护栏过滤后为空（如全部为出场人物名目）
- When 收尾完成
- Then 本章不产生世界要素待确认行、既有未决行不被空批覆盖，「待确认」计数不因此增加

#### Scenario: 跨章同名目归并不双落
- Given history 已有「停战条款第三条」（origin=第 1 章）
- When 作者采纳第 2 章提案中归一化同名目、但 `set` 归属为 factions 的条目
- Then 既有 history 条目更新 value（用既有条目字面 key/origin 改写，保留原格与原 origin=第 1 章），factions SHALL NOT 出现该名目（真机实锤：该条款曾双落于两格）

#### Scenario: 批内同名目只落一条
- Given 同一提案批内含归一化同名目两条、`set` 归属各异（真机实锤形态：停战条款第三条一批内 history/factions 各一条）
- When 作者采纳该批
- Then 仅首条按归并口径入账，后续同名目丢弃，SHALL NOT 双落

#### Scenario: 存量未决行采纳前复检
- Given 一条护栏上线前的存量 kind=lore 未决提案，其中含名目为出场人物（或现无卡人物）的候选
- When 作者点「采纳」
- Then 人物类候选被丢弃不入账，其余候选照常归并入账，行正常置「已采纳」
