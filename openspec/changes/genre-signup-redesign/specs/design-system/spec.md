## ADDED Requirements

### Requirement: AI 写作助手卡片与结果区组件词汇
- 新增「AI 写作助手」卡片组件（C端设定视图右栏）：PRO 徽标并入卡片头部＋标题＋一行套餐归属/只加工不代写；内部为**并列能力行**（每行＝名称上＋描述下从属＋右侧箭头，整行可点）；底部一条来源/去向声明。命名 `.rail-assist` + `.ra-*`。
- 新增「AI 结果区」组件 `.ai-sink`：`TintPanel`（fg-soft 平底）只读说明，置于左侧对应输入框/字段**正下方**；顶部操作名标签（`.aiz-head`）＋候选文本＋采纳/重试按钮。必须用 fg-soft，不得用 `--surface`（surface 是可编辑/可操作容器底色，与输入框撞色会误判结果区可编辑）。
- 这些是 **C端局部组件类**（不在两端共享 `base.css` 共享段），归 C端工作台设定视图作用域（`book.css` 或设定视图局部样式）；只复用共享令牌（`--fg-soft`/`--surface`/`--border`），不新增全局 token。
- 能力行在无套餐时 SHALL 复用既有「可见 + 锁定」门控（见 Requirement: Free vs PRO gating stays visible）：整卡降透明、徽标转灰、行降透明 + cursor:not-allowed，点击给统一升级提示，不各自弹窗；锁定态卡片名 `.rail-assist.locked`。门控 key 用已登记的 `settings-ai-fields`（memberOnly），而非未登记的新 key。

#### Scenario: 结果区不用可编辑底色
- Given 简介/题材 AI 反馈已产出
- When 查看结果区样式
- Then 结果为 fg-soft 只读底（TintPanel），与输入框（surface）可区分，误判不可编辑

#### Scenario: 能力行锁定态可见且不可点
- Given 无套餐用户
- When 查看 AI 写作助手卡片
- Then 能力行名称/描述可见、整体降透明、点击给升级提示且不产出结果

## MODIFIED Requirements

（无 — 均为新增组件词汇，未改动既有组件/状态定义。）
