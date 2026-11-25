## Why

C 端已从“按钮式 AI 功能”升级为写作 AI 助理，但套餐仍按旧四档（free/standard/pro/max）卖：标准档收费、PRO 与 MAX 的助理能力没上货架，官方库/本地库/拆书/人味检测/图像的档位边界也与实际代码不一致。2026-11-25 产品拍板收成三档会员：**标准（免费）= 写作无忧、PRO = AI 写手、MAX = 写作秘书**；本次把 C 端档位词汇、门禁、助理行为、知识库/拆书/人味/图像归属一次性对齐，避免“页面一个说法、代码一个说法”。

## What Changes

- **档位模型改为三档会员**：`free`（展示名“标准”）＝写作无忧；`pro`＝AI 写手；`max`＝写作秘书。原付费 `standard` 档停售/退役，仅保留存量权益（grandfather）。
- **标准（免费）**：完整创作流程 + 自己的知识库（本书设定/人物/决策/条目，可看可编辑、助理可读）+ AI 头脑风暴（读你的书、聊设定/人物/剧情/走向；不生成章纲/正文、不写入书、不执行写操作）+ 助理问答；1 本书 / 1 台设备。
- **PRO**：AI 写手——AI 规划/章纲/正文生成/助理执行（每写必确认）+ 官方写作知识库 331 本 + AI 拆书/导入已有书 + 朱雀检测 + 提示词页签；书不限 / 3 台设备。
- **MAX**：写作秘书——PRO 全部 + 人味检测/逐行修改指引 + AI 封面/头像/试画/批量头像 + 拆书产物一键建书 + 发散起草/剧情推演/文风蒸馏 + 全权托管（`allow_book` 自动执行）+ 5 台设备 + 飞书内测群。
- **feature key 重排**：旧 standard 的 AI keys（`ai-plan`、`chapter-review`、`settings-ai-fields`、`style-suggest`、`outline-advanced-fields`、`assistant-execute`）最低档改为 `pro`；`image-generate` 改为 `max`；新增 `human-taste`（max）与 `kb-official`（pro）；`deconstruct` = pro、`deconstruct-import` = max；本地库/官方库拆层，本地层免费。
- **助理授权梯度**：`confirm_each` 标准/PRO 可用；`allow_book` 仅 MAX；硬地板（删全书/批量删章/覆盖已确认设定/改授权档位）任何档位都弹卡。
- **试用**：7 天 PRO（AI 写手），不送 MAX；试用到期回标准（免费）。
- **BREAKING**：原 `standard` 付费档不再售卖；存量 standard 用户到期前权益不变，到期走 PRO 升级券或回标准；原 standard 的 AI 能力不再对标准（免费）用户开放。

## Capabilities

### New Capabilities

（无新增 capability；三档模型落在既有 tier/assistant/knowledge 能力内。）

### Modified Capabilities

- `tier-access`: 三档会员的档位判定、免费基线、存量 standard 兼容与 project limit 口径。
- `tier-gating`: FeatureKey 词汇表与 minTier 重排（含 `human-taste`、`kb-official`）、档位标签/升级提示、`allow_book` 仅 MAX。
- `writing-assistant`: 标准=只读头脑风暴、PRO=可写 AI 写手、MAX=可查/可画/可建书/可自动执行的秘书。
- `assistant-tools`: 工具级 feature/requires_feature 归属（官方库 vs 本地库、human-taste、拆书收库、自动执行）。
- `assistant-chat-ui`: 授权档位选择器、锁定行/升级出口与档位文案。
- `knowledge-base`: 本地库（标准免费）与官方库（PRO）分层访问；助理检索/收录的档位边界。
- `knowledge-baseline`: 官方基线同步/更新随官方库归 PRO。
- `renwei-check`: 人味检测与逐行修改指引归 MAX；本地检测不再免档。
- `cover-avatar`: AI 封面/头像/试画/批量头像归 MAX；手动上传保持标准免费。
- `deconstruct-book`: AI 拆书归 PRO；拆书产物收进本地库归 PRO；一键建书归 MAX。
- `import-own-book`: 明确“导入旧稿接着写”（标准免费）与“AI 拆书/导入已有书”（PRO）是两条路。

## Design Impact

- **受影响端**：C 端（本仓）；S 端套餐目录/落地页由 S 仓同批 change 承接。
- **受影响屏/弹层**：升级弹窗（`UpgradeModal`）、工作台右栏 AI 卡与助理 Dock、知识库页/面板、拆书任务页、图像工坊/批量头像弹窗、设定页“按题材填文风”、我的套餐/档位徽标。
- **对象状态**：沿用现有 `member_required` / `no_key` / `missing_model` / `invalid` 状态；新增档位锁定只改变“最低档”与文案，不新增视觉形态。
- **共享段**：不触碰 `base.css` 令牌/基础组件类/状态语言词汇；不新增 `pill`/`notice`/`b`/`strip` 形态。
- **原型先行**：本次为档位文案/门禁调整，无新增视觉形态与布局；先在实现侧对照 `docs/ux/design-language.html` §13 核对文案，若评审认为需要新增屏/弹层形态，再补原型与 ADJUSTMENTS 登记。
- **设计工件产出**：实现侧自查（文案与门禁）；不新增设计侧会话。

## Impact

- `client/frontend/src/lib/features.ts`、`hooks/useTier.ts`、`lib/tier.ts`、`UpgradeModal.tsx`、`AiWriterAssistant.tsx`、`AiAssistPanel.tsx`、`Aui2Dock.tsx`、知识库/拆书/图像相关页面与测试。
- `client/backend/auth_local/service.py`（STANDARD_FALLBACK / `_LEGACY_IMPLICIT_FEATURES`）、`auth_local/deps.py`、`assistant/router.py`、`assistant/tools*.py`、`kb/*`、`deconstruct/router.py`、`write/router.py`（renwei-check）、`image_assets/*`、`cover_avatar`/`cover_extract`。
- `docs/contracts/entitlement-defaults.json` 与 C/S 两端对拍测试；S 端 `tiers/skus/entitlement` 由 S change 提供。
- 既有测试：`test_entitlement_sync`、`test_ai_feature_registry`、`test_assistant_registry`、`test_assistant_execute_gate`、`test_assistant_write_gate`、`test_deconstruct_*`、`test_kb_*`、`test_renwei*`、`test_image_assets`、前端 features/UpgradeModal/Aui2Dock/AiWriterAssistant 等；e2e 档位种子 `e2e/tier-features.ts`。
- 兼容：旧 S 端快照不含新 key 时，按 `_LEGACY_IMPLICIT_FEATURES` 保守放行；存量 `standard` 档按 legacy 处理，不做追溯降级。
