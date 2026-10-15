import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { request } from "@/lib/api";
import { formatVersion } from "@/lib/version";
import { toast } from "@/lib/toast";

interface AutoState {
  state: "idle" | "downloading" | "staged" | "applied";
  version: string | null;
  received?: number;
  total?: number | null;
}

interface UpdateCheckState {
  current: string;
  latest: string | null;
  has_update: boolean;
  notes: string;
  notes_url: string;
  download_url: string;
  auto?: AutoState;
}

/** 节拍＝5 秒一跳（轮本地端点零负担）：快面（下载中/已就绪/有更新未生效）每跳都拉
 *  ——10-15 boss 口径「都要有地方可以看到，不然就像没反应」，下载百分比实时走这；
 *  慢面每 180 跳（＝15 分钟）拉一次。真实外呼仍由后端 1 小时节流统一裁决。 */
const TICK_MS = 5 * 1000;
const SLOW_TICKS = 180;

import { DOWNLOAD_HOME } from "@/lib/updateUrl";

declare global {
  interface Window {
    /** 「已自动更新」一次笛的会话内去重标记（applied 版本号） */
    __updateAppliedSeen?: string;
  }
}

/**
 * 全局更新提示条（client-update-notify ＋ silent-upgrade P1 三态）。
 * - 手动态（auto 非 staged）：发现新版本 →「去下载」开官网（现有手动链不变）；
 * - staged（新包已备好已验签）：主按钮「重启更新」＝ POST /apply → 桥 quit_app →
 *   退出链尾部静默装＋自动回新版；「暂不」＝ auto-skip（删暂存、本版本不再自动）；
 * - downloading：只说"正在后台准备"，不给按钮（不打扰写作）；
 * - applied：一次性「已更新」轻提示由 toast 承担，横幅回到常规态。
 * ⚠️「重启更新」的保护做在点击处（后端 /apply 成功才关窗）：destroy 不触发
 * beforeunload，生成/保存中请先在业务处确认（桥路径绕不过关窗链）。
 */
