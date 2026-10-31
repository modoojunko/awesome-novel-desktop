# 写作知识库 · 数据结构（每类知识一条）（C端 · 2026-10-30）

**一句话**：一条知识＝**公共信封（`kb_entries` 行）＋按概念强校验的 `payload_json`**。信封管身份（谁、哪个题材、挂哪个概念/子概念、从哪来、证据是什么）；payload 管**内容形状**——六类概念各有自己的字段表，字段直接对齐消费端真实键（`style` 白名单 7 键、`world` V2 8 键、角色档案格），渲染是确定性的映射，不是再加工。

- 上游：整体方案 §2.3（六概念）、§5（表模型）、§6（消费契约）、§8（导入与闸门）
- 原则（先立三条）：
  1. **一条知识只讲一个侧面（一个 slot）**。“冷峻的叙事身份”是一条，“禁用‘仿佛’”是另一条；不是一条塞一整套文风。同 slot 多条在同步预览并排，作家选。
  2. **payload 字段名＝消费端键名**。文风的 `role`、文笔的 `banned_words`、世界的 `constraints` 直接就是 `STYLE_WRITE_KEYS`/`V2_KEYS` 里的名字，渲染函数只做“挑选＋拼接”，不做语义转换。
  3. **原文永不入库进提示词**。示范段走 `style_samples` 通道（≤6×500），证据只读展示。

---

## 字段 → 数据 → 划分（总模型，用户拍板 10-31）

**知识库本体是一套字段系统；知识是按字段填进去的行；库是对行按字段值做的划分。** 三层只有第一层是结构，后两层都是数据：

```
① 字段层（结构，开发者维护）
   kb_entries 的信封字段 ＋ 每概念的 payload 字段表（本文 §0–§6）
        ↓ 按字段填
② 数据层（知识，作家/拆书/蒸馏填）
   一行 = 一条知识；题材、概念、子概念、场面、情绪、来源全是**字段值**，不是结构
        ↓ 按字段值划分
③ 划分层（库，视图）
   库 = 一个字段谓词命中的行集 ＋ 手动例外；默认库 = genre×concept 的格子；
   书内启用 = 再叠一层 novel 维度（binding）
```

由此三条硬推论：

1. **题材不是柜子，是 `genre` 字段的值**。21 类是该字段的封闭词表（themeCatalog）；“仙侠/修真”＝`genre='仙侠/修真'` 的行集；空题材＝该值下 0 行（空态卡），不需要预建任何东西。
2. **概念同理**：`concept` 六值、`concept_id` 指向概念树的叶子；“手法”＝`concept='手法'` 的行集。
3. **库不存知识，只存划分条件**：`kb_libraries.rule_json` 是字段谓词（默认库 `{"genre":X,"concept":Y,"kind":"auto_all"}`；自定义库 P1 如 `{"scene":"打斗","emotion":"燃"}`），`kb_library_items` 只是谓词结果的物化＋手动增删。删库不丢知识，行还在字段层。

## 本体四要素对照（audit · 10-31）

| 本体要求 | 现状 | 判定 | 缺口 → 补丁（本文已并入） |
|---|---|---|---|
| **概念名词** | `kb_concepts`(id/name/level/parent)＋21 题材封闭词表＋六概念注册表 | ✅ | 加 `aliases` 同义词（拆书映射/搜索归一用） |
| **关系层** | `kb_relations` 六类白名单、AI 整理、confidence/status | ✅ 类型化 | 缺逆关系/定义域值域/函数性 → §10 关系元数据表 |
| **概念解读** | L1 六概念有 `definition/props`（CONCEPT_DEFS） | ⚠️ 只到六概念 | 子概念 `definition` 必填（种子）；概念统一带 `interp_json{定义,同义,正例ref,反例ref}` |
| **正反案例** | 手法 instruction+negative；文风 sample；文笔 banned/tic | ⚠️ 非全概念一等字段 | 信封新增 `example`(正例) 与 `negative_example` 并列，六概念统一 |
| **原始文字** | `evidence` 只读、永不进提示词＋原文闸 | ✅ | 结构化 `evidence_json{quotes[{loc,text}],task_ref}`（§0） |

