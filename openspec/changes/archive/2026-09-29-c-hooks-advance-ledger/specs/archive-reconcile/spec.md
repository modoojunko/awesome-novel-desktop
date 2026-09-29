# archive-reconcile 变更

## MODIFIED Requirements

### Requirement: 收尾行生命周期

- 系统 SHALL 提供 `chapter_reconcile` 行：每行＝某章某类收尾的一次产出，字段含章引用、类别（**伏笔登记/世界 lore 两类**——设定变化/角色关系/角色状态三类已迁章档能力 chapter-dossier，SHALL NOT 再产此三类收尾行）、状态（待确认/已采纳/已驳回/失败）、payload（待确认的差异描述与建议值）。
- hooks 类 payload SHALL 为对账制三类（c-hooks-advance-ledger）：`resolved`（兑现——`ref` 引用台账编号＋`note` 怎么收的＋证据）、`advanced`（推进——`ref`＋`note` 一句推进说明＋证据，未收束）、`planted`（新埋——描述＋证据）；三类各 ≤3；**本章无新悬念时 `planted` SHALL 为空数组，SHALL NOT 为凑数产出**。
- hooks 类收尾的 prompt SHALL 注入活跃台账全量（编号＋描述＋计划收束章），并要求先对账（兑现/推进既有条目）再判新埋；台账排重（#589「相同或高度相似的不要重复登记」）与真伏笔判据维持。
- 行的初始状态 SHALL 为「待确认」；采纳后置「已采纳」并执行写回；驳回后置「已驳回」；后台产出失败置「失败」并 SHALL 可重试（重试生成新行或覆盖同键行，两者取一并登记）。
- 同章同键重复产出 SHALL 覆盖未决行而非新增（避免同类提案堆积）；已决（已采纳/已驳回）行 SHALL 保留原样不覆盖（审计留痕）。
- 收尾进度 SHALL 由行聚合派生（待确认数/失败数/已完成数），SHALL NOT 另存独立的任务进度实体。
- `chapter_reconcile` 行属于**运行态待办**：SHALL NOT 进入备份导出包。
- 收尾产出解析失败 SHALL 显式落「失败」行（含错误摘要、可重试），SHALL NOT 静默丢弃。

#### Scenario: 三类收尾各成待确认行

- **WHEN** 一章归档成功且收尾 AI 全部成功
- **THEN** 该章只出现伏笔登记/世界 lore 两类待确认行；设定变化/角色关系/角色状态三类 SHALL NOT 再产收尾行（四域产出在章档页签，chapter-dossier）

#### Scenario: 失败可重试

- **WHEN** 某类收尾 AI 调用失败或返回不可解析内容
- **THEN** 对应行状态为「失败」含原因，作者可重试，重试成功后行转为「待确认」

#### Scenario: 同键覆盖

- **WHEN** 同一章重归档或重试，且上一条同键行仍是待确认
- **THEN** 未决行被新产出覆盖，不堆积第二条待确认

#### Scenario: 对账产出按编号引用

- **WHEN** 收尾 AI 判定本章兑现/推进了既有伏笔
- **THEN** 产出行的 resolved/advanced 条目带台账编号 ref（如 `#H-0003`）与证据；本章无新悬念时 planted 为空数组

### Requirement: 采纳经目标对象自身服务写回

- 采纳 SHALL 调用目标对象自身的服务完成写回（**仅两类**：伏笔→伏笔服务；世界 lore→lore-apply 幂等合并），`chapter_reconcile` 的 payload SHALL NOT 直接成为第二份对象数据。
- 伏笔登记类提案的 payload SHALL 含建议的类型（9 类词表内）、优先级与证据句；采纳后写入 `novel_hooks` 并按建议置章节引用。
- hooks 类采纳 SHALL 按编号精确匹配（c-hooks-advance-ledger）：`resolved` 命中→patch `resolved` 状态＋收束章＋payoff_note（note 有值时）；`advanced` 命中→回填该行 `mentioned_chapter_id`=本章（最近推进留痕，状态不动）。ref 无法解析或行不存在 SHALL 跳过该条目（SHALL NOT 报错中断整批）；payload 条目无 ref 的旧格式（存量待确认行）兼容按描述包含匹配。
- 写回失败 SHALL 将行置「失败」并保留 payload 供重试，SHALL NOT 出现「行已采纳但对象未变」的中间态。

#### Scenario: 采纳伏笔登记

- **WHEN** 作者采纳一条「本章埋下：信标坐标漂移」的伏笔提案
- **THEN** `novel_hooks` 新增对应条目（类型/优先级按建议值），行置「已采纳」；再次采纳同键提案 SHALL NOT 重复建条

#### Scenario: 采纳关系建议

- **WHEN** 作者查看收尾提案列表或采纳入口
- **THEN** 收尾通道只含伏笔登记/世界 lore 两类；关系类产出在章档页签的章档行中处理，SHALL NOT 走关系服务写回书级

#### Scenario: 兑现与推进按编号落账

- **WHEN** 作者采纳一条含 resolved=[{ref:"#H-0003",…}] 与 advanced=[{ref:"#H-0001",…}] 的伏笔提案
- **THEN** #H-0003 转「已收束」（收束章＝本章，payoff_note 按 note）、#H-0001 保持活跃且「最近推进」更新为本章；不新建任何台账行
