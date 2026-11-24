# Proposal: c-writing-agent-tier

## Why

落地页与定价将对外承诺「免费档助理能聊能查、不能动手；标准起可授权执行」。当前助手写类工具只受授权梯度管控，没有任何档位门——免费用户同样能让助理改设定、建章纲、收录知识库，文案与产品行为冲突。需要把「执行」做成独立的档位能力键 `assistant-execute`，作为跨端契约由 S 端发放、C 端判定。

## What Changes

- `features.ts` 新增 `FeatureKey`：`assistant-execute`（minTier `standard`）；沿用快照判定与 `useFeature` 机制，不做新组件。
- 助手执行路径加门：写/改类工具（书内实体写、知识库写、页面字段写）**执行前**要求 `assistant-execute`；未授权时在对话内出升级引导卡（复用现有升级卡，不 403、不打断对话流）。
- 读类工具、问答、只读检索、决策档案召回保持免费可用；生成/起草类仍按各自既有 key（`ai-plan` 标准起、`ai-generate` PRO 起、`deconstruct` PRO 起等）；发散类 `assistant-diverge` MAX 不变。
- 工具注册表每条执行类工具 SHALL 声明所需能力键；缺声明启动校验 fail loud，并加对拍测试（注册表 × 执行类清单）。
- 跨仓依赖：由 S 端 `s-landing-writing-agent` 在 entitlement 目录发放 `assistant-execute`（standard/pro/max；trial 同 pro；free 不发）；两仓同批发版。
- **不做**：C 端界面全面改名「写作 AI 助理」（另行立项）；不做次数/额度配额（已拍板不实施）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `tier-gating`: 词汇表新增 `assistant-execute` 及快照缺失兜底口径；执行能力判定统一走 `useFeature`。
- `writing-assistant`: 「档位门控与免费体验」需求更新——免费只读、标准起可执行；执行不足时对话内升级卡。
- `assistant-tools`: 执行类工具在注册表中声明所需能力键，启动校验与对拍测试覆盖。

## Design Impact

- **受影响端**：C端。
- **受影响屏/弹层**：工作台右栏助手对话（免费档触发执行请求时）；对话内升级引导卡（复用既有 `assistant` 升级卡组件与文案位）。
- **对象状态**：执行入口两态——「锁定（无 assistant-execute）/ 可用」；不新增状态语言、不新增组件词汇。
- **是否触碰两端共享段**：否（`features.ts`、助手工具注册表均为 C端 私有；不改 `base.css`、不改两端同名组件类）。
- **原型先行**：更新 `docs/design-c/drafts/ai-novel-c端-写作助手对话框-原型.html`，补「免费档点执行类 chip → 升级卡」状态并在同目录设计说明登记；若判定与既有升级卡零视觉差异，以真机截图作为对照证据。
- **设计工件来源**：实现侧自查 + 真机截图（无新增视觉，不需设计侧出稿）。

## Impact

- `client/frontend/src/lib/features.ts`（词汇表）、`client/frontend/src/lib/useFeature*` 消费点。
- `client/backend/assistant/router.py`（执行前档位判定与升级事件）、`client/backend/assistant/tools_*.py`（工具声明所需键）、`client/backend/auth_local/service.py`（兜底 features 列表如需随契约更新）。
- 测试：`client/backend/tests/test_assistant_write_gate.py`、`test_assistant_registry.py`、前端 features 单测、e2e 助手用例（免费档执行拦截）。
- **兼容性**：旧客户端忽略 `assistant-execute` 不报错；C 端先发版而 S 端未发 key 时，所有档位按「无该键」处理（免费化行为，产品需按灰度顺序说明，避免标准用户被误拦）。
- **不触资金流、不新增端点、无 DB schema 变更**（S 端 entitlement 为数据行更新，属 S 端 change）。
