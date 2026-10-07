## ADDED Requirements

### Requirement: C端 toast 自动消失与可关闭基线

- C端 全站 toast（底部居中深底胶囊）SHALL 默认 **3 秒自动消失**；多条叠放时 SHALL 各自独立计时、互不清除。
- 每条 toast SHALL 带 **× 手动关闭钮**（无障碍名「关闭」）；点击 × SHALL 立即收掉该条。
- toast SHALL NOT 常驻屏幕：不得存在永不自动消失的 toast（既有「sticky 常驻回执」口径自本 change 起退役）。
- 撤销类入口（如剧情采纳回执的「撤销」链接）SHALL 随所在 toast 存活——toast 自动消失或被 × 关闭后，
  该撤销入口不再可得；需要更长撤销窗口的场景走面板内自管回执（如软删除 8 秒撤销窗口，§12 L4），SHALL NOT
  借 toast 常驻实现。
- 自动消失与 × 关闭 SHALL NOT 中断 toast 内动作入口——窗口内点击撤销/补救链接 SHALL 照常生效；
  动作处理方需要时可在自身回调内主动收掉该条（如剧情撤销链路经「编辑即收」），未主动收的按本基线自动收口。

#### Scenario: 三秒自动消失

- **WHEN** 任一操作弹出 toast 且作者 3 秒内不做任何点击
- **THEN** 该 toast 自动消失，屏幕恢复干净；同屏多条 toast 各自计时、先到先走

#### Scenario: × 立即收掉

- **WHEN** toast 在场时作者点其右侧 ×
- **THEN** 该条立即消失，其余 toast 不受影响

#### Scenario: 撤销入口只在窗口内可得

- **WHEN** 带撤销链接的 toast 弹出后作者未在窗口内点击，toast 自动消失
- **THEN** 撤销入口一并消失，无法再触发该次撤销；已生效的操作结果保持不变
