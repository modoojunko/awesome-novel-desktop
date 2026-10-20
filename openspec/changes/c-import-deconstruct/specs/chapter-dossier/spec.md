## MODIFIED Requirements

### Requirement: 下章提示词消费（故事状态·截至上章）

- 写正文素材 SHALL 新增「故事状态（截至上章）」块：archived 章取**已采纳**的四域变化行；历史章（`origin=import && status!=archived`）取 `chapter_import_baseline` 中已采纳/未过期的基线行（A 路无基线则不贡献）；unarchive 章不消费；按章序（卷号,章号）累计合并去重（关系按双方 upsert、物品按名取最新持有者、认知按角色×事实翻转覆盖、设定按键取最新）。
- 历史章若被作者显式「重新提取」，SHALL 以四域变化行为准，并把该章基线标 `superseded_at`；未显式重提时 SHALL 以基线为准，SHALL NOT 同时消费基线与变化行造成双份。
- 块 SHALL 由代码单源渲染（素材包与提示词两路同源），空（无已采纳/基线行）时整块缺席不出空段；每域条数配额（默认 ≤6）与单条截断，超出按「章近优先」截断；证据句 SHALL NOT 进消费段。
- 块内 SHALL 带定位与防泄底措辞：状态是既成事实不是本章任务、与本章剧情冲突以本章为准；「（某角色不知）」条目 SHALL 附规则行禁止该角色表现出知情或提前摊牌；历史章基线 SHALL 在块头注明「其中 N 章为导入原文状态，基于首尾约 6000 字，中段可能未覆盖」。
- 消费侧遇到 `dossier_stale` 章 SHALL 跳过其章档并在块头注明该章状态基于旧设定仅供参考；历史章被编辑后同样按 stale 处理，SHALL NOT 继续把旧基线当作既成事实。

#### Scenario: 只消费已采纳且已归档
- **WHEN** 上一章有 3 条 pending、2 条 accepted 且 archived，另一 unarchive 章有 5 条 accepted
- **THEN** 故事状态块只含前者的 2 条，pending 与 unarchive 章内容不出现

#### Scenario: 防泄底规则生效
- **WHEN** 认知域含「乙不知甲的身份」
- **THEN** 块中该条标「（乙不知）」且块尾规则行禁止乙表现出知情

#### Scenario: 空章档不出现空段
- **WHEN** 截至上章无任何已采纳章档行/基线行
- **THEN** 写正文素材不含故事状态块，组装产物与现状逐字一致

#### Scenario: 导入基线参与故事状态
- **WHEN** 第 1–5 章为历史章且各有导入基线，作者开始写第 6 章
- **THEN** 故事状态块折叠第 1–5 章基线，按章序去重；块头注明导入原文状态与覆盖范围

#### Scenario: 直接导入无基线不出空段
- **WHEN** 第 1–5 章为历史章但没有任何导入基线（A 路）
- **THEN** 故事状态块整块缺席，不出空段，也不报错

#### Scenario: 编辑历史章后旧基线跳过
- **WHEN** 作者修改第 3 章正文，使该章基线标记 stale
- **THEN** 写第 6 章时跳过第 3 章旧基线，块头注明该章状态基于旧设定仅供参考

## ADDED Requirements

### Requirement: 导入基线表、覆盖与补齐本章

- B 路开书 SHALL 写 `chapter_import_baseline`：`chapter_id`（FK CASCADE）、`domain`（summary/world/character/relation/hook/cast）、`key`、`value_json`、`source_card`、`ranges_json`、`evidence_absent`、`superseded_at`；唯一 `(chapter_id, domain, key)`。
- 系统 SHALL 写 `chapter_dossier_coverage`：`chapter_id`（FK CASCADE）、`domains_json`、`ranges`（首 4000 + 尾 2000 两段）、`source_card`；世界/关系/角色标 `partial`，物品/认知标 `not_extracted`，SHALL NOT 标 `full`。
- 基线 SHALL NOT 写入 `chapter_setting_changes` 等「变化」表；「变化」表继续只存归档提取。卡片可见项映射为 summary/world/character/relation/hook/cast 六域。
- 「补齐本章」SHALL 只补指定域：不替换已 accepted 基线、不把章自动归档、不触发下游 stale 级联；补算结果写入基线并更新 coverage，回执/按钮明示本次消耗。
- 作者编辑历史章正文/标题 SHALL 标 `dossier_stale` 并提示「后面章节可能受影响」；作者可「核对并保留旧摘要」（清 stale）或「重新提取本章」（覆盖并显示 token 估算），「补齐本章」不负责修 stale。
- 作者对历史章「归档本章」：有基线默认沿用基线、不强制重提；显式「重新提取」才走正常四域提取并覆盖；归档只改 status，origin 保留，阶段不前进。

#### Scenario: 开书写入基线
- **WHEN** B 路拆书完成并为 42 章开书
- **THEN** 每章写 summary/world/character/relation/hook/cast 基线，coverage 标 partial/not_extracted，无 42 次新提取

#### Scenario: 补齐指定域不替换
- **WHEN** 作者对第 7 章点「补齐本章」的物品域
- **THEN** 只补物品域，摘要/关系/角色基线逐字不变，章不自动归档

#### Scenario: 编辑后两个修复动作
- **WHEN** 作者修改第 3 章正文后打开章档
- **THEN** 出现「核对并保留旧摘要」与「重新提取本章」两个动作；前者清 stale，后者显示 token 估算并覆盖

#### Scenario: 单章归档默认沿用基线
- **WHEN** 作者把第 3 章（历史章、有基线）归档
- **THEN** 章转 archived，基线沿用、不重新提取；作者显式选「重新提取」才覆盖

#### Scenario: 删除章不留基线孤儿
- **WHEN** 删除一本书或按既有规则删除章
- **THEN** 基线与 coverage 随 FK CASCADE 删除，不出现指向不存在章的基线
