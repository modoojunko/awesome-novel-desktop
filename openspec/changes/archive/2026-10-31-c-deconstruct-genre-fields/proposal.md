## Why

真机验收 v0.44.2 时，新书设定页顶部出现提示：

> 题材 core_promise、forbidden、cost_ratio、battlefield 拆书产物未覆盖，已按题材/主线/世界代价给起点（请在设定页确认）

查下来是两件事叠在一起：

1. **拆书根本没产出这四格**：`deconstruct_genre.prompt` 的输出契约只有
   `genre / tags / promise / confidence / note`（真跑产物 `products_json.genre.data` 的键就这五个）。
   书内题材面板要的是 `core_promise / promise_note / forbidden_list / cost_ratio / battlefield`
   五格，其中禁写清单/代价比例/战场三项在 prompts 仓里只有**设定页 AI 起草**用的模板，
   拆书链从未接过。
2. **核心承诺是假缺失**：拆书给的 `promise`（200 字「…都市夜班公交…解密快感」）被映射到
   `promise_note`，而 `core_promise` 那格读的是 `dg.get("core_promise")`（模板从不输出这个键）
   → 读不到 → 又按关键词猜了一句「层层反转的智力快感」，并报「未覆盖」。

C 端兼容层其实早就为这四格准备好了（`deconstruct/settings_map.py:genre_extras` 注释：
「优先取产物新字段；旧产物没有时给可编辑起点」；`apply.import_book` 也已按
`forbidden:/battlefield:` 词表 id 写入关联表）。**缺的是拆书模板这一侧**，所以修法落在提示词契约，
C 端只需要补一处词表注入和一处回退。

同时这句提示本身两处不合规：印了数据库键名（违反 design-language §13「界面不出现内部术语」），
且把「假缺失」和「真推断」混在一句里报给作家。

## What Changes

- **拆书题材维度补齐五格**：`deconstruct_genre.prompt` 输出契约由 5 键扩到
  `core_promise / promise_note / forbidden / cost_ratio / battlefield / genre / tags / confidence / note`，
  沿用既有三铁律（硬事实回指章号、标 confidence、原文没写的标「原文未明确」）。
  `core_promise` ≤60 字短句，`promise_note` ≤200 字说明，`forbidden` ≤6 条、`battlefield` ≤2 条
  **必须从注入的词表里选**，`cost_ratio` 为 1–10 整数并给依据。
- **C 端注入禁写/战场词表**：维度调用是通用的（`pipeline.py` 的占位符 dict），现在只注入
  `{genre_vocab}`（题材名）；补 `{forbidden_vocab}` / `{battlefield_vocab}`（取
  `genres.vocab_presets.VOCAB_PRESETS` 对应 kind）。其他维度模板没有这两个占位符，注入不影响它们。
- **核心承诺回退**：`genre_extras` 的 `core_promise` 读不到时回退读旧字段 `promise`
  （按 60 字收口），旧任务/旧包产物也能拿到真值，不再白猜。
- **建书提示改为如实且人话**：只报**真正推断**的项，用中文标签（核心承诺／禁写清单／代价比例／战场），
  文案说明「按题材与主线推的起点，请去设定 → 题材核对」；SHALL NOT 出现数据库键名。
- **词表外的值走自定义文本**：模型给了词表外标签时按 `custom_text` 落（现成路径），不硬塞 vocab id。
- 不新增模型调用：题材维度仍是「每批归并一次」，只是单次输出变长；超预算走既有的截断拆半兜底。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `deconstruct-book`：
  - 「十维度拆解管线与断点续拆」：题材维度的产物契约扩为九键（含四格题材设定字段），
    并新增禁写/战场词表注入。
  - 「建书逐字段回填与旧产物兼容」：`core_promise` 允许回退旧字段 `promise`；
    推断提示改为只报真推断项 + 中文标签。
- 提示词模板本体住在 prompts 仓（`awesome-novel-prompts`），不在本仓；本 change 的 spec 只约束
  「产物契约与消费行为」，模板改动与发包在 prompts 仓按自己的流程走（本 change 记录契约要求与验收）。

## Design Impact

- **受影响端**：仅 C端（拆书链 + 提示词模板）。
- **受影响屏**：无新增界面。变化体现在：新书设定页「题材」面板五格由「推断值」变成「拆书原文」；
  新书顶部提示条在四格都有真值时**不再出现**。
- **对象状态**：沿用既有 `notice`（warn）语气，不新增令牌/类名/胶囊形态。
- **共享段**：零改动。
- **原型先行**：不需要（无版式变化；提示条形态已在 `c-deconstruct-import-async` 的 drafts 里定过）。
- **设计工件产出**：实现侧自查。

## Impact

- **prompts 仓（`awesome-novel-prompts`）**：`prompts/deconstruct_genre.prompt` 输出契约扩字段；
  manifest 版本进位、`min_client` 判定、发包与灰度下发。
- **C 端**：`deconstruct/pipeline.py`（占位符 dict 补两个词表）、
  `deconstruct/settings_map.py`（`core_promise` 回退 `promise`；`inferred` 增加中文标签映射）、
  `deconstruct/apply.py`（提示文案拼装）。
- **数据**：零 schema 变更。存量任务不受影响（旧产物无新键 → 走回退 + 推断，提示如实标注）。
- **兼容**：旧客户端读新产物不受影响（`genre_extras` 早已优先读新键）；新客户端读旧产物走回退。
- **发包依赖**：C 端改动可独立发布（0.44.3 先修回退与文案）；**契约生效需 prompts 包下发**，
  两者解耦，互不阻塞。