## 0. 公共信封（所有知识共用，`kb_entries` 行）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | str | 条目 id |
| `user_id` | str | 账号级，不挂书 |
| `genre` | str | 主题材，词表＝**21 类 ＋ `""` 通用**（`仙侠/修真`…；`""`＝跨题材通用，P0） |
| `concept` | str | L1 概念之一：`文风/文笔/世界设定/角色设定/手法/情节` |
| `concept_id` | str | 叶子子概念 id（`kb_concepts` 行，如 `s:仙侠:手法:打斗`） |
| `title` | str ≤40 | 名字（“冷峻的叙事身份”），列表/图上显示 |
| `payload_json` | json | **本概念的内容**，schema 见 §1–§6 |
| `payload_version` | int | payload schema 版本，当前 1 |
| `instruction` | str ≤240 | 生成用指令（长度闸：句末断，断不出不收） |
| `example` | str ≤500 | **正例**（示范段/范文句，过原文闸；文风 `slot=sample` 即此字段的概念内形态） |
| `negative_example` | str ≤200 | **反例**（“不要这样写”；文笔的 banned/tic 是它的概念内形态） |
| `when_json` | json | 适用条件 `{scene,emotion,chapter_pos}`。**手法必填；文风/文笔带它＝场景条目（逐章挑），不带＝基线（快照）**；世界/角色必须为空（带了拒收） |
| `scope` | 派生 | `base`(when_json 空) / `scene`(非空)——**读时由 when_json 推导，不落库**；列表、库页、同步预览都用它分组 |
| `evidence` | str | 证据展示串（章号＋原文摘录），**只读，永不进提示词** |
| `evidence_json` | json | `{quotes:[{loc,text}], task_ref}`——原始文字的结构化形态，与 `src_ref` 关联到拆书任务产物 |
| `status` | `active/archived` | |
| `rev` | int | 内容版本，同步差异用它 |
| `src_kind` | `deconstruct/manual/distill/seed` | 来源四通道 |
| `src_ref` / `src_key` / `src_novel_name` | str | 幂等键 `(user_id, src_ref, src_key)`；`src_key` 如 `techniques:0`、`style.role` |
| `created_at/updated_at` | ts | |

**payload 通用约束**：所有字符串字段进库前 `strip`；空串存 null 不存 `""`；未知键拒绝（Pydantic `extra="forbid"`）；`payload_version` 升级走迁移函数不改旧数据。

---

## 0b. 场景条目与三级知识（10-31）

文风/文笔的知识分**两个正交维度**，都由字段值决定，不需要新表：

```
维度一：题材归属   genre ∈ {"", 21 类}        （""＝通用）
维度二：生效方式   scope ∈ {base, scene}       （when_json 空/非空）
```

**三级×两级矩阵（同槽多条时的优先级，高→低）**：

| 优先级 | genre | scope | 例 |
|---|---|---|---|
| 1 | 题材 | scene | 仙侠·打斗文风（句长≤12、动词连用） |
| 2 | `""` | scene | 通用打斗文风（短句压节奏） |
| 3 | 题材 | base | 仙侠基线（冷眼旁观的记录者） |
| 4 | `""` | base | 通用基线（少形容词） |

- **基线（base）**：启用库时快照进 `style`，书级恒定；同步预览只处理基线。
- **场景（scene）**：不进快照；写章时与手法走同一选择器进 user 块。配额：手法 ≤6 ＋ 场面写法 ≤4，动态块 ≤2K tokens。
- **合并规则**：基线在前、场景在后；列表槽（rules/craft/banned/tic/samples）拼接去重；单值槽（`role/pov`）只来自基线——场景条目声明 `role/pov` 直接拒收（§8 闸）。
- 打分＝匹配度 × 有用率（`kb_prefs`）× 新鲜度（`last_used_at` 距今），与手法同公式；`kb_match_runs/items` 的 `clause` 增加 `scene_style` 类别，留痕不分家。
- **同槽冲突策略**：`rule/craft/tic` 基线与场景同时命中 → **场景覆盖基线**（组装器丢基线那条）；`sample/banned_word` 追加。多场面章取主导场面（＋1 次要，配额减半）。
- **scene/emotion 封闭词表＋别名**（`kb/concepts.py` 注册）：打斗{交手/出招/追逃}、文戏{对话/日常/感情}…——`when_json.scene` 只能取词表值，章纲文本经别名表归类，不新跑模型。
- **重试确定性**：同 `chapter_id+brief_hash` 复用 `kb_match_run`，新鲜度只算首次。

