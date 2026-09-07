import { useCallback, useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { request } from "@/lib/api";
import { formatVersion } from "@/lib/version";

interface UpdateCheckState {
  current: string;
  latest: string | null;
  has_update: boolean;
  notes: string;
  notes_url: string;
  download_url: string;
}

/** 会话内复查节奏：只打本地端点；真实外呼由后端 1 小时节流统一裁决 */
const POLL_INTERVAL_MS = 15 * 60 * 1000;

const DOWNLOAD_HOME = "https://www.awesomenovel.com/";

/**
 * 全局更新提示条（client-update-notify）。
 * 启动拉一次 + 每 15 分钟复查；有更新时所有屏顶端呈现 info 提示条，
 * 「去下载」开官网下载页、「查看更新内容」开该版本说明页（均为系统浏览器），
 * 「知道了」按版本关闭（后端 data/update-check.json 记忆）。
 */
export default function UpdateNotice() {
  const { pathname } = useLocation();
  const [state, setState] = useState<UpdateCheckState | null>(null);

  const refresh = useCallback(async () => {
    try {
      // quiet：检测是后台探测，任何失败（含 503）都不得弹全局错误 toast
      setState(await request("/update-check", { quiet: true }));
    } catch {
      /* 检测失败静默：不打扰写作 */
    }
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  if (!state?.has_update || !state.latest) return null;

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

  // 外链用真实锚点（target=_blank）而非编程式 window.open：pywebview cocoa
  // 后端只对 LinkActivated（锚点点击）走 OPEN_EXTERNAL_LINKS_IN_BROWSER →
  // 系统浏览器；与 NovelListPage upgradeBtn 同款写法。
  return (
    <div className={immersive ? "update-strip update-strip--imm" : "update-strip"}>
      <div className="notice info">
        <span className="nt">
          <b>
            发现新版本 v{state.latest}
            {/* 对照的当前版本取自同一次检测响应，零额外请求；缺失时退回原文案 */}
            {state.current ? `（当前 ${formatVersion(state.current)}）` : ""}
          </b>
          {state.notes ? <span>{state.notes}</span> : null}
        </span>
        <a
          className="btn btn-secondary btn-sm"
          href={state.download_url || DOWNLOAD_HOME}
          target="_blank"
          rel="noopener noreferrer"
        >
          去下载
        </a>
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
      </div>
    </div>
  );
}