export default function UpdateNotice({
  /** 双轨兜底判定阈值（测试注入 0＝立即判定自动链不可用）；默认 90 秒 */
  stallMs = 90_000,
}: {
  stallMs?: number;
} = {}) {
  const { pathname } = useLocation();
  const [state, setState] = useState<UpdateCheckState | null>(null);
  const [applying, setApplying] = useState(false);

  const refresh = useCallback(async () => {
    try {
      // quiet：检测是后台探测，任何失败（含 503）都不得弹全局错误 toast
      setState(await request("/update-check", { quiet: true }));
    } catch {
      /* 检测失败静默：不打扰写作 */
    }
  }, []);

  const auto = state?.auto;
  const downloading = auto?.state === "downloading";
  const downloadPct =
    downloading && auto?.total
      ? Math.min(99, Math.round(((auto.received ?? 0) / auto.total) * 100))
      : null;
  // 快轮询面（10-14 真机复盘）：只要「有更新且尚未生效/未被暂缓」就 1 分钟复查——
  // 否则下载触发后横幅最长 15 分钟才变脸（v6 验收实锤「没有你说的这些」）。
  // 轮的是本地端点，零外呼负担。
  const pollFast = downloading || auto?.state === "staged" || !!state?.has_update;

  // 双轨收敛（10-15 boss 口径「有这套了，老的还在起作用」）：检测到更新后正常几秒内
  // 就转 downloading——手动态横幅若 90 秒仍停在 idle，判定自动链不可用（渠道坏/闸关），
  // 这时才亮「去下载」兜底；90 秒内只说「正在自动准备」，不给手动入口。
  const [idleSince, setIdleSince] = useState<number | null>(null);
  const manualIdle = !!state?.has_update && (auto?.state ?? "idle") === "idle";
  useEffect(() => {
    setIdleSince(manualIdle ? (t) => t ?? Date.now() : null);
  }, [manualIdle]);
  const autoStalled = idleSince !== null && Date.now() - idleSince >= stallMs;

  // 节拍器模式（判例：把节奏量放进 effect 依赖＝状态每翻转一次就重拉一次，
  // 「知道了」刚关掉的横幅被立刻拉回）。定时器恒 1 分钟一跳：快面每跳都拉，
  // 慢面每 180 跳拉一次（＝15 分钟），轮的始终是本地端点。
  const pollFastRef = useRef(pollFast);
  pollFastRef.current = pollFast;
  const tickRef = useRef(0);

  useEffect(() => {
    refresh();
    const timer = setInterval(() => {
      tickRef.current += 1;
      if (pollFastRef.current || tickRef.current % SLOW_TICKS === 0) {
        refresh();
      }
    }, TICK_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  if (!state?.latest) return null;

  const stagedVersion = auto?.state === "staged" ? auto.version : null;

  // staged 的横幅独立于 has_update（dismissed 只管手动文案；就绪态要一直可见）
  if (!stagedVersion && (!state.has_update || !state.latest)) {
    // 「已自动更新」一次笛（按版本记忆由后端 applied 标记承担，会话内只说一次）
    if (auto?.state === "applied" && auto.version && window.__updateAppliedSeen !== auto.version) {
      window.__updateAppliedSeen = auto.version;
      toast.success(`已自动更新到 v${auto.version}`);
    }
    return null;
  }

  const immersive = pathname.startsWith("/novel/");

  const dismiss = async () => {
    const latest = state.latest;
    setState((s) => (s ? { ...s, has_update: false } : s));
    try {
      await request("/update-check/dismiss", {
        method: "POST",
        body: JSON.stringify({ version: latest }),
        quiet: true,
      });
    } catch {
      /* 关闭失败无感：大不了下次启动再提示 */
    }
  };

  const skipAuto = async () => {
    const v = auto?.version ?? state.latest;
    setState((s) => (s ? { ...s, auto: { state: "idle", version: null } } : s));
    try {
      await request("/update-check/auto-skip", {
        method: "POST",
        body: JSON.stringify({ version: v }),
        quiet: true,
      });
    } catch {
      /* 失败无感：下个检测窗自动链会回来 */
    }
  };

  const restartToUpdate = async () => {
    if (applying) return;
    // 前置确认（唯一一次点击语义）：在途生成/未保存由用户此刻自查——桥路径不经 beforeunload
    if (!window.confirm(`即将退出并安装 v${auto?.version ?? state.latest}，完成后自动重新打开。继续？`)) {
      return;
    }
    setApplying(true);
    try {
      await request("/update-check/apply", { method: "POST", quiet: true });
    } catch {
      toast.error("更新未能就绪（可能已被发布方暂停），请稍后用「检查更新」重试");
      setApplying(false);
      return;
    }
    const bridge = (window as unknown as {
      pywebview?: { api?: { quit_app?: () => void } };
    }).pywebview?.api;
    if (bridge?.quit_app) {
      bridge.quit_app(); // 壳层退出链接管：静默装＋自动回新版
    } else {
      // 浏览器兜底形态（无桥）：pending 已落，用户关闭应用即生效
      toast.info("更新已就绪：关闭应用后将自动安装并重新打开");
      setApplying(false);
    }
  };

  // 外链用真实锚点（target=_blank）而非编程式 window.open：pywebview cocoa
  // 后端只对 LinkActivated（锚点点击）走 OPEN_EXTERNAL_LINKS_IN_BROWSER →
  // 系统浏览器；与 NovelListPage upgradeBtn 同款写法。
  return (
    <div className={immersive ? "update-strip update-strip--imm" : "update-strip"}>
      <div className="notice info">
        {stagedVersion ? (
          <>
            <span className="nt">
              <b>
                新版本 v{stagedVersion} 已就绪
                {state.current ? `（当前 ${formatVersion(state.current)}）` : ""}
              </b>
              <span>重启后自动完成安装，书稿与配置不受影响</span>
            </span>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={applying}
              onClick={restartToUpdate}
            >
              {applying ? "正在准备…" : "重启更新"}
            </button>
            <button type="button" className="btn btn-ghost btn-sm" onClick={skipAuto}>
              暂不
            </button>
          </>
        ) : (
          <>
            <span className="nt">
              <b>
                {downloading
                  ? `新版本 v${state.latest} 正在后台下载${downloadPct !== null ? ` ${downloadPct}%` : ""}，就绪后一键安装`
                  : !autoStalled
                    ? `正在自动准备新版本 v${state.latest}…`
                    : `发现新版本 v${state.latest}（自动准备不可用，可手动下载）`}
              </b>
              {state.notes ? <span>{state.notes}</span> : null}
            </span>
            {!downloading ? (
              <>
                {autoStalled ? (
                  <a
                    className="btn btn-secondary btn-sm"
                    href={state.download_url || DOWNLOAD_HOME}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    去下载
                  </a>
                ) : null}
                {state.notes_url ? (
                  <a
                    className="btn btn-ghost btn-sm"
                    href={state.notes_url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    查看更新内容
                  </a>
                ) : null}
                <button type="button" className="btn btn-ghost btn-sm" onClick={dismiss}>
                  知道了
                </button>
              </>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
