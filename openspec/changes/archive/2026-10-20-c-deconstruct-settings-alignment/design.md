# 拆书输出对齐设定页字段契约 · 设计

## D1. 契约方向：设定页为准绳

设定页 schema 不动；拆书输出契约向设定页字段对齐。提示词负责「按字段要求归纳产出」，apply 负责「逐字段映射＋旧形状双认」，渲染负责「作家视角呈现」。三层各自单源：提示词仓模板（输出契约）、apply.py（映射）、pipeline._render_md（标签表 _MD_LABELS）。

## D2. 输出契约（提示词仓 #18）

- 主线剧情：fullstory（300–500 字全书全景散文）＋arcs（3–8 条全书级弧，可跨段）＋ending{scene,hero,tone}；SHALL NOT 按材料分段机械切分。
- 文风：role（≤40 字身份一句话）＋rules/craft（「名：怎么用」条目）＋examples（原文短例）；narration/dialogue/rhythm 旧形状退役。
- 角色：+aliases 数组；plot 合并跨材料行动。关系：+stance。题材：+{genre_vocab} 词表逐字选词（词表外降 low）。伏笔：+type 九值闭集＋priority。
- reduce 维度分策略（按 {dim_key} 分支）：实体类并集补全；mainplot 归纳重写（全书级弧＋fullstory 重写＋ending 取最末段）；foreshadow 跨段埋收接线；style/world.stage 全书视角重写。

## D3. apply 逐字段映射（桌面仓 #906/#907/#908）

- mainplot：story_arc.fullstory＝fullstory 直灌（弧条目串→旧 ending 字符串→原文未明确 四档兜底链）；story_arc.ending 三格回填，「原文未明确」置空。
- 文风：role/rules/craft 直灌三区；旧形状 narration/dialogue/rhythm 降级双认（回退只拼有内容字段）。
- 角色 aliases 数组（旧 alias 字符串双认）；关系 stance；伏笔 type/priority/回收状态→resolved（回收章并入描述）；batch_create_hooks 扩展可选三字段（闭集白名单，越界回落默认；abandoned 不收）。

## D4. 渲染（#907）

键名→中文标签（_MD_LABELS 单源，未登记回退原键）；confidence 值翻高/中/低，单值 confidence 并抬头不单独成节；对象值逐字段展开（SHALL NOT str(dict)）；标量节裸值；空列表/空对象/空标量无正文不出节；页脚＝作家口径说明（章号＝出处、可信度＝依据程度）。

## D5. 回归纪律

后端全量 SHALL 带 PROMPT_PACK_DEV_DIR 真跑（needs_prompts 缺源跳过会掩护存量回归——本次即靠带源真跑暴露 test_volume_plan_ai 过期期望并修正）。

## Risks / Trade-offs

- 旧任务产物重灌依赖 apply 双认降级；新契约字段在旧产物缺格时落默认（不脑补）。
- 提示词 CI 受 Actions 配额墙限制：本地同闸门全绿（109 passed）为验收口径，额度恢复后发布提示词包。
