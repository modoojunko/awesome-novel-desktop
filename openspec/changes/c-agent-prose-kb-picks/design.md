## Context

见 proposal.md「Why」。实现面需要对齐的现状：

- `kb_search_craft`（`assistant/tools_kb.py`）的候选域来自 `kb.match.digest_candidates`：`wanted = tech | style` 混池，style 组要求 `scope=scene`（全书级 `scope=base` 的文笔/文风不进）；基线 8197 条里文笔/文风 0 条 scene，style 组恒空。打分用 `_craft_terms`（CJK bigram）与剧情查询词求交，`overlap==0` 直接丢弃。
- `draft_prose_plan`（`assistant/tools_cards.py`）的 picks 只认 list：`picks = picks if isinstance(picks, list) else []`，字符串形态静默清空。
- 本书文风三区存于 `project_settings` 的 `style` 键（`ProjectSetting(root_path,key)`，JSON 文本）；`settings/style_kb.style_draft_from_kb` 已有「按题材取全书级文风/文笔」的只读取数（用户条目＋基线 merged、`when_json` 空、同题材优先），但返回的是 role/rules/craft/samples 聚合文本，丢失条目级标题与归属。
- 前端方案卡渲染（`Aui2Dock.tsx`）只消费 `picks`/`prompt`/`has_existing_prose` 等既有字段；本次不改前端。

## Goals / Non-Goals

**Goals：**
- picks 参数形态不再导致静默丢失；失败与空态对 agent/作家可见。
- `kb_search_craft` 返回结构按概念分桶，并解释「场面级文笔/文风为什么没有」。
- 本书文风三区为空时，编排能拿到知识库全书级文笔/文风的条目级草稿（名称＋写法短句），作为提示词参考素材。
- 工具描述与正文页纪律文案与实现一致。

**Non-Goals：**
- 不放开全书级文笔/文风进入写章写法块或 picks（保持 `prose-writing` 的「手法与场景定性文风/文笔」边界）。
- 不自动写 `style` KV、不新增端点、不改前端方案卡结构与文案。
- 不改基线数据（拆书产出 `when` 与存量回标由 `c-kb-scene-tagging` 负责）。
- 不改 write 链注入逻辑与 `digest_candidates` 的写块旧路行为。

## Decisions

### D1｜picks 剥壳放在 `_draft_prose_plan` 入口，失败即报错
`picks` 先做形态归一：`str` → `json.loads`（长度上限 8K 防滥用）→ 必须是 `list[dict]`；解析失败返回 `ToolResult(ok=False)` 并说明期望形态，不再降级为空数组。数组内条目沿用既有 `entry_id/id + reason` 归一与去重。

- 为什么不在提示词里要求「必须传数组」：本轮实锤模型会输出 JSON 字符串形态，纯靠提示词不可靠。
- 为什么不放 router 层：picks 的契约与解析在方案卡工具，放外层会让「卡上展示」与「实际注入」再次分叉。

### D2｜分桶在 `_kb_search_craft` 内做，不动 `digest_candidates`
先把候选行按 `concept` 分成 tech/style 两组，各自用现有 `_craft_terms` 打分（同一公式、同一 `overlap>0` 门槛），各自排序取 `limit`，summary 分段输出。style 段为空时按两种原因区分文案：候选域本身为空 / 域内只有全书级条目（读基线 `scope=base` 的文笔/文风计数）。

- 为什么不动 `digest_candidates`：它同时服务写块旧路 `select_block`，改返回结构会波及未启用的旧路径；分桶只是检索展示层行为。

### D3｜书级草稿走「条目级」只读，抽 `load_style_entries` 单一取数口径
在 `settings/style_kb.py` 抽出 `load_style_entries(db, user_id, theme)`：返回用户条目＋基线 merged 的条目列表（`concept ∈ 文风/文笔`、`when_json` 空、同题材优先、去重），`style_draft_from_kb` 改为调用它，产物契约不变。`assistant/tools_kb.py` 复用它取草稿：同题材优先，文风/文笔按概念交替取（各占一半，最多 6 条），**不按剧情词打分**——全书级声音不是本章场景条目，按剧情筛会挑出与基调撕裂的条目（真库抽检实锤：剧情词排序把「内心吐槽穿插」排到前排）。输出 `- [文风/文笔] 标题｜instruction`，段头声明「按题材列出，需按本书基调筛选；与基调撕裂的不选；不进 picks」。

