# Change: c-cast-split-user-layer

## Why

用户看实际渲染产物（2026-10-10 定）拍板：write_chapter 的 system 恒定层设定负载过重，其中人物档案 2496 字是最大块——主角 783、反派 1027（认知六层全量）、配角各约 200、废卡 275。配角卡全量恒定注入有两个代价：①不出场章全额付费（300-500 字/卡/章，多配角书随角色数线性涨）；②废卡（如测试卡「小憨憨」，人设与主角雷同）在恒定层制造身份歧义且每章吃缓存税。

原设计「全书角色集恒定注入、不按本章出场过滤」（c-write-prompt-layering 设计决策 5）的理由是保 system 逐章字节一致吃前缀缓存——本变更**不破坏该前提**：恒定层瘦身为「主角/反派极性卡」（真正逐章都该在场、且带认知六层的两张），配角与未设角色卡整体挪到 user 章级动态层、按本章出场注入。system 仍然只随设定变更而变（**新增配角不再改写 system 缓存前缀**，比原口径更恒定）；user 层本来就逐章变化，配角进那里零缓存代价。

配套拍板（同日，不改）：量化基线「对话 6%/内心 38%」与人味对白导向的冲突**维持现状**（有的书就该内心主导，靠重蒸馏纠偏）；世界观 lore-keep 增长**暂不设闸**。

## What Changes

- `client/backend/prompt/context.py`：新增 `cast_anchors_block(items)`——只收主角/反派（复用 `_CAST_DEPTH_ROLES`）后走 `cast_profile_block` 渲染；`cast_profile_block` 本身不动（arc_draft/素材包等既有消费方不受影响）。
- `client/backend/write/chapter_writer.py`：
  - `build_system_prompt` 的 `{cast_anchors}` 改用 `cast_anchors_block`——system 恒定锚只剩主角/反派；
  - `to_user_material` 新增「## 本章出场配角」块（角色状态块之后）：配角/未设角色卡，出场判定＝卡名或别名**逐字出现**在本章素材文本（章纲概要/要撞的墙/章末落点/剧情条目/前情/上章结尾原文/故事状态/必须完成，故事状态以 JSON 序列化参与匹配）；无命中不出节；
  - 相关注释与理由句同步（`c-write-prompt-layering` 装、`c-cast-split-user-layer` 拆）。
- `client/backend/tests/test_chapter_writer.py`：`test_cast_anchors_full_roster_not_chapter_filtered` 与 `test_new_character_changes_system_once_user_carries_appearance` 由旧设计断言改写为新契约；新增别名匹配用例。34/34 绿。
- `awesome-novel-prompts`（配合提交 cb4d53b）：write_chapter 纳管注释 `{cast_anchors}` 占位符描述同步（sync.py CURATED）——模板正文零改动。
- 明确不做：量化基线配比行（维持现状）；世界观 lore 总预算闸（暂不控制）；主角/反派认知层裁剪（本次不动，另行观察）；废卡「小憨憨」删除（数据侧，作者手工）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `prose-writing`：「system 恒定层组装」Requirement——cast_anchors 由「全书角色集」改为「主角/反派恒定锚」；user 段新增「本章出场配角」块（按出场注入，别名参与匹配）；身份句先立题材作家（`{theme}` 空兜底「网文」）＋手填值剥尾句读（纯句读走兜底）。delta 见本 change `specs/prose-writing/spec.md`。

## Impact

- C端：`client/backend/{prompt/context.py,write/chapter_writer.py,tests/test_chapter_writer.py}`；全量套件 2147 passed＋15 个存量失败（与本变更无关：pytest 9.x 缺 pytest-asyncio 的 async 用例、auth 时序、挂载触发的 repo_no_prompt_templates——原版代码同样失败，已对照实证）
- 提示词仓：仅元数据（cb4d53b），无模板正文变化
- 发布：随下次客户端打包/容器镜像生效；5274 演示栈重建后即时体验
- 无端点/前端/schema 变化；golden 全量提示词回归（tests/golden）不含人物档案场景，未受影响
