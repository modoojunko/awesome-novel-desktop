# design-system 变更（增量）

## ADDED Requirements

### Requirement: 设定页内页签与文风量化词表

- 设定面板内层级 SHALL 允许页签（`.settings-v .ptabs/.ptab`），并在 ADJUSTMENTS 登记页签回归例外（仅面板内层级，面板间导航仍走左树）；页签激活态沿 modnav 口径（accent 下划线）。
- 文风面板 SHALL 收编以下 settings-v 作用域词表（book.css 本地段，随 ADJUSTMENTS 登记映射）：锚定块 `.fblock/.fb-head/.fb-no/.hint` 与锚定链 `.anchor-chain/.ac-node/.ac-arrow/.ac-note`；基线 `.dims/.dims-meta/.bx-row/.bx-head/.bx-name/.bx-dims/.bx-vals/.bx-note/.lock-btn/.five-bar/.fb-legend/.det-row`；蒸馏 `.sample-box/.sample-row/.s-name/.s-cnt/.s-check/.sample-total/.dist-step/.ds-no/.ds-b/.ds-ok/.portrait/.pz-head/.pz-note/.pz-ask/.pz-act`。
- `Cfg` 折叠组件 SHALL 加可选 `sum` 摘要位（组头一行灰字，收起态也传达信息）；`ListEditor` SHALL 加可选上移与 `x/y` 计数（`maxItems` 到量隐藏添加钮已有）；均 SHALL 以可选 prop 扩展，SHALL NOT 新造平行词表。
- `.hk-sec-label/.hk-sl-tag` SHALL 提升为 `.settings-v .sec-label/.sl-tag` 共享类（hk-* 保留别名或机械改名，映射表随 ADJUSTMENTS 登记），SHALL NOT 长期两套。
- 已撤并入口的遗留词表（src-card 家族、genre-grid/g-chip、badge.done）SHALL NOT 入库。
- 基线锁定按钮 SHALL 带 `aria-pressed`；五层占比条为纯装饰 SHALL 带 `aria-hidden`。

#### Scenario: 页签例外已登记

- **WHEN** design:lint 检查 settings-v 作用域新类
- **THEN** ptabs/ptab 在 ADJUSTMENTS 例外清单内放行；面板间导航未出现第二套页签

#### Scenario: 锁定状态可被辅助技术读出

- **WHEN** 基线行「篇幅配比」处于锁定态
- **THEN** 锁定按钮带 aria-pressed=true，五层条 aria-hidden=true
