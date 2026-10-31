## Context

真机证据（v0.44.2，任务 `80284908…`《13路末班车》）：

- 题材产物 `products_json.genre.data` 的键＝`genre / tags / promise / confidence / note`（只有五个）。
- 书侧题材面板五格：`core_promise / promise_note / forbidden_list / cost_ratio / battlefield`
  （`novel_genre` + `novel_genre_forbidden` / `novel_genre_battlefield` 两张关联表）。
- 建书后 `core_promise`＝「层层反转的智力快感」（`_pick_label` 关键词猜的），
  `promise_note`＝产物 `promise` 全文（200 字那句），`cost_ratio`＝8（从世界 cost 推），
  禁写 2 条 / 战场 2 条（从规则表推）——即四格全是推断值。
- 提示词契约源在 prompts 仓 `prompts/deconstruct_genre.prompt`：
  「用途｜拆书·题材：主题材＋标签（≤5）＋核心承诺（标证据章节）」，输出契约只列
  `genre / tags / promise / confidence / note`。
- 消费侧早已为四格准备好：`deconstruct/settings_map.py:genre_extras` 注释
  「优先取产物新字段（core_promise/forbidden/cost_ratio/battlefield）；旧产物没有这些字段时
  给可编辑起点」；`apply.import_book` 已按 `forbidden:`/`battlefield:` 词表 id 写关联表，
  词表外落 `custom_text`。
- 维度调用是通用实现（`deconstruct/pipeline.py` `_run_dim` → `load_layers(f"deconstruct_{dim}")`
  + 固定占位符 dict：`book_name / genre_or_unknown / genre_vocab / full_synopsis / seg_range /
  excerpts`）；`{genre_vocab}` 由 `_genre_vocab_names()` 注入，只有题材名。
- 词表源：`genres/vocab_presets.py:VOCAB_PRESETS`（条目含 `kind`/`id`/`label`）；
  `settings_map.genre_vocab_id(label, kind)` 按 kind+label 取稳定 id。
- 提示词模板经签名包下发（本机 `data/prompt-pack/v2026.10.29-2/pack.bin`），模板改动不能随
  C 端发版走，必须发包。

## Goals / Non-Goals

**Goals:**

- 拆书题材维度一次产出书侧五格所需全部字段，建书不再靠猜。
- 旧产物/旧提示词包仍能取到核心承诺真值（回退 `promise`），不因契约升级而回归。
- 推断提示如实、面向作家：只说真推断的项、中文标签、无内部键名。
- 零 schema 变更；C 端改动可独立发布，不被发包阻塞。

**Non-Goals:**

- 不把设定页的 AI 起草（`settings_genre_*`）搬进建书链（多 3 次调用、且属 AI 起草需过目）。
- 不改 `cost_ratio` 的书侧校验（仍 1–10，越界 400 由 `put_novel_genre` 拦）。
- 不新增模型调用次数（题材维度仍每批一次归并，只是输出变长）。
- 不动其他维度的模板与占位符行为。

## Decisions

### D1 · 契约扩在 `deconstruct_genre`，而不是拆成新维度

题材四格是「题材定位」的延伸，另起维度会多一轮调用与一套状态账；扩字段只增输出 token。
`promise` 保留为 `promise_note` 的语义来源（≤200 字），新增 `core_promise`（≤60 字）做面板第一格，
两者同源不同粒度——避免把 200 字塞进 60 字格子后再被机械截断。

**否掉的替代**：建书时调 `settings_genre_*` 补三格（多 3 次调用、把分析与生成混在建书里、
按 AI 起草规矩还得加过目面）。

### D2 · 词表注入走通用占位符 dict

在 `_run_dim` 的占位符 dict 里补 `forbidden_vocab` / `battlefield_vocab`（按 `kind` 从
`VOCAB_PRESETS` 取 label 列表）。所有维度共用同一 dict，未声明这两个占位符的模板不受影响
（`str.format` 只替换模板里出现的占位符——需要确认 `load_layers` 的填充方式是否容忍多余键，
见风险）。

**否掉的替代**：给题材维度单开一条调用路径（破坏「维度通用」的现有结构，续拆/调用账/断点都要分叉）。

### D3 · `core_promise` 回退链：`core_promise → promise（60 字收口）→ 关键词推断`

回退放在 `genre_extras`（消费侧单点投影），这样旧任务、旧提示词包、以及发包未到达的客户端
都能拿到真值；推断退到最后，且只在真的没有时发生，`inferred` 记账随之准确。

### D4 · 提示文案与 `inferred` 分离：内部键留在数据层，展示层用中文标签

`genre_extras` 的 `inferred` 继续返回内部键（供测试与后续逻辑），另给一份
`inferred_labels`（核心承诺/承诺说明/禁写清单/代价比例/战场）；`apply.import_book` 拼提示时只用
labels，并按「按题材与主线推了起点，请去设定 → 题材核对」的作家口吻。

### D5 · 发包与 C 端解耦

C 端先发（回退 + 文案），prompts 包后发（契约扩字段）。两者互不阻塞：
- 旧包 + 新 C 端：`core_promise` 走回退，提示只报三项，行为正确；
- 新包 + 旧 C 端：`genre_extras` 本就优先读新键（该逻辑早于本次变更），新字段直接生效；
- 新包 + 新 C 端：四格全部来自拆书，提示条不出现。

## Risks / Trade-offs

- [占位符注入方式] `load_layers` 的 user 段若用 `str.format(**kwargs)`，多传键无害；若用严格模板
  校验（白名单）则需同步登记 → 实现前先读 `prompts` 加载器确认；不成立时改为只对题材维度传扩展 dict。
- [输出变长触发截断] 题材维度输出从 ~5 键扩到 9 键，长书单批可能撞 `merge_out_tokens`；既有
  「截断→拆半重试」兜底可用，但会多花调用。缓解：`core_promise`/`promise_note` 限长、`forbidden`
  ≤6、`battlefield` ≤2，并在模板里明令「只输出 JSON、不解释」。
- [词表过大抬高输入] 禁写/战场词表若各上百条会挤占输入预算。缓解：只注入 top N（如各 40 条）或按
  主题材过滤；实现时量一次 token。
- [模型不遵守词表] 给词表外标签 → 消费侧落 `custom_text`（现成路径），不硬塞 id，不报错。
- [发包节奏] prompts 包改动会影响**所有用户**的拆书输出，需按 prompts 仓流程走发布与灰度；
  C 端修复不必等它。
- [旧任务复验] 存量任务产物没有新键，重跑建书仍走推断并如实提示——这是预期，不是回归。

## Migration Plan

- 零 DB schema 变更；存量任务/存量书不受影响。
- C 端（回退 + 文案）→ 随下一个补丁版发布（0.44.3 形态）。
- prompts 契约 → prompts 仓 PR + 打包 + 灰度下发；下发后**新拆的任务**才带四格。
- 回滚：C 端回退逻辑对旧产物无副作用；prompts 包可回滚到上一版（拆书产物回到 5 键，C 端走回退）。
