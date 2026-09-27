# Design — 提示词素材补漏

## Context

审计（12 条，见 proposal.md）的共同病根：**素材零件在 c-plan-material-fullinfo 全量化改造时只修了"主干三条链路"（拆卷/拆章/写正文的部分块），其余环节的同类零件留在旧形态**——旧预算（1200/600/3000/8/5/12/15）、旧字段名（`factions[*].value`）、旧判据（渲染文本子串 `"power："`）、退役路径（`settings/character-setting/*.yaml`）。另有一条**从上线起就断的死通道**（`world_rules` 在 v2 契约下恒空）。

## Goals / Non-Goals

**Goals:** 让每个环节的素材与它要判/要写的东西对齐；把"取值为空也照样跑"的死通道改成单源真值；spec 与新行为冲突处同批改口径。

**Non-Goals:** 反推/归档提示词治理（3 处硬编码＋死模板＋缺失 system）另立项；写正文深卡全量（A 类口径）另拍；`known_entities` 窄口径另立项；写正文世界块 600 预算（决策记录明文"维持现预算另评"）不动。

## Decisions

**D1 铁律走 `render_red_lines` 单源，不复活 `constraints` 字符串分支**：v2 契约下 `constraints` 是 `list[dict{key,value}]`，任何 `isinstance(str)` 判据都是恒假。三个消费方（拆章 ⑦、章内剧情、卷体检）不改代码即恢复——它们本来就读 `mat["world_rules"]`。
备选（弃）：删字段让消费方读 `world_brief` 的红线尾段——改动面更大且卷体检模板要跟着改。

**D2 章纲起草的素材在端点侧组装、复用叶子零件**：`world_summary_text(raw, None)`／`ctx.genre_section`／`list_characters`＋`_display_name`。一行卡**不截 persona**（用户口径「填了的原封不动」），主角置顶；空设定给「（世界设定：未填）」类轻占位（不写"不要补写"——章纲本身必须落到具体细节，占位只需诚实）。
备选（弃）：抽公共 `plan_material` 模块——三处消费方（拆卷/主线/章纲）零件已同源，抽模块等第四个消费方出现。

**D3 角色 AI 的 `no_power` 改读结构真值**：旧判据 `"power：" not in world` 依赖渲染文本里的小写键名——世界块改中文标签后必然失效（本 change 顺带修掉的连带失效）。真值＝`normalize_world(raw)` 的 `power` 非空且 `no_power=False`。

**D4 写正文角色状态＝逐格 40 字**：`WRITE_STATE_PER_CELL_MAX=40` 是既有常量（此前只 import 未用），改为逐格截；整串 120 的上限退役（逐格已封顶，总量自然有界 ~245 字）。`WRITE_STATE_PER_CHAR_MAX` 保留常量但不再使用（注释说明）。
备选（弃）：保住 120 总量并让各格均分——会在格数少时浪费额度，且判据关心的是"每格都在"。

**D5 伏笔 ≤8 与「active 全量」的裁决：以全量为准**。理由：spec 另一处明文「active 全量」、决策记录 A 类「任何环节不设预算」，且 ≤8 让第 9 条起的未收伏笔在下游（写正文/拆卷展开/卷体检）全部不可见——漏还债、漏判提前揭。删 ≤8 句并同步 storyline-settings 里的引用。

**D6 归档收尾带「现有世界设定」**：set_changes/lore 两段的语义是"新增或与之前不同"，没有"之前"必然重复提案；两段拼 `world_summary_text(raw, None)` 并声明「与之重复的不要提」。从 reconcile 入口读 raw 传入（`_collect_prompts` 加参），保持该函数纯函数形态。

## Risks / Trade-offs

- [素材变大 → 相关环节更慢/更贵] → 属既定"全量"口径的代价，与拆卷/主线同量级；观测走既有 usage 记账。
- [写正文在场者全量 → 群戏章提示词变长] → 逐格 40 已封顶；若真书实测超预算，回退点＝给在场者加"名字＋定位"兜底行（不改判据）。
- [伏笔全量 → 台账很长时稀释注意力] → 只提醒"active 全量"是 spec 明文的裁决；若实测注意力下降，回退点＝按「计划收束章＝本章」优先排序并列前。
- [改口径的连带失效（如 `no_power` 判据）] → 本 change 已把"依赖渲染文本"的判据全部改成结构真值；测试锁死（`test_characters_ai` 力量向项集）。

## Migration Plan

纯后端取值/口径修正，无存储/接口变化；随常规发版。回滚＝回退该 commit。本地/演示栈需重建 client-backend 镜像才生效。

## Open Questions

- 写正文「在场者全深卡」（A 类）与写正文世界块预算（600）——两者都属决策记录里"另评"的既有口径，留待下一次素材评审。
