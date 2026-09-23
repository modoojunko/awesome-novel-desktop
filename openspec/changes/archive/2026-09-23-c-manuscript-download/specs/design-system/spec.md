## MODIFIED Requirements

### Requirement: Component vocabulary reuse before invention
- Buttons SHALL map to the existing `.btn` size/variant ladder; C-end wrappers around it MUST NOT be introduced, and S-end shell components SHALL compile down to those same classes.
- Static capsules belong to pill roles (tag/status/count); clickable capsule-like controls belong to the chip family.
- File-format checkbox rows in the download overlay (`.ex-fmt`) SHALL be a single reusable control (role=checkbox semantics, visible selected state) rather than ad-hoc toggle markup, and its selected state SHALL use token-derived color-mix values only.
- Progress lists in task overlays (`.ex-steps`) SHALL express per-item state as text (等待 / 下载中 / 完成) with the ok tone reserved for the completed state; they MUST NOT animate prose or the reading area.
- Destructive confirmations SHALL render through an in-app modal confirm (no native `window.confirm`), listing affected items as inventory when deletion cascades.
- Empty states SHALL offer at least one actionable exit alongside the descriptive line.

#### Scenario: Delete affecting linked content
- Given deleting a config that books depend on
- When the user confirms
- Then an in-app dialog lists the affected items as inventory chips before deletion executes

#### Scenario: 格式勾选行即统一控件
- Given 下载成稿弹层渲染三种格式
- When 用户点选其中一行
- Then 该行呈现选中态（token 派生配色）且可键盘操作，另两行保持未选态
