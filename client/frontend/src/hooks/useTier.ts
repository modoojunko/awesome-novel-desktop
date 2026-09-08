import { useContext } from "react";
import { FEATURES, type FeatureKey } from "@/lib/features";
import { TierContext, type TierState } from "@/components/novel/license/LicenseProvider";

const SAFE_FREE: TierState = {
  tier: "none",
  isFree: true,
  isMember: false,
  expired: false,
  expiresAt: "",
  isPro: false,
  trialRemainingDays: 0,
  entitlement: null,
  entitlementDegraded: false,
  syncFailed: false,
  loading: false,
  error: null,
  refetch: () => {},
};

/** 取当前套餐状态；未包 LicenseProvider 时返回免费安全默认值，不抛。 */
export function useTier(): TierState {
  return useContext(TierContext) ?? SAFE_FREE;
}

/** 功能开关（c-s-entitlement-sync）：快照 features 包含判定；无快照回退静态
 * 注册表（免费 true / 会员 false）。未包 LicenseProvider 同样走静态兜底，不抛。 */
export function useFeature(key: FeatureKey): boolean {
  const ctx = useContext(TierContext);
  if (!ctx) return !FEATURES[key].memberOnly;
  if (ctx.entitlement && Array.isArray(ctx.entitlement.features)) {
    return ctx.entitlement.features.includes(key);
  }
  return !FEATURES[key].memberOnly;
}
