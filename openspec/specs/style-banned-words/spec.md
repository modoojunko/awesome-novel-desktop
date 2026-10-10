# style-banned-words Specification

## Purpose
禁用词与句式规则收编为文风硬约束的子区：数据落 writing-style KV、硬约束三块编辑、存量 anti-ai.yaml 一次性迁移、注入与程序化体检单源化，禁用词句独立面板退役。

## Requirements

### Requirement: 禁用词与句式规则落文风 KV

- writing-style KV SHALL 新增两个白名单写键：`banned_words`（字符串列表，≤100 条、单条 ≤50 字）与 `tic_patterns`（句式规则列表，≤20 条，每条含 pattern/name/threshold/severity/description）。
- GET/PUT `/settings/style` SHALL 对两键做与三区同款的归一边界处理（去空白、保序去重、上限截断）。
- 幽灵键 `fatigue_words` SHALL 在归一时并入 `banned_words`（去重）后从文档剥离，GET 响应 SHALL NOT 再返回该键。

#### Scenario: 两键读写回路
- **WHEN** PUT /settings/style 带 banned_words 3 条、tic_patterns 1 条后再 GET
- **THEN** 两键原样返回（顺序保持、无重复）；GET 响应无 fatigue_words 键

#### Scenario: 幽灵键存量词迁移可见
- **WHEN** 存量书 style KV 带 fatigue_words ["突然","瞬间"]
- **THEN** 归一后两词出现在 banned_words，写章提示词照常禁用，文风面板禁用词块可见可编辑

#### Scenario: 上限截断
- **WHEN** PUT 带 120 条禁用词
- **THEN** 只保留前 100 条，不报错

### Requirement: 硬约束三块与面板退役

- 文风面板硬约束区 SHALL 含三块：① 禁令（自然语言，上限 100 条——与后端 `_MAX_RULES` 对齐，UI 建议 3–5 条；模板/迁移预填的通用红线计入上限、可直接删改）② 禁用词（词表编辑器，模板预填通用 AI 腔词）③ 句式规则（正则＋阈值＋严重度编辑器）。
- 禁用词与句式规则两块 SHALL 为折叠组（Cfg）：默认收起，组头摘要位常显「N 条」，展开编辑。
- 设定页左栏菜单 SHALL NOT 再有「禁用词句」项；系统 SHALL NOT 渲染独立禁用词句面板。
- 原禁用词句面板的编辑能力（7 分类词表展平为词表、句式规则整体）SHALL 全部在文风面板可达。

#### Scenario: 菜单无禁用词句
- **WHEN** 打开设定视图左栏菜单
- **THEN** 菜单为 模型设定/简介/题材/世界/角色/主线/文风/伏笔，无禁用词句项

#### Scenario: 词表与句式在文风页编辑
- **WHEN** 作者在文风面板硬约束区编辑禁用词并保存
- **THEN** 词表写入 writing-style KV 的 banned_words，无需访问任何其他面板

#### Scenario: 预填超旧上限仍可添加
- **WHEN** 书硬约束已被模板/迁移预填 58 条（任意超过旧上限 5 条），作者点①禁令块的「添加一项」
- **THEN** 计数显示「58/100 条」，「添加一项」可见可用；新增行填值保存后计入 rules（PUT 侧 100 条截断口径不变）

#### Scenario: 上限 100 条收起添加
- **WHEN** 硬约束行数达到 100 条（后端 `_MAX_RULES` 上限）
- **THEN** 「添加一项」不再渲染（加载与保存行为不变）

### Requirement: 存量 anti-ai 数据一次性迁移

- 系统 SHALL 在读取或写入文风 KV、或任一后端内部读者（写章组装/程序化体检/辅助注入/AI 体检）首次取用禁用词时，把存量 anti-ai KV（7 分类疲劳词＋句式规则）一次性迁入文风 KV：词表经半/全角（NFKC）与大小写归一去重并入 `banned_words`，句式规则平移为 `tic_patterns`。
- 迁移 SHALL 幂等：完成后于文风 KV 落完成标记（该标记 GET 响应 SHALL 剥离）；标记存在即不再重迁，作者此后对 `banned_words` 的删改 SHALL NOT 被回灌。
- **anti-ai 原键 SHALL 原样保留、不删除不改名**：这是回滚安全的唯一保证（回滚版本读原键恢复全部能力）；其存储路由映射 SHALL 原样保留，导出/导入回路对未迁移书照常携带、迁移后随标记位保持幂等。原键的清理属后续版本的独立清理项，不在本变更内。
- 无 anti-ai 数据的书 SHALL 不受影响（存在性判定 SHALL 区分「键不存在」与「键内容为空」）。

