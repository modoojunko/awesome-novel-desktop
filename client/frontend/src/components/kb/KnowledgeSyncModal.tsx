import { useCallback, useEffect, useRef, useState } from "react";
import Modal from "@/components/design/Modal";
import { kbApi } from "@/lib/kbApi";
import {
  setLastKbProbe,
  writeKbUpdateDismissed,
  type KbProbe,
  type KbSyncModalMode,
} from "@/lib/kbProbe";
import { toast } from "@/lib/toast";
import { finishDialog } from "@/lib/dialogQueue";

/**
 * 官方知识按题材同步弹窗（s-kb-signed-delivery）。
 *
 * - 内容不分档，但每个题材是独立对象；一次只同步一个题材、S 端扣 1 次/天；
 * - 弹窗只展示题材清单/已同步状态/今日剩余次数，用户点哪行同步哪行；
 * - 登录钩子与周期复查只做免费探测，不会在这里静默扣额度；
 * - `focusGenre`（写作提示带入）高亮该书题材，未同步时给一句说明。
 *
 * 单实例壳层挂载（App），CustomEvent `kb-sync-modal:open` 开启；关闭走壳层队列。
 */
type KbStage = "loading" | "list" | "running" | "error";

interface GenreRow {
  genre: string;
  state?: { version: number; sha256: string };
  synced: boolean;
  updated: boolean;
}

function buildRows(probe: KbProbe | null): GenreRow[] {
  const genres = probe?.genres ?? {};
  const installed = probe?.installed_genres ?? {};
  return Object.keys(genres)
    .sort((a, b) => a.localeCompare(b, "zh-Hans-CN"))
    .map((genre) => {
      const meta = genres[genre];
      const state = installed[genre];
      const synced = !!state && state.sha256 === meta.sha256;
      return {
        genre,
        state,
        synced,
        updated: !!state && !synced,
      };
    });
}

function quotaText(probe: KbProbe | null): string {
  const quota = probe?.quota;
  if (!quota || quota.free) return "按题材逐个同步；每个题材每天记 1 次。";
  if (quota.remaining > 0) {
    return `今日还可同步 ${quota.remaining} 个题材（${quota.used}/${quota.limit}）。`;
  }
  return `今天的题材同步次数用完了（${quota.used}/${quota.limit}），明天恢复。`;
}

function skipNote(reason?: string): string {
  switch (reason) {
    case "quota_exceeded":
      return "今天的题材同步次数用完了，明天再来吧。";
    case "tier_denied":
      return "当前套餐不包含官方知识库。";
    case "not_logged_in":
      return "登录后就能同步官方知识。";
    case "retired":
      return "官方知识暂未开放，先用手头已有的。";
    case "format_newer":
      return "这个题材要用新版客户端才能装上。";
    case "genre_not_found":
      return "这一版没有这个题材。";
    case "older_than_installed":
      return "本机已有更新的版本，先不降级。";
    case "syncing":
      return "正在同步，稍等一下。";
    default:
      return "这次没有同步到内容。";
  }
}