## 1. 文风（这本书的声音）→ `style.role / style_samples / few_shot_examples`

一条文风知识＝**一个声音侧面**。消费：快照进本书 `style`（启用库同步时落）。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `slot` | enum | ✓ | `role`(叙事身份,单值) / `tone`(基调) / `pov`(视角) / `register`(语言口径) / `sample`(示范段) |
| `role` | str ≤120 | slot=role 时✓ | 一句身份：“冷眼旁观的说书人，只记录不评判” |
| `text` | str ≤500 | slot=tone/pov/register 时✓ | 该侧面的一句话描述 |
| `sample` | str ≤500 | slot=sample 时✓ | 成段示范（原文改写后，过原文闸） |
| `sample_note` | str ≤80 | | 示范段注（“打斗开场的声音”） |

**基线 vs 场景（10-31）**：不带 `when_json` ＝ 基线条目（启用库时快照进 `style`，逐章一致）；带 `when_json` ＝ 场景条目（逐章挑进 user 块）。**场景条目只许 `tone/register/sample` 三槽——`role/pov` 是书级恒定，场面不许改**；文笔四槽全开放为场景条目。

**渲染映射（基线）**：`slot=role` → `style.role`（**单值槽**：多条必须选一条，同步预览标冲突）；`slot=sample` → `style.style_samples[]`（≤6 条，取前 3 注入）；`tone/pov/register` → 拼进 `role` 后缀说明（P0 简化）。
**渲染映射（场景条目）**：`build_scene_style_block()` 挑选后追加在基线之后——`sample` 进“本章写法块”的示范位、`tone/register/rule/craft/banned/tic` 进写法指引；列表槽拼接去重，`role/pov` 永不被场景条目覆盖。

```json
{ "slot": "role", "role": "冷眼旁观的记录者，只报事实不下判断" }
{ "slot": "sample", "sample": "剑停在半寸。血先到，声音后到。", "sample_note": "出手瞬间" }
```

## 2. 文笔（句子怎么写）→ `style.rules / craft / banned_words / tic_patterns`

一条文笔知识＝**一条句法规则/手法/禁令**。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `slot` | enum | ✓ | `rule`(硬约束) / `craft`(描写手法) / `banned_word`(禁用词) / `tic`(禁用句式) |
| `rule` | str ≤160 | slot=rule 时✓ | “一句不超过 22 字，段落不超过 4 句” |
| `craft` | str ≤160 | slot=craft 时✓ | “打斗只写三个感官：听声、看影、数呼吸” |
| `banned` | str ≤50 | slot=banned_word 时✓ | 禁用的词：“仿佛” |
| `banned_alt` | str ≤50 | | 替代建议：“改成直接比喻或删掉” |
| `tic_pattern` | str ≤200 | slot=tic 时✓ | 禁用句式（正则/描述）：“不是…而是…”连用两句以上 |
| `tic_severity` | enum | | `high/medium/low`（对齐 `_TIC_SEVERITIES`） |

**渲染映射**：`rule`→`style.rules[]`（≤100）；`craft`→`style.craft[]`（≤50）；`banned_word`→`banned_words[]`（≤100，词≤50 字）；`tic`→`tic_patterns[]`（≤20，`{pattern, severity}`）。全部列表型——**同 slot 多条都保留**，不互斥。**带 `when_json` 的文笔条目＝场景条目**（“打斗：一句≤12字”只在打斗章进 user 块），基线与场景同槽叠加去重。

## 3. 世界设定（舞台与规则）→ `world` V2 8 键

一条世界知识＝**一个分区的一条事实**。消费：快照进本书 `world` KV。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `part` | enum | ✓ | `stage`(舞台) / `power`(力量) / `cost`(代价) / `factions`(势力) / `history`(历史) / `extra`(细节) / `constraint`(铁律) |
| `content` | str ≤300 | ✓ | 该分区一条内容；`factions` 用“势力名：一句话” |
| `hard` | bool | part=constraint | 是否硬铁律（手法 `depends_on` 它） |

