# 卷的瘦身与三选一抽卡 — 设计

## Context

c-volume-plan-ai 已上线（三端点/规划台/回填/体检）；用户四轮设计收敛（09-21）定稿：字段按
消费裁剪、角色下沉到章聚合、付费入口 roguelike 三选一。原型（drafts/整书拆纲.html +
prototypes/book.html）已按终版落定并 Playwright 验证。

## Goals / Non-Goals

**Goals:** 卷字段终版（增 antagonist 两列；退役 template_name/plan_line/goal/cast 行集）；
四问双路（付费三选一抽卡确认即成卷／免费四问手写）；添加卷弹窗四问化；体检对抗物三判据；
卷角色聚合只读视图（读侧）。

**Non-Goals（章层后续 todo）：** 章纲点新名字建卡提示；正文提示词消费「本卷在场的人」；
体检「登记没戏份」改读聚合清单；退役列/表的物理清理。

## Decisions

1. **退役不清库**：template_name/plan_line/goal 与 volume_cast_members 停止读写，DDL 不动、
   不做迁移（additive 历史列无害；「无真实用户」窗口允许干净停用，物理清理挂 todo）。
2. **抽卡确认＝端点串接零新增**：选定卡（options 的套）→ 前端调 expand（line=走向、
   antagonist 带入）→ 草稿＋四问一次走既有建卷/更新卷接口落库。「确认即成卷」没有新语义，
   只是省掉回填/保存的中间 UI。
3. **聚合视图在 get_volume 读侧实现**：cast_members 改由卷下各章章纲 characters 合集计算
   （主角置顶＝角色表 role=主角；坎标反派＝antagonist_type=人物时标注），不落新表；章数据
   变化即变。写侧登记天然在章纲（既有字段）。
4. **plan_line 退役语义**：规划台那句话是会话期素材（expand 的 author_line），铺完长进
   主旨；「展开依据」行撤出卷纲；体检查「不改走向」对照主旨而非历史原话。
5. **goal 并入 ending**：卷末结局一栏可含「收在哪＋局面变成什么样」两小句；装配文本
   `- 预期结局：` 行承载；旧值迁移＝展示期拼接（读侧 goal 非空时并入 ending 尾句显示，
   写侧不再独立保存）。
6. **付费抽卡首屏自动调 options**；「换 3 套」＝重调（重试温度档）；免费无卡直接四问页。
7. **对抗物判据并入 volume_rules.prompt 单源**（对拍随迁）；体检素材加上一卷/本卷对抗物
   两行；玄幻/都市题材段 boss 台阶默认提示在 build_genre_section。

## Risks / Trade-offs

- 旧卷纲存量 goal/plan_line/结构模板数据不再显示——可接受（无真实用户；spec 已登记退役）。
- 聚合视图依赖章纲 characters 质量（空章纲＝清单空）——空态文案已定「写到谁就有谁」。
- 抽卡确认即落库跳过人工检查——AI 输出仍有字段上限与自查；落点后进卷纲随时改；属用户
  点名的体验取向（决策在卡上做，不在表单里做）。
