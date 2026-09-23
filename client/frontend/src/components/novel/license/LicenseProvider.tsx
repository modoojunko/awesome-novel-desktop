import { createContext, useCallback, useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { api } from "@/lib/api";
import { isLoggedIn } from "@/lib/auth";
import {
  getVerifyCache,
  getLastRefreshAt,
  getLastRefreshPath,
  resetVerifyCache,
  resetLicenseCache,
  setLastRefresh,
  setVerifyCache,
  type EntitlementSnapshot,
  type LicenseVerify,
} from "@/lib/licenseCache";

/** 权益快照（entitlement 契约 v1，S端 check-auth 下发 / C端 verify 透传） */
export type { EntitlementSnapshot };

export interface TierState {
  tier: string;
  /** 免费待遇 = 非有效会员（免费层或套餐过期，与后端口径一致） */
  isFree: boolean;
  /** 有效会员（含归一化档位 pro/max，未过期）——AI 能力判据 */
  isMember: boolean;
  /** 套餐已过期（降为免费待遇，前端显示已过期徽标 + 续费引导） */
  expired: boolean;
  expiresAt: string;
  isPro: boolean;
  trialRemainingDays: number;
  /** 权益快照原文（无快照=老 S端/未刷新，null） */
  entitlement: EntitlementSnapshot | null;
  /** 快照不完整经档位标准兜底供给（后端 entitlement_degraded；防御态，徽章不消费） */
  entitlementDegraded: boolean;
  /** S端失联（权益同步刷新失败）：徽章文案保持既有档位仅转 warn，恢复后自动回常规色 */
  syncFailed: boolean;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

// 两跳刷新节流（c-s-entitlement-sync Q1）：路由切换 → /auth/check-auth（S端
// 静默往返写快照）→ refetch 刷上下文；60 秒窗口内不重复打 S端。无定时轮询。
const REFRESH_THROTTLE_MS = 60_000;

function isEntitlementRoute(pathname: string): boolean {
  return pathname === "/novels" || pathname.startsWith("/novel/");
}

const TierContext = createContext<TierState | null>(null);

export function LicenseProvider({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  // 恒挂载口径（c-session-flip-stability）：登录态翻转只切换上下文值（未登录
  // 注 null，消费方 useTier 已有 SAFE_FREE 兜底），壳层子树身份稳定不重挂。
  // 未登录时不发 verify/check-auth，与旧「壳层条件不挂 Provider」语义一致。
  const loggedIn = isLoggedIn();
  const cachedVerify = getVerifyCache();
  const [tier, setTier] = useState(cachedVerify?.tier ?? "none");
  const [isMember, setIsMember] = useState(cachedVerify?.is_member ?? false);
  const [expired, setExpired] = useState(cachedVerify?.expired ?? false);
  const [expiresAt, setExpiresAt] = useState(cachedVerify?.expires_at ?? "");
  const [trialRemainingDays, setTrialRemainingDays] = useState(
    cachedVerify?.trial_remaining_days ?? 0,
  );
  const [entitlement, setEntitlement] = useState<EntitlementSnapshot | null>(
    cachedVerify?.entitlement ?? null,
  );
  const [entitlementDegraded, setEntitlementDegraded] = useState(
    cachedVerify?.entitlement_degraded ?? false,
  );
  const [syncFailed, setSyncFailed] = useState(false);
  const [loading, setLoading] = useState(!cachedVerify);
  const [error, setError] = useState<string | null>(null);
  // 登录态上升沿探测：false→true（登出后再登录／换账号）时清残留判定
  const prevLoggedInRef = useRef(loggedIn);

  // 登录上升沿（c-silent-data-guards）：清上一账号的 verify 缓存与节流状态，
  // 本地判定同步回免费默认——首个请求发出前徽章也不得显示上一账号的档位
  useEffect(() => {
    if (loggedIn && !prevLoggedInRef.current) {
      resetLicenseCache();
      setTier("none");
      setIsMember(false);
      setExpired(false);
      setExpiresAt("");
      setTrialRemainingDays(0);
      setEntitlement(null);
      setEntitlementDegraded(false);
      setSyncFailed(false);
    }
    prevLoggedInRef.current = loggedIn;
  }, [loggedIn]);

  const load = useCallback(async (useCache: boolean) => {
    const cache = getVerifyCache();
    if (useCache && cache) {
      setTier(cache.tier ?? "none");
      setIsMember(cache.is_member ?? false);
      setExpired(cache.expired ?? false);
      setExpiresAt(cache.expires_at ?? "");
      setTrialRemainingDays(cache.trial_remaining_days ?? 0);
      setEntitlement(cache.entitlement ?? null);
      setEntitlementDegraded(cache.entitlement_degraded ?? false);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const r = (await api.post("/auth/verify")) as LicenseVerify;
      setVerifyCache(r);
      setTier(r.tier ?? "none");
      setIsMember(r.is_member ?? false);
      setExpired(r.expired ?? false);
      setExpiresAt(r.expires_at ?? "");
      setTrialRemainingDays(r.trial_remaining_days ?? 0);
      setEntitlement(r.entitlement ?? null);
      setEntitlementDegraded(r.entitlement_degraded ?? false);
      setError(null);
    } catch {
      // 失联口径（c-account-control-center）：保留上次快照判定，文案不变不清缓存不降级；
      // syncFailed 驱动徽章转 warn，恢复后随既有同步节奏回常规色。
      setSyncFailed(true);
      setError("套餐信息暂时无法核实，已按最近一次结果展示");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!loggedIn) return;
    void load(true);
  }, [load, loggedIn]);

  const refetch = useCallback(() => {
    resetVerifyCache();
    void load(false);
  }, [load]);

  // 两跳刷新（路由切换）：check-auth 写快照 → refetch 刷上下文；失败置失联标志
  useEffect(() => {
    if (!loggedIn) return;
    const path = location.pathname;
    if (!isEntitlementRoute(path) || path === getLastRefreshPath()) return;
    const now = Date.now();
    if (now - getLastRefreshAt() < REFRESH_THROTTLE_MS) {
      setLastRefresh(now, path);
      return;
    }
    setLastRefresh(now, path);
    void (async () => {
      try {
        await api.get("/auth/check-auth"); // S端 静默往返，更新本地快照
        setSyncFailed(false);
      } catch {
        // S端失联：沿用本地快照（c-account-control-center 失联变色信号源）
        setSyncFailed(true);
      }
      refetch();
    })();
  }, [location.pathname, refetch]);

  // window focus 尽力补一刀（pywebview 无保证 focus 桥，不作依赖）
  useEffect(() => {
    if (!loggedIn) return;
    const onFocus = () => {
      const now = Date.now();
      if (now - getLastRefreshAt() < REFRESH_THROTTLE_MS) return;
      setLastRefresh(now, getLastRefreshPath());
      void (async () => {
        try {
          await api.get("/auth/check-auth");
          setSyncFailed(false);
        } catch {
          setSyncFailed(true);
        }
        refetch();
      })();
    };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [refetch, loggedIn]);

  // 免费待遇 = 非有效会员（免费层或过期降级）；isPro 同步为有效会员语义
  const value: TierState = {
    tier,
    isFree: !isMember,
    isMember,
    expired,
    expiresAt,
    isPro: isMember,
    trialRemainingDays,
    entitlement,
    entitlementDegraded,
    syncFailed,
    loading,
    error,
    refetch,
  };
  // 未登录注入 null：上下文消费语义与旧「未登录不挂 Provider」完全一致
  return (
    <TierContext.Provider value={loggedIn ? value : null}>
      {children}
    </TierContext.Provider>
  );
}

export { TierContext };
