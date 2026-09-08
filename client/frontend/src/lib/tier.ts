/**
 * 套餐文案单源（c-account-control-center）：面板头完整档 + 触发钮短档同源派生。
 * 判定优先级与后端 check_permission 一致：expired → trial → is_member → 免费版。
 * S端失联（前端同步失败信号，LicenseProvider.syncFailed）不是独立态：文案不变，仅徽章转 warn。
 */

export interface TierJudgment {
  tier?: string;
  is_member?: boolean;
  expired?: boolean;
  trial_remaining_days?: number;
}

export type TierTone = "accent" | "muted" | "warn";

/** 面板头完整档原文（账号区头「用户名 · 完整档」用） */
export function tierLabel(r: TierJudgment | null): string {
  if (!r) return "…";
  if (r.expired) return "套餐已过期 · 免费待遇";
  if (r.tier === "trial")
    return r.trial_remaining_days != null && r.trial_remaining_days > 0
      ? `试用中 · 剩 ${r.trial_remaining_days} 天`
      : "试用中";
  if (r.is_member) return "PRO 会员";
  return "免费版 · 单机使用";
}

export interface TierShort {
  text: string;
  tone: TierTone;
}

/** 触发钮短档（四态投影，允许缩短措辞）：免费版含过期合并单档 */
export function tierShort(r: TierJudgment | null): TierShort | null {
  if (!r || r.tier === undefined) return null;
  if (r.expired) return { text: "免费版", tone: "muted" };
  if (r.tier === "trial") {
    const n = r.trial_remaining_days ?? 0;
    return { text: `试用 · 剩 ${n} 天`, tone: n <= 3 ? "warn" : "muted" };
  }
  if (r.is_member) return { text: "PRO 会员", tone: "accent" };
  return { text: "免费版", tone: "muted" };
}
