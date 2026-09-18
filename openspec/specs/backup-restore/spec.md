# backup-restore Specification

## Purpose
C端 备份导出与恢复导入：把用户的全部小说资产打包为与数据库无关的开放格式文件（yaml/md），并能从包完整恢复；同时携带账号与模型配置的配置包，使升级/换机后无需重配。是 C端 长期本地升级向前兼容的保底能力。

## Requirements

### Requirement: 双包格式契约 v1

双包契约新增/明确以下字段归属（其余不变）：

- `chapters/{ref}.yaml` 的出场引用行 SHALL 携带 `state_change`（可空）；导入 SHALL 原样落库。
- `relations.yaml` 的关系记录 SHALL 携带 `origin_chapter`（章 ref 形式，可空）；导入 SHALL 按 ref→id 重绑为 `origin_chapter_id`，目标章不存在时 SHALL 留空并计入导入告警（不阻断）。
- `chapter_reconcile`（归档收尾提案/进度）SHALL 属**运行态待办，不随包**——包边界原则：丢了不心疼的内容不进包；登记归属即界外。
- 导出 SHALL 在包内 `manifest` 或相应段登记上述字段的存在（格式版本号不变，加键兼容）。
- 既有约束 SHALL 原样保留：包为数据库无关 yaml/md、N-1 读窗、章引用一律 ref 形态、versions/archives 冻结原文不重排、token_log/模型历史/events 不随包。

#### Scenario: v3 包含伏笔段且不含旧 KV 键

- **WHEN** 对含伏笔的书执行导出
- **THEN** 包内存在 `hooks/hooks.yaml`（章引用为 ref 形态），不存在 `settings/hooks.yaml`

#### Scenario: 备份导出双包

- **WHEN** 已登录用户在设置发起备份并选择保存目录
- **THEN** 所选目录内生成资产包与配置包两个 zip，包含全部活跃书的 8 类资产对象与全部 api_configs（密钥明文，本机解密导出）
- **AND** 用量台账（token_log）、模型切换历史、埋点（events）不出现在任何包内

#### Scenario: 冻结原文不重排

