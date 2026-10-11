## MODIFIED Requirements

### Requirement: 卷域关系与伏笔投影

- 角色关系页签（卷选中态）SHALL 呈现**截至本卷末章**的关系图（只读投影，无按章高亮、无增删控件），并按章纲出场角色登记集收窄（c-rel-graph-cast-filter，随章口径同章态：登记集＝主线章 `chapter_characters` 按 (volume_no, chapter_no) 截至本卷末累计，`GET /api/novels/{novel_id}/characters/graph?volume_no={卷号}`；未登记角色卡与仅涉未登记名的边 SHALL NOT 上图，登记过未建卡名 SHALL 以虚线占位节点上图）。
- 伏笔页签（卷选中态）SHALL 呈现**截至本卷末章**的伏笔台账投影，并标注本卷埋下/本卷回收/跨卷悬置归类；卷内 SHALL NOT 提供伏笔增删。
- 两页签 SHALL 复用章工作台同款图组件与台账组件，仅切换为卷域截止口径。

#### Scenario: 卷域关系截止口径

- **WHEN** 查看某卷的角色关系页签
- **THEN** 图呈现截至本卷末章的关系边（节点与边按章纲登记集收窄），无新增/编辑控件，图例说明截止口径与登记集过滤口径

#### Scenario: 卷域伏笔归组

- **WHEN** 查看某卷的伏笔页签
- **THEN** 台账标注每条伏笔「本卷埋下/本卷回收/跨卷悬置」，空组显示空态文案