**渲染映射**：`part` 即 `V2_KEYS` 键（`stage/power/cost/history/factions/extra`），同分区多条按 `sort` 拼接；`constraint` → `world.constraints[]` **逐条渲染不合并**。`no_power` 不开放录入（建书流程产物）。

## 4. 角色设定（人物的造法）→ 角色卡档案格（起草型）

一条角色知识＝**一个可复用的原型/造法**，不是某个具体角色（那是角色库的事）。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `archetype` | str ≤40 | ✓ | 原型名：“落魄天才”“笑面反派”“寒门谋士” |
| `dossier` | obj | | 档案格（键＝角色卡真实格）：`look`(外貌) / `background`(来历) / `speech`(说话方式)，各 ≤200 |
| `cog` | obj | | 认知格：`w1`(世界观) / `s1`(自我) / `v1`(价值观)，各 ≤120 |
| `relation_slot` | str ≤80 | | 关系位置：“站在主角对面的旧识” |
| `arc` | str ≤160 | | 弧光一句话：“从藏到争，代价是右手” |

**渲染映射**：`render_character_prototype()` 把 `dossier/cog` **逐格复制**进新建角色表单（作家可改），不写正文；“复制落卡”后记录用了哪个原型。字段名对齐角色卡 v2（`dossier.look/background/speech`、`cog.w1/s1/v1`）。

## 5. 手法（场景打法）→ 章级 user 提示词（实时型）

一条手法＝**一个可挑选的打法**，每章生成前现挑。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `instruction` | str ≤240 | ✓ | 生成用指令：“先给果再补因：第一句就写结果” |
| `negative` | str ≤200 | | 反面：“不要按时间顺序铺陈” |
| `scene` | enum | ✓ | `打斗/文戏/开篇/转折/收尾/对峙/日常` |
| `emotion` | enum | | `燃/冷/虐/甜/疑/静`（可空） |
| `steps` | list[str] | | 步骤（≤5 步各 ≤60 字），打斗类常用 |

**`when_json`（信封字段，手法专用）**：`{"scene":"打斗","emotion":"燃","chapter_pos":"开头"}`——匹配引擎按场面/情绪/位置挑，`kb_match_runs/items` 记每次清单与“有用/没用”。**渲染映射**：`build_technique_block()` 拼进 user 提示词末尾、收尾行之前；不落任何书内设定。

## 6. 情节（结构套路，P1）

| 字段 | 类型 | 说明 |
|---|---|---|
| `steps` | list[str] | 套路步骤（“被轻视→藏拙→遇宿敌→扬名”） |
| `payoff` | str | 爽点/钩子 |
| `volume_pos` | enum | 卷位（开卷/中段/卷末） |
| `pacing` | str | 节奏（“三快一慢”） |

消费：剧情抽卡/推演起草（P1，本期只保留分类与派生位）。

---

## 7. 关系、标签、库（围绕条目的三张薄表）

- **`kb_relations`**：`from_id/to_id`（`concept:*` 或 `entry:*`）＋`rel_type`（六类白名单）＋`source(ai/seed)`＋`confidence`＋`status`＋`run_id`＋`evidence`。AI 整理只写这张表，**永不写条目**。
- **`kb_entry_tags`**：`(entry_id, dim, value)`，dim ∈ `concept/genre/scope/scene/emotion/chapter_pos/slot/tag`——写入时同事务重建（**when_json 与 scope 也物化进 tag**，因为 SQLite 不能索引 JSON 路径）。**选择器只查 tag 不查 JSON**：`scene=打斗` 走 `(user_id, dim, value)` 索引出候选短名单，再回表读 payload 打分——两段式，目标 <50ms。
- **`kb_libraries / kb_library_items`**：库＝`{genre, concept, name, purpose, contract, rule_json}`；items 是 join。**默认库两组**（10-31）：`题材×概念`（`genre=X`）与 **`通用×概念`**（`genre=""`，如“通用文风库”）——都 `rule_json={"kind":"auto_all"}`，首个条目入库时自动生成；**场景条目也在所属库里**（靠 `scope` 分组展示，不单独立库）。**场景库**（如“打斗文风库”）＝谓词含 when 条件的库，`rule_json={"kind":"field", "when":{"scene":"打斗"}}`，P1。手动圈选 P1。

## 8. 校验闸门（入库时，全部在后端）

