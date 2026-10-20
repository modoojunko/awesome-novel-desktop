## MODIFIED Requirements

### Requirement: 下章提示词消费（故事状态·截至上章）

- 写正文素材 SHALL 新增「故事状态（截至上章）」块：只取**已采纳**行、只取**现态为 archived 或 imported** 的章（unarchive 章不消费；imported 章仅当存在 `origin=import` 且已采纳的基线行时消费，A 路无基线的导入章不贡献内容）、按章序（卷号,章号）累计合并去重（关系按双方 upsert、物品按名取最新持有者、认知按角色×事实翻转覆盖、设定按键取最新）。
- 块 SHALL 由代码单源渲染（素材包与提示词两路同源），空（无已采纳行）时整块缺席不出空段；每域条数配额（默认 ≤6）与单条截断，超出按「章近优先」截断；证据句 SHALL NOT 进消费段。
- 块内 SHALL 带定位与防泄底措辞：状态是既成事实不是本章任务、与本章剧情冲突以本章为准；「（某角色不知）」条目 SHALL 附规则行禁止该角色表现出知情或提前摊牌。
- 消费侧遇到 `dossier_stale` 章 SHALL 跳过其章档并在块头注明该章状态基于旧设定仅供参考；导入章被编辑后同样按 stale 处理，SHALL NOT 继续把旧基线当作既成事实。
- 导入章基线行 SHALL 带来源标记 `origin=import` 并以 accepted 状态落库；作者逐行否决/删除后该行 SHALL 退出消费；作者把导入章归档后按 archived 章参与消费，统计口径不变。

#### Scenario: 只消费已采纳且已归档

- **WHEN** 上一章有 3 条 pending、2 条 accepted 且 archived，另一 unarchive 章有 5 条 accepted
- **THEN** 故事状态块只含前者的 2 条，pending 与 unarchive 章内容不出现

#### Scenario: 防泄底规则生效

- **WHEN** 认知域含「乙不知甲的身份」
- **THEN** 块中该条标「（乙不知）」且块尾规则行禁止乙表现出知情

#### Scenario: 空章档不出现空段

- **WHEN** 截至.上章无任何已采纳章档行
- **THEN** 写正文素材不含故事状态块，组装产物与现状逐字一致

#### Scenario: 导入基线参与故事状态

- **WHEN** 第 1–5 章为 imported 且各有 2 条 `origin=import` 的已采纳基线行，作者开始写第 6 章
- **THEN** 故事状态块折叠第 1–5 章基线，按章序去重后进入素材；第 6 章生成可引用这些既成事实

#### Scenario: 直接导入无基线不出空段

- **WHEN** 第 1–5 章为 imported 但没有任何章档行（A 路直接导入）
- **THEN** 故事状态块整块缺席，不出空段，也不报错

#### Scenario: 编辑导入章后旧基线跳过

- **WHEN** 作者修改第 3 章（imported）正文，使该章基线标记 `dossier_stale`
- **THEN** 写第 6 章时跳过第 3 章旧基线，块头注明该章状态基于旧设定仅供参考

## ADDED Requirements

### Requirement: 导入基线写入、补算与编辑失效

- B 路开书 SHALL 用拆书阶段既有逐章卡为每章写入章档基线：设定变化、关系变化、伏笔锚定、出场角色；基线行 SHALL 带 `origin=import` 并以 accepted 落库；物品与认知域 SHALL 如实标记「未提取」，SHALL NOT 伪造空行。
- 单章「补算」SHALL 只刷新作者指定的域；SHALL NOT 替换该章已采纳的基线行；SHALL NOT 因补算把章自动归档；补算结果 SHALL 走既有待确认/采纳口径（若产品选择直接采纳，须在回执中明示）。
- 作者编辑导入章正文或标题后，该章 SHALL 标记 `dossier_stale`，并在章档页签/写作页提示「后面章节可能受影响」；系统 SHALL NOT 静默跳过、SHALL NOT 自动废弃全部下游基线；是否补算由作者决定。
- 作者可对导入章执行「归档本章」：SHALL 走归档链把 `imported` 转为 `archived`；有导入基线的章默认沿用基线、不强制重新提取，作者显式选择「重新提取」才走正常四域提取并覆盖；SHALL NOT 把该书阶段改成「待完本」，阶段仍以既有 archived 计数口径判定且排除导入来源。

#### Scenario: 开书写入逐章基线

- **WHEN** B 路拆书完成并为 42 章开书
- **THEN** 每章写入来自拆书卡的设定/关系/伏笔/角色基线，行带 `origin=import` 且为 accepted；物品/认知在回执标「未提取」

#### Scenario: 补算只刷新指定域

- **WHEN** 作者对第 7 章点「补算物品」
- **THEN** 只新增/更新物品域，原有设定/关系/伏笔已采纳行保持不变，章状态不因补算自动变为 archived

#### Scenario: 编辑导入章标 stale

- **WHEN** 作者修改第 3 章正文并保存
- **THEN** 第 3 章标 `dossier_stale`，界面提示后续章节可能受影响，旧基线不再作为既成事实消费

#### Scenario: 单章归档不改变完本阶段

- **WHEN** 作者把第 3 章（imported）归档
- **THEN** 第 3 章转为 archived 并参与正常消费；书本阶段仍为写作中，不因导入章归档进入待完本
