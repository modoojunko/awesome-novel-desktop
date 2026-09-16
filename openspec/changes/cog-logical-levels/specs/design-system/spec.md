# design-system 变更（增量）

## ADDED Requirements

### Requirement: 认知六层的理解层次标记

角色认知六层区块 SHALL 在层头补理解层次标记：六问 hint（还有谁？/我是谁？/为什么？/怎样做？/做什么？/何时何地？）与上三层（认知：世界观/自我观/价值观）/下三层（执行·结果：能力/行为/环境）分组标记；hint 与标记 SHALL 复用既有 `.cog-layer-tag` 视觉档位（或同档位等价类），SHALL NOT 新增胶囊形态。层名（世界观/自我观/价值观/能力/行为/环境）SHALL 保留既有叫法，理解层次对应词（精神/身份/信念价值/…）SHALL 只出现在 hint 文案，SHALL NOT 改写层名。s5 的展示口径 SHALL 显性化「宿命 · 精神层（我与世界的关系）」。

#### Scenario: 层头带六问 hint

- **WHEN** 作者展开认知六层的「自我观」层
- **THEN** 层头可见「我是谁？」hint 与上三层分组标记；s5 格位展示「宿命 · 精神层」口径

#### Scenario: 词表双源一致

- **WHEN** 后端 character_model 与前端 characterModel 的 label/口径变更
- **THEN** 两端同批修改且 parity 测试通过（镜像个数为零）
