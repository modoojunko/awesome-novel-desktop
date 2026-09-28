# Design: c-write-prompt-layering

## Context

写正文调用（`write/router.py` `_stream_chapter`）现状：`system = f"{role}\n\n{WRITING_IRON_RULES}"`＋`messages=[{user: prompt}]`，其中 prompt＝`stored or ctx.to_prompt()`（`router.py:342`）。`to_prompt()`（`chapter_writer.py:350-470`）一包组装恒定素材与章级素材；生产调用方三处：GET /write/prompt fresh（`router.py:183`）、写正文兜底（`router.py:342`）、提示词精修（`router.py:500`），全仓 grep 无第四处。润色链（`/prompt/polish`）输入是独立渲染器 `ctx.material_markdown()`（【】块风格），其润色产物按 `prompt_crafting.prompt` 要求为 `##` 分节、经 `validate_polished_prompt` 校验 `_POLISH_ANCHORS`（任务指示/红线/质感）三锚后落库——即**润色落库行必然含三锚**。两套渲染器已在伏笔前缀（素材包带 `[编号]`＋优先级、粗组不带）与角色语言特征分隔符上口径漂移。世界观块走 `render_world_block(world)`（默认 600 字预算、显式「另有 N 条从略」），`char_budget=None` 全量通道已存在（c-plan-material-fullinfo）。全人物档案原文块在 `settings/ai_router.py` `_cast_block`（名字/类型/人设/档案八格，认知六层逐格原文只给主角与反派），内部消费 `settings/character_model.py` 的 `COG_LAYERS/DOSSIER_FIELDS`。**章级文风影子** `ctx.style_shadow`（章 YAML，回退/支线章用）经 `quant_section(quant, shadow)`（`settings/render.py`）把命中行渲染为「约 X（本章覆盖：理由）」替换基线值——已上线的章级覆盖功能。占位符填充现状：`load_layers` 只做纯切片，填充由调用方 `str.format` 完成（现 polish 链 `{material}` 已暴露花括号素材崩溃风险）。门禁：`tests/test_prompt_layering.py` 名单外新模板天然纳管（要求双标记在位）；`test_prose_pipeline.py:181-184` 直断言 `WRITING_IRON_RULES` 常量文本。`chapter_position`（本章位置标注）是另一会话在途 WIP，尚未合入 main。

## Goals / Non-Goals

**Goals:**

- system 层落成版本化模板文件，内容逐章字节恒定，为供应商前缀缓存创造条件。
- 修复「你是。」空串缺陷、铁律缺仲裁句、输出契约单写、世界观势力被裁剪四个已实锤缺陷。
- 现有 `to_prompt` 全部成分在新两层各有归属（显式归属表，零静默蒸发）。
- 持久化提示词语义收敛为「user 层内容」，旧整包行按形状分级引导软着陆。
- 组装期 lint 逮住「必须完成未覆盖」「伏笔混入已兑现」两类素材病。

**Non-Goals:**

- 题材→persona 闭集映射表（resolver 先落地「手填优先＋默认兜底」，另立）。
- 地点/场景 lore 条目注入、非卡 NPC 最小设定两根新管子（另立）。
- `auxiliary.py` 续写/扩写/润色的 system 收编（其 system 内插 `recent_context` 可变量，另立）。
- 「爱用词∩世界观词表」lint——后端无爱用词数据源，本就做不了，随文风蒸馏数据模型另议。
- 流式链路缓存记账字段（`StreamEvent` 补 cache 读数）——另立；本 change 验收走非流式。
- 两套渲染器（`to_user_material` vs `material_markdown`）完全合一——本次只对齐伏笔前缀，其余漂移（语言特征分隔符等）在归档总结登记遗留清单。
- 「本章位置」枚举契约——依赖未合入 main 的开篇期 WIP，待其落地后补。

## Decisions

1. **模板形状与安全渲染**：新模板 `prompts/write_chapter.prompt`，system 段＝骨架标题＋固定文本（输出契约含仲裁句/节奏分档全文写死）＋占位符 `{persona}/{premise_story}/{genre_section}/{style_block}/{craft_rules}/{world_block}/{iron_rules}/{volume_outline}/{cast_anchors}`；user 段＝单一 `{chapter_material}` 占位。填充**不用 `str.format`**（素材含 `{}` 即崩），新 helper 顺序 `str.replace` 渲染并配花括号素材用例。节奏分档全文进模板（常量条件表写法，迁移母本＝开篇期 WIP 合入后的 `WRITING_IRON_RULES` 第 4 条），user 侧标注驱动——不随章变。
2. **组装拆两段**：`ChapterContext` 新增 `build_system_prompt() -> str`（load_layers＋安全渲染＋空段跳过）；`to_prompt()` 重构为纯章级组装并更名 `to_user_material()`（三处调用方与测试同步改，不留别名——无存量用户，破坏性选干净方案）。收尾重申行常量放 write 模块，`_stream_chapter` 拿到最终 user 内容（stored 或重组）后追加——两条路径、POST 入口全覆盖，且位于 `save_chapter/word_check/self_check` 之前互不干扰。
3. **成分归属表（现状 → 新归属，零蒸发）**：

