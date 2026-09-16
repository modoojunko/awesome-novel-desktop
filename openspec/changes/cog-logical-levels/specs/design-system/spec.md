# design-system 变更（增量）

## ADDED Requirements

### Requirement: 认知六层的理解层次标记

角色认知六层区块 SHALL 在层头补一句大白话 hint（给作家看的，不出现「理解层次/NLP/上三层下三层/精神层」等术语）：
- 世界观：「他眼里的世界是什么样的？」
- 自我观：「他把自己当成谁？」
- 价值观：「他在乎什么？为什么做这些事？」
- 能力：「他能做什么？怎么做到的？」
- 行为：「遇到事，他会怎么做？」
- 环境：「他身边有什么人、什么事？」
s5 的展示口径 SHALL 为「宿命认知观」＋hint「他和这个世界到底是怎么回事？这条路走到头，他注定要面对什么？」。层名 SHALL 保留既有叫法不改写。hint 与分组标记 SHALL 复用既有 `.cog-layer-tag` 档位（或同档位等价类），SHALL NOT 新增胶囊形态。

#### Scenario: 层头带大白话 hint

- **WHEN** 作者展开认知六层的「自我观」层
- **THEN** 层头可见 hint「他把自己当成谁？」；s5 格位 hint 为「他和这个世界到底是怎么回事？这条路走到头，他注定要面对什么？」

#### Scenario: 词表双源一致

- **WHEN** 后端 character_model 与前端 characterModel 的 label/口径变更
- **THEN** 两端同批修改且 parity 测试通过（镜像个数为零）
