/**
 * 档位权益种子（tier-plan-four-tiers 6.2）——e2e 会话种子的 entitlement 单源。
 *
 * writeOAuthSession 写 config.json 时同步写入 cfg.entitlement（v2 五档口径），
 * LicenseProvider 经 /auth/verify 读到 features → useFeature 按**快照单源**判定，
 * 与生产判定链同构（不绕 useFeature、不依赖静态注册表兜底）。
 *
 * 口径与 docs/contracts/entitlement-defaults.json v2 逐键对齐——改档位能力两处同批。
 */

const V2_STANDARD = [
  "ai-plan",
  "chapter-review",
  "settings-ai-fields",
  "style-suggest",
  "outline-advanced-fields",
  "ai-model",
] as const;

const V2_PRO = [...V2_STANDARD, "ai-generate", "prompt-panel", "ai-detect"] as const;

const V2_MAX = [...V2_PRO, "ai-plot", "ai-polish", "style-quant"] as const;

export const TIER_FEATURES: Record<string, string[]> = {
  free: [],
  standard: [...V2_STANDARD],
  trial: [...V2_PRO], // trial=pro 同权含朱雀（2026-10-05 拍板）
  pro: [...V2_PRO],
  max: [...V2_MAX],
  // legacy 别名（与后端 _TIER_ALIAS 同口径）
  monthly: [...V2_PRO],
  quarterly: [...V2_PRO],
  yearly: [...V2_PRO],
  lifetime: [...V2_MAX],
};

/** tier → entitlement 快照（writeOAuthSession 直接塞 cfg.entitlement） */
export function entitlementFor(tier: string): {
  v: number;
  features: string[];
  limits: { max_projects: number | null };
} {
  const feats = TIER_FEATURES[tier] ?? TIER_FEATURES.free;
  return {
    v: 2,
    features: feats,
    limits: { max_projects: feats.length ? null : 1 },
  };
}
