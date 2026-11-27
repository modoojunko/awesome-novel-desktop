# 提案：拆书产出适用场景（when）贯通与存量回标（c-kb-scene-tagging）

## Why

2026-11-27 定诊：知识库文笔/文风在写章候选里结构性为 0，主因不是过滤，是**生产链从来没产适用条件**：

- 源条目实测：文风 1604 条、文笔 1464 条，`when` 字段 100% 为空；
- 官方基线 8197 条里，文笔/文风 `scope=scene` 为 **0 条**（全部 `base`）；
- 拆书三条提示词（`deconstruct_style` / `deconstruct_techniques` / `deconstruct_card`）的输出契约里没有任何场景/情绪/章位字段；
- 内容仓 `deconstruct_batch.py` 虽有 `when` 参数，上游不产 → 全部 `None`；
- C 端入库 `kb/deconstruct_import.py` 原样透传空 `when_json`；
- 消费端 `digest_candidates` 的 style 组要求 `scope=scene` → 恒空。

规格允许、闸门放行（`kb/gates.py` 只拒世界/角色设定带 when）、前端编辑器却没有编辑入口（只读展示），结果文笔/文风从生产到消费全程没有场景信息。章级按剧情选文笔文风因此无米下锅，只能靠书级三区或模型现编。

## What Changes

- **拆书产出契约补适用条件**（prompts 仓）：
  - `deconstruct_style`：`rules`/`craft` 每项增加可选 `when`，键限 `scene`/`emotion`/`chapter_pos`，值限封闭词表；判不出就留空，**不硬填「日常」**（沿用既有判例）。`role`/`examples` 不标（全书恒定）。
  - `deconstruct_techniques`：`techniques` 卡增加可选 `when`（手法本来就该有场景）。
  - `deconstruct_condense`：归并时保留/合并 `when`，冲突取并集或标 low。
- **入库贯通**（desktop）：C 端拆书管线把条目级 `when` 写进 `when_json`（`create_entry` 已支持该参数，接线即可）；内容仓 `deconstruct_batch.py` 接线（参数已有）。
- **存量回标**（knowledge 仓）：对 3068 条 base 文笔/文风按 `instruction` 做一次场景分类（LLM＋封闭词表；只标 `rules`/`craft`，`role`/`sample` 保持 base），人工抽检后重打包基线 v6。
- **验证**：西式奇幻抽一批看产出质量（能标出「对峙/打斗/日常」且不乱标）；回标后基线 scene 条目 > 0；消费端 `kb_search_craft` style 段出现候选。
- **不做**：不标世界设定/角色设定（合规红线）；不做前端「适用场景」编辑器（本次靠拆书产出与回标；作者手写场景条目挂账）；不改书级三区与写法块的消费口径。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `deconstruct-book`：拆书文风/技法产出的字段契约增加可选适用条件（`when`），并在入库时写入 `when_json`；判不出留空。
- `knowledge-base`：存量文笔/文风条目的适用条件回标与基线条目 `scope=scene` 的贯通（消费端 style 组不再恒空）；回标只动写法条目，不碰世界/角色。

## Impact

- 跨三仓：
  - `awesome-novel-prompts`：`deconstruct_style.prompt`、`deconstruct_techniques.prompt`、`deconstruct_condense.prompt` 输出契约；发提示词包新版本。
  - `ai-novel`（本仓）：`client/backend/deconstruct/` 入库映射（`when_json` 接线）；相关测试。
  - `awesome-novel-knowledge`：`tools/deconstruct_batch.py` 接线；存量回标脚本；`tools/build.py` 打包 v6 与发布。
- 无数据库迁移（`when_json` 字段早已存在）；无新端点；无前端改动。
- **Design Impact**：无用户可见界面改动（不新增/修改屏、弹层、组件；知识详情页的「适用」只读展示沿用现状）。不触碰两端共享段，无需原型先行。
