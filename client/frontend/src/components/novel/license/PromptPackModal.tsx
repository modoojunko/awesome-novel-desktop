import { useCallback, useEffect, useRef, useState } from "react";
import Modal from "@/components/design/Modal";
import { Ico, P } from "@/components/icons";
import { useTier } from "@/hooks/useTier";
import { isLoggedIn } from "@/lib/auth";
import { api } from "@/lib/api";
import type { PackStatus } from "@/lib/licenseCache";
import { getLastProbe, setLastProbe, type PackModalMode, type PackProbe } from "@/lib/packProbe";
import { toast } from "@/lib/toast";
import { finishDialog } from "@/lib/dialogQueue";

/**
 * 写作能力引导弹窗（c-prompt-pack-onboard-modal）：首装自动／更新确认／手动检查
 * 三模式单实例状态机（design D7），壳层单点挂载（App），CustomEvent `pack-modal:open`
 * 开启——触发方＝NovelListPage 挂载探测、AcctMenu「写作能力」菜单项。
 *
 * - install：开窗即 running（POST /prompt-pack/check 触发后台同步＋分步进度）；
 * - update：开窗即 confirm（当前 vN → 最新 vM），确认后复用同一进度；
 * - manual：状态＋「检查更新」→ 有更新转 confirm／未就绪转 install 流／无更新 toast。
 *
 * running 期 1s 短轮询 /prompt-pack/status（≤180s，S端 冷启动 60s 口径）；进度期弹窗
 * 锁定（用户拍板 10-07 二次：完成才提示可关闭，失败解锁给重试；confirm/manual 态
 * 不锁）。文案沿用「写作能力」统一口径，
 * 提示词包/manifest/验签等内部词不进文案（design-language §13）。
 */
type PackStage = "idle" | "confirm" | "running" | "done" | "failed";

const POLL_INTERVAL_MS = 1000;
const POLL_MAX_MS = 180_000;

const STEP_LABELS = ["检查版本", "下载能力包", "校验安装"] as const;

/** 失败原因→人话（评审 P2-4：spec 点名失败态呈现失败原因；未映射 reason 走默认文案） */
const FAIL_NOTES: Record<string, string> = {
  cdn_unreachable: "网络暂时连不上，稍后可以重试。",
  download: "下载没有完成（网络或服务暂时不可用）。",
  key_retired: "服务端已发布新版，重试会自动获取。",
  install: "安装没有完成，可以重试。",
};
const STEP_INDEX: Record<string, number> = { probe: 0, download: 1, install: 2 };

