## 1. 设计影响判定

- [ ] 1.1 核对 proposal「Design Impact」与 `docs/ux/design-language.html` §13：确认本次仅档位文案/门禁与升级出口，无新增视觉令牌/组件形态；若评审认为需要新弹层形态，补 `docs/design-c/prototypes/<screen>.html` 与 `prototypes/ADJUSTMENTS.md` 登记（验证：change 目录留判定记录/截图）
- [ ] 1.2 全文案清单对照三档口径（标准/PRO/MAX；不再出现“免费版/标准档起/升级标准”），逐条核对按钮词为动词、补救语句带可点击出口（验证：文案清单 diff + design:lint 通过）

## 2. 契约与档位词汇

- [ ] 2.1 `client/frontend/src/lib/features.ts`：FreeKey 收敛为 8 项；`ai-plan`/`chapter-review`/`settings-ai-fields`/`style-suggest`/`outline-advanced-fields`/`assistant-execute` 改 `pro`；`image-generate` 改 `max`；新增 `kb-official`（pro）与 `human-taste`（max）；`tierLabel("free")="标准"`、存量 standard 显示“标准会员（旧）”；`upgradeHintOf` 只出 PRO/MAX（验证：`vitest run src/__tests__/features.test.ts`）
- [ ] 2.2 `docs/contracts/entitlement-defaults.json` 升 v4：free（标准）空 features/1 本；pro = 旧 standard+pro+`assistant-execute`+`kb-official`；max = pro+`image-generate`/`human-taste`/`assistant-diverge`/`ai-plot`/`style-quant`/`deconstruct-import`；trial = pro；standard 仅 legacy（验证：C/S 两端对拍测试 `test_entitlement_sync.py` 全绿）
- [ ] 2.3 `client/backend/auth_local/service.py` 的 `STANDARD_FALLBACK` 与 `_LEGACY_IMPLICIT_FEATURES` 同批更新：`kb-official`→pro、`human-taste`→max、`image-generate`→max、`deconstruct`→pro、`deconstruct-import`→max、`assistant-execute`→pro；标准（免费）/过期不隐式放行（验证：`pytest tests/test_entitlement_sync.py tests/test_ai_feature_registry.py -q`）
- [ ] 2.4 `client/frontend/src/hooks/useTier.ts`、`lib/tier.ts`：`isStandard` 覆盖 `free` 与存量 `standard`；`isFree` 仍为非会员；档位短名/角标统一“标准/PRO/MAX”（验证：`vitest run src/__tests__/tier.test.ts src/__tests__/features.test.ts`）

## 3. 后端门禁与工具归属

- [ ] 3.1 `client/backend/auth_local/deps.py`：`_LEGACY_IMPLICIT_FEATURES` 与 `_TIER_RANK` 按三档更新；`assistant-execute` 不再对 standard/free 放行；`kb-official`/`human-taste` 新键进入词汇表与端点对拍（验证：`pytest tests/test_ai_feature_http.py tests/test_ai_feature_matrix.py -q`）
- [ ] 3.2 助理工具注册表：`kb_search`/`kb_read` 保持无键；`kb_search_craft` 挂 `kb-official`；`kb_create_entry`/`kb_update_entry` 保持 `assistant-execute`；`read_prose_checks` 挂 `human-taste`；`draft_prose_plan` 保持 `ai-generate`；`diverge_*`/`simulate_plot` 保持 MAX 键；启动校验仍 fail-loud（验证：`pytest tests/test_assistant_registry.py tests/test_assistant_execute_gate.py -q`）
- [ ] 3.3 `client/backend/assistant/router.py`：gate 文案按 `tier_required` 出 PRO/MAX（不再“这个要 PRO 档才能让我动手”一刀切）；`ai-plan` 的 `tier_required` 改 pro；`allow_book` 仅 MAX（验证：`pytest tests/test_assistant_write_gate.py tests/test_assistant_execute_gate.py -q`）
- [ ] 3.4 `client/backend/kb/*`：官方层查询/树/图谱/草稿挂 `kb-official`；本地层查询/条目 CRUD 不挂；`/settings/style/kb-draft` 挂 PRO（验证：`pytest tests/test_kb_* tests/test_style_kb_draft.py -q`）
- [ ] 3.5 `client/backend/write/router.py` 人味端点挂 `human-taste`（MAX）；`client/backend/image_assets/*`、cover/avatar/批量头像挂 `image-generate`（MAX）；`deconstruct/router.py` 的 `collect-to-kb` 挂 `deconstruct`（PRO），取消/删除保持无门（验证：`pytest tests/test_renwei* tests/test_image_assets.py tests/test_deconstruct_api.py -q`）
- [ ] 3.6 写类工具授权梯度：`setPermissionTier`/`write_gate.evaluate` 拒绝非 MAX 的 `allow_book`（存量 `allow_all` 映射 `allow_book`）；硬地板清单不变（验证：`pytest tests/test_assistant_write_gate.py -q`）

