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

// ── 引导弹窗关闭记忆（c-pack-modal-dismiss） ──────────────────────────────
// 单 key JSON：install＝用户关过首装引导（自动弹资格取消，装上即清自愈）；
// updateVersion＝「暂不更新」时所见的 CDN 版本锚（同版不重弹，版本变化自动重臂）。
// 纯本机 UX 偏好（design Non-Goals：不进服务端）；写失败（隐私模式等）静默——
// 最坏退回现状「每次重弹」。
const DISMISS_KEY = "pack-modal-dismissed";

interface PackDismissal {
  install?: boolean;
  updateVersion?: string;
}

export const readPackDismissal = (): PackDismissal => {
  try {
    const raw = window.localStorage.getItem(DISMISS_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as PackDismissal;
    return typeof parsed === "object" && parsed !== null ? parsed : {};
  } catch {
    return {};
  }
};

const writePackDismissal = (next: PackDismissal) => {
  try {
    window.localStorage.setItem(DISMISS_KEY, JSON.stringify(next));
  } catch {
    /* 写失败不补偿：关闭记忆是打扰抑制，丢标记只回到基线行为 */
  }
};

/** 关过首装引导（包仍未装上时关窗）——自动首装提醒资格取消 */
export const writePackInstallDismissed = () => {
  writePackDismissal({ ...readPackDismissal(), install: true });
};
/** 安装成功自愈：清首装标记（包再度缺失时自动提醒资格恢复，spec 场景钉） */
export const clearPackInstallDismissed = () => {
  const cur = readPackDismissal();
  if (!cur.install) return;
  writePackDismissal({ updateVersion: cur.updateVersion });
};
/** 暂不更新：记当下 CDN 版本锚——同版不再弹，probe 版本号变化即重臂 */
export const writePackUpdateDismissed = (version: string) => {
  writePackDismissal({ ...readPackDismissal(), updateVersion: version });
};
