// 官方知识探测的会话内缓存与弹窗开启事件（s-kb-signed-delivery）。
// KnowledgeBasePage 挂载探测写入，弹窗读取——内存缓存不落盘。

import { enqueueDialog } from "@/lib/dialogQueue";

/** 单个题材数据对象（S 端签名 manifest 里的 genres 映射值）。 */
export interface KbGenreMeta {
  path: string;
  sha256: string;
  bytes: number;
  entry_count: number;
}

/** 本机已同步的题材状态（AppMeta kb_baseline_genres 的镜像）。 */
export interface KbGenreState {
  version: number;
  sha256: string;
  path: string;
  entries: number;
  synced_at: string;
}

/** 今日题材同步配额（S 端按档位算；tree 为 {free:true}）。 */
export interface KbQuota {
  limit: number;
  used: number;
  remaining: number;
  reset_at: string;
  free?: boolean;
}

export interface KbProbe {
  installed: number;
  latest: number;
  update_available: boolean;
  reason?: string;
  /** release manifest 的题材映射（未知/失败时缺省） */
  genres?: Record<string, KbGenreMeta>;
  /** 本机已同步题材（sha 与 genres 对拍得出可更新/未同步） */
  installed_genres?: Record<string, KbGenreState>;
  /** 内容有变化/未同步的题材 */
  updates?: string[];
  quota?: KbQuota;
  /** latest.json 的 resume_baseline（撤回后显式放行） */
  resume?: boolean;
}

export type KbSyncModalMode = "update" | "manual";

export interface KbSyncModalDetail {
  mode: KbSyncModalMode;
  /** 页面已探测到的快照；缺省时弹窗自己 probe 一次（免费） */
  probe?: KbProbe;
  /** 写作提示带入的题材（弹窗内高亮） */
  focusGenre?: string;
}

let lastProbe: KbProbe | null = null;

export const getLastKbProbe = (): KbProbe | null => lastProbe;
export const setLastKbProbe = (p: KbProbe) => {
  lastProbe = p;
};

/**
 * 打开官方知识弹窗（单实例 KnowledgeSyncModal 监听；沿用 pack-modal:open 先例）。
 * 经壳层弹窗队列（shell-dialog-queue）——带回流程未收尾前不入场；队列只延迟
 * 呈现，不延迟探测。
 */
export const openKbSyncModal = (detail: KbSyncModalDetail) => {
  enqueueDialog("kb-sync", 2, () => {
    window.dispatchEvent(new CustomEvent<KbSyncModalDetail>("kb-sync-modal:open", { detail }));
  });
};

// ── 挂载探测在途槽（StrictMode 双挂载去重：只放行一次） ────────────────
let probeInFlight = false;

/** 返回 true＝获得本轮探测权（调用方 finally 里必须 releaseKbProbe） */
export const claimKbProbe = (): boolean => {
  if (probeInFlight) return false;
  probeInFlight = true;
  return true;
};
export const releaseKbProbe = () => {
  probeInFlight = false;
};
/** 登出/换号复位（照 packProbe 同款）：下一账号不得沿用上一账号结果 */
export const resetKbProbeState = () => {
  lastProbe = null;
  probeInFlight = false;
};

// ── 「暂不更新」锚（照 pack-modal-dismiss 同构） ──────────────────────
// 单 key JSON：updateVersion＝「暂不更新」时所见的 release 版本锚（同版不重弹，
// 版本变化自动重臂）。纯本机 UX 偏好，不进服务端；写失败静默。
const DISMISS_KEY = "kb-sync-dismissed";

interface KbDismissal {
  updateVersion?: string;
}

export const readKbDismissal = (): KbDismissal => {
  try {
    const raw = window.localStorage.getItem(DISMISS_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as KbDismissal;
    return typeof parsed === "object" && parsed !== null ? parsed : {};
  } catch {
    return {};
  }
};

/** 暂不更新：记当下 release 版本锚——同版不再弹，probe 版本号变化即重臂 */
export const writeKbUpdateDismissed = (version: number) => {
  try {
    window.localStorage.setItem(DISMISS_KEY, JSON.stringify({ updateVersion: String(version) }));
  } catch {
    /* 写失败不补偿：关闭记忆是打扰抑制，丢标记只回到基线行为 */
  }
};
