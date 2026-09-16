# cog-logical-levels

## Why

角色认知六层的权威解读已由用户拍板为 NLP「理解层次」（Logical Levels）：精神（还有谁？）→ 身份（我是谁？）→ 信念价值（为什么？）→ 能力（怎样做？）→ 行为（做什么？）→ 环境（何时何地？）。实勘暴露三类问题：

1. **出稿错位（已热修、未收编）**：bootstrap/cog 两 prompt 此前无格位口径与主观认知铁律，真书主角卡六层被写成「世界设定＋简介冲突句」转录（地点进自我观、力量等级进价值观、两难冲突进性格与人际生态）。热修已注入格位口径与「认知六层铁律」（main@44b0e06/9b922d3/4705f50），但属应急、未走 openspec、无框架级回归测试。
2. **模型语义未显性化**：词表 label 与 UI 只呈现「认知层/执行层/结果层」的层标签，理解层次的六问（还有谁/我是谁/为什么/怎样做/做什么/何时何地）、上三层主宰下三层、六层一致连贯与「不协调＝戏剧张力」均未落到任何用户可见面或 AI 口径。
3. **精神层缺位**：理解层次最高层「精神」（我与世界的关系、意义、三赢）在现有 30 格中仅有 s5 宿命认知观一个隐性落点，label「宿命认知观」不显性；bootstrap 出稿范围不含 s5。

另有一致连贯的产品机会（用户已点名要立项）：**身心一致体检**——检查上三层（身份/信念价值）与下三层（能力/行为/环境）是否互相矛盾；角色卡里刻意保留的不协调正是压力源与成长弧线刻度，体检 SHALL 区分「戏剧张力（有意）」与「设定矛盾（无意）」两读。

## What Changes

- **认知口径正式收编**：bootstrap 与 cog 单格补全两 prompt 的「理解层次框架」段＋格位口径渲染＋认知六层铁律（主观认知、禁抄世界设定/简介冲突句、阶位名只进 p 层）从热修转为 change 内登记的正式契约，补框架级回归测试（prompt 渲染断言）
- **词表对齐理解层次（label 微调，键名冻结不动）**：层名/格 label 按六问校准——层 1 世界观（他眼中的世界＝信念基座，作品特有层，非 NLP 六层之一，显性登记此偏差）；s5 label「宿命认知观」→「宿命 · 精神层（我与世界的关系）」口径显性化；能力层口径补「有的选就是能力，情绪管理也算」；双源（backend character_model / frontend characterModel）同批＋parity 测试
- **bootstrap 出稿范围 ＋1 格**：s5（精神层落点）纳入 bootstrap fills（出稿键 10→11），认知补全同步；性别/年龄禁令不变
- **身心一致体检（新 AI 检查能力）**：check_character 扩展检查项——身份×行为、信念价值×能力使用、精神×环境三组「上三层 vs 下三层」一致性；每项两读输出：「不协调＝戏剧张力（有意保留）」或「矛盾（建议改）」；只提醒不拦确认
- **写章注入登记**：角色状态块现按六层主格（w1/s1/v1/p2/b1/e3）层序注入——本 change 显性登记该口径与理解层次的映射，不改行为
- **前端认知区**：认知六层区块头补理解层次六问 hint（还有谁/我是谁/为什么/怎样做/做什么/何时何地）与上三层/下三层分组标记；不新增弹层
- 明确不做（non-goals）：认知格键名/格位结构不变（30 格冻结）；层名不改写（世界观/自我观等既有层名保留，仅在 hint 中给出 NLP 对应）；不出「强制一致」的自动改写；不加独立体检端点（扩展现有 check）

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `character-settings`: 认知六层口径正式对齐理解层次——bootstrap/cog prompt 理解层次框架与格位口径成为契约（含回归断言）；s5 纳入 bootstrap 出稿范围；新增「身心一致体检」检查项（身份×行为、信念价值×能力、精神×环境，两读：戏剧张力/矛盾，只提醒不拦确认）；s5 label 口径显性化；性别年龄禁令不变
- `design-system`: 认知六层区块头补理解层次六问 hint 与上三层（认知）/下三层（执行·结果）分组标记的词表登记；既有 .cog-layer-tag 档位复用不新增形态
- `prompt-crafting`: 写章「角色初始状态」注入口径显性登记理解层次映射（六层主格按层序＝身份→信念→……的环境放映链），行为不变仅登记

## Impact

- **C端后端** `client/backend`：`settings/character_model.py`（s5 label 口径、check_items 加三组一致连贯项）；`prompts/settings_characters_bootstrap.prompt`、`settings_characters_cog.prompt`、`settings_characters_check.prompt`（框架段收编＋体检项）；`settings/characters_ai.py`（bootstrap fills 白名单 ＋s5、check 出参项数）；`tests/test_characters_ai.py`＋`tests/test_character_model.py`（框架断言＋双源 parity＋s5 用例）
- **C端前端** `client/frontend`：`lib/characterModel.ts`（s5 label 镜像）；`components/novel/settings/CharacterManager.tsx`（认知区层头六问 hint＋上下层分组标记）；`design/book.css`（如需分组标记样式，沿 .cog-layer-tag 档位）；e2e 视既有覆盖增补 1 例（体检含身心一致项）
- **迁移**：无（键名冻结、无 schema 变更；存量卡不动，体检对新旧卡同等可用）
- **设计工件**：认知区 hint 文案在本 change 内自查（文案量级小，无新原型屏；ADJUSTMENTS 登记 hint 词表即可）
