## Context

见 proposal.md「Why」。设计受四条现状约束：

1. **两条正文提示词路径**：`write/chapter_writer.py` 的 `to_prompt`（粗组兜底，未润色直写用）与 `material_markdown`（润色素材包，产物存为 `write-prompt` 后被直接采用）。两条路共享 `_scene_material_text` / `_narrative_goals_lines` / `_red_lines` / `_plot_block` 四个渲染器。
2. **存储拆装无 presence-gate**：`chapters/store.py` 的 `_disassemble_scalars` 对 `_OUTLINE_SCALARS`/`_EMOTIONAL_SCALARS`/`_EXPECTATION_SCALARS` 是无条件 `setattr`；子表侧由 `_CHILD_ATTRS` 的 `.clear()` ＋ `_replace_children_impl` 内显式赋值（`row.key_points = [...]`）。**前端一旦停发键，第一次自动保存即清空存量**——这是本次最大的数据风险点。
3. **三条会重放旧数据的路**：正常保存、章版本恢复（`chapters/versions.py:124-136`，快照只含 `{prose, outline, status}`，恢复时整体替换 `outline` 再走 `save_chapter`）、备份包导入（`backup/importer.py:652-662` 走同一拆装链）。
4. **删除的两条既有机制**：`db-generation`（新代库 `create_all` 建出模型声明的列/表；旧库经迁入引擎按**列交集**搬运、源库只读留存）与 `backup/format.py`（「加键＝兼容不升版；删键/改布局＝升版」，当前 `FORMAT_VERSION = 4`）。

## Goals / Non-Goals

**Goals**

- 章纲页 24 格收敛到 13 格，且删除对正文信息量**零损失**（先补两个漏信息缺陷，再删）。
- 删除做到「模型层摘除 + 拆装链摘除 + 消费链摘除」三处一致，不留半死字段。
- 旧数据（旧库、旧备份包、旧章快照）不因删除而报错，且行为可预测。

**Non-Goals**

- 不做场景卡权重到剧情条目的迁移（选项③已裁定整组退役）。
- 不做旧数据兼容搬运（零用户，被删字段的存量内容按删除处理）。
- 不清理同类历史死子表 `chapter_knowledge_states` / `chapter_downtime_functions` / `chapter_key_choices`（无 UI 无读者，但不在本次字段清单内，另评）。
- 不改 `plot_items` 的字符串数组形态（无 per-item 结构字段的契约保持）。

## Decisions

**D1 删列而非留列（与 c-og-fields-slim 的「只留不读写」分道）**

c-og-fields-slim 选择留列，理由是「SQLite 无迁移链，删列无路径」。该理由只对**存量库文件**成立；C端 的库是**每版新建**（`db-generation`），删列的路径就是「模型不再声明该列」——新代库不建、旧库经迁入走列交集、源库只读留存。留列反而有代价：拆装映射表里必须继续维护这些键（漏一处就是停发即清空）。故本次**从模型摘除**。

退化的边界：旧版应用打开新代库 = 库文件名不同代，走既有「旧库只读留存/迁入」分流，不需要新逻辑。

**D2 子表退役必须同改三处**

只改 `assemble_chapter` 不够。`key_points` / `scene_cards` / `segments` 三张子表退役要同时处理：① 装配端不再输出；② `_CHILD_ATTRS` 去掉对应项；③ `_replace_children_impl` 内**显式赋值**语句删除（留着 `or []` 会在请求缺键时把表清空）。三步缺一即出现「停发即清空」。`chapter_payoff_items` 保留（`must_resolve`/`must_hold` 仍活），只去掉 `partial_advance` 档的写入与读取。

**D3 备份包升 v5，旧包读窗只「忽略」**

`backup/format.py` 的规则决定必须升版（删键）。读窗策略：v4 及更早包照常导入，退役键**忽略**（不进任何模型字段），其余字段回写。**不做键名映射、不做数据搬运**——零用户前提下，搬运只会引入一条需要长期维护的兼容分支。

**D4 `plot_items` 输入收口选 422 而非静默丢弃**

`chapters/schemas.py:normalize_plot_items` 现在对非 str 项做 `str(item)`，导致 `{"text": ...}` 被存成 dict repr 再拼进提示词（静默污染）。改为请求 schema 层拒绝非字符串项（422），与 `plot_stage` 越界的既有 422 口径一致。**不采用**「丢弃非字符串项」：静默丢弃会让作者以为写进去了。

**D5 推演「收进章纲」= 追加剧情条目**

