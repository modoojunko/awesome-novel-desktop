## REMOVED Requirements

### Requirement: 卷节点点击弹出右侧抽屉（卷纲编辑）

**Reason**: 「右侧抽屉 + `VolumeEditor`」形态已被 book.html v2 工作台改版（#183/#184，左树选中卷 → 中栏面板）取代并漂移至今，与本 change 的「卷视图整页四页签」新形态直接冲突——保留会让 canonical spec 描述一个不存在的交互。

**Migration**: 无用户、无发布包需要迁移；卷节点点击行为口径由本 delta 的 ADDED 需求「卷节点点击打开中栏卷视图（卷 · 分卷计划）」承接，`VolumeEditor` 复用口径随 `VolumePanel` 重构一并退役。

## ADDED Requirements

### Requirement: 卷节点点击打开中栏卷视图（卷 · 分卷计划）

- Clicking a volume node in the left tree SHALL open that volume's 卷视图 in the 中栏（头部＋「卷纲｜本卷章节｜角色关系｜伏笔」四页签；行为细节见 volume-outline 能力）；右侧抽屉形态（backdrop/400px 面板/Escape 关闭）与 `VolumeEditor` 复用口径 SHALL 退役。
- Selecting a chapter from within the 卷视图（「本卷章节」页签点行）SHALL switch the 中栏 to that chapter's workspace and sync the left-tree selection.
- Creating a volume (`创建第一卷` / tree「新建卷」) SHALL select the new volume and open its 卷视图 in the 中栏（离开后对同一选中不重复自动打开）。

#### Scenario: Click volume opens middle-column volume view
- Given a novel with a volume and a chapter
- When the user clicks the volume node in the tree
- Then the 中栏 renders the volume view with the four tabs and no right-side drawer appears

#### Scenario: 卷视图内进入章节
- Given 卷视图「本卷章节」页签可见
- When 点击其中一章
- Then 中栏切换为该章工作台，左树选中同步到该章