- 为什么不直接调 `style_draft_from_kb`：它返回聚合文本，丢条目名与逐条归属，且 `role/rules/craft` 三区会把同一批条目切碎，无法按概念均衡展示。
- 为什么不新增端点：编排工具在同一进程内可直接读 DB；端点保持「文风面板专用」语义不变。
- 为什么不按剧情打分：实测选择质量差（书级草稿是「本书声音」候选，不是本章场景匹配）；剧情匹配留给真正的 scene 条目。

### D4｜三区空检测 fail-visible
工具内读 `ProjectSetting(root_path="...", key="style")` 的 JSON，`role/rules/craft/few_shot_examples` 全空即视为「未配置」；读取失败也按未配置处理并输出提示（不阻断检索）。三区已配置时不追加草稿段。

### D5｜可见化只走工具回执，不动前端契约
方案卡 `payload` 不加字段；「本书文风三区未配置」「picks 未带/id 无效」全部写在 `draft_prose_plan` 与 `kb_search_craft` 的 summary 里，由 agent 转述、作家在对话里看见。避免触发 UI 原型/像素门禁，也避免方案卡契约漂移。

### D6｜书级 vs 章级：编排阶段做「语义去重 + 剧情裁决」，不让正文模型临场选
书级三区作为上下文已在 `read_write_prompt` 的 system 基底里（`style_block`）；场景候选来自 `kb_search_craft`。编排 agent 在出方案卡前完成两步：

1. **语义去重**：场景条目与书级三区同义/近义（如「短句」vs「句子要短」）→ 只留更具体、更贴本章的一条，提示词里不出现两次。
2. **冲突裁决**：按本章剧情判断，判据顺序＝贴场面节奏 → 贴人物声线 → 念读顺口 → 不与书级基调撕裂（底线，宁可不用该条目）。结论写进 `picks.reason` 与「本次写法要求」，作者过目可改。

- 为什么不在 system 模板里改仲裁句：模板是书级恒定层，不带章级信息；把章级结论写进 user 层「本次写法要求」才是单源。模板现有的「本书文风优先」只针对人味缺省条款，不覆盖知识库场景条目。
- 为什么不交给正文模型：冲突双方同时出现在 prompt 里，模型会各写一半，最终两头不像；裁决必须在人过目的方案卡阶段完成。
- 作者章级文风影子（`style_shadow`）是作者显式值，高于自动裁决；该路径既有实现不动。

## Risks / Trade-offs

- [草稿被误当 picks] → 草稿段头显式写「非写章块条目、不进 picks」；工具描述同步；测试断言草稿条目 id 不出现在 picks 建议里。
- [返回文本变长挤占预算] → 草稿限 6 条、每条 instruction ≤120 字；summary 仍走既有 `_clip`（2600）；分桶后两段各自上限，测试钉总长。
- [抽 `load_style_entries` 改到既有 kb-draft] → 保持 `style_draft_from_kb` 返回契约逐字段不变，补回归用例（现有 style/kb-draft 行为断言）。
- [三区读取失败被当成未配置] → 按未配置处理是安全的（只多提示、不写数据）；日志留痕由工具 meta 记录。
- [与在途 `c-agent-dialog-prose` 规格重叠] → 该 change 的 `assistant-dialog-prose` 规格尚未入主 specs；本次在 design/tasks 挂账，归档时同步「按剧情动态匹配」条款的分桶措辞。

## Migration Plan

无数据库迁移、无接口变更、无发布开关。纯后端工具行为，随下一次构建生效；回滚只需还原 `assistant/tools_kb.py`、`assistant/tools_cards.py`、`assistant/scopes.py`、`settings/style_kb.py` 四处。

## Open Questions

- 基线内容仓何时补「场面级文笔/文风」条目（当前 0 条）——由 `c-kb-scene-tagging` 负责（拆书产出 `when`＋存量回标＋基线 v6）；本变更的草稿出口在数据就位后自然收敛。
- `limit` 在分桶后按「每段上限」解释（默认 12），如实测回执过长再收敛为总上限——属可调参数，不改规格。
