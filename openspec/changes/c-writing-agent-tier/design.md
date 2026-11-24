# Design: c-writing-agent-tier

## Context

- 能力词汇表：`client/frontend/src/lib/features.ts`（FeatureKey + FEATURES minTier + 快照缺失兜底）；判定经 `useFeature` 走 entitlement 快照。
- 助手执行链：`client/backend/assistant/router.py` 目前只对「产卡类」按 `feature_key` 做档位闸（如 `assistant-diverge` MAX）；写类工具走「授权梯度」（默认每写必确认/本书授权/全部允许），**没有档位门**。
- 工具注册表：`client/backend/assistant/tools_*.py` 的 ToolSpec（name/description/parameters/feature_key 等）；启动校验已存在（能力 id 与注册表对拍）。
- 权益来源：S 端 entitlement 快照；S 端 change `s-landing-writing-agent` 新增发放 `assistant-execute`。

## Goals / Non-Goals

**Goals**
- 免费档：可对话、可读、可检索，不可执行写入；标准起可执行，且仍受授权梯度。
- 执行门在「工具真正执行前」判定，无权时回对话内升级事件，不 403 断流。
- 工具声明制：执行类工具必须声明 `assistant-execute`，漏声明启动失败。

**Non-Goals**
- 不做 C 端 UI 全面改名「写作 AI 助理」。
- 不改授权梯度语义与硬地板清单。
- 不做次数/额度。
- 不改 S 端目录（属 `s-landing-writing-agent`）。

## Decisions

### 1. 判定位置与顺序
- 在 agent 工具调用分发处（执行前）判定：`if tool.requires_feature and not granted` → 发 `upgrade_required` 事件（携带 `feature_key`、所需档位、可选文案位），不调用工具。
- 判定顺序：`requires_feature`（档位）→ 既有授权梯度（授权卡/放行）→ 执行。档位不足时不得先弹授权卡（避免误导用户可以批准即执行）。
- 读类工具 `requires_feature` 为空，行为不变。

### 2. 工具声明
- ToolSpec 增字段 `requires_feature: FeatureKey | None`；执行类工具统一填 `assistant-execute`。
- 启动校验：执行类集合（写/改/页面字段写/知识库写）遍历，缺声明 fail loud；对拍测试双向断言（执行类全声明、读类全不声明）。

### 3. 快照语义
- `useFeature("assistant-execute")` 沿用快照优先；快照缺失/不完整按**未授权**兜底（与 `ai-detect` 同类锁定口径）。
- 旧 S 端未下发该键时，所有档位按未授权处理——因此**发版顺序：S 端先发 entitlement，C 端后发**（旧 C 端忽略新键，标准用户不受影响；C 端上线时键已在）。

### 4. 交互与文案
- 升级卡复用现有助手内升级引导组件与消息位，不新增视觉组件、不新增状态语言。
- 卡文案需说明「标准起可让助理执行」，并给可点击升级出口（复用 `/plans` 或收银台）。

## Open Questions

1. 升级卡文案最终措辞（PM 拍板；默认「标准起可让助理动手」）。
2. 免费档「执行类 chip」是否置灰并带锁标（建议：样式沿用现有锁定态，不加新样式）。

## Risks

- **发版顺序**：C 端先于 S 端 → 标准用户被误拦；须以 S 端目录先上线为发布前置。
- **存量用户感知**：免费档原本可用执行，上线后收紧——需更新日志与客服话术；是否补偿/过渡由商业拍板（S 端 change Open Question）。
- **e2e 选择器**：助手免费档拦截将改变既有用例的期望路径，需同批更新。
- **注册表盲区**：新增工具若漏声明会被启动校验拦下，属预期；需在贡献指引里写明。