export default function PromptPackModal() {
  const tier = useTier();
  const [open, setOpen] = useState(false);
  const [stage, setStage] = useState<PackStage>("idle");
  // 进度期文案分诊（拍板 10-07 三次）：首装/更新（升级）同锁定口径，标题与耗时说明各自明说
  const [runKind, setRunKind] = useState<"install" | "update">("install");
  const [fromVersion, setFromVersion] = useState("");
  const [toVersion, setToVersion] = useState("");
  const [checking, setChecking] = useState(false);
  const [liveStep, setLiveStep] = useState<"" | "probe" | "download" | "install">("");
  const [doneVersion, setDoneVersion] = useState("");
  // 轮询拿到的终态相位与失败原因（评审 P2-4/P3-3：denied 不再等 refetch 落地才翻）
  const [finalPhase, setFinalPhase] = useState("");
  const [failNote, setFailNote] = useState("");
  const pollStopRef = useRef<number | null>(null);
  // run-token（评审 P1-3）：每轮轮询持序号，恢复时序号不符即自杀——根治
  // 「旧 tick 在途恢复后覆盖 pollStopRef 杀不掉」的双链竞态
  const runSeqRef = useRef(0);
  // running 守卫镜像：onOpen 闭包读它（读 state 会拿到订阅时的旧值）
  const runningRef = useRef(false);
  runningRef.current = stage === "running";

  const stopPoll = useCallback(() => {
    if (pollStopRef.current !== null) {
      window.clearTimeout(pollStopRef.current);
      pollStopRef.current = null;
    }
  }, []);

  const startRun = useCallback(async () => {
    stopPoll();
    runSeqRef.current += 1;
    const seq = runSeqRef.current;
    setLiveStep("");
    setFinalPhase("");
    setFailNote("");
    setStage("running");
    try {
      await api.post("/prompt-pack/check", undefined, { quiet: true });
    } catch {
      /* 触发失败走轮询兜底：状态不变则继续等 */
    }
    const deadline = Date.now() + POLL_MAX_MS;
    const tick = async () => {
      if (runSeqRef.current !== seq) return; // 旧链自杀：新一轮已开跑
      if (Date.now() > deadline) {
        stopPoll();
        setStage("failed");
        return;
      }
      try {
        const st = (await api.get("/prompt-pack/status", { quiet: true })) as PackStatus;
        if (runSeqRef.current !== seq) return; // await 期间被新轮替换
        setLiveStep(st.step ?? "");
        if (st.phase === "ready" || st.phase === "failed" || st.phase === "tier_denied") {
          stopPoll();
          setStage(st.phase === "ready" ? "done" : "failed");
          setFinalPhase(st.phase);
          setDoneVersion(st.version ?? "");
          setFailNote(st.reason ? (FAIL_NOTES[st.reason] ?? "") : "");
          if (st.phase === "ready") {
            // 探测缓存随安装完成收敛（评审 P2-3）：菜单 hint 不再滞留「有新版本」
            const last = getLastProbe();
            if (last) {
              setLastProbe({
                ...last,
                installed_version: st.version ?? last.installed_version,
                latest_version: st.version ?? last.latest_version,
                update_available: false,
              });
            }
          }
          tier?.refetch?.();
          return;
        }
      } catch {
        /* 本地接口瞬时失败：继续轮询 */
      }
      pollStopRef.current = window.setTimeout(() => void tick(), POLL_INTERVAL_MS);
    };
    pollStopRef.current = window.setTimeout(() => void tick(), POLL_INTERVAL_MS);
  }, [stopPoll, tier]);

  useEffect(() => {
    const onOpen = (e: Event) => {
      // running 重入守卫（评审 P1-3）：进度期收到新开启事件（如进度中回作品页再探测）
      // 一律忽略——锁定态不得被降级成可关的确认弹窗，也不得重开第二条轮询链
      if (runningRef.current) return;
      const d = ((e as CustomEvent).detail ?? {}) as {
        mode?: PackModalMode;
        from?: string;
        to?: string;
      };
      const m = d.mode === "update" || d.mode === "manual" ? d.mode : "install";
      if (m === "install") {
        setRunKind("install");
        void startRun();
      } else if (m === "update") {
        setRunKind("update");
        setFromVersion(d.from ?? "");
        setToVersion(d.to ?? "");
        setStage("confirm");
      } else {
        setStage("idle");
      }
      setOpen(true);
    };
    window.addEventListener("pack-modal:open", onOpen as EventListener);
    return () => {
      window.removeEventListener("pack-modal:open", onOpen as EventListener);
    };
  }, [startRun]);
  // 卸载专用清理（stopPoll 恒稳，不随渲染重跑）——轮询链绝不能被重渲染打断
  useEffect(() => stopPoll, [stopPoll]);

  const close = useCallback(() => {
    // 中途关窗＝纯视觉退出：后台同步继续（不 abort），四态卡兜底
    stopPoll();
    setOpen(false);
    // c-lossless-upgrade：出队（放行壳层队列的后续条目）
    finishDialog("pack");
  }, [stopPoll]);

  const runProbe = useCallback(async () => {
    if (checking) return;
    setChecking(true);
    try {
      const out = (await api.get("/prompt-pack/probe", { quiet: true })) as PackProbe;
      setLastProbe(out);
      if (out.update_available) {
        setRunKind("update");
        setFromVersion(out.installed_version);
        setToVersion(out.latest_version);
        setStage("confirm");
        return;
      }
      if (!out.installed_version && out.reason === "min_client_version") {
        // 旧客户端装不了新包：不进首装流（评审 P1-2），引导先更新客户端
        toast.info("先更新客户端后可获取写作能力");
        return;
      }
      const phase = tier?.pack?.phase;
      if (!out.installed_version || phase === "missing" || phase === "failed" || phase === "syncing") {
        // 未就绪／receipt 缺失 → 转首装进度流（不弹 toast，直接开跑）
        setRunKind("install");
        void startRun();
        return;
      }
      toast.info("已是最新");
    } catch {
      toast.info("暂时检查不了，稍后再试");
    } finally {
      setChecking(false);
    }
  }, [checking, startRun, tier]);

  const copyDiag = useCallback(async () => {
    const pack = tier?.pack;
    const text = JSON.stringify({
      phase: pack?.phase,
      reason: pack?.reason,
      tier: pack?.tier,
      version: pack?.version,
      updated_at: pack?.updated_at,
    });
    try {
      await navigator.clipboard.writeText(text);
      toast.success("诊断信息已复制，可发给客服");
    } catch {
      toast.info(text);
    }
  }, [tier]);

  const denied = (finalPhase || tier?.pack?.phase) === "tier_denied";
  const curStep = liveStep ? (STEP_INDEX[liveStep] ?? 0) : 0;

  const title =
    stage === "running"
      ? runKind === "update"
        ? "正在更新写作能力"
        : "正在准备写作能力"
      : stage === "confirm"
        ? "写作能力有更新"
        : stage === "done"
          ? "写作能力已就绪"
          : stage === "failed"
            ? "写作能力没有就绪"
            : "写作能力";

  const footer =
    stage === "running" ? null : stage === "confirm" ? (
      <>
        <button className="btn btn-ghost btn-sm" onClick={close}>
          暂不更新
        </button>
        <button
          className="btn btn-primary btn-sm"
          data-testid="pack-confirm-update"
          onClick={() => void startRun()}
        >
          立即更新
        </button>
      </>
    ) : stage === "done" ? (
      <button className="btn btn-primary btn-sm" data-testid="pack-done-close" onClick={close}>
        开始写作
      </button>
    ) : stage === "failed" ? (
      denied ? (
        <button
          className="btn btn-primary btn-sm"
          onClick={() => {
            close();
            window.dispatchEvent(
              new CustomEvent("member-block", {
                detail: { message: "写作能力的高级按 MAX 提供——升级后解锁" },
              }),
            );
          }}
        >
          去升级
        </button>
      ) : (
        <>
          <button className="btn btn-ghost btn-sm" onClick={() => void copyDiag()}>
            复制诊断信息
          </button>
          <button className="btn btn-primary btn-sm" data-testid="pack-retry" onClick={() => void startRun()}>
            重新获取
          </button>
        </>
      )
    ) : isLoggedIn() ? (
      <button
        className="btn btn-primary btn-sm"
        data-testid="pack-check-update"
        disabled={checking}
        onClick={() => void runProbe()}
      >
        {checking ? "正在检查…" : "检查更新"}
      </button>
    ) : (
      <a className="btn btn-primary btn-sm" href="#/login" onClick={close}>
        去登录
      </a>
    );

  // 进度期锁定（Modal locked：Esc/遮罩/X 全失效）；完成/失败/确认/手动态解锁
  return (
    <Modal open={open} onClose={close} title={title} footer={footer} locked={stage === "running"}>
      {stage === "running" && (
        <>
          <p className="pm-note" data-testid="pack-running-note">
            {runKind === "update"
              ? "正在更新到最新版本，期间不能关闭此窗口；预计 1 分钟左右，网络较慢时可能需要几分钟。"
              : "首次登录自动获取，期间不能关闭此窗口；预计 1 分钟左右，网络较慢时可能需要几分钟。完成后即可使用全部 AI 写作。"}
          </p>
          <div className="pm-steps" data-testid="pack-steps">
            {STEP_LABELS.map((label, i) => (
              <div
                key={label}
                className={`pm-step ${i < curStep ? "done" : i === curStep ? "doing" : "wait"}`}
              >
                <span className="pm-ic">
                  {i < curStep ? <Ico d={P.check} sw={2.2} /> : <span className="dot" />}
                </span>
                {label}
              </div>
            ))}
          </div>
        </>
      )}
      {stage === "confirm" && (
        <>
          <div className="pm-ver" data-testid="pack-versions">
            当前 <b>{fromVersion || "-"}</b>
            <span aria-hidden="true">→</span>
            最新 <b>{toVersion || "-"}</b>
          </div>
          <p className="pm-note" data-testid="pack-confirm-note">
            更新会自动完成，期间不能关闭此窗口；预计 1 分钟左右，网络较慢时可能需要几分钟。现在不更新也不影响手头工作。
          </p>
        </>
      )}
      {stage === "done" && (
        <div className="pm-ok" data-testid="pack-done">
          <span className="pm-ic">
            <Ico d={P.check} sw={2} />
          </span>
          {doneVersion || tier?.pack?.version || toVersion
            ? `v${doneVersion || tier?.pack?.version || toVersion} `
            : ""}
          已安装完成，AI 写作可以使用了。
        </div>
      )}
      {stage === "failed" &&
        (denied ? (
          <p className="pm-note">该能力随 MAX 提供——升级后解锁剧情推演、去 AI 味与文风蒸馏。</p>
        ) : (
          <p className="pm-warn" data-testid="pack-fail-note">
            {failNote
              ? `${failNote} 手写不受影响，随时可以重试。`
              : "获取没有完成（网络或服务暂时不可用）。手写不受影响，随时可以重试。"}
          </p>
        ))}
      {stage === "idle" && (
        <p className="pm-note" data-testid="pack-manual-note">
          {isLoggedIn()
            ? "检查写作能力是否有更新；下载在后台自动完成，期间可以正常写作。"
            : "登录一次，自动下载写作所需的全部能力；之后离线也能照常写。"}
        </p>
      )}
    </Modal>
  );
}
