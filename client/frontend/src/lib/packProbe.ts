// 写作能力版本探测的会话内缓存与弹窗开启事件（c-prompt-pack-onboard-modal）。
import { enqueueDialog } from "@/lib/dialogQueue";
// 独立叶子模块：NovelListPage 挂载探测写入，AcctMenu hint / PromptPackModal 手动
// 模式读取——内存缓存不落盘（探测廉价幂等，刷新页面后重新探测即可）。

export interface PackProbe {
  installed_version: string;
  latest_version: string;
  update_available: boolean;
  reason?: string;
  /** source=dev：开发/测试态包内目录可用（书架挂载据此静默，不弹首装窗） */
  source?: "pack" | "dev";
}

export type PackModalMode = "install" | "update" | "manual";

export interface PackModalDetail {
  mode: PackModalMode;
  /** update 模式：确认行展示 当前 from → 最新 to */
  from?: string;
  to?: string;
}

let lastProbe: PackProbe | null = null;

export const getLastProbe = (): PackProbe | null => lastProbe;
export const setLastProbe = (p: PackProbe) => {
  lastProbe = p;
};

/**
 * 打开写作能力弹窗（单实例 PromptPackModal 监听；沿用 legacy-migrate:open 先例）。
 * c-lossless-upgrade：呈现经壳层弹窗队列（shell-dialog-queue）——带回流程未由
 * 用户「完成确认」收尾前不入场；**队列只延迟呈现，不延迟探测与后台下载**。
 */
export const openPackModal = (detail: PackModalDetail) => {
  enqueueDialog("pack", 2, () => {
    window.dispatchEvent(new CustomEvent<PackModalDetail>("pack-modal:open", { detail }));
  });
};

// ── 挂载探测在途槽（StrictMode 双挂载去重：只放行一次） ────────────────────
let probeInFlight = false;

/** 返回 true＝获得本轮探测权（调用方 finally 里必须 releasePackProbe） */
export const claimPackProbe = (): boolean => {
  if (probeInFlight) return false;
  probeInFlight = true;
  return true;
};
export const releasePackProbe = () => {
  probeInFlight = false;
};
/** 登出/换号复位（评审 P2-3）：探测缓存与在途槽一并清——下一账号不得沿用上一账号结果 */
export const resetPackProbeState = () => {
  lastProbe = null;
  probeInFlight = false;
};
/** 测试夹具专用：复位在途槽 */
export const resetPackProbeSlotForTests = () => {
  probeInFlight = false;
};
