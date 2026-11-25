/**
 * 档位权益种子（三档会员，2026-11-25）——e2e 会话种子的 entitlement 单源。
 *
 * writeOAuthSession 写 config.json 时同步写入 cfg.entitlement，
 * LicenseProvider 经 /auth/verify 读到 features → useFeature 按**快照单源**判定，
 * 与生产判定链同构（不绕 useFeature、不依赖静态注册表兜底）。
 *
 * 口径与 docs/contracts/entitlement-defaults.json v4 逐键对齐——改档位能力两处同批。
 */

const V2_STANDARD_LEGACY = [
  "ai-plan",
  "chapter-review",
  "settings-ai-fields",
  "style-suggest",
  "outline-advanced-fields",
  "ai-model",
  "assistant-execute",
] as const;

const V4_PRO = [
  ...V2_STANDARD_LEGACY,
  "ai-generate",
  "prompt-panel",
  "ai-detect",
  "deconstruct",
  "kb-official",
] as const;

const V4_MAX = [
  ...V4_PRO,
  "image-generate",
  "human-taste",
  "assistant-diverge",
  "ai-plot",
  "style-quant",
  "deconstruct-import",
] as const;

export const TIER_FEATURES: Record<string, string[]> = {
  free: [],
  // 存量标准档（不再新售）：e2e 兼容；新标准（免费）用 free。
  standard: [...V2_STANDARD_LEGACY],
  trial: [...V4_PRO], // trial=PRO，不含 MAX 独有键
  pro: [...V4_PRO],
  max: [...V4_MAX],
  // legacy 别名（与后端 _TIER_ALIAS 同口径）
  monthly: [...V4_PRO],
  quarterly: [...V4_PRO],
  yearly: [...V4_PRO],
  lifetime: [...V4_MAX],
};

/** tier → entitlement 快照（writeOAuthSession 直接塞 cfg.entitlement） */
export function entitlementFor(tier: string): {
  v: number;
  features: string[];
  limits: { max_projects: number | null };
} {
  const feats = TIER_FEATURES[tier] ?? TIER_FEATURES.free;
  return {
    v: 4,
    features: feats,
    limits: { max_projects: feats.length ? null : 1 },
  };
}