1. `concept` 六选一；`genre` 21 目录之一或 `""`；`concept_id` 必须存在且属于该 genre 的概念树。
2. payload 按本文字段表 Pydantic 强校验（`extra="forbid"`），slot 与字段一致性（`slot=role` 必有 `role`，`slot=sample` 必有 `sample`）。**场景条目闸**：文风场景条目 `slot ∈ {tone,register,sample}`（带 when_json 却声明 role/pov → 拒收）。
3. 长度闸：`instruction ≤240` 且句末断；示范段 ≤500；禁用词 ≤50。
4. 原文闸：`sample/craft` 与拆书原文比对，连续 ≥20 字逐字相同 → 标记待改写，默认不收。
5. 幂等：`(user_id, src_ref, src_key)` 唯一，重复导入跳过不更新。
6. **when_json 概念白名单**：只允许 手法/文风/文笔 非空；世界/角色带 when_json → 拒收（事实与造法没有“只在某场面成立”）。
7. **快照只取基线**：`kb_book_bindings.snapshot_json` 只序列化 `scope=base` 的成员；场景条目变更不触发“库有更新”的差异预览（它逐章挑，不存在同步语义），只在库页显示“场景条目 N 条”。

## 9. 一个完整例子（拆书一条手法）

```json
// kb_entries 行
{
  "id": "kb_01H...", "user_id": "u_123", "genre": "仙侠/修真", "concept": "手法",
  "concept_id": "s:仙侠:手法:打斗", "title": "先果后因",
  "payload_json": {
    "instruction": "先给果再补因：第一句直接写结果，第二句起补动作",
    "negative": "不要按时间顺序从起手写起",
    "scene": "打斗", "emotion": "燃", "steps": ["结果一句", "回补半拍", "再推一层"]
  },
  "payload_version": 1,
  "instruction": "先给果再补因：第一句直接写结果，第二句起补动作",
  "when_json": { "scene": "打斗", "emotion": "燃" },
  "evidence": "《剑照山河》第 14 章：断剑先落地，出招后补。",
  "src_kind": "deconstruct", "src_ref": "task_79baac22", "src_key": "techniques:0",
  "src_novel_name": "剑照山河", "status": "active", "rev": 1
}
```

## 9b. 角色库迁移到知识库（10-31 拍板方向）

**定位**：角色库不是独立系统，是知识库在"角色"维度的投影。知识库是通用底座，角色库/手法库/文风库等都是它的视图。

### 现状

| 表 | 内容 | 问题 |
|---|---|---|
| `character_library` | 跨书角色成品（name/aliases/role/genre/kind/persona/dossier 8格/cog 11格/legacy/avatar/relations） | 独立系统，与 kb_entries 数据分裂 |
| `kb_entries`（角色设定） | 角色的造法/原型（archetype/dossier 3格/cog 3格/arc） | 载荷太窄，承接不了角色库的全量字段 |

### 迁移策略：三步

**第一步：扩 payload schema（本 PR 或下一个 PR）**

CharacterPayload 从 9 字段扩到覆盖角色库全量字段：
```python
class CharacterPayload(BaseModel):
    model_config = {"extra": "forbid"}
    archetype: str = Field(..., max_length=40)
    # dossier 全 8 格（对齐 characters 表 dossier JSON 键名）
    gender: Optional[str] = Field(None, max_length=20)
    age: Optional[str] = Field(None, max_length=20)
    race: Optional[str] = Field(None, max_length=20)
    faction: Optional[str] = Field(None, max_length=40)
    look: Optional[str] = Field(None, max_length=200)
    speech: Optional[str] = Field(None, max_length=200)
    background: Optional[str] = Field(None, max_length=200)
    plot: Optional[str] = Field(None, max_length=200)
    # cog 11 格（对齐 characters 表 cog JSON 键名）
    w1: Optional[str] = Field(None, max_length=120)   # 世界观
    w5: Optional[str] = Field(None, max_length=120)
    s1: Optional[str] = Field(None, max_length=120)   # 自我
    s5: Optional[str] = Field(None, max_length=120)
    v1: Optional[str] = Field(None, max_length=120)   # 价值观
    p2: Optional[str] = Field(None, max_length=120)   # 能力
    p6: Optional[str] = Field(None, max_length=120)   # 技能
    p3: Optional[str] = Field(None, max_length=120)
    p4: Optional[str] = Field(None, max_length=120)
    b1: Optional[str] = Field(None, max_length=120)
    e3: Optional[str] = Field(None, max_length=120)   # 环境
    persona: Optional[str] = Field(None, max_length=300)
    relation_slot: Optional[str] = Field(None, max_length=80)
    arc: Optional[str] = Field(None, max_length=160)
```

