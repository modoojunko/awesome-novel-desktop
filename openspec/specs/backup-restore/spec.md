# backup-restore Specification

## Purpose
C端 备份导出与恢复导入：把用户的全部小说资产打包为与数据库无关的开放格式文件（yaml/md），并能从包完整恢复；同时携带账号与模型配置的配置包，使升级/换机后无需重配。是 C端 长期本地升级向前兼容的保底能力。

## Requirements

### Requirement: 双包格式契约 v1

- 小说资产包 SHALL 以与数据库无关的开放格式（yaml/md）打包；format_version SHALL 升至 **3**（本 change：新增伏笔段、settings 树摘除 hooks 键）。
- 导入端 SHALL 保留 N-1 读窗：format_version ≤3 的包 SHALL 全部可导入；format_version 大于当前版本的包 SHALL 被响亮拒绝。
- 小说资产包的伏笔段 SHALL 位于 `hooks/hooks.yaml`，每条含：description、type（slug）、priority、status、introduced_chapter_ref / planned_chapter_ref / resolved_chapter_ref / mentioned_chapter_ref（章引用一律存 `vol-N-ch-M` 规范 ref，**不存运行态 chapter id**——导入时章 id 重新生成）、payoff_note、seq。`settings/hooks.yaml` SHALL 不再出现在包内。
- settings 树（PATH_TO_KEY）SHALL 摘除 hooks 键（同时收掉 KV 端点白名单与导出遍历）；新建项目模板 SHALL 不再种 hooks.yaml。

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
### Requirement: 备份导出（目录选择+后端直写）

备份导出 SHALL 通过壳层原生目录选择框（js_api 桥）由用户指定保存目录，后端（本机进程）直接将双包写入该目录并提供进度查询；无壳环境回退 HTTP 下载。单书交付导出 SHALL 通过壳层保存框指定文件名。

#### Scenario: 选目录一键备份

- **WHEN** 用户点「选择保存位置」完成目录选择并发起备份
- **THEN** 后端将资产包与配置包写入所选目录，前端轮询获得真进度（逐书阶段）
- **AND** 磁盘满/权限错误时给出人话原因与「换个位置/重试」出口，已写文件清理语义明确

#### Scenario: 单书交付导出

- **WHEN** 用户在书卡菜单点「导出」
- **THEN** 通过保存框得到《书名》-作品包-日期.zip，不含任何配置或密钥

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