#### Scenario: 旧书迁移后词句齐全
- **WHEN** 存量书 anti-ai 数据有 3 分类共 8 词与 2 条句式规则，作者首次打开文风面板
- **THEN** 8 词与 2 条句式出现在文风硬约束对应块，完成标记已落，anti-ai 原键仍在

#### Scenario: 迁移幂等且删词不被回灌
- **WHEN** 迁移完成后作者从禁用词块删掉「突然」，再次触发文风读取或写章组装
- **THEN** 「突然」不被回灌（标记位拦截重迁）；重复触发不产生重复条目

#### Scenario: 回滚安全
- **WHEN** 迁移后的书回滚到旧版本应用
- **THEN** 旧代码读 anti-ai 原键照常获得全部词与句式，注入与体检能力不丢

#### Scenario: 新书无感知
- **WHEN** 新建书（无 anti-ai 数据）
- **THEN** 文风面板禁用词块为模板预填词，无迁移动作发生

### Requirement: 注入与体检单源

- 写章提示词「禁止使用以下词汇／禁止以下句式」、辅助写作链注入、quality 程序化体检（词命中＋正则句式）、AI 体检 SHALL 只从文风 KV 的 `banned_words`/`tic_patterns` 取数，且 SHALL 经统一迁移感知读路径取用（内部读者不绕过迁移）；`chapter_writer` 对 style 卡 fatigue_words 与题材行疲劳词的合并读取 SHALL 删除。
- `POST /settings/anti-ai/words` 端点 SHALL 退役删除；通用 `/settings/anti-ai` 读写端点 SHALL 加退役分支（写拒绝并给退役提示，沿伏笔退役先例）。

#### Scenario: 提示词禁用词来自文风 KV
- **WHEN** 文风 KV banned_words 含「突然」，组装写章提示词
- **THEN** 「禁止使用以下词汇」段含「突然」；不含任何已迁移原键中的独有词

#### Scenario: 未进设定页的旧书体检不假通过
- **WHEN** 存量书从未打开文风面板，直接对正文跑 quality 程序化体检
- **THEN** 体检先经统一读路径完成迁移再取词，anti-ai 里的词照常命中

#### Scenario: 程序化体检命中迁移词
- **WHEN** 正文含「综上所述」且该词在 banned_words
- **THEN** quality 检查报告该词命中

#### Scenario: 旧端点不可达
- **WHEN** POST /settings/anti-ai/words
- **THEN** 返回 404/405（端点已删除，路由表象任一即视为不可达）

### Requirement: 蒸馏并入文风词表

- 蒸馏 commit 产出的禁用词候选 SHALL 由服务端 append 进文风 KV `banned_words`（半/全角 NFKC、大小写归一后跨词表去重），文风面板禁用词块可见。
- 蒸馏 commit 成功后，前端 SHALL 回读文风 KV 并只把 `banned_words`/`tic_patterns` 两键合入表单态与脏快照基线（SHALL NOT 整表覆盖用户未保存的三区编辑），避免作者持旧表单快照保存时覆盖丢词。
- 词表已满上限时 SHALL 静默丢弃新词并返回实际新增数（0），SHALL NOT 报错。

#### Scenario: 蒸馏新词落入禁用词块
- **WHEN** 蒸馏产出禁用词「眸子」且词表已有「突然」
- **THEN** commit 后 banned_words 为原词表＋「眸子」，无重复；文风面板可见

#### Scenario: commit 后直接保存不丢词
- **WHEN** 作者进文风面板（词表快照加载）→ 蒸馏 commit 并入新词 → 不切面板直接点保存
- **THEN** 新词仍在 banned_words（表单态已经回读合并）

#### Scenario: 满表静默丢弃
- **WHEN** banned_words 已满 100 条，蒸馏 commit 产出 3 个新词
- **THEN** 无报错，返回新增数 0，词表不变
