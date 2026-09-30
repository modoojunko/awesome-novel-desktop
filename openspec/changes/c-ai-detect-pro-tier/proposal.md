# Proposal: c-ai-detect-pro-tier（朱雀 AI 检测权益自 MAX 下放 PRO）

## Why

朱雀 AI 检测（c-zhuque-ai-detect，#617）上线时按定价终拍（docs/prd/pricing-tiers-launch-promo.md §6.2/§6.4）挂在 MAX 会员专属，S端 entitlement 快照只对 max 发放 `ai-detect` key。但 MAX 档至今未上线（TIER_POLICY max 标注「规划中」，无对应 SKU、不可购买）——结果是**所有真实账号都拿不到该 key，朱雀全链（配置→工作台检测→段落标注）零人可用，也无法真机验证**。用户拍板（2026-09-30）：先把朱雀权益从 MAX 降到 PRO，让 PRO 档（可购买）能配置并使用朱雀，打通验证；试用仍不含。

## What Changes

- **权益发放**：`docs/contracts/entitlement-defaults.json` 与两端镜像（S端 `ENTITLEMENT_DEFAULTS`、C端 `STANDARD_FALLBACK`）的 pro/max 两档 features 各追加 `ai-detect`（max 保持 ⊇ pro）；trial/free/none 不动（试用不含口径保持）。
- **C端文案**：工作台检测行锁定态徽章「MAX 专属」→「PRO 专属」、描述「MAX 会员权益 · 升级后…」→「PRO 会员权益 · …」、就绪徽章「MAX 权益」→「PRO 权益」；朱雀配置页介绍「MAX 会员权益（试用不含）」→「PRO 会员权益（试用不含）」；注释与词汇表口径同步。
- **行为不变项**：门禁机制零改动——仍为快照单源（useFeature 读快照 features），快照缺失一律锁定；配置页签全档可见可配置；锁定行可点走升级出口；`require_ai_access` 会员级拦截不变（PRO 本就可过）。
- **非目标**：定价文档（pricing-tiers-launch-promo.md）与 S端 落地页营销文案仍按「MAX 剧情规划＋朱雀检测」终拍表述，本次不动——MAX 上线时是否收回朱雀权益另立 change 再拍；S端 tiers 表若线上按档位目录配置了 entitlement JSON，须随发布同步运维改配（代码 defaults 仅为兜底）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `tier-gating`：Free-locked keys 中 `ai-detect` 的发放口径（MAX 专属 → PRO 起发放、试用不含）；「ai-detect 对非 MAX 锁定」场景按 openspec 保名改内容（Given 收窄为免费/试用）。
- `zhuque-workbench`：检测行四态中的锁定/引导/就绪表述与徽章文案（MAX → PRO / 权益态），降级锁定场景措辞同步。
- `zhuque-config`：朱雀页签文案口径（MAX 会员权益 → PRO 会员权益）与「非会员可配置」场景措辞。

## Impact

- 权益契约：`docs/contracts/entitlement-defaults.json`（对拍基准）、`server/app/config.py`（ENTITLEMENT_DEFAULTS）、`client/backend/auth_local/service.py`（STANDARD_FALLBACK）三处同批改，C端对拍测试（test_entitlement_sync 3.6）保持绿。
- 前端：`AiAssistPanel.tsx`（检测行文案＋注释）、`ZhuquePanel.tsx`（介绍文案＋头注）、`features.ts`／`features.test.ts`／`AiWriterAssistant.tsx`（注释口径）。`maxlk` 行变体为内部标识（CSS `zq-maxlk`），本次不改名。
- 测试：无测试钉「MAX 专属」文案（vitest/e2e 均以 testid 断言）；e2e 种子为 MAX＋已配 Key，收窄到 PRO 后仍绿（max ⊇ pro）。
- 运维：生产 S端 发布本改后，若 tiers 表按档位目录存有 entitlement JSON，须同步给 pro 档补 `ai-detect`（find_entitlement_by_key 优先于 defaults）；TTL 60s 自愈。