**第二步：迁移脚本（一次性，幂等）**

```
读取 character_library 全量行 →
  每行创建 kb_entry：
    concept = "角色设定"
    genre = 行.genre（映射到 21 类目录）
    title = 行.name
    payload = {archetype: 行.name, look: ..., background: ..., cog 各格...}
    src_kind = "character_library_migration"
    src_ref = "character_library"
    src_key = 行.id
  角色关系 → kb_relations（rel_type="related_to"，两端=条目 id）
  头像 → 前端头像存储（不进 kb_entries）
  手录来源标 manual
```

**第三步：角色库 UI 改读知识库**

- 角色库列表页 → 读 `kb_entries WHERE concept='角色设定'`
- 角色卡编辑器 → 读写 kb_entry payload
- 角色关系 → 读 kb_relations
- 角色库特有功能（头像管理/来源追踪/卡片导出）保留，数据源换
- `character_library` 表标记 deprecated，不再写入

### 迁移的边界

| 角色库特有 | 迁移策略 |
|---|---|
| 头像（url/thumb_url） | 保留独立存储，kb_entry 加 `avatar_url` 字段引用（不存二进制） |
| 角色关系（character_relations） | 迁移到 kb_relations（rel_type="related_to"） |
| legacy 原文（possessions/experiences/等） | 不迁移——标记为"只存不读不上界面不进 AI"，留 character_library 不动 |
| 卡片导出/分享 | 走知识库导出（P1） |

### 为什么不一起做

角色库迁移是**独立变更**（c-kb-character-migration），不影响批1（底座＋浏览）的范围。原因是：
1. 角色库有独立的 spec（`openspec/specs/character-library/`）、独立的 UI 和消费链（书内挑原型、卡编辑器、导出）
2. 迁移需要扩 CharacterPayload schema＋写迁移脚本＋改 UI 数据源，工作量与批1 相当
3. kb_entries 的角色设定概念已经预留了字段空间，迁移不会破坏批1 的架构

**时机**：批1 合入后、角色库下一个迭代周期时做。不是本变更的事。

## 10. 本体约束（关系元数据 · 概念解读三件套）

### 10.1 关系元数据（六类，注册进 `kb/concepts.py`，AI 整理与前端共用）

| rel_type | 定义域 → 值域 | 逆关系 | 函数性 | 例子 |
|---|---|---|---|---|
| `implements` | 概念 → 概念 | `implemented_by` | 一个源可多目标 | 文笔 implements 文风 |
| `depends_on` | 概念/条目 → 概念/条目 | `supports` | — | 手法 depends_on 世界铁律 |
| `applies_to` | 手法(概念/条目) → 文笔(概念/条目) | `applied_by` | — | 先果后因 applies_to 打斗描写 |
| `uses` | 情节(概念/条目) → 手法(概念/条目) | `used_by` | — | 擂台扬名 uses 先果后因 |
| `refines` | 条目 → 条目(同概念) | `refined_from` | 函数（一条至多一条来源） | 示范段 refines 叙事身份 |
| `related_to` | 任意 | 自逆（对称） | — | 都市冷硬 参照 仙侠冷峻 |

**硬约束**：端点必须是存在的 `concept:*`/`entry:*`；无自环；`hierarchy(parent_of)` 是树（无环、单亲）；同一 `(from,to,rel_type)` 只一条 active；逆关系不自动落库（读时推导），避免双写漂移。条目→概念的 `instance_of` 不入关系表——由 `kb_entries.concept/concept_id` 隐式承担，读时展开。

### 10.2 概念解读三件套（每个概念/子概念标配）

`kb_concepts` 增加（种子维护，作家只读）：

| 字段 | 说明 |
|---|---|
| `definition` | 一句话解读（**子概念也必填**，如“打斗＝冲突落到身体与物件上的场面”） |
| `aliases` | 同义词列表（“打斗/交手/出招”），供拆书映射与搜索归一 |
| `interp_json` | `{positive_ref, negative_ref}`——该概念的**标准正例/反例各指向一条条目**（种子内置，图/详情页“这个概念长什么样/什么叫跑偏”直达） |

