# c-cog-cells-slim — 任务

## 1. 后端

- [x] 1.1 `settings/character_model.py`：COG_LAYERS 退役 19 格（w2 w3 w4 / s2 s3 s4 / v2 v3 v4 / p1 p5 / b2 b3 b4 b5 / e1 e2 e4 e5），注释 30 格 → 11 格；COG_FILL_KEYS 派生式与注记同步（保留集 = 全集）。
- [x] 1.2 `characters/legacy_map.py`：LEGACY_FIELD_MAP 落点 world_view→w1、self_image→s1、values→v1、environment→e3；docstring 同步。
- [x] 1.3 `scripts/upgrade_drill.py`：角色段断言 g["w3"]/g["s2"]/g["v2"]/g["e1"] → g["w1"]/g["s1"]/g["v1"]/g["e3"]。

## 2. 前端

- [x] 2.1 `src/lib/characterModel.ts`：COG_LAYERS 镜像删同 19 格，注释同步（parity 对拍锁逐字一致）。
- [x] 2.2 CharacterManager 认知区复跑确认自动收窄（无硬编码格位/计数残留；`30 格` 等字样全仓清零）。

## 3. 测试

- [x] 3.1 `tests/test_character_model.py`：`len(COG_KEYS) == 30` → `== 11`；补一条「退役键不在写入白名单」钉子。
- [x] 3.2 `tests/test_characters_ai.py`：skipped 键示例 "e5" → 换保留键（如 "s5"）。
- [x] 3.3 `tests/test_shared_constants_parity.py` 随镜像自动过；后端全量 pytest + 前端全量 vitest 绿。
- [x] 3.4 e2e：`settings-forms.spec.ts` 认知区用例（六问 hint / s5 格位 hint）与门禁文案用例复跑绿。

## 4. 收尾

- [x] 4.1 openspec sync＋archive 随实现 PR（boss 规矩）；ADJUSTMENTS 不涉及。
- [ ] 4.2 （余项）真机抽检：角色屏认知区 11 格、AI 认知补充出卡键位、写章状态块六主格照旧。
