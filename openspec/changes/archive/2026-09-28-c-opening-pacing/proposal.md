# c-opening-pacing：开篇期节奏三链同源（#574）

## Why
用户拍板（2026-09-28）：「前 500 字主角陷入危机/冲突」是**首章**要求——拉入的是全章主冲突、要让读者觉得很难解决、冲突前的经过压到剧情中途借回忆带出；**第 2–3 章**改为聚焦冲突解决——第一个冲突还在解决，第二、第三个冲突接着来（冲突叠加）；第 4 章起不加额外要求。此前三条生成链路（正文/剧情抽卡/拆章）各自节奏口径不一致，且正文侧无任何开场节奏约束。

## What Changes（#574=f738ebfb，squash 7 文件＋85/−22）
- **位置判定单源**：`chapters/ai_plan` 新增 `global_chapter_position`/`position_label`（复用拆章 `chapter_position_tags`/`_global_chapter_no`，滤 ghost；`_global_chapter_no` 改收 project_id）；标注文案两路同词：`全书第 1 章（首章）`／`全书第 N 章（开篇期）`。
- **剧情抽卡**（`chapter_plot_draw.prompt`＋`chapters/ai_plot.py`）：规则 4 改「本章位置」分档——首章＝开场即入局（每版从头 500 字内拽进【本章概要】/【碰到的挑战】指向、压到【本章结尾】的主冲突，难解决，冲突前经过中途回忆带出；进场平静时第一条中段入局）；开篇期＝冲突叠加（旧的未解、新的又起，至少一条「旧冲突未平、新冲突又压到主角头上」），SHALL NOT 串行解决；素材新增【本章位置】块（仅首章/开篇期章携带）。
- **正文**（`write_chapter.prompt`＋`write/chapter_writer.py`）：system 恒定层新增「## 开篇期节奏」节（兑现模板头预留的 WIP 占位；恒定文本按 user 层标注行事，逐章字节一致不破前缀缓存）；`to_user_material` 增「本章位置：」标注行；`build_chapter_context` 经位置单源产出（novel_id 缺失降级无标注）。
- **拆章**（`pos_golden3.prompt`）：补第 3 条「冲突叠加着走：上一章的冲突还没解决完，本章剧情就要让第二个冲突压上来——旧的未解、新的又起」，原 3/4 顺延；`pos_ch1` 已有「开场即冲突」不动（首章侧先例）。
- **测试**：`test_plan_pacing_rules` 补 golden3 关键词钉子两处（片段对拍＋出卡渲染注入）。

## Capabilities
specs sync 三处：
- `chapter-plan-ai`：golden3 片段枚举补「冲突叠加着走」
- `chapter-plot-items`：三版抽卡 Requirement 补【本章位置】分档 bullet＋场景
- `prose-writing`：新增「开篇期节奏分档」Requirement（system 恒定层组装既有的「节奏分档规则」枚举落两档具体口径）

## Impact
client/backend/{prompts/chapter_plot_draw.prompt,prompts/pos_golden3.prompt,prompts/write_chapter.prompt,chapters/ai_plan.py,chapters/ai_plot.py,write/chapter_writer.py}＋tests/test_plan_pacing_rules.py；pytest 相关套件全绿（prose_pipeline/chapter_writer(+context)/prompt_layering/plot_ai/plan_pacing_rules/plan_ai_t2+t3/write 系列）。

## 备注
- 事故留痕：编辑期间并行会话在同一共享检出连续合 PR（#543–#571），未提交的 chapter_writer.py 改动被冲掉（`git log -S` 全历史零命中证纯丢失）；因 #551/#559 已重构正文链路（WRITING_IRON_RULES 常量退役进模板、to_prompt→to_user_material），在当前 HEAD 按新架构重放，未从旧底座容器捞回。
- 演示栈镜像重建挂起：待共享检出的并行在途改动（prompt_refine 退役）落定后重建，避免烤进半成品。
