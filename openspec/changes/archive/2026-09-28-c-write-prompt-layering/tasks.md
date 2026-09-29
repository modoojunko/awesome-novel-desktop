## 1. system 恒定层模板与组装

- [ ] 1.1 【遗留：WIP 未合 main，随其落地后补】前置：确认开篇期 WIP（chapter_position）已合入 main，本分支 rebase；同步核对 WIP 会话是否已给 `material_markdown` 补「本章位置」标注（漏则催办）
- [ ] 1.2 【遗留：节奏分档段随 1.1 补，模板已留插入位注释；其余已落】新建 `prompts/write_chapter.prompt`：`<<system>>` 段含角色定位（`{persona}`＋题材声明＋「语言：中文」）、输出契约（铁律三条＋「本章必须完成视为已写情节，优先级高于剧情条目；未覆盖完成项须安排最小拍点」仲裁句）、节奏分档（原铁律第 4 条条件表逐字迁移的常量文本）、故事前提与全书主线（`{premise_story}`）、题材设定（`{genre_section}`）、文风基线（`{style_block}`＝量化六行＋文风例句＋禁用词/句式，空则跳过对应行）、写法要求（`{craft_rules}`＝质感要求）、世界观（`{world_block}`）、世界铁律（`{iron_rules}` 行集）、本卷卷纲（`{volume_outline}`）、人物档案锚（`{cast_anchors}`＝全书角色静态档案）；`<<user>>` 段为单一 `{chapter_material}` 占位
- [x] 1.3 `build_system_prompt()`：load_layers＋**顺序 replace 安全渲染**（新 helper，拒用 str.format）＋逐段空内容跳过（禁用词空不出禁令行、卷纲/前提空整段缺省）；世界观块走全量通道（势力/历史/细节不裁剪、无「另有 N 条从略」）
- [x] 1.4 persona resolver 单源：手填优先、空串/缺失兜底「一位小说家」；system 组装与 `material_markdown` 角色默认同源消费；`to_prompt` 的「## 角色定位」节与 router f-string 拼接、`WRITING_IRON_RULES` 常量退役
- [x] 1.5 人物档案锚：`_cast_block` 抽至 `prompt/context.py` 共享（`ai_router` 原处委托），渲染**全书角色静态档案**（不按出场名单过滤）进 `{cast_anchors}`；认知主格双写按设计决策 5 落（user 状态行为叙事权威）
- [x] 1.6 组装 lint：`lint_assembled_prompt()` 两件——「本章必须完成未被剧情条目覆盖」「活跃伏笔混入已兑现（揭）记录」——告警不阻断，接进组装出口

## 2. user 层重构与调用方切换

- [x] 2.1 `to_prompt()` 重构为 `to_user_material()`（节标题维持 `##` 风格）：本章位置标注（随 WIP）→章纲概要→剧情条目（补 `[编号]`＋优先级前缀）→要撞的墙→卷内位置→**章末落点**→叙事目标（含微爽点）→前文回顾→角色状态→文风影子覆盖块（有影子章：命中行渲染「本章覆盖」清单＋优先级语）→活跃伏笔→章级红线（必须完成/兑现/维持/禁止，段头压缩说明）→字数目标（含 ±10% 与压缩策略）；删恒定块与「疲劳词见上方」悬空引用
- [x] 2.2 三处调用方切换：GET /write/prompt fresh（`router.py:183`）、写正文兜底（`router.py:342`）、提示词精修（`router.py:500`）；`prompts/prompt_refine.prompt` 中引用旧分节结构（「不可违反规则段」等）的文案同步新口径
- [x] 2.3 收尾重申行：常量定义＋`_stream_chapter` 在最终 user 内容（stored 与重组两路径）末尾追加；不落库、不进弹窗预览；核对与 `save_chapter/word_check/self_check` 无交互

## 3. 存量稿 legacy 分级引导

