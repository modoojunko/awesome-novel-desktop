## ADDED Requirements

### Requirement: 跨卷实际收尾包含历史章

- 卷纲/进场材料解析「上一卷实际收尾」时，上一卷主线的 archived 章与历史章（`origin=import && status!=archived`）SHALL 都算「已经写到」；取其中章序最后的一章，用其摘要/标题作为实际收尾。
- 若上一卷只有 draft/planned 章、没有任何 archived 或历史章，SHALL 保持既有口径回落到卷纲预期结局。
- 历史章被编辑后，实际收尾 SHALL 使用最新摘要/标题。

#### Scenario: 上一卷以导入章收尾
- **WHEN** 第 1 卷最后一章是 origin=import 的第 24 章，作者打开第 2 卷卷纲
- **THEN** 进场材料给第 24 章的摘要/标题，并注明「实际收尾」，不回落卷纲预期

#### Scenario: 上一卷未写到
- **WHEN** 上一卷只有拟定章，没有 archived/历史章
- **THEN** 保持既有「预期结局（还没写到，先按卷纲）」口径