## 4. 前端 UI 与升级出口

- [ ] 4.1 `UpgradeModal.tsx`：收成两跳（标准→PRO、PRO→MAX），删除 `TIER_PITCH.standard` 旧话术；PRO 权益补官方库/正文/拆书/朱雀/提示词；MAX 权益补人味+改法/图像/拆书建书/发散/推演/蒸馏/自动执行（验证：`vitest run src/__tests__/UpgradeModal.test.tsx`）
- [ ] 4.2 `AiWriterAssistant.tsx` / `AiAssistPanel.tsx`：人味行取消 `ungated`，改 MAX 锁定+升级出口；设定/规划/正文行按 PRO/MAX 锁定；档位角标“标准/PRO/MAX”（验证：`vitest run src/__tests__/AiWriterAssistant.test.tsx src/__tests__/AiAssistPanel.test.tsx`）
- [ ] 4.3 `Aui2Dock.tsx`：授权选择器自动档对非 MAX 显示 MAX 锁定/升级出口；标准（免费）只读对话仍可用；PRO 写类 gate 文案指向 PRO（验证：`vitest run src/__tests__/Aui2Dock.test.tsx`）
- [ ] 4.4 知识库页面/面板：官方库入口对标准（免费）锁定、按题材填文风锁 PRO；本地库/决策档案标准可用；助理代收录取 PRO 出口（验证：相关 vitest + 真机/截图）
- [ ] 4.5 图像工坊/批量头像：标准（免费）/PRO 只上传，AI 生成/试画/批量头像走 MAX 出口；手动上传不受影响（验证：`vitest run src/__tests__/imageWorkshop* src/__tests__/BatchAvatar*`）
- [ ] 4.6 拆书任务页/导入向导：直接导入标准（免费）可用；AI 拆书 PRO；收进知识库 PRO；一键建书 MAX；取消/删除无门（验证：`vitest run src/__tests__/toolsDetail.test.tsx src/__tests__/toolsCreate.test.tsx` + e2e）
- [ ] 4.7 我的套餐/档位徽标/书架配额提示：标准/PRO/MAX 文案与 1 本/不限一致；存量 standard 显示“标准会员（旧）”且不出现新售入口（验证：相关 vitest + 真机/截图）

## 5. 测试与回归

- [ ] 5.1 更新 e2e 档位种子 `client/frontend/e2e/tier-features.ts`：三档快照（标准空/PRO 全集/MAX 全集/trial=PRO），旧 standard 仅 legacy 用例（验证：`npm run e2e -- --grep "tier|upgrade|assistant"` 相关用例通过）
- [ ] 5.2 新增负向钉：标准（免费）无 AI 写手/官方库/人味/图像/拆书建书；PRO 无 MAX 键；非 MAX 不能 `allow_book`；官方库与本地库分层（验证：backend pytest + vitest 对应新增用例）
- [ ] 5.3 回归：`cd client/backend && pytest tests/test_entitlement_sync.py tests/test_ai_feature_registry.py tests/test_assistant_registry.py tests/test_assistant_execute_gate.py tests/test_assistant_write_gate.py tests/test_kb_* tests/test_deconstruct_api.py tests/test_image_assets.py -q`（apply 时附实际输出）
- [ ] 5.4 回归：`cd client/frontend && npm run design:lint && npx tsc --noEmit && vitest run src/__tests__/features.test.ts src/__tests__/UpgradeModal.test.tsx src/__tests__/Aui2Dock.test.tsx src/__tests__/AiWriterAssistant.test.tsx`（apply 时附实际输出；未触共享段，design-cross 不跑，引用 proposal Design Impact 判定）
- [ ] 5.5 回归：`npm run design:check`（C端像素差 <0.2%）与相关 e2e（apply 时附实际输出；如新增原型，补 ADJUSTMENTS 登记）