export default function KnowledgeSyncModal() {
  const [open, setOpen] = useState(false);
  const [stage, setStage] = useState<KbStage>("list");
  const [mode, setMode] = useState<KbSyncModalMode>("manual");
  const [probe, setProbe] = useState<KbProbe | null>(null);
  const [focusGenre, setFocusGenre] = useState("");
  const [runningGenre, setRunningGenre] = useState("");
  const [failReason, setFailReason] = useState("");
  const runningRef = useRef(false);
  runningRef.current = stage === "running";

  const loadProbe = useCallback(async () => {
    setStage("loading");
    try {
      const p = await kbApi.baselineProbe();
      setProbe(p);
      setLastKbProbe(p);
      setStage("list");
    } catch {
      setFailReason("");
      setStage("error");
    }
  }, []);

  useEffect(() => {
    const onOpen = (e: Event) => {
      // running 期收到新开启事件一律忽略（照 PromptPackModal 重入守卫）
      if (runningRef.current) return;
      const d = ((e as CustomEvent).detail ?? {}) as {
        mode?: KbSyncModalMode;
        probe?: KbProbe;
        focusGenre?: string;
      };
      setMode(d.mode === "update" ? "update" : "manual");
      setFocusGenre(d.focusGenre ?? "");
      setRunningGenre("");
      setFailReason("");
      setOpen(true);
      if (d.probe) {
        setProbe(d.probe);
        setStage("list");
      } else {
        setProbe(null);
        void loadProbe();
      }
    };
    window.addEventListener("kb-sync-modal:open", onOpen as EventListener);
    return () => {
      window.removeEventListener("kb-sync-modal:open", onOpen as EventListener);
    };
  }, [loadProbe]);

  const close = useCallback(() => {
    // update 模式关闭＝暂不同步：记 release 版本锚（同版不重弹）
    if (mode === "update" && probe?.latest) {
      writeKbUpdateDismissed(probe.latest);
    }
    setOpen(false);
    finishDialog("kb-sync");
  }, [mode, probe?.latest]);

  const startRun = useCallback(
    async (genre: string) => {
      setStage("running");
      setRunningGenre(genre);
      try {
        const r = await kbApi.baselineSync(genre);
        if (r.status === "synced" || r.status === "current") {
          toast.success(
            r.status === "synced" ? `「${genre}」已同步` : `「${genre}」已经是最新`,
          );
          if (probe) {
            const meta = probe.genres?.[genre];
            const next: KbProbe = {
              ...probe,
              installed: Math.max(probe.installed, r.version ?? probe.latest),
              latest: Math.max(probe.latest, r.version ?? probe.latest),
              update_available: false,
              quota: r.quota ?? probe.quota,
              installed_genres: meta
                ? {
                    ...(probe.installed_genres ?? {}),
                    [genre]: {
                      version: r.version ?? probe.latest,
                      sha256: meta.sha256,
                      path: meta.path,
                      entries: r.entries ?? meta.entry_count,
                      synced_at: "",
                    },
                  }
                : probe.installed_genres,
            };
            setProbe(next);
            setLastKbProbe(next);
          }
          // 工作台/知识库页监听：同步完成后重算本题材提示（免费读缓存）
          window.dispatchEvent(new Event("kb-sync-completed"));
          setStage("list");
        } else if (r.status === "skipped") {
          toast.info(skipNote(r.reason));
          if (r.quota) {
            setProbe((prev) => (prev ? { ...prev, quota: r.quota } : prev));
          }
          setStage("list");
        } else {
          setFailReason(r.reason ?? "");
          setStage("error");
        }
      } catch {
        setFailReason("");
        setStage("error");
      } finally {
        setRunningGenre("");
      }
    },
    [probe],
  );

  const rows = buildRows(probe);
  const quota = probe?.quota;
  const quotaLeft = !quota || !!quota.free || quota.remaining > 0;
  const focusRow = rows.find((row) => row.genre === focusGenre);
  const probeNote =
    probe?.reason === "retired"
      ? "官方知识已撤回，先用手头已有的。"
      : probe?.reason === "not_configured"
        ? "这台机器的官方知识还没配置好。"
        : probe?.reason === "tier_denied"
          ? "当前套餐不包含官方知识库。"
          : probe?.reason === "format_newer"
            ? "这一版知识要用新版客户端才能装上。"
            : probe?.reason
              ? "暂时拿不到官方知识，稍后再试。"
              : "";

  const title =
    stage === "running" ? "正在同步官方知识" : "官方知识";

  const footer =
    stage === "running" ? null : stage === "error" ? (
      <>
        <button className="btn btn-ghost btn-sm" data-testid="kb-sync-close" onClick={close}>
          关闭
        </button>
        <button
          className="btn btn-primary btn-sm"
          data-testid="kb-sync-retry"
          onClick={() => void loadProbe()}
        >
          再试一次
        </button>
      </>
    ) : (
      <button className="btn btn-ghost btn-sm" data-testid="kb-sync-close" onClick={close}>
        {mode === "update" ? "暂不同步" : "关闭"}
      </button>
    );

  return (
    <Modal open={open} onClose={close} title={title} footer={footer} locked={stage === "running"}>
      {stage === "loading" && (
        <p className="pm-note" data-testid="kb-sync-loading">
          正在检查官方知识，很快就好。
        </p>
      )}
      {stage === "running" && (
        <p className="pm-note" data-testid="kb-sync-running-note">
          正在同步「{runningGenre}」，很快就好；其他题材不受影响。
        </p>
      )}
      {stage === "error" && (
        <p className="pm-warn" data-testid="kb-sync-fail-note">
          {failReason === "proxy_fake_ip"
            ? "代理软件的 TUN 模式接管了网络：请关闭 TUN 模式，或将本站域名加入代理软件的白名单，再点「再试一次」；已有的知识不受影响。"
            : "网络或服务暂时不可用，稍后可以再试；已有的知识不受影响。"}
        </p>
      )}
      {stage === "list" && (
        <>
          <p className="pm-note">
            按题材逐个同步；每个题材每天记 1 次，同步过的写作时就能用上。
          </p>
          <div className="pm-ver" data-testid="kb-genre-quota">
            {quotaText(probe)}
          </div>
          {probe?.resume && (
            <p className="pm-note" data-testid="kb-genre-resume">
              官方知识已恢复，可以按题材同步。
            </p>
          )}
          {probeNote && (
            <p className="pm-warn" data-testid="kb-genre-note">
              {probeNote}
            </p>
          )}
          {rows.length === 0 ? (
            <p className="pm-note" data-testid="kb-genre-empty">
              暂时没有可同步的题材。
            </p>
          ) : (
            <ul
              className="mt-3 divide-y divide-[var(--border)] rounded-md border border-[var(--border)]"
              data-testid="kb-genre-list"
            >
              {rows.map((row) => (
                <li
                  key={row.genre}
                  data-testid={`kb-genre-row-${row.genre}`}
                  className={`flex items-center gap-3 px-3 py-2 ${
                    focusGenre === row.genre ? "bg-[var(--accent-soft)]" : ""
                  }`}
                >
                  <span className="flex-1 text-[13px] text-[var(--fg)]">{row.genre}</span>
                  <span
                    className="text-[11px] text-[var(--muted)]"
                    data-testid={`kb-genre-state-${row.genre}`}
                  >
                    {row.synced
                      ? `已同步${row.state?.version ? ` v${row.state.version}` : ""}`
                      : row.updated
                        ? "可更新"
                        : "未同步"}
                  </span>
                  <button
                    className="btn btn-ghost btn-sm"
                    data-testid={`kb-genre-sync-${row.genre}`}
                    disabled={!!runningGenre || !quotaLeft}
                    onClick={() => void startRun(row.genre)}
                  >
                    {runningGenre === row.genre
                      ? "同步中…"
                      : row.synced
                        ? "重新同步"
                        : "同步"}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {focusRow && !focusRow.synced && (
            <p className="pm-note mt-2" data-testid="kb-genre-focus-note">
              这本书的题材「{focusGenre}」还没同步官方知识；同步后写作时就能用上。
            </p>
          )}
        </>
      )}
    </Modal>
  );
}
