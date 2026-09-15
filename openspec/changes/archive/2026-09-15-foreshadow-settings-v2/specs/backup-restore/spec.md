# backup-restore 变更（增量）

## MODIFIED Requirements

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

## ADDED Requirements

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