原落点「预期策略」退役。改为向 `plot_items` **追加**一条走法行：语义最近的落点（剧情条目是「这一章怎么演」的主干），且与既有 AI 三版采纳的「整表替换」语义区分开（追加而非替换，避免误清作者已写条目）。写入仍走章纲既有保存链，不新增存储通道。

**D6 前情上下文换源**

`mood_progression`/`emotional_hook`/`expectation_detail` 退役后，`build_previous_context` 的来源改为**上章章纲概要 ＋ `required_changes` ＋ `ladder_exit`**。理由：`ladder_exit` 是拆章写入的「止」，本身承载「停在哪个紧张度」；概要是整章主干——此前的情绪末段与情绪钩子在页面上根本没有编辑控件（只有 AI 起草会写），属于「AI 写、AI 读」的自闭环，删掉不损失作者可编辑的信息。

**D7 场景卡退役后的笔墨分配**

权重不迁移（D-选项③）。提示词里「按场景权重分配笔墨（高权重细化、低权重简笔转场）」的指令与【场景原材料】块一并退役；笔墨由剧情条目顺序 + 质感要求段承担。**已知代价**：作者失去对「哪块详写」的显式控制，只能靠条目详略暗示。

**D8 被删字段的下游换源**

| 消费者 | 原取数 | 换源 |
|---|---|---|
| `write/ai_check.py`（六类体检） | `key_points` | 章纲概要 ＋ 剧情条目 |
| `write/style_shadow.py`（文风建议素材） | `key_points` | 剧情条目 ＋ 概要 |
| `write/plot_sim.py`（兜底回合） | `key_points` 前 4 | `plot_items` 前 4；空则概要；再空则固定句 |
| `chapters/ai_plan.py`（越纲已知地点集） | 章级 `location` 裸列 | 世界设定与设定侧地点单源（**接受地点警告增多**：警告只提醒不拦） |
| `write/router.py`（`has_outline` 判定） | 含 `outline.segments` | 概要 ＋ `plot_items` |
| `write/prompt_sources.py`（本章章纲来源） | 概要＋关键情节点＋场景＋出场角色＋剧情条目 | 概要＋出场角色＋剧情条目 |

**D9 顺序：先补洞、再关门、后撤格、最后退役存储**

按「每批可独立上线」拆四批（见 tasks.md）。**P0 必须是补两个漏信息缺陷**——否则删除会让润色路径彻底丢章纲主干。P2（页面撤格）的前置是 D2 的三处收口已完成，否则一上线即清存量。

## Risks / Trade-offs

- **[停发即清空]** 子表/标量撤键不彻底 → 第一次自动保存清空存量数据。→ D2 三处收口同批改；P2 前跑「保存往返不清空」专项测试（旧库快照存一份，撤格后保存、比对留存字段逐字不变）。
- **[旧包导入静默丢数据]** v4 包的退役键内容永久消失。→ 属预期（零用户、已裁定）；但**必须显式**：导入报告如实标注「忽略 N 个已退役键」，SHALL NOT 静默。
- **[越纲地点警告回升]** `location` 退役使已知地点集变小。→ 接受；文案与既有 warn 口径一致（提醒核对、不拦）。
- **[前情信息量下降]** 丢情绪末段与情绪钩子。→ D6 换源为概要＋必变＋落点；若实测偏薄，后续可把「上章剧情条目末条」加入来源（不动本 change 契约）。
- **[笔墨分配失控]** D7 的代价。→ 若实测正文篇幅分配变差，另立 change 在剧情条目上补一个章级/条目级档位（届时需先修 D4 的输入收口，已在本 change 内完成）。
- **[backup 升版读窗]** 升 v5 后 v5 包不能被 v4 应用读取（既有规则，非新增问题）。→ 归档/发布说明中标注。
- **[规格卫生]** 为保住归档连续性，若干场景名保留原名而正文改为新行为（如「五段随导出导入往返」「收进章纲写预期策略」），正文内已注明退役字段。→ 归档时视需要由 docs 侧统一更名（不阻塞实现）。

## Migration Plan

1. P0/P1 上线后即可发布（含提示词缺口修复与门禁降级，无破坏性存储变更）。
2. P2（页面撤格）与 P3（存储退役）同批发布：模型摘列 + 拆装收口 + 前端停发 + 备份升 v5，一次性换代（新版本库）。
3. 回滚：回滚到旧版应用 → 打开的是旧代库（只读留存/迁入分流），新代库留档；提示词与章纲行为随版本回退，不产生跨代半写状态。
4. 归档时同步：`plot-sim` 与 `workbench` spec 的 Purpose 中「收进章纲写预期策略」措辞更新（delta 不支持改 Purpose，需归档时手改）。