| 现状成分（to_prompt/素材包） | 新归属 |
|---|---|
| 角色定位身份句 | system `{persona}`（resolver 单源；`material_markdown` 的角色默认同源消费） |
| 输出契约（只写正文/无 Markdown 等） | system 固定文本＋user 末尾代码追加收尾行（同词不同句） |
| 铁律 2/3（不加戏/泛指）＋仲裁句 | system 固定文本 |
| 节奏分档（原铁律 4 条件表） | system 固定文本；激活靠 user「本章位置」标注（WIP 前置） |
| 故事前提＋全书主线 | system `{premise_story}` |
| 题材设定 | system `{genre_section}` |
| 文风量化基线＋禁用词/句式 | system `{style_block}`（书级；空则跳过对应行） |
| 文风例句 few_shot_examples | system `{style_block}` 内（书级恒定） |
| **章级文风影子 style_shadow** | **user 层覆盖块**：量化基线本体留在 system，影子命中行渲染为「本章覆盖」清单＋优先级语（「以下维度以本章值为准」）；无影子章该块缺省，system 不变 |
| 质感要求＋「语言：中文」 | system `{craft_rules}`（写法恒定） |
| 世界观＋世界铁律 | system `{world_block}`＋`{iron_rules}`（全量不裁剪） |
| 本卷卷纲 | system `{volume_outline}` |
| 人物档案锚 | system `{cast_anchors}`（**全书角色静态档案，不按出场名单过滤**） |
| 本章位置标注（WIP） | user 层行 |
| 章纲概要/剧情条目/墙/卷位置/章末落点/叙事目标/前文回顾 | user 层 |
| 角色状态（本章初始状态＋语言特征） | user 层；与档案锚的认知六层构成同源受控双写（状态行是「本章叙事口径」，六层是全量档案），以 user 层为叙事权威 |
| 活跃伏笔 | user 层（补 `[编号]`＋优先级前缀，与素材包同口径） |
| 章级红线（必须完成/兑现/维持/禁止） | user 层；段头说明压缩为「章级红线优先于字数与写法；世界铁律见指令恒定层」 |
| 字数目标 | user 层，保 ±10%＋压缩策略说明（prose-writing 既有 SHALL） |

   user 层顺序（稳定在前、易变在后）：本章位置 → 章纲概要 → 剧情条目 → 要撞的墙 → 卷内位置 → 章末落点 → 叙事目标 → 前文回顾 → 角色状态 → 文风影子覆盖块 → 活跃伏笔 → 章级红线 → 字数目标。节标题维持 `##` 风格（润色锚词与 legacy 判定都吃文本形状，钉死防漂移）。

4. **legacy 分级判定与引导**：持久化行命中标记即 legacy——润色稿行按 `_POLISH_ANCHORS` 三锚（任务指示＋红线＋质感）同现判定（凡成功落库的润色行必然满足；新 user 层不含「任务指示」「质感」两词，无误报）；粗组存稿行按恒定块标题（`## 角色定位/## 故事背景/## 题材设定/## 文风/## 原则与禁忌`）判定；【】块组合保留作历史兜底。引导分级：`polished=true` 的旧整包行（含作者手改）**只做信息性提示**（「恒定设定已由系统注入，与旧稿并存」）不出刷新动作；未润色的粗组存稿旧行才建议「刷新提示词」——避免引导作者用粗组稿覆盖刚润色的稿、形成循环。GET 响应加 `legacy: bool`（fresh 恒 false）。已知并接受：legacy 整包行里作者手改的旧设定文本会与 system 新设定同场出现（真冲突而非纯冗余），靠刷新/重润色消解，提示文案写明。
5. **档案锚**：`_cast_block` 抽至 `prompt/context.py` 共享（`inject_world_setting` 同居地），`ai_router` 原处委托保单源，依赖方向 write→settings 无环。system 放**全书角色静态档案**（不按章纲出场名单过滤——出场名单是章级数据，过滤会让 system 逐章变化，违反恒定承诺）；出场与否由 user 层角色状态行表达。认知主格双写裁决：user 状态行（主格切片）＝本章叙事口径权威，system 六层＝全量档案，受控双写，设计接受。
6. **润色链不动**：`material_markdown()` 与润色模板、锚词校验全部维持现状；其落库行按决策 4 分级提示。
7. **组装 lint**：`build_system_prompt/to_user_material` 旁落 `lint_assembled_prompt()`，带两件——「本章必须完成未被剧情条目覆盖」「活跃伏笔混入已兑现（揭）记录」——显式告警不阻断；随任务清单补两条单测。

## Risks / Trade-offs

- **弹窗预览变短**：user 层不再含恒定块，作者在弹窗里看不到全文——接受（恒定层本就不可编辑；弹窗说明带一句「恒定设定由系统按本书设定注入」，两处「设定＋章纲」旧文案同步对齐 fresh 新语义）。
- **legacy 行与 system 的真冲突**：作者手改过世界观的旧整包行，旧设定与新设定同场出现、system 权重更高——作者旧覆盖从「权威」降级为「噪音」。零用户阶段接受，分级提示＋刷新/重润色消解。
- **回滚方向（新→旧）**：本 change 落地后新落库的纯 user 层行，若 revert 回旧代码，会被旧代码当整章提示词用（缺恒定块）且旧 system 也只剩 role＋铁律——双重缺失。出口：点「刷新提示词」（#545 已在 main，revert 目标含它）重组整包即恢复。记入归档总结。
- **合并次序**：开篇期 WIP（chapter_position，同文件 chapter_writer.py）先合入 main，本提案 rebase 其上；冲突点（to_prompt 函数体、WRITING_IRON_RULES、build_chapter_context）归属：以本提案的重构形状为准收编 WIP 行。user 层「本章位置」行随 WIP 落地；其素材包侧漏加标注由该会话补齐。
- **验收不保证生成质量不回退**：单测守结构不守行为——设专门质量对比验收（见 tasks 4.5）。
- **缓存收益不保证立现**：TTL 5-10 分钟＋Anthropic 系零命中为已知代价；预期管理写进验收基准。

## Open Questions

（无——四路评审的取舍均已落入决策或 Non-Goals。）
