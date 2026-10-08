# design-system Delta — 生成弹窗模型选择器词汇

## ADDED Requirements

### Requirement: C端 生成弹窗模型选择器词汇

- 「AI 生成正文」弹窗的模型选择位 SHALL 复用 C端 model-config 作用域既有的**组合框＋弹层**词汇（`.mp-wrap` / `.mp-panel` / `.mp-list` / `.mp-item`，含 `.cur`/`.on` 状态位），SHALL NOT 新建平行词汇、SHALL NOT 用原生 `<select>`。
- 本次新增三词并登记：`.mp-trigger`（触发位：字段触感 + 「配置名 · 模型名」值文案 + chevron）、`.mp-group`（弹层内配置组头：配置名 + 供应商，muted 小字）、`.mp-flag`（模型行尾注「本书模型」标记，muted 小字）；既有 `.mp-item` 由 block 改 flex 以容纳尾注（行型不变）。三词 SHALL 只用既有 token（`--muted`/`--border` 与既有字号档），SHALL NOT 引入新令牌档位、新语气档或第四种胶囊形态。
- 弹层 SHALL 走既有「portal 到 body + fixed 定位」先例（`.mp-panel` 的 Modal 裁剪对策），SHALL NOT 在弹窗卡内做绝对定位浮层。

#### Scenario: 弹层不被弹窗裁剪

- **WHEN** 生成弹窗内容区可滚动且弹层已展开
- **THEN** 弹层完整可见（portal 挂 body、fixed 定位），不被 `.mcard` 的滚动裁剪

#### Scenario: 词汇无新增语气档

- **WHEN** 检查本次新增样式（`.mp-group`/`.mp-flag`）
- **THEN** 只出现既有 token 与既有字号档，无裸 hex/rgb、无 emoji、无 info/ok/warn/err 之外的新语气词
