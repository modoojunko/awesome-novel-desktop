# design-system Delta — 出场角色胶囊身份小标与悬停身份卡词汇

## ADDED Requirements

### Requirement: 出场角色胶囊身份小标与悬停身份卡词汇

- 胶囊内身份小标 SHALL 沿「chip 内小标」既有形制（`.no-card` 同款 10px 胶囊），登记为 `.cast-role`，四档配色沿既有**角色类型色语言**（关系图 `.rg-node.role-*` 先例）：主角 accent、反派 err、配角 muted、路人虚线 muted；SHALL NOT 为本屏发明新状态色、SHALL NOT 引入 info/ok/warn/err 之外语气档、SHALL NOT 新增第四种胶囊形态。
- 悬停身份卡 SHALL 登记为 `.cast-hover` 一族（面卡＋标题行＋别名行＋人设行＋档案行＋脚注行），仅用既有 token（`--surface/--border/--muted/--fg-soft/--shadow-card` 与既有字号档 10/11/11.5/12/12.5/13.5px；浮层阴影沿 `.mp-panel`/`.acct-menu` 的 `--shadow-card` 先例），SHALL NOT 引入新令牌档位或裸色值。
- 身份卡浮层 SHALL 走既有「portal 到 body ＋ fixed 定位」先例（`.mp-panel` 的滚动裁剪对策），定位 SHALL 按 `html` 的 zoom（大屏缩放层）折算后再铺到 fixed 的 top/left 上，SHALL NOT 把 `getBoundingClientRect()` 视觉值直铺入被 zoom 的子树。

#### Scenario: 词汇无新增语气档与胶囊形态

- **WHEN** 检查本次新增样式（`.cast-role` / `.cast-hover` 一族）
- **THEN** 只出现既有 token 与既有字号档，无裸 hex/rgb、无 emoji、无 info/ok/warn/err 之外的新语气词，身份小标仍是 10px 小标形制（非新胶囊形态）

#### Scenario: 身份卡不被滚动容器裁剪

- **WHEN** 章纲面板可滚动且悬停身份卡已展开
- **THEN** 身份卡完整可见（portal 挂 body、fixed 定位），不被 `.og-pane` 的滚动裁切

#### Scenario: 大屏缩放下定位不双重放大

- **WHEN** 大屏缩放层 `--ui-zoom > 1` 时悬停任一胶囊
- **THEN** 身份卡锚在该胶囊旁（按 zoom 折算后的坐标铺 fixed），不偏移、不放大两倍
