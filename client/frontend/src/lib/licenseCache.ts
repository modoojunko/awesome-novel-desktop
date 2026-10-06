// 权益快照的模块级缓存与两跳刷新节流状态（c-s-entitlement-sync Q1）。
// 独立叶子模块：logout（lib/auth）登出要清缓存，而 LicenseProvider 又依赖 lib/auth——
// 缓存放 Provider 内会成环；放这里两端单向依赖。
// c-silent-data-guards：缓存必须随登出/换号失效——换账号登录不得沿用上一账号快照，
// reset 由 logout() 与登录上升沿双保险触发。

export interface EntitlementSnapshot {
  v: number;
  features: string[];
  limits: { max_projects: number | null };
}

/** 档位目录投影（tier-catalog）：{v:1, tiers:[{key,rank,display_name,features}]} */
export interface TierCatalog {
  v: number;
  tiers: Array<{
    key: string;
    rank: number;
    display_name: string;
    features: string[];
  }>;
}

/** 写作能力包状态（c-prompt-pack-client：/auth/verify 挂载，本地 prompt_pack 快照） */
export interface PackStatus {
  phase: 'syncing' | 'ready' | 'missing' | 'failed' | 'tier_denied';
  reason?: string;
  tier?: string;
  version?: string;
  updated_at?: number;
}

export interface LicenseVerify {
  tier?: string;
  is_member?: boolean;
  expired?: boolean;
  expires_at?: string;
  trial_remaining_days?: number;
  /** 建书上限（null=不限；免费=1、标准=3）——verify_session 透传后端口径 */
  project_limit?: number | null;
  entitlement?: EntitlementSnapshot;
  entitlement_degraded?: boolean;
  /** 档位目录投影（tier-catalog）：快照缺失时按目录行兜底判定（新 S端 才下发） */
  tier_catalog?: TierCatalog;
  /** 写作能力包状态（c-prompt-pack-client） */
  prompt_pack?: PackStatus;
}

let cachedVerify: LicenseVerify | null = null;
let lastRefreshAt = 0;
let lastRefreshPath: string | null = null;

export const getVerifyCache = (): LicenseVerify | null => cachedVerify;
export const setVerifyCache = (v: LicenseVerify) => {
  cachedVerify = v;
};
export const getLastRefreshAt = () => lastRefreshAt;
export const getLastRefreshPath = () => lastRefreshPath;
export const setLastRefresh = (at: number, path: string | null) => {
  lastRefreshAt = at;
  lastRefreshPath = path;
};

/** 只清 verify 快照（refetch 用）——保留两跳刷新节流状态，避免路由去抖被重置 */
export function resetVerifyCache() {
  cachedVerify = null;
}

/** 登出/换号时清权益缓存与节流状态（下一账号从真取数开始） */
export function resetLicenseCache() {
  cachedVerify = null;
  lastRefreshAt = 0;
  lastRefreshPath = null;
}