概念详情页因此固定四块：**名词与定义 → 属性 schema → 关系（含逆）→ 正反例**；条目级正反例由信封 `example/negative_example` 承担（§0）。原始文字（`evidence_json.quotes`）只在条目侧，作为正例的出处回链。

## 11. 场景条目完整示例（仙侠·打斗·文笔）

```json
{
  "id": "kb_01H...DUEL", "user_id": "u_123", "genre": "仙侠/修真", "concept": "文笔",
  "concept_id": "s:仙侠:文笔:句式", "title": "打斗句长压到 12 字",
  "payload_json": {
    "slot": "rule",
    "rule": "打斗段落一句不超过 12 字，连续动词不超过两个"
  },
  "payload_version": 1,
  "instruction": "打斗段落一句不超过 12 字，连续动词不超过两个",
  "negative_example": "不要出现三个以上连续动作塞进一句的长句",
  "when_json": { "scene": "打斗", "chapter_pos": "any" },
  "evidence": "《剑照山河》第 14 章连打三段，最长句 11 字。",
  "evidence_json": { "quotes": [{ "loc": "第14章", "text": "剑出，血溅，人退半步。" }], "task_ref": "task_79baac22" },
  "src_kind": "deconstruct", "src_ref": "task_79baac22", "src_key": "style.rules:3",
  "status": "active", "rev": 1
}
// scope=scene（when_json 非空）→ 不进快照；写打斗章时选择器命中进 user 写法块
```

## 12. 容量与扩展性（类型 × 条目 · 10-31 评估）

### 12.1 知识类型扩展：加类型＝零迁移

结构上**类型不是表，是注册表项**。新增一个知识类型四件套，全部代码侧，不动 DDL、不动备份段：

| 件 | 落点 |
|---|---|
| 概念注册 | `kb/concepts.py`：{schema, relations, quality_rules, renderer, contract} |
| payload 字段表 | 本文档新增一节（Pydantic 模型，`extra="forbid"`） |
| 渲染器 | 消费端键映射（如情节→抽卡草稿） |
| 消费契约 | live/snapshot/draft 三选一＋注入位 |

- `kb_entries` 单表＋`payload_json`＋`payload_version`：新类型旧类型互不影响；旧类型改字段走 `payload_version` 迁移函数。
- 门槛不变：**没有消费链的类型不进注册表**（§12 风险表既有规则），防止类型膨胀成表单集。
- 作家自定义类型永不做（概念是本体，开发者维护）；作家能加的是**子概念**（kb_concepts P1），同样是行不是表。

### 12.2 条目量级：单表＋tag 索引扛到 10 万级

| 账号条目量 | 判定 | 手段 |
|---|---|---|
| 1 千（正常） | 无感 | 全表都行 |
| 1 万（重度拆书） | ✅ | `(user_id,genre,concept,concept_id,status)` 索引＋FTS5＋tag 索引 |
| 10 万（极端） | ✅ 需守三条 | ①列表全部走索引前缀＋keyset 分页（不做深 offset）；②搜索只走 FTS/tag（LIKE 仅兜底）；③**选择器两段式**：tag 短名单（≤200 条）→内存打分，不整表 join `kb_prefs`（prefs 只对短名单查） |
| 50 万+ | P2 再议 | 届时按 `genre` 分区表或迁 PG；P0/P1 不为它设计 |

体积估算：条目均 <1KB，10 万条 ≈ 100MB 库——SQLite 无压力；**注意配置包备份体积**（账号级全量进包），P1 给“备份含/不含知识库”开关。

### 12.3 周边表的保险丝

- `kb_relations`：AI 整理有阈值（≥0.75 才 active），再挂硬上限 **active 关系 ≤ 5× 条目数**；超了按置信度淘汰最旧的——防关系表比条目表还大。
- `kb_match_runs/items`：**每章每 brief_hash 只留一个 run**（重试复用），随书级联删除；不设保留窗口之外的堆积。
- `kb_entry_tags`：纯物化索引，任何时刻可 `DELETE + 重建`（损坏自愈），不参与备份必要性判断（恢复后重建）。
