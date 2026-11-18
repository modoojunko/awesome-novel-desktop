# c-agent-tools-expand：结构管理动作＋世界观能力收编为 agent 工具

## Why

boss 走查（2026-11-17）问「后端 API 是否够封装成 agent skill」——全量盘点结论：作家「查＋拟」闭环已够，但**结构管理动作**（确认章纲/归档/建卷章）和**设定·世界观三件**后端有 API、agent 摸不到。作家高频意图（「把第七章归档」「开第二卷」「确认这章章纲」「帮我起草世界观」）目前都要回面板操作。

## What Changes

- 新增 6 个写/读类 agent 工具（封闭注册表＋域挂账）：
  - **结构动作三件（写类，走授权梯度，默认每写必确认）**：确认章纲/撤回确认（confirm_chapter/unconfirm_chapter）、章节归档/取消归档（archive_chapter/unarchive_chapter）、新增一卷（add_volume）、新增一章（add_chapter）
  - **世界观三件（读/产卡类）**：世界观起草（draft_worldbuilding）、世界观校验（check_worldbuilding）、传说建议（lore_suggest）——设定·世界观面板能力收编（/ai/world 三端点同源）
- 写授权卡预览补新工具条目（作家批前看得见改什么）
- scopes 域挂账：结构动作全域共享（书级操作）；世界观三件挂设定域
- 明确不收编：正文写流（终态链路）、key 管理、版本回退（硬地板候选）、迁移备份

## Capabilities

### 新增
- `assistant-tools`——agent 工具面：结构管理动作与世界观能力的收编口径、授权分类、域挂账、孤儿/回喂形态防线

## Design Impact

- C端 only；dock 无新 UI（工具即能力，产物/回执沿用既有卡面）
- 授权卡预览新增条目（write_gate._preview 补新工具映射）
- 提示词：新工具目录自动进 ACT_PROTOCOL 工具清单（tool_catalog_text 单源）

## Impact

- backend：assistant/tools.py（新工具＋注册）、assistant/caps/chapter.py（confirm/archive/add caps）、assistant/caps/world.py（世界观 caps）、assistant/scopes.py（域挂账）、write_gate.py（预览映射）
- 测试：注册表/域覆盖钉、工具行为钉（写类走 gate、世界观产卡）
