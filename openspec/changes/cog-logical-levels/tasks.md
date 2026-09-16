# cog-logical-levels · Tasks

> 两批：§1–§3＝批1 口径与体检（后端＋前端 UI）；§4＝e2e 与验收。热修（main@44b0e06/9b922d3/4705f50）的 prompt 框架段在本 change 内转正登记。

## 1. 词表与口径（批1）

- [x] 1.1 backend `character_model.py`：s5 label→「宿命 · 精神层（我与世界的关系）」；`COG_FILL_KEYS` ＋s5；新增 `COG_LEVEL_BRIEFS`（六问＋上/下三层分组常量）；`check_items` 追加「身份 × 行为」「信念价值 × 能力」「精神 × 环境」三项
- [x] 1.2 frontend `characterModel.ts` 同批镜像（s5 label、FILL keys、briefs 常量）；parity 测试（COG_LAYERS/COG_FILL_KEYS/COG_LEVEL_BRIEFS 后端↔前端零镜像差）
- [x] 1.3 单测：compute_targets 含 s5；check_items 项数/顺序/项名快照

## 2. prompt 契约化（批1）

- [x] 2.1 `settings_characters_bootstrap.prompt`／`settings_characters_cog.prompt`：框架段（六问/主宰/一致连贯/不协调张力/铁律）与格位口径注入已在 main（热修 4705f50）——本 change 登记 + 渲染断言（bootstrap 与 cog 各 1 例：prompt 含六问、s5 口径、铁律禁令、格位 label）
- [x] 2.2 `settings_characters_check.prompt` 口径段增三组一致连贯判定（张力 vs 矛盾判别：有无「改变弧线」注记/设定依据）
- [x] 2.3 `characters_ai.py`：bootstrap fills 白名单随 COG_FILL_KEYS 自动含 s5（assert）；check 出参 +3 项（mock AI 断言项名与顺序）

## 3. 前端认知区（批1）

- [x] 3.1 `CharacterManager.tsx` 认知区层头：六问 hint＋上/下三层分组标记（沿 .cog-layer-tag 档位）；s5 label 随词表
- [x] 3.2 vitest：认知区层头 hint 渲染 + s5 口径显示

## 4. e2e 与验收（批2）

- [x] 4.1 e2e 增补：体检含「身份 × 行为」等身心一致项（桩 AI 出参含张力判读）；既有 bootstrap/cog 用例回归
- [x] 4.2 全量验收：容器 pytest 全量绿、vitest 绿、tsc 绿、design:lint/check 绿、e2e 本地栈全量绿
