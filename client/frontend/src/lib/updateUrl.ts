import { request } from './api';

// 下载地址三级回落单源（loginless-data-exit）：S端 hint → 本地 update-check
// 缓存 → 官网常量。UpgradeGate 与 UpdateNotice 共用（收敛两处 DOWNLOAD_HOME）。

export const DOWNLOAD_HOME = 'https://github.com/modoojunko/ai-novel/releases';

/** 三级回落解析下载地址：hint（S端 载荷）优先，其次本地 update-check，最后常量。 */
export async function resolveDownloadUrl(hint?: string): Promise<string> {
  if (hint) return hint;
  try {
    const res = await request('/update-check');
    if (res.data?.download_url) return res.data.download_url as string;
  } catch {
    /* 兜底常量 */
  }
  return DOWNLOAD_HOME;
}
