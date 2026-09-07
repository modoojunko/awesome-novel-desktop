# 1.2 映射矩阵 × entitlement-defaults.json 交叉核对（2026-09-06）

对照：PRD §6.6 矩阵 ↔ docs/contracts/entitlement-defaults.json ↔ client/frontend/src/lib/features.ts 12 key

| FeatureKey | features.ts memberOnly | JSON 覆盖位置 | 结论 |
|---|---|---|---|
| tree-crud / prose-edit / version-history / archive / volume-chapter-config / advanced-config-entry / settings-7-items | false（免费） | 不进 features 数组（免费能力不做 key 门禁，与 PRD"免费基线保留"一致） | ✅ |
| settings-ai-fields | true | trial/pro/max features 含 | ✅ |
| outline-advanced-fields | true | 同上 | ✅ |
| ai-generate | true | 同上 | ✅ |
| prompt-panel | true | 同上 | ✅ |
| ai-model | true | 同上 | ✅ |
| 多本书 | —（不走 key） | limits.max_projects：none/free=1，trial/pro/max=null | ✅ |

结论：12 key 全部落位，免费/会员差异与矩阵一致，无缺漏。免费 7 项不设 key（现有代码本就无门禁点），JSON 只表达"收费维度的差异"。