- [x] 3.1 legacy 判定：润色稿行＝`_POLISH_ANCHORS` 三锚（任务指示＋红线＋质感）同现；粗组存稿行＝恒定块标题（`## 角色定位/## 故事背景/## 题材设定/## 文风/## 原则与禁忌`）；【】块组合留历史兜底；GET /write/prompt 响应新增 `legacy` 字段（fresh 恒 false）
- [x] 3.2 前端 AiModal 分级提示：`polished=true` 旧整包行只显示信息性提示（「恒定设定已由系统注入，与旧稿并存」）不出刷新动作；未润色粗组旧行才建议「刷新提示词」；「已润色」徽章与信息行共存样式；说明文案补「恒定设定由系统按本书设定注入」；两处「设定＋章纲」文案（说明行与按钮 title）对齐 fresh 新语义
- [x] 3.3 AiModal vitest：润色旧行信息性提示（无刷新引导）＋粗组旧行刷新引导＋刷新后提示消失三条用例

## 4. 测试与验收

- [x] 4.1 `test_chapter_writer.py`：to_user_material 形状断言迁移（章级块在、恒定块不在、章末落点在、伏笔带编号前缀、影子覆盖块在/不在两态、空禁用词无空节）；build_system_prompt 用例（恒定块齐全含前提/主线/例句、势力全量无「从略」、tie-breaker 在、role 空串兜底、禁用词空跳过、档案锚为全书静态不随章变、花括号素材不崩、lint 两件告警）
- [x] 4.2 恒定性断言：同书两章（不同出场名单、不同影子状态、不同剧情）system 渲染产物逐字节相等；新角色插入→system 变化且 user 承接出场的用例
- [x] 4.3 `test_write_prompt_polish.py`：GET 契约（user 层形状＋legacy 字段分级＋fresh 恒 false）；收尾行追加（stored/重组两路径、不落库）；legacy 判定三形状（润色三锚行/粗组标题行/新 user 层行）；润色链回归（material_markdown 输入与锚词校验不变）
- [x] 4.4 存量断言迁移：`test_novel_genre_relational.py`（题材块断言改指 system 产物）、`test_prose_pipeline.py:181-184`（WRITING_IRON_RULES 直断言改读模板 system 段）；`test_prompt_layering.py` 纳管确认（名单不动）
- [ ] 4.5 【pytest 1651 绿＋vitest 937 绿＋tsc 绿已验；e2e 待演示栈重建/CI 补跑（两 spec 只钉 testid，已静态核对不受影响）】全量门禁：后端 pytest 全绿＋前端 vitest/tsc 全绿；e2e prompt-pipeline/workbench-features 本地跑通
- [ ] 4.6 【待真机人工验收】质量对比验收（价值验收，排在缓存之前）：选 3 章——首章（分档激活）、多势力章（原被裁剪）、带 style_shadow 章——旧形状 vs 新形状各生成一次，作者盲评势力名/完成项/文风量化不劣化；复用 done 事件 `word_check/self_check` 统计纯正文率与字数达标率不降
- [ ] 4.7 【待真机人工验收】缓存核对（非流式）：用非流式 `chat()` 同 system 试发核对 `cache_read_input_tokens` 命中量级≈system token 数，按供应商分列判定（自动前缀缓存供应商核对命中；Anthropic 系 0 命中记「预期内，等 cache_control change」）；流式无缓存读数字段的局限写入归档总结
- [x] 4.8 渲染器漂移遗留登记：见下方遗留清单（2026-09-28 归档时登记）


## 遗留清单（2026-09-28 归档登记，供后续提案领走）

1. **节奏分档段＋user「本章位置」行**（task 1.1/1.2 局部）：母本在开篇期 WIP（chapter_position）——该会话合入 main 时随批补入 `prompts/write_chapter.prompt`（模板已留插入位注释）与 `to_user_material`（标注行）；其素材包侧【本章位置】块漏加一并补。
2. **两套渲染器口径漂移**：`to_user_material` 与 `material_markdown` 的角色语言特征分隔符（`（语言特征：…）` vs `｜语言特征：`）、伏笔块外的节名差异——`_plot_block` 已单源，其余待一次收编提案。
3. **e2e 补跑**（prompt-pipeline / workbench-features）：待演示栈重建或 CI 恢复；两 spec 只钉 testid/徽标，已静态核对不受影响。
4. **真机人工验收**：同章改前改后质量对比盲评（task 4.6）＋分供应商缓存核对（task 4.7，非流式 `chat()`）。
5. **persona 题材映射表**、**地点/场景 lore 与非卡 NPC 注入管子**、**auxiliary.py 续写/扩写/润色 system 收编**、**流式链路缓存记账字段**：见 change design Non-Goals，均需另立。
