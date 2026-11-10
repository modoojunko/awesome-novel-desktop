// 官方知识版本探测的会话内缓存与弹窗开启事件（c-kb-baseline-update-ux）。
// 照 lib/packProbe.ts 同构剪裁：KnowledgeBasePage 挂载探测写入，弹窗手动
// 模式读取——内存缓存不落盘（探测廉价幂等，刷新页面后重新探测即可）。

import { enqueueDialog } from "@/lib/dialogQueue";

export interface KbProbe {
  installed: number;
  latest: number;
  update_available: boolean;
  reason?: string;
}

export type KbSyncModalMode = "update" | "manual";

export interface KbSyncModalDetail {
  mode: KbSyncModalMode;
  /** update 模式：确认行展示 当前 from → 最新 to */
  from?: number;
  to?: number;
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

// ── 「暂不更新」锚（c-kb-baseline-update-ux，照 pack-modal-dismiss 同构） ──
// 单 key JSON：updateVersion＝「暂不更新」时所见的 CDN 版本锚（同版不重弹，
// 版本变化自动重臂）。纯本机 UX 偏好，不进服务端；写失败静默——最坏退回
// 现状「每次重弹」。
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

/** 暂不更新：记当下 CDN 版本锚——同版不再弹，probe 版本号变化即重臂 */
export const writeKbUpdateDismissed = (version: number) => {
  try {
    window.localStorage.setItem(DISMISS_KEY, JSON.stringify({ updateVersion: String(version) }));
  } catch {
    /* 写失败不补偿：关闭记忆是打扰抑制，丢标记只回到基线行为 */
  }
};
