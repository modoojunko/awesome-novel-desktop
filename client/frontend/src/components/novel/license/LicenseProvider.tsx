import { createContext, useCallback, useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { api } from "@/lib/api";

/** 权益快照（entitlement 契约 v1，S端 check-auth 下发 / C端 verify 透传） */
export interface EntitlementSnapshot {
  v: number;
  features: string[];
  limits: { max_projects: number | null };
}

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

interface VerifyResponse {
  tier?: string;
  is_member?: boolean;
  expired?: boolean;
  expires_at?: string;
  trial_remaining_days?: number;
  entitlement?: EntitlementSnapshot;
  entitlement_degraded?: boolean;
}

// module 级缓存：同会话多 Provider/重挂载不重复请求（/auth/verify 仅 1 次）。
let cachedVerify: VerifyResponse | null = null;

// 两跳刷新节流（c-s-entitlement-sync Q1）：路由切换 → /auth/check-auth（S端
// 静默往返写快照）→ refetch 刷上下文；60 秒窗口内不重复打 S端。无定时轮询。
const REFRESH_THROTTLE_MS = 60_000;
let lastRefreshAt = 0;
let lastRefreshPath: string | null = null;

function isEntitlementRoute(pathname: string): boolean {
  return pathname === "/novels" || pathname.startsWith("/novel/");
}

const TierContext = createContext<TierState | null>(null);

export function LicenseProvider({ children }: { children: React.ReactNode }) {
  const location = useLocation();
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

  const load = useCallback(async (useCache: boolean) => {
    if (useCache && cachedVerify) {
      setTier(cachedVerify.tier ?? "none");
      setIsMember(cachedVerify.is_member ?? false);
      setExpired(cachedVerify.expired ?? false);
      setExpiresAt(cachedVerify.expires_at ?? "");
      setTrialRemainingDays(cachedVerify.trial_remaining_days ?? 0);
      setEntitlement(cachedVerify.entitlement ?? null);
      setEntitlementDegraded(cachedVerify.entitlement_degraded ?? false);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const r = (await api.post("/auth/verify")) as VerifyResponse;
      cachedVerify = r;
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
    void load(true);
  }, [load]);

  const refetch = useCallback(() => {
    cachedVerify = null;
    void load(false);
  }, [load]);

  // 两跳刷新（路由切换）：check-auth 写快照 → refetch 刷上下文；失败置失联标志
  useEffect(() => {
    const path = location.pathname;
    if (!isEntitlementRoute(path) || path === lastRefreshPath) return;
    const now = Date.now();
    if (now - lastRefreshAt < REFRESH_THROTTLE_MS) {
      lastRefreshPath = path;
      return;
    }
    lastRefreshAt = now;
    lastRefreshPath = path;
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
    const onFocus = () => {
      const now = Date.now();
      if (now - lastRefreshAt < REFRESH_THROTTLE_MS) return;
      lastRefreshAt = now;
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
  }, [refetch]);

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
  return <TierContext.Provider value={value}>{children}</TierContext.Provider>;
}

export { TierContext };
