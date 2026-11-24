## Context

见 proposal.md 的 Why。现状约束：

- 字段级写只有两条通道：`write_chapter_fields` 与 `write_settings_field`（均带 `preview_builder`），授权卡字段行由 preview 的 `label` 提供，写核在批准后才执行。
- 页面侧已有契约模型：世界 `settings/world_model.WorldIn`、题材 `genres/novel_genre_service.NovelGenreIn`、章纲 `chapters/schemas.validate_chapter_fields`＋`store.save_chapter` 的 patch-gates。
- preview 与写核目前各写一套判断：preview 只查字段名/长度，写核才跑契约；世界写核完全不跑 WorldIn，直接 `str(value)` 落库。
- 章纲 patch 由 `_chapter_data_for` 逐字段生成嵌套族 dict，再用 `dict.update` 浅合并。

## Goals / Non-Goals

**Goals:**

- 授权卡能显示的字段写，批准后一定能落库（preview 与写核同源校验）。
- 字段类型/形状与页面契约一致：世界布尔与条目数组、章纲多字段同族合并、题材列表/数值形状。
- 卡面字段名与页面小标题一致；世界值按页面口径显示。

**Non-Goals:**

- 不新增/修改页面写接口契约（WorldIn/NovelGenreIn/save_chapter 均复用）。
- 不迁移历史上已被字符串化写坏的世界 KV（读侧 normalize 已将其视为空；本次只保证后续写入不再产生）。
- 不改授权档位、hard-floor、write_log/撤销机制。

## Decisions

### D1：preview 与写核共用契约校验，不复制形状逻辑

- 世界：新增 caps 层 `validate_world_field_patch(raw, field, value) -> merged`，内部按字段规范化后用 `WorldIn.model_validate(merged)`；preview 与写核都调用。
- 题材：新增 caps 层 helper（读现卡 → `{**card, field: value}` → `NovelGenreIn.model_validate`）；preview 与写核都调用。
- 章纲：把写核里的「逐字段 `_chapter_data_for` + `validate_chapter_fields` + 族合并」抽成 `build_chapter_patch(fields)`，preview 只校验、写核拿合并结果落库。
- 备选：在 preview 里再写一套形状判断——已证明会漂移（本次世界/章纲就是两套口径），否决。

### D2：世界值保留原生类型，边界做小范围宽松

- `no_power`：接受 JSON bool；字符串只接受 `开/关/true/false/1/0`（忽略大小写），其余 → 人话错误。存布尔。
- `history/factions/constraints/extra`：接受条目数组；元素可为 dict（key/value 或 name/note）或字符串（映射为 key/name、内容为空）；非数组 → 人话错误。存数组。
- 文本格（stage/power/cost）：仍按文本处理。
- 合法性最终以 `WorldIn` 为准（长度/条数/重复名目等），错误统一转人话 `CapabilityError`。

### D3：章纲 patch 按族深合并

- 新增 `_merge_patch(data, probe)`：`outline`/`memo`/`emotional_design` 三个 dict 族逐子键合并，顶层标量直接覆盖；保证同族多字段（summary+characters、required_changes+prohibitions）全部进入 patch。
- 备选：改 `_chapter_data_for` 返回扁平键——违反 save_chapter 的族契约，否决。

### D4：preview 的展示口径与写值分离

- preview 的 `before/after` 是**展示值**：世界 `no_power` → 「开/关」；条目数组 → 「名目：内容；…」一行；章纲/题材沿用现文本。
- 写核仍用原始值；write_log 的 previous/after 不受展示格式影响。
- 备选：让前端 GatePreviewField 识别结构并渲染——需前端改动且授权卡组件与业务字段耦合，否决。

### D5：标签单一源

- 章纲字段名表改为页面小标题（章纲概要/禁止事项/剧情），工具参数说明从同一表派生或同步。
- 世界沿用 `SETTINGS_FIELD_WRITE` 的页面文案；`no_power` 的展示由 D4 负责。

### D6：页面字段说明书作为「作家说法 → 字段键」的桥

- 新增 `assistant/page_schema.py`：按页面声明 `FieldMeta`（key/页面名/类型/上限/写入口/别名），标签复用 `SETTINGS_FIELD_WRITE` / `CHAPTER_FIELD_WRITE_KEYS`，不另抄一份。
- 新增零参数只读工具 `read_page_schema`，由 `ctx.thread` 决定页面；覆盖 set:genre/intro/world、ch:og、vol；其他页面返回「本页没有字段级写入口」。
- 写工具说明与页签纪律都指向它（先读说明书找键，再按写入口写）；匹配仍靠模型语义判断，不唯一时问一句。
- 备选：把元数据塞进 `read_page_fields`——现值与静态说明混在一起，模型容易把「现值」当字段定义；分开更清晰。

### D7：02 标签退出 agent 字段写（2026-11-24 拍板）

- `core_promise` 是给作家省字的短标签，页面不设独立输入框；agent 字段写白名单拆为
  `SETTINGS_FIELD_AGENT_WRITE`（= `SETTINGS_FIELD_WRITE` 去掉 `core_promise`）。
- 写核/preview 对 `core_promise` 统一返回人话拒绝（标签走出爽点采纳卡，主句写
  `promise_note`）；工具 enum 不含它；`read_page_fields`/`read_page_schema` 仍展示
  标签现值与「不直接写」的写入口。
- 备选：保留可写 + 卡面标「标签」——短句仍可能进标签槽，拍板选确定性。

### D8：review 整改（2026-11-24）

- **旧叫法不挂标签**：`核心承诺` 历史上指 02 主字段，不作为 `core_promise` 别名（否则又把人指向标签）；匹配不唯一时按规则问一句。
- **读值逐格**：`read_chapter` 按章纲字段表逐格人话（memo/情绪/剧情条目全部出现，不再 `str(outline)` repr）；`read_outline` 卷纲按卷纲字段表逐格（补上卷名/章数目标）。
- **卷纲 preview**：`write_volume_fields` 补 `preview_builder`，按页面名呈现字段前后，并与 `VolumeUpdate` 同源校验。
- **拒绝语收口**：非法字段文案只列 `SETTINGS_FIELD_AGENT_WRITE`（不再把 `core_promise` 说成可写）。

## Risks / Trade-offs

- [世界写行为收紧：以前「看似成功」的字符串列表写会改为报错] → 报错文案给出可用形状与页面字段名；不静默吞。
- [preview 增加一次全量卡/世界文档读取] → 均为单书本地读写，授权卡本就读现值，开销可忽略。
- [模型仍可能传奇怪形状] → 统一在 preview 前拦下并回喂人话理由，最多多一轮重试，不产生空头卡。
- [历史脏值无法恢复] → 已丢失的数据不再尝试猜测重建；读侧继续按空处理，非目标。

## Migration Plan

- 无数据迁移/DDL。上线即生效；回滚按代码回退，已写入的正确形态数据不受影响。
- 旧版本写入的字符串形态世界 KV 保持现状（读侧 normalize 视为空），不做自动修复。
