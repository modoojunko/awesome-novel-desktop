# 提示词素材同类缺陷补漏（审计批量）

## Why

用户追问「还有没有类似情况」后做了一轮全量审计（提示词工程师扫全部 AI 环节，主会话抽验）：**同类缺陷还有 12 条**，其中两处 P0 比已修的两处更严重——① 章纲起草（每章剧情的主干链路）**零世界/铁律/题材素材**；②「世界铁律」通道在 v2 契约下**恒为空**：拆章素材里规格要求全量必到的【世界铁律】块永不渲染，卷体检还恒印一句假话「（世界设定未登记铁律）」，而同一提示词的世界观块里恰恰带着铁律行（自相矛盾，直接短路判据）。本 change 按审计清单批量补漏：P0 两条＋P1 六条＋两处 spec 自相矛盾的默认裁决。

## What Changes

**P0**
- **章纲起草**（`chapters/ai_draft.py` 两个素材函数）：补【世界观】（`world_summary_text(raw, None)`，含铁律红线）＋【题材与节奏】＋【人物】（全名单一行卡、主角置顶、人设原文）；出场者的角色状态不再封 5 人；活跃伏笔不再封 8。
- **世界铁律单源**（`volumes/ai_plan.py`）：`world_rules` 由 `isinstance(constraints, str)`（v2 下恒假）改为 `render_red_lines(raw)` 单源——拆章 ⑦ 块、章内剧情、卷体检三处消费方同批恢复；测试从「因数据为空而恒真」改为「有铁律必在块」。

**P1**
- **角色 AI 三处**（`settings/characters_ai.py`）：世界素材改 `world_summary_text(raw, None)`（旧实现读 `factions[*].value`，v2 是 `name/note` → 势力清单恒空）；体检判据 `no_power` 从渲染文本子串改读结构真值；卡文本不再 `[:2000]` 尾部硬切；主线不再切 600；同事名册不再 12 人封顶。
- **世界体检/世界起草/lore 建议**：`world_summary_text(..., 1200)` → `None`（校验型手里没法典）。
- **写正文**（`write/chapter_writer.py`）：在场者不再封 5 人（第 6 人曾"根本不存在"）；角色状态按**逐格 40 字**（旧实现整串切 120，首格写长就把后五层挤掉）；`write/router.py` 提示词精修的 `[:12000]` 取消（曾把组装稿尾部世界观/红线/角色/伏笔切掉后回写覆盖）。
- **续写/润色**（`write/auxiliary.py`）：角色快照从**已退役的 YAML 路径**改走真表（人设＋语言特征，与写章同源；旧路径恒空 → 「角色状态」永远「（暂无角色信息）」）；禁用词/句式不再截 15/5 条。
- **伏笔链**（`settings/ai_router.py`）：起草/收束/体检的主线不再切 600、世界不再切 1200。
- **归档**（`archive/service.py`、`archive/reconcile.py`）：摘要正文不再切 3000；收尾提案的 set_changes/lore 两段带上**现有世界设定**（旧实现没有"之前"可比，必然重复提案）。

**P2（含两处 spec 自相矛盾的默认裁决）**
- 拆卷「已拆卷清单」字段不再各切 60 字；拆章「已经拆过的章」不再只取最近 12 章、不再每行切 40 字。
- 卷体检补「主角最终怎样／读者读后的感觉」两问（此前只给第①问，spec 要求三问）。
- **活跃伏笔注入全量**（`prompt/context.py` 的 `[:8]` 退役）——裁决口径：以 spec「active 全量」为准，删掉与之矛盾的「≤8 条」条款。

**非目标（留档待办）**
- 反推链/归档链的提示词治理（4 个 `backfill_*_system` 提示词不存在→system 恒空；`backfill_outlines` 占位符永不渲染；`archive_summary.prompt` 死模板；reconcile/style-shadow 共 3 处硬编码提示词）——属治理重构，另行立项。
- 写正文「在场者全深卡」（决策记录 A 类）仍为口径登记；本 change 只修机械缺陷。
- `known_entities` 窄口径（注记内子派系词被判"设定里没有"）——已在台账登记，另行立项。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `outline-ai-draft`：章纲起草素材包＝主线卡＋世界观全量（含铁律）＋题材全字段＋全人物一行卡＋出场者角色状态（全量）；补场景「素材含设定全量」。
- `chapter-plan-ai`：素材预算条款加例外（已拆章节/已拆卷清单按原文全量；⑦ 铁律与 ⑩ 世界块全量）；补场景「已拆章节与铁律全量进包」。
- `volume-plan-ai`：「伏笔 ≤8 条」改为 active 全量（退役上限）。
- `storyline-settings`：归档域 schema 条款里「不挤占伏笔 ≤8 条口子」的引用随上限退役改写。

## Design Impact

无用户可见界面改动（全部为后端提示词素材与取值修正；前端不消费这些文本）。受影响端＝仅 C端 后端。

## Impact

- **代码**：`chapters/ai_draft.py`、`chapters/ai_plan.py`、`volumes/ai_plan.py`、`settings/characters_ai.py`、`settings/ai_router.py`、`write/chapter_writer.py`、`write/auxiliary.py`、`write/router.py`、`archive/service.py`、`archive/reconcile.py`、`prompt/context.py`、`prompts/volume_check.prompt`。
- **计费**：相关环节输入 token 上升（尤其是章纲起草从"零设定"到全量、卷体检铁律恢复），与所属环节既有量级一致；`operation` 口径不变。
- **接口/存储**：无变化（无新增字段/端点）。
- **测试**：新增 2 例（章纲起草素材三块在包；铁律块真渲染），改 2 例（角色不再封 5；伏笔不再封 8）。
