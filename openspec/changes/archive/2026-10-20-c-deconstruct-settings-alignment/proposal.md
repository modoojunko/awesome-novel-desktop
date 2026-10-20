# 拆书输出对齐设定页字段契约（c-deconstruct-settings-alignment）

## Why

用户审阅链暴露三层病：①作家看不懂拆书产物（`## intro`/`confidence: high` 英文键名裸奔、三铁律内部话术页脚）；②主线剧情产物是「各章节段拼接」，没有全书归纳（reduce 通用合并对实体类正确、对剧情弧＝拼接）；③拆书回填设定页大片字段空或内容不合身（ending 三格/tone/craft/aliases/stance/伏笔回收状态从未回填，fullstory 灌的是弧条目串）。拍板（2026-10-20）：**设定页契约为准绳**——拆书按设定项字段要求归纳提炼，apply 逐字段对齐。

## What Changes

- **提示词仓（#18）**：十维度输出契约改为设定页字段形状——主线剧情补 fullstory 全景叙述＋ending 三格（scene/hero/tone）、弧按全书起承转合归纳；文风改三区（role/rules/craft/examples）；角色补 aliases；关系补 stance；题材注入词表逐字选词；伏笔补 type 九值闭集＋priority。reduce 模板维度分策略：实体类并集补全／mainplot 归纳重写全书级弧／伏笔跨段埋收接线／文风与舞台全书视角重写。
- **桌面仓（#906/#907/#908）**：apply 逐字段回填（fullstory 全景直灌＋ending 三格「原文未明确」置空＋文风三区旧形状双认＋aliases＋stance＋伏笔 type/priority/回收状态→resolved）；batch_create_hooks 扩展 type/priority/status；pipeline 注入 dim_key 与题材库词表；_render_md 作家视角（键名翻中文标签、可信度翻高/中/低、单值可信度并抬头、对象值逐字段展开、无正文不出节、页脚作家口径）。
- 附带修复：test_volume_plan_ai 存量过期期望（needs_prompts 缺源跳过掩护的全书号口径遗留）。

## Design Impact

- 仅 C 端；提示词模板在私有提示词仓（#18），本仓改 deconstruct 管线/apply/hooks_service。
- 消费面：拆书产物 md（结果目录/只读预览/本地导出）与建书灌设定；SHALL NOT 改任何设定页既有 schema。
- 旧产物兼容：apply 对旧形状（ending 字符串、narration/dialogue/rhythm、alias 单数）降级双认，存量任务重灌不丢信息。

## Verification

- 后端带提示词源全量 2621–2623 passed / 0 failed（needs_prompts 文件真跑）；提示词仓 109 passed（含 7 个新契约钉）。
- 容器内指纹与主线形状渲染实跑断言通过。
- 实现：#906（842d000）/#907（b8023750）/#908（933cd79b）＋prompts #18（774bbb0，CI 配额墙本地全绿验收）。
