# archive-reconcile 变更

## ADDED Requirements

### Requirement: 提案展示各归各的页签

- 收尾提案行 SHALL NOT 出现在「操作」页签：伏笔登记提案在「伏笔」页签展示，世界要素提案在「设定」页签展示（与采纳写回目标同位）；「操作」页签只承载生命周期卡与归档进度（chapter-dossier）。
- 已决（已采纳/已驳回）行 SHALL 默认折叠、只显计数，可展开查看留痕；失败行的错误 SHALL 单行省略展示（悬停可见全文）。
- 免费档 SHALL NOT 渲染收尾区（PRO 能力信号由归档弹窗的「归档收尾（PRO）」计划区承载），且 SHALL NOT 发起收尾行请求。

#### Scenario: 提案在对应页签

- **WHEN** 一章归档且收尾产出伏笔登记与世界要素两类待确认行
- **THEN** 「伏笔」页签出现伏笔登记行（采纳写回 `novel_hooks`）、「设定」页签出现世界要素行；「操作」页签无任何提案行

## MODIFIED Requirements

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
- **THEN** 作者立即可写下一章，收尾完成后提案出现在对应页签（伏笔登记→「伏笔」、世界要素→「设定」）

### Requirement: 收尾门控与免费档

- 收尾 AI（伏笔登记/世界 lore）SHALL 归 PRO：免费档归档成功但 SHALL NOT 产生收尾提案，也不渲染收尾区（PRO 能力信号由归档弹窗收尾计划承载）。
- 收尾 AI 调用失败（含模型未就绪）SHALL 降级为「失败」行或无行，SHALL NOT 影响归档本身的成功。
- 章档四域提取的门控（全档可用、不挂会员门）由 chapter-dossier 能力定义；两条链互不搭车。

#### Scenario: 免费档归档

- **WHEN** 免费档作者归档一章（提取成功收口）
- **THEN** 归档成功，章档四域照常（全档可用），但无伏笔/lore 收尾提案，任何页签不出现收尾区

#### Scenario: PRO 模型未就绪

- **WHEN** PRO 作者归档但本书 AI 模型未配置
- **THEN** 归档放行生效（无章档），收尾行缺失或标「失败」（可重试），流程不报错

### Requirement: 按需触发本章收尾（run）

- 系统 SHALL 提供 `POST /api/novels/{id}/chapters/{ref}/reconcile/run`：body `kind` 限一类（**KINDS 白名单收缩为 hooks/lore**，非法 400），缺省 SHALL 跑全量两类；挂 PRO 与本书模型双门控（拦截零模型调用）。
- 命中单飞语义：同章已有收尾在跑 SHALL 返回 `started=false`（不排队、不报错）；产出仍为 `chapter_reconcile` 待确认行（提案制不变）。
- 工作台右栏「AI 辅助」的旧三入口 SHALL 收敛：伏笔「登记新伏笔」保留并指路「产出在『伏笔』页签待确认」；设定提取/关系识别两入口退役（章档重提走操作页签归档卡的重新归档）。

#### Scenario: 按类触发只跑该类

- **WHEN** PRO 用户点「登记新伏笔」
- **THEN** 以 kinds=[hooks] 启动本章收尾；产出（若有）出现在「伏笔」页签待确认

#### Scenario: 缺省全量

- **WHEN** 请求不带 kind
- **THEN** 按全量两类启动；kind 传 set_changes/relations/char_states 返回 400

#### Scenario: 单飞

- **WHEN** 本章已有收尾在跑时再次触发
- **THEN** 返回 started=false，不排队不报错

#### Scenario: 未归档禁用

- **WHEN** 章节尚未归档
- **THEN** 右栏「登记新伏笔」入口禁用（产出位置「伏笔」页签此时不可见）
