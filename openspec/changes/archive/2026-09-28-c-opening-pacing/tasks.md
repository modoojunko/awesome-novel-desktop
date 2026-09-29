# c-opening-pacing 任务（回填执行记录）

- [x] 1. 剧情抽卡分档：chapter_plot_draw 规则 4 改「本章位置」分档＋ai_plot 素材装【本章位置】块（首章入局／开篇期叠加）
- [x] 2. 正文分档：write_chapter.prompt 增「## 开篇期节奏」节（兑现模板头 WIP 占位）＋to_user_material「本章位置：」行＋build_chapter_context 位置单源取数
- [x] 3. 拆章补条：pos_golden3 加第 3 条「冲突叠加着走」＋test_plan_pacing_rules 两处关键词钉子
- [x] 4. 位置判定单源：ai_plan.global_chapter_position/position_label（chapter_position_tags 复用，滤 ghost；_global_chapter_no 改收 project_id）
- [x] 5. 全量相关测试绿＋PR #574 合入 main（f738ebfb）；期间并行会话冲掉未提交 chapter_writer.py，在新架构上重放（见 proposal 备注）
