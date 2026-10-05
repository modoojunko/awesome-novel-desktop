import { useContext } from "react";
import { FEATURES, tierRank, type FeatureKey } from "@/lib/features";
import { getVerifyCache } from "@/lib/licenseCache";
import { TierContext, type TierState } from "@/components/novel/license/LicenseProvider";

const SAFE_FREE: TierState = {
  tier: "none",
  isFree: true,
  isMember: false,
  expired: false,
  expiresAt: "",
  isStandard: false,
  isPro: false,
  isMax: false,
  trialRemainingDays: 0,
  entitlement: null,
  entitlementDegraded: false,
  syncFailed: false,
  pack: null,
  loading: false,
  error: null,
  refetch: () => {},
};

/** 取当前套餐状态；未包 LicenseProvider 时返回免费安全默认值，不抛。 */
export function useTier(): TierState {
  return useContext(TierContext) ?? SAFE_FREE;
}

/** 快照缺失时的兜底判定（tier-plan-four-tiers 3.1）：目录缓存行 features 含 key
 * → true；目录行缺 key → false；目录与快照皆无 → 静态注册表（免费键 true）。 */
function fallbackAllowed(key: FeatureKey): boolean {
  // 快照在场：快照单源（即便不在 Provider 上下文——快照是权威判定依据）
  const v = getVerifyCache();
  if (v?.entitlement && Array.isArray(v.entitlement.features)) {
    return v.entitlement.features.includes(key);
  }
  // 快照缺失：目录缓存行兜底（tier-catalog 新 S端 下发）
  const rows = v?.tier_catalog?.tiers;
  if (Array.isArray(rows) && rows.length > 0) {
    const row = rows.find((r) => r.key === (v?.tier ?? "none"));
    if (row && Array.isArray(row.features)) return row.features.includes(key);
  }
  // 皆无：静态注册表 minTier（免费键 true）
  return tierRank(FEATURES[key].minTier) === 0;
}

/** 功能开关（tier-plan-four-tiers）：完整快照 features 包含判定（快照单源）；
 * 快照缺失/降级 → 目录缓存兜底；皆无 → 静态注册表 minTier。未包 Provider 走兜底。 */
export function useFeature(key: FeatureKey): boolean {
  const ctx = useContext(TierContext);
  if (!ctx) return fallbackAllowed(key);
  if (ctx.entitlement && Array.isArray(ctx.entitlement.features)) {
    return ctx.entitlement.features.includes(key);
  }
  return fallbackAllowed(key);
}
