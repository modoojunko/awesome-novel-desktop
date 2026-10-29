# c-cog-cells-slim — 认知六层瘦身：退役 19 格零填充格位（30 格 → 11 格）

## Why

认知六层现有 30 格，其中 **19 格从未被填过**：AI 补全的候选键只有 11 格（六层主格 + 必填 w5/p3/p4 + 技能 p6 + 宿命 s5），其余 19 格是纯手填格。本地库实测（99 张角色卡，覆盖全部在写书）：19 格历史填充数全部为 **0**，全部认知内容集中在 11 格 AI 候选格上。用户实测反馈同向——角色卡上成排的空格子（局势主观判定 / 世界运行规则信仰 / 人性通用认知……）既不会手填、AI 也不碰，只制造「还差很多」的心理负担与界面噪音。

## What Changes

- 认知六层退役 19 格零填充格位，保留 11 格（全部在 AI 认知补充候选内）：
  - 01 世界观：w1 世界规则认知度、w5 核心认知盲区（必填）；
  - 02 自我观：s1 自我身份定位、s5 宿命认知观；
  - 03 价值观：v1 核心追求；
  - 04 能力：p2 后天综合能力（金手指）、p6 技能 · 习得与来源、p3 能力上限阈值（必填）、p4 能力代价 · 短板（必填）；
  - 05 行为：b1 性格 · 待人态度；
  - 06 环境：e3 人际生态环境。
- v1→v2 老字段映射落点随迁：world_view→cog.**w1**、self_image→cog.**s1**、values→cog.**v1**、environment→cog.**e3**（原落点 w3/s2/v2/e1 已退役，改落层主格；原文双写 legacy 的回滚基准不变）。
- 退役格位：界面不再呈现、单格写入白名单拒绝、AI 认知补充不再出键；JSON 列中的历史残留键（如有）读取侧忽略、**零迁移**。
- 门禁（w5/p3/p4）、写章状态块（六层主格）、一致性体检（按层）、认知补充出卡口径均不受影响（所引用格全部保留）。

## Capabilities

### Modified Capabilities

- `character-settings`：角色卡字段契约新增「认知格位退役」场景——退役格位零迁移、读写两侧口径（不呈现 / 不写入 / 残留键忽略）。

## Impact

- `client/backend/settings/character_model.py`（COG_LAYERS 删 19 格＋注释）、`client/backend/characters/legacy_map.py`（四处落点改层主格）、`client/backend/scripts/upgrade_drill.py`(断言随迁)。
- `client/frontend/src/lib/characterModel.ts`（镜像逐字同步，parity 测试锁死）。
- 测试：`test_character_model.py`（30→11 计数）、`test_characters_ai.py`（skipped 键示例）、e2e 认知区用例复核。
- UI（CharacterManager 认知区）由常量驱动自动收窄，无独立改动；提示词模板格名由后端常量渲染，提示词仓零改动（已核）。

## Design Impact

- 受影响端＝C端；受影响屏＝设定 · 角色认知区（格位收窄）。版式由既有 `.cog-layer-grid` 自适应，无新设计。
