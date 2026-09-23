## REMOVED Requirements

### Requirement: 待完本提示条

（works.html v2 删除 `#readySlot` 提示条——「在哪完本」职责并入：ready 分组头 `去完本`（works-toolbar「生命周期分组视图」）＋待完本卡页脚 `完本`（本 capability 卡片 requirement）＋「全部」视图待完本恒置顶（works-toolbar「排序语义」）。）

## MODIFIED Requirements

### Requirement: 书架卡片四态徽章与分状态页脚

- 书架卡片阶段徽章 SHALL 呈现四态（单源 `lib/novelStage.ts`）：`setting`＝设定中、`writing`＝写作中、`ready`＝**待完本**（accent 底）、`done`＝**已完结**（ok 底）；「已归档」标签 SHALL 退役。判据：`finished_at` 非空→已完结；主线章数 ≤0→设定中；主线全归档未完结→待完本；其余→写作中。
- 卡片页脚 SHALL 分状态呈现：
  - **待完本**：「全书 N 章已归档」＋`回看`（secondary sm，落预览视图）＋`完本`（primary sm，打开完本清单弹窗）；
  - **已完结**：「完结于 X」（相对时间口径与「更新于」一致）＋`回看`（secondary sm，落预览视图，同一次性落点覆盖机制）＋`查看`（落预览视图）；
  - **写作中/设定中**：「更新于 X」＋`继续创作`（现状不变）。
- 卡片本体点击落点 SHALL 与标签同结论：待完本落写作视图；已完结落预览视图（现状口径）；其余不变。
- ⋯ 菜单（重命名/删除）对四态书 SHALL 均可用；已完结书 SHALL 增「完本信息 · 撤完本」项，点击打开完本清单弹窗（已完结态）。

#### Scenario: 全归档未完结书呈现待完本

- **WHEN** 书架上一本书主线章全部归档且 `finished_at` 为空
- **THEN** 徽章为「待完本」，页脚为「全书 N 章已归档」＋`回看`＋`完本`，卡片点击落写作视图

#### Scenario: 已完结书呈现完结页脚

- **WHEN** 一本书 `finished_at` 非空
- **THEN** 徽章为「已完结」，页脚为「完结于 X」＋`回看`＋`查看`，⋯ 菜单含「完本信息 · 撤完本」

#### Scenario: 待完本卡回看落预览

- **WHEN** 在待完本书卡片页脚点「回看」
- **THEN** 打开该书且落预览视图（一次性落点覆盖，刷新或再次进入不受影响）
