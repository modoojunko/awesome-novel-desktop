# cog-logical-levels · Design

## 评审结论与拍板落纸

- 认知六层权威解读＝NLP 理解层次（用户拍板）：精神（还有谁）/身份（我是谁）/信念价值（为什么）/能力（怎样做）/行为（做什么）/环境（何时何地）；上三层主宰下三层，下层是上层的放映；六层一致连贯＝身心一致；**层间刻意不协调＝压力源与戏剧张力**；成长弧线＝上层松动带动下层转变。
- 热修收编：main@44b0e06/9b922d3/4705f50 已把格位口径渲染与框架段打进 bootstrap/cog prompt——本 change 把这批热修转为正式契约＋回归断言，不再改 prompt 结构（只按本 change 增补 s5 与体检项）。

## 拍板采纳（评审/口径决策）

| 决策 | 采纳 |
|---|---|
| 层名是否改写 | 不改（世界观/自我观/价值观/能力/行为/环境保留），理解层次对应词只进 hint；世界观层登记为「作品特有认知基座」（NLP 六层之外） |
| 精神层落点 | s5 宿命认知观（label 口径显性化「宿命 · 精神层」）；纳入 bootstrap 出稿（可补键 10→11）与认知补全 |
| 身心一致体检形态 | 扩展现有 check_character 检查项（+3 项），不立新端点；沿用四态输出，「有意不协调」=达标＋note「张力：」前缀 |
| 键名/格位 | 30 格冻结不动；label 口径可调（双源同批） |

## 实现要点

### 词表（双源同批）
- backend `character_model.py`：s5 label →「宿命 · 精神层（我与世界的关系）」；`COG_FILL_KEYS` ＋s5（10→11；cog 补全 compute_targets 自动随动）；新增 `COG_LEVEL_BRIEFS`（理解层次六问＋上/下三层分组常量，供 prompt 渲染与前端镜像）
- frontend `characterModel.ts`：同批镜像（label、FILL keys、briefs）；`tests` parity（沿 test_shared_constants_parity 先例——确认既有 parity 测试覆盖 COG_FILL_KEYS，缺则补）

### prompt（三文件）
- `settings_characters_bootstrap.prompt` / `settings_characters_cog.prompt`：框架段已在 main——本 change 只把「框架段存在＋含六问＋含铁律禁令」写成回归断言（prompt 渲染捕获断言，沿 test_characters_ai 既有 _install_fake 手法）
- `settings_characters_check.prompt` 口径段：增三组一致连贯项的判定口径（张力 vs 矛盾的判别：卡面有无「改变弧线」注记/设定依据）
- `characters_ai.py`：`_BOOTSTRAP_FILL_KEYS` 自动随 COG_FILL_KEYS 扩 s5（ frozenset 并集，无独立改动）

### check 扩展（character_model.check_items + characters_ai.check_character）
- check_items 追加三项：`身份 × 行为`、`信念价值 × 能力`、`精神 × 环境`（项名照抄注入，服务端给定顺序）
- check_character 组卡时补上三层材料（s1/v1 与 s5 现值）＋下三层材料（p2/p6/b1/e3）——现有卡面渲染已带，无需新读
- 判定口径进 prompt（张力：卡面/设定有依据的不协调 → ok＋「张力：」前缀；无依据的自相矛盾 → 矛盾）
- 出参项数 +3，前端 chk 渲染按现有四态类映射，零改动

### 前端
- CharacterManager 认知区层头：`还有谁？`等六问 hint（沿 .cog-layer-tag 档位）＋上三层/下三层分组小标；s5 label 随词表
- 无新弹层、无新请求；体检结果渲染零改动（四态映射不变）

## 测试策略
- 双源 parity：COG_LAYERS/COG_FILL_KEYS/briefs 后端↔前端镜像相等
- prompt 渲染断言：bootstrap/cog 两 prompt 含六问、铁律禁令、s5 口径
- check：+3 项出参、张力/矛盾判定口径（mock AI）、项数顺序稳定
- e2e：体检含身心一致项 1 例（桩 AI）；既有 bootstrap/cog 用例回归