- **WHEN** 导出含版本快照与归档的书
- **THEN** versions/*.json 与 archives/*.md 的内容为库内原文字节级直写，不做任何格式转换

#### Scenario: format_version 演进规则

- **WHEN** 导入端遇到包内 format_version
- **THEN** 缺失（v0 旧包）按兼容模式全量回吃；≤3 全部可导入（1=v1 契约、2=角色 v2、3=本 change 伏笔段）；大于 3 拒绝并提示「请先升级应用」
- **AND** 未来演进：加键=兼容不升版；删键/改布局=升版且导入端保留 N-1 读窗

#### Scenario: 出场引用带状态变化跨机恢复
- **WHEN** 导出含「第 3 章出场沉舟 state_change=从犹豫到决意」的包并在新机导入
- **THEN** 该字段原样恢复，且「截至本章」视图可显示

#### Scenario: 关系来源章跨机重绑
- **WHEN** 导出关系记录 origin_chapter=vol-1-ch-5 并在新机导入
- **THEN** 来源章重绑为对应章 id；若该章缺失则来源留空并出现导入告警

#### Scenario: 收尾提案不随包
- **WHEN** 作者有 3 条待确认提案未处理即导出全书
- **THEN** 包内不含提案数据，新机导入后提案区为空（不视为数据丢失）

### Requirement: 备份导出（目录选择+后端直写）

备份导出 SHALL 通过壳层原生目录选择框（js_api 桥）由用户指定保存目录，后端（本机进程）直接将双包写入该目录并提供进度查询；无壳环境回退 HTTP 下载。单书交付导出 SHALL 通过壳层保存框指定文件名。

- 备份与「下载成稿」（`manuscript-download` 能力）SHALL 共用全局单飞任务机制：同一时间全系统只允许一个任务（备份或下载）在跑；互斥被触发时 409 响应 SHALL 携带在跑任务的类型（`running_kind`），备份被下载挡回时前端提示 SHALL 说明「已有下载在进行」。
- 账号菜单备份项的提示文案 SHALL NOT 使用「导出」动词（「选择文件夹导出」→「选择文件夹保存」）；书卡菜单的单书交付「导出」用法不变。

#### Scenario: 选目录一键备份

- **WHEN** 用户点「选择保存位置」完成目录选择并发起备份
- **THEN** 后端将资产包与配置包写入所选目录，前端轮询获得真进度（逐书阶段）
- **AND** 磁盘满/权限错误时给出人话原因与「换个位置/重试」出口，已写文件清理语义明确

#### Scenario: 单书交付导出

- **WHEN** 用户在书卡菜单点「导出」
- **THEN** 通过保存框得到《书名》-作品包-日期.zip，不含任何配置或密钥

#### Scenario: 备份被进行中的下载挡回

- **WHEN** 下载成稿任务进行中用户发起备份
- **THEN** 备份发起被拒绝（409），响应体标明在跑任务为下载，前端提示「已有下载在进行」且不并发写盘

### Requirement: 恢复导入（双槽位+逐书原子）

恢复 SHALL 提供两个明确槽位（作品备份/账号与模型配置）分别选择文件，至少一项；parse 校验归并预览（作品块+配置块分块、冲突标记、warnings 通道），persist 按**书为原子单元**逐书落库（单书单事务全成全败，书间独立，失败可单独重试），配置包落库后执行**智能挂回**（active 配置唯一→全挂；书内模型名命中恰一个配置→挂之；否则置空待选），挂回双向幂等。同名书恢复为《书名（备份）》递增命名；同名配置跳过不覆盖。免费额度只拦新建，恢复放行。

#### Scenario: 双包一次恢复

- **WHEN** 用户选择资产包与配置包并发起恢复
- **THEN** 书与配置全部恢复，完成摘要报告恢复数、挂回结果（已接回/待选择）与 warnings
- **WHEN** 用户只选择作品包
- **THEN** 仅恢复书，配置保持现状（合法单包）

#### Scenario: 坏包不落半截

- **WHEN** 包损坏/路径穿越/format_version 过高/元数据缺失
- **THEN** 422 整包拒绝（或按容错矩阵跳过单项+warning），数据库无半截行

#### Scenario: 恢复后可再导出（幂等）

- **WHEN** 恢复完成的项目再次导出
- **THEN** 新包与原包目录布局与 yaml 键集合相等（防「导入即降级」漂移）

### Requirement: 旧库留档与升级演练

新版本启动 SHALL 对 schema 指纹不匹配的存量库执行三件套改名留档（db/-wal/-shm，零接触）并以全新空库启动；留档仅可经只读检测端点消费。**任何 schema 破坏性版本的发布验收 MUST 包含全链演练**：旧库造书→导双包→装新版（留档断言）→导入→八层 roundtrip 断言全绿。

#### Scenario: 升级后旧数据可救

- **WHEN** 用户升级后删除新库（极端救援）
- **THEN** 新版空库上导入升级前导出的资产包，八层 roundtrip 断言全绿
- **AND** 留档库文件全程原样保留

### Requirement: 角色段的导入导出契约（v2）

资产包的角色段 SHALL 随本次改版升到 `format_version: 2`：角色与人物关系从"派生键的文件树"改为**真表结构**的导出形态，并保留 N-1 读窗（**新版 SHALL 能读旧包**；旧版本读新包不在承诺内——本机应用回退会触发旧库留档，须由新版重新导入）。导入 SHALL 把旧包（v1，角色为若干平铺字段的 yaml）按映射搬进新形状：已有归属的字段逐格落位、**无归宿的老字段只保留原文、不上界面**。导入 SHALL NOT 把角色写回旧的派生键位置（`character:` 前缀），且恢复完成后该前缀下的行数 SHALL 为 0。角色与关系的 id SHALL 在"导出 → 导入 → 再导出"后保持稳定；出场引用未命中角色时 SHALL 落原文快照并在恢复摘要里计数告警，SHALL NOT 使整包导入失败。包内出现多位主角或重名时，导入 SHALL 做确定性收敛并给出告警。

#### Scenario: 新包导出形态
- **WHEN** 用本版导出资产包
- **THEN** 角色段以新形态落盘（不再写旧的角色目录树），元数据 `format_version` 为 2

#### Scenario: 读旧包并搬进新形状
- **WHEN** 导入一个 v1 资产包
- **THEN** 角色与其关系的可归属字段全部落位，无归宿字段的原文被保留，界面不展示它们；老包缺的格保持为空等待作者补

#### Scenario: 角色不写回旧位置
- **WHEN** 导入完成后检查存储
- **THEN** `character:` 前缀下的行数为 0，角色数据只存在于新结构里

#### Scenario: id 往返稳定
- **WHEN** 导出后导入、再导出同一本书
- **THEN** 角色与关系记录的 id 逐条一致

#### Scenario: 出场引用未命中
- **WHEN** 包内某章的出场角色名在书中找不到对应角色
- **THEN** 该名字按原文快照保留，恢复摘要里计数告警，整包导入仍然成功

#### Scenario: 包内多主角
- **WHEN** 导入的包里有多位主角或重名
- **THEN** 导入按确定性规则收敛（保留最早的一位，其余降级 / 重名报错），并在摘要中给出告警

### Requirement: 伏笔段的导入导出契约（v3）

- 导出端 SHALL 把 novel_hooks 行序列化为伏笔段：章引用四列做 id→ref 解析（无法解析的置空）；seq 原样导出。
- 导入端 SHALL 在「章循环落库之后」执行 ref→id 重绑（与既有的「characters 先于 chapters」顺序约束并存，落库顺序须显式注释）；目标 ref 不存在时 SHALL 置 NULL 并计入 warnings，SHALL NOT 丢行。
- v1 读窗：导入器 SHALL 接受旧包 `settings/hooks.yaml` 的三数组形状——数组名→status；`introduced_in` 自由文本经规范归一后按章 ref 绑定 introduced_chapter_id（绑不上置 NULL）；旧条目 `status:"mentioned"` SHALL 迁为 status=active＋mentioned_in_chapter_id=引入章（无引入章则列空）；priority 接受 int/字符串/"high" 形混形归一；未知 type 置空。旧 KV 形状导入后 SHALL NOT 在 project_settings 残留 hooks 键。
- roundtrip 验收 SHALL 含伏笔段：计数对拍、章引用经 ref 对拍一致、status 映射逐条相等；升级演练（留档→空库→v1 包恢复）SHALL 扩伏笔种子（含短格式/垃圾文本/mentioned/priority 混形/空描述样例）并断言幂等重跑。

#### Scenario: v1 包恢复不丢伏笔

- **WHEN** 旧版书（KV 三数组，含 mentioned 与绑不上章的条目）经「留档＋空库＋v1 包恢复」升级
- **THEN** 每条有效伏笔成为一行真表数据：status 映射正确、可解析的章引用绑定到新章 id、不可解析的置 NULL、mentioned 条目转为 active＋mentioned 列；行数与有效条数一致

#### Scenario: v3 包 roundtrip 引用跟随

- **WHEN** 导出 v3 包并在另一空库导入
- **THEN** 伏笔计数一致，每条伏笔的四个章引用指向与源库「同 ref」的章（id 允许重映射，引用跟随）

### Requirement: 归档段唯一性与完整性

备份包（整库资产包 `kind=backup` 与单书交付导出 `kind=single`）的归档段 SHALL 满足：zip 内 `archives/` 每条归档**恰一个条目**（多卷书不得因卷循环产生同名重复条目）；`archives/manifest.yaml` 的 `archives` 列表条数 SHALL 恰等于**归档行数**（Archive 表行数；一章至多一行），且 `filename` 字段无重复。

- 归档查询 SHALL 保持书级口径（按 `Chapter.project_id` 全量），与卷遍历解耦，并带显式排序（卷序 + 章序）保证 manifest 顺序确定。
- 本条款为既有意图的契约化，不改任何字段与布局，`format_version` 不变；多卷包内条目顺序由「逐卷交错」变为「收拢于卷循环之后」（无消费方依赖顺序）。
- `GET /novels/{id}/export`（并行旧端点）不在本条款覆盖面。

#### Scenario: 多卷书归档条目唯一

- **WHEN** 一本 2 卷、每卷各含 1 条归档（共 2 条归档行）的书执行整库备份导出
- **THEN** 包内 `projects/{slug}/archives/` 下恰有 2 个归档条目（`namelist` 计数为 2，无同名重复——断言必须用 list 计数，集合会掩盖重复），manifest 的 `archives` 列表恰 2 条且 `filename` 互不相同

#### Scenario: 单卷书行为不变

- **WHEN** 单卷书的常规导出执行
- **THEN** 归档段产物与修复前逐字段一致（条目名、条目内容字节、manifest 字段集不变；条目相对顺序仅在多卷时变化）
