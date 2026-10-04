## 1. 改模板前置核对

- [x] 1.1 改模板前全量 grep 完成。实测命中：t3 断言区三处（:733/:741/:749/:754/:764）、test_prose_pipeline.py:191（`assert "征兆" in system_tpl`——第 4 处，3.1 一并消化）；其余为测试数据串（chapter_patch_gates 的 ladder_exit 值、writer_context 的 ctx 字段值），非桩短语；e2e 零命中
- [x] 1.2 进场派生实证（立项期已完成）：`chapters/ai_plan.py:68-99 resolve_prev_chapter_ending`——has_prose 分流（上一章有正文→`paras[-1][:200]` 取正文末段、无正文→落点拟定），带来源标注、纯文本无解析依赖，对台词/动作式结尾天然兼容；拆章提示词层无进场口径可改。**遗留缺口转入 2.5**：`[:200]` 硬截无句边界回退

## 2. 章首接缝：素材注入（chapter_writer.py）

- [x] 2.1 新增 `PREV_TAIL_MAX_CHARS = 800` 与 `_clip_tail_paragraphs(text, max_chars)`：按 `\n` 分段从末向前累加至 ≤800 字；单独一段超限取段尾并回退句边界（。！？」……）起头；空正文返回空串。验证：单测覆盖整段裁剪/超长单段/空串/残句不出现
- [x] 2.2 `build_chapter_context` 在 `prev_ref` 取数处读 `prev.get("prose")`，填充 ctx 新字段 `previous_tail`；**回退块化**：上一章有正文即注入；章纲全空回退场景下由尾块承载正文末段（`previous_chapter_recap` 退役置空，旧 `prose[-500:]` 硬截一并消灭），语义前情段缺席；第一章/无上章为空。验证：语义前情/回退/无正文三态单测
- [x] 2.3 新增 `render_previous_tail(tail)` 单源渲染函数（定位句三合一：直接接下去写＋原文已有画面信息不重述＋衔接画面与章末落点摘要出入时以原文为准），接入 `to_user_material`（`## 上章结尾（原文）`，前文回顾之后、故事状态块之前）与 `material_markdown`（【上章结尾（原文）】，【前情上下文】之后）；两路无块时与现状逐字一致。验证：两路同源同字单测＋空缺逐字一致单测
- [x] 2.4 `validate_polished_prompt` 增加条件锚：`previous_tail` 非空时产物须含「上章结尾」段标题锚（与「前情」条件锚同手法）。验证：含/不含块的润色校验正反用；回退态（语义前情缺席）下「前情」锚不再触发、「上章结尾」锚照常触发。验证：含/不含块＋回退态三组润色校验用例
- [x] 2.5 进场取文句边界回退（chapters/ai_plan.py:92）：把 2.1 的句边界回退抽成 `_clip_to_sentence_boundary(text, max_chars)` 单源小函数，`resolve_prev_chapter_ending` 的 `paras[-1][:200]` 改走该函数——拆章进场不再以残句开头（与写作端上章结尾取文同口径）。验证：单测覆盖超长末段（进场文本不以半句开头）＋`test_chapter_plan_ai_t3` 进场来源分流用例仍绿

## 3. 章首接缝＋章末硬切：写作模板（write_chapter.prompt）

- [x] 3.1 输出契约第 5 条「章末切点」重排为分点结构（停在哪／末句形状／硬切示范／短禁令／豁免），既有禁令全部保留、不增负清单长度；豁免触发条件用可判定表述（章末落点缺失或为局面陈述），并含收束 carve-out（落点/章纲带收尾结局语义时停在落点本身，与拆章末章例外对称）；「示例不得进正文」免责句作用域上移为模板级。验证：文件 diff 逐条对 spec delta；test_prompt_layering 闸门绿
- [x] 3.2 输出契约新增第 7 条「章首接点」（条件句触发词统一用「上章结尾」）：第一段从上章结尾画面的下一拍直接写起、原文已有画面信息不复述，禁重设场景/时间跳切/氛围句重开（剧情条目第一拍不在上一幕现场时短句转场）；模板头部 changelog 注释补 v5 说明，system 段首行身份句不动。验证：含与不含尾段块的两章 system 段逐字节一致（单测断言）
- [x] 3.3 `WRITE_CLOSING_LINE`（chapter_writer.py:87-91）措辞同步：追加末句形状＋局面落点硬切口径；机制不动（不落库、不进预览）。验证：`_stream_chapter` 单测/e2e 现有断言不红
- [x] 3.4 章首接点与开篇期节奏并行性核对：首章（`_CH1_PREVIOUS` 固定句、无尾段块）自然不触发；开篇期章两规则并行不悖。验证：首章素材组装单测＋「本章位置：开篇期」章组装单测

## 4. 章末硬切：拆章与自检模板（chapter-plan-ai 域）

- [x] 4.1 `chapter_split.prompt` 规则 4 全句重写（下一拍要砸下来的动向/动作或台词瞬间/禁局面陈述/悬念道具禁令收窄），输出契约 `ending` 字段定义同步改口径；`plot`「结果带局面」不动。验证：文件 diff 对 spec delta
- [x] 4.2 `chapter_selfcheck.prompt` 拉力维问句改写（停在下一拍要爆发的一瞬；末句是动作/台词/声响还是旁白总结）；四维闭集与 JSON 契约不动。验证：`ai_chapter_selfcheck` 相关单测绿（mock 桩若钉问句原文则同步）
- [x] 4.3 `test_chapter_plan_ai_t3.py:733-764` 三处「自然断点」断言改钉新口径（rule4 含「下一拍」、ending 定义含「动作或台词瞬间」、拉力问句含「下一拍要爆发」）。验证：`pytest tests/test_chapter_plan_ai_t3.py` 绿

## 5. 润色通道同步（prompt-crafting 域）

- [x] 5.1 `prompt_crafting.prompt` 要素清单第 3 条扩尾（上章结尾原样透传不得摘要化）＋锚词行追加「上章结尾（仅当素材包含对应块时）」。验证：`test_write_prompt_polish.py` 现有用例绿＋新增含块校验用例
- [x] 5.2 润色产物校验链路联调：素材含块→产物缺段判不合格；素材无块→不要求。验证：单测正反用例（与 2.4 呼应）

## 6. 全量验证

- [x] 6.1 后端单测全量：`pytest`（关注 test_chapter_writer_context / test_chapter_writer / test_chapter_plan_ai_t3 / test_write_prompt_polish / test_prompt_layering / test_prose_pipeline）
- [x] 6.2 改模板后复跑 1.1 的全量 grep，确认桩短语零残留；ruff 按 CI 钉版本复核（0.16.3）
- [x] 6.3 真机验证完成（2026-10-04，本地隔离环境：临时 DATA_ROOT/DB/端口 8100＋GLM 真模型，已销毁）。新建微型设定书连生成两章＋归档＋拆章抽卡：①素材「## 上章结尾（原文）」块＋仲裁句在组装产物直证在场；②第 2 章首段「雨衣人没有走过来。他就站在巷口……」从上章结尾下一拍直接写起，无氛围句重开、无复述；③两章末句均落在动作/台词/声响（第 1 章末「便签…一路往上烧」、第 2 章末停在「记账人：」四字），零旁白定格；④拆章三方向 ending 全部动作/台词瞬间（零局面陈述），进场正确取第 2 章末句「记账人：」（正文优先＋句边界）。润色路径未验（单轨免登书无润色产物链路，校验锚已由单测三态覆盖）。出卡首连败为小模型 JSON 契约抖动，重试即成，与本次改动无关（输出契约未动）
