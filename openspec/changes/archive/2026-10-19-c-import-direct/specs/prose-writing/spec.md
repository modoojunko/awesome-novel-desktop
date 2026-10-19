## ADDED Requirements

### Requirement: 历史章作为上一章上下文

- 写正文素材组装「上一章」上下文时，若上一章是历史章（`origin=import && status!=archived`），系统 SHALL 用该章摘要；无摘要时 SHALL 用标题＋正文首段 ≤200 字；SHALL NOT 返回「上一章未归档」或空字符串。
- 若上一章已归档，SHALL 保持既有口径（摘要/实际收尾/未归档提示按原规则）；若没有上一章，SHALL 保持空。
- 历史章被编辑后，上一章上下文 SHALL 使用最新正文摘要，SHALL NOT 继续引用旧内容。
- 本要求 SHALL NOT 改变 story_state 的折叠规则（历史章的逐章基线由 `chapter-dossier` 的后续 change 提供；本 change A 路无基线）。

#### Scenario: 导入书的上一章
- **WHEN** 作者写第 43 章，上一章第 42 章是 origin=import 且有正文
- **THEN** 上一章上下文给第 42 章的摘要或首段 ≤200 字，不出现「上一章未归档」

#### Scenario: 历史章编辑后更新
- **WHEN** 作者修改第 42 章正文后写第 43 章
- **THEN** 上一章上下文使用修改后的最新内容，不引用旧摘要

#### Scenario: 已归档章口径不变
- **WHEN** 上一章是 archived 作者章
- **THEN** 上一章上下文继续按既有归档口径生成
