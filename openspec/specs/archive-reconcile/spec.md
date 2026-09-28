# archive-reconcile Specification

## Purpose
归档收尾提案制：一章归档即刻生效后，AI 在后台完成收尾（提取本章设定变化、建议角色关系变化、登记本章伏笔、世界 lore 建议、出场角色状态变化），产出一律先落「待确认」行；作者逐条采纳才写进对应对象。未确认提案不参与后续章节的提示词与体检。

## Requirements

### Requirement: 收尾行生命周期

- 系统 SHALL 提供 `chapter_reconcile` 行：每行＝某章某类收尾的一次产出，字段含章引用、类别（**伏笔登记/世界 lore 两类**——设定变化/角色关系/角色状态三类已迁章档能力 chapter-dossier，SHALL NOT 再产此三类收尾行）、状态（待确认/已采纳/已驳回/失败）、payload（待确认的差异描述与建议值）。
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

### Requirement: 采纳经目标对象自身服务写回

- 采纳 SHALL 调用目标对象自身的服务完成写回（**仅两类**：伏笔→伏笔服务；世界 lore→lore-apply 幂等合并），`chapter_reconcile` 的 payload SHALL NOT 直接成为第二份对象数据。
- 伏笔登记类提案的 payload SHALL 含建议的类型（9 类词表内）、优先级与证据句；采纳后写入 `novel_hooks` 并按建议置章节引用。
- 写回失败 SHALL 将行置「失败」并保留 payload 供重试，SHALL NOT 出现「行已采纳但对象未变」的中间态。

#### Scenario: 采纳伏笔登记

- **WHEN** 作者采纳一条「本章埋下：信标坐标漂移」的伏笔提案
- **THEN** `novel_hooks` 新增对应条目（类型/优先级按建议值），行置「已采纳」；再次采纳同键提案 SHALL NOT 重复建条

#### Scenario: 采纳关系建议

- **WHEN** 作者查看收尾提案列表或采纳入口
- **THEN** 收尾通道只含伏笔登记/世界 lore 两类；关系类产出在章档页签的章档行中处理，SHALL NOT 走关系服务写回书级

### Requirement: 未确认提案不参与提示词与体检

- 待确认/已驳回/失败状态的提案 SHALL NOT 影响后续章节的提示词组装与程序化体检；只有已被采纳并写回目标对象的内容才参与。
- 收尾后台任务 SHALL NOT 阻塞归档收口（archives 行、状态迁移、threads、伏笔 mentioned 留痕随归档成功事务一并生效），SHALL NOT 阻塞作者继续写作后续章节；归档本身的生效前置（提取成功）由章档能力定义。

#### Scenario: 不确认就继续写

- **WHEN** 作者归档第 3 章后未处理任何提案，直接开写第 4 章
- **THEN** 第 4 章的提示词只包含已采纳内容，第 3 章的待确认提案不注入；第 3 章提案仍可稍后确认

#### Scenario: 归档即刻生效

- **WHEN** 本书未配置模型（无提取任务）归档请求完成
- **THEN** 章状态与 archives 行即刻生效（archived、无章档）；有模型时归档以提取成功为前置（chapter-dossier），收尾仍不阻塞已生效部分

#### Scenario: 收尾慢不拖归档

- **WHEN** 归档成功收口后收尾仍在后台进行
- **THEN** 作者立即可写下一章，收尾完成后提案出现在操作页签

### Requirement: 收尾门控与免费档

- 收尾 AI（伏笔登记/世界 lore）SHALL 归 PRO：免费档归档成功但 SHALL NOT 产生收尾提案，也不产生收尾进度区（或以「PRO 可用」占位）。
- 收尾 AI 调用失败（含模型未就绪）SHALL 降级为「失败」行或无行，SHALL NOT 影响归档本身的成功。
- 章档四域提取的门控（全档可用、不挂会员门）由 chapter-dossier 能力定义；两条链互不搭车。

#### Scenario: 免费档归档

- **WHEN** 免费档作者归档一章（提取成功收口）
- **THEN** 归档成功，章档四域照常（全档可用），但无伏笔/lore 收尾提案，操作页签不出现收尾进度区

#### Scenario: PRO 模型未就绪

- **WHEN** PRO 作者归档但本书 AI 模型未配置
- **THEN** 归档放行生效（无章档），收尾行缺失或标「失败」（可重试），流程不报错

### Requirement: 按需触发本章收尾（run）

- 系统 SHALL 提供 `POST /api/novels/{id}/chapters/{ref}/reconcile/run`：body `kind` 限一类（**KINDS 白名单收缩为 hooks/lore**，非法 400），缺省 SHALL 跑全量两类；挂 PRO 与本书模型双门控（拦截零模型调用）。
- 命中单飞语义：同章已有收尾在跑 SHALL 返回 `started=false`（不排队、不报错）；产出仍为 `chapter_reconcile` 待确认行（提案制不变）。
- 工作台右栏「AI 辅助」的旧三入口 SHALL 收敛：伏笔「登记新伏笔」保留并指路「产出在『操作』页签待确认」；设定提取/关系识别两入口退役（章档重提走章档页签的重新提取）。

#### Scenario: 按类触发只跑该类

- **WHEN** PRO 用户点「登记新伏笔」
- **THEN** 以 kinds=[hooks] 启动本章收尾；产出（若有）出现在「操作」页签待确认

#### Scenario: 缺省全量

- **WHEN** 请求不带 kind
- **THEN** 按全量两类启动；kind 传 set_changes/relations/char_states 返回 400

#### Scenario: 单飞

- **WHEN** 本章已有收尾在跑时再次触发
- **THEN** 返回 started=false，不排队不报错

#### Scenario: 未归档禁用

- **WHEN** 章节尚未归档
- **THEN** 右栏「登记新伏笔」入口禁用（产出位置「操作」页签此时不可见）

