/**
 * 服务端时间解析（存量 bug 修：C端 后端下发**无时区**的 ISO 串，形如
 * `2026-09-20T03:53:13`——按 ES 规范浏览器把它当本地时间解析，UTC+8 下
 * 相对时间整体偏 8 小时（「刚刚归档」显示「8 小时前」）。
 * 这里统一补 `Z` 按 UTC 解析；带时区（Z / ±hh:mm）的串原样解析，非法串回落原值。
 */
export function parseServerTime(v: string): Date {
  const hasTz = /(?:Z|[+-]\d{2}:?\d{2})$/.test(v);
  return new Date(hasTz ? v : `${v}Z`);
}

/** 服务端时间 → 毫秒时间戳（非法归 0；排序/比较用容错口径）。 */
export function serverTimeMs(v?: string | null): number {
  if (!v) return 0;
  const n = parseServerTime(v).getTime();
  return Number.isFinite(n) ? n : 0;
}
