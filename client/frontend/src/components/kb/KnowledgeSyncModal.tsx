import { useCallback, useEffect, useRef, useState } from "react";
import Modal from "@/components/design/Modal";
import { Ico, P } from "@/components/icons";
import { kbApi } from "@/lib/kbApi";
import {
  setLastKbProbe,
  writeKbUpdateDismissed,
  type KbSyncModalMode,
} from "@/lib/kbProbe";
import { toast } from "@/lib/toast";
import { finishDialog } from "@/lib/dialogQueue";

/**
 * 官方知识更新弹窗（c-kb-baseline-update-ux）：更新确认／手动检查两模式单实例
 * 状态机，照 PromptPackModal 剪裁（基线无档位无登录，同步秒级——不做分步轮询）。
 * 壳层单点挂载（App），CustomEvent `kb-sync-modal:open` 开启——触发方＝
 * KnowledgeBasePage 挂载探测（update）、页头「官方知识 vN」入口（manual）。
 *
 * - update：开窗即确认态（当前 vN → 最新 vM）；
 * - manual：检查更新 → 有更新转确认 / 无更新 toast「已是最新」；
 * - 点「立即更新」→ await POST /kb/baseline/sync（幂等直回）→ 完成 toast。
 */
type KbStage = "idle" | "confirm" | "running" | "done" | "failed";

export default function KnowledgeSyncModal() {
  const [open, setOpen] = useState(false);
  const [stage, setStage] = useState<KbStage>("idle");
  const [fromVersion, setFromVersion] = useState(0);
  const [toVersion, setToVersion] = useState(0);
  const [checking, setChecking] = useState(false);
  const [doneVersion, setDoneVersion] = useState(0);
  // running 守卫镜像：onOpen 闭包读它（读 state 会拿到订阅时的旧值）
  const runningRef = useRef(false);
  runningRef.current = stage === "running";

  const startRun = useCallback(async () => {
    setStage("running");
    try {
      const r = await kbApi.baselineSync();
      const version = r.version ?? toVersion;
      if (r.status === "failed") {
        setStage("failed");
        return;
      }
      // synced / current（竞态下他路已装同版）都算就绪
      setDoneVersion(version);
      setStage("done");
      toast.success(`官方知识已更新到 v${version}`);
      // 探测缓存随完成收敛：页头入口不再滞留旧版本号
      setLastKbProbe({
        installed: version,
        latest: version,
        update_available: false,
      });
    } catch {
      setStage("failed");
    }
  }, [toVersion]);

  useEffect(() => {
    const onOpen = (e: Event) => {
      // 进度期收到新开启事件一律忽略（照 PromptPackModal 重入守卫）
      if (runningRef.current) return;
      const d = ((e as CustomEvent).detail ?? {}) as {
        mode?: KbSyncModalMode;
        from?: number;
        to?: number;
      };
      if (d.mode === "update") {
        setFromVersion(d.from ?? 0);
        setToVersion(d.to ?? 0);
        setStage("confirm");
      } else {
        setStage("idle");
      }
      setOpen(true);
    };
    window.addEventListener("kb-sync-modal:open", onOpen as EventListener);
    return () => {
      window.removeEventListener("kb-sync-modal:open", onOpen as EventListener);
    };
  }, []);

  const close = useCallback(() => {
    // 关闭记忆（照 pack-modal-dismiss 口径）：更新确认态关＝暂不更新记版本锚
    // （同版不重弹）；manual 空闲态不记——用户主动开的检查窗，关闭不带
    // 「别再提醒」语义。
    if (stage === "confirm") {
      writeKbUpdateDismissed(toVersion);
    }
    setOpen(false);
    // 出队（放行壳层队列的后续条目）
    finishDialog("kb-sync");
  }, [stage, toVersion]);

  const runProbe = useCallback(async () => {
    if (checking) return;
    setChecking(true);
    try {
      const out = await kbApi.baselineProbe();
      if (out.update_available) {
        setFromVersion(out.installed);
        setToVersion(out.latest);
        setStage("confirm");
        return;
      }
      toast.info("已是最新");
    } catch {
      toast.info("暂时检查不了，稍后再试");
    } finally {
      setChecking(false);
    }
  }, [checking]);

  const title =
    stage === "running"
      ? "正在更新官方知识"
      : stage === "confirm"
        ? "官方知识有更新"
        : stage === "done"
          ? "官方知识已更新"
          : stage === "failed"
            ? "更新没有完成"
            : "官方知识";

  const footer =
    stage === "running" ? null : stage === "confirm" ? (
      <>
        <button className="btn btn-ghost btn-sm" data-testid="kb-sync-later" onClick={close}>
          暂不更新
        </button>
        <button
          className="btn btn-primary btn-sm"
          data-testid="kb-sync-confirm"
          onClick={() => void startRun()}
        >
          立即更新
        </button>
      </>
    ) : stage === "done" ? (
      <button className="btn btn-primary btn-sm" data-testid="kb-sync-done-close" onClick={close}>
        好的
      </button>
    ) : stage === "failed" ? (
      <button
        className="btn btn-primary btn-sm"
        data-testid="kb-sync-retry"
        onClick={() => void startRun()}
      >
        再试一次
      </button>
    ) : (
      <button
        className="btn btn-primary btn-sm"
        data-testid="kb-sync-check"
        disabled={checking}
        onClick={() => void runProbe()}
      >
        {checking ? "正在检查…" : "检查更新"}
      </button>
    );

  return (
    <Modal open={open} onClose={close} title={title} footer={footer} locked={stage === "running"}>
      {stage === "running" && (
        <p className="pm-note" data-testid="kb-sync-running-note">
          正在获取最新一版官方知识，很快就好；网络较慢时可能需要一会儿。
        </p>
      )}
      {stage === "confirm" && (
        <>
          <div className="pm-ver" data-testid="kb-sync-versions">
            当前 <b>v{fromVersion || "-"}</b>
            <span aria-hidden="true">→</span>
            最新 <b>v{toVersion || "-"}</b>
          </div>
          <p className="pm-note" data-testid="kb-sync-confirm-note">
            更新自动完成，已有的知识和书不受影响；现在不更新也不影响手头工作。
          </p>
        </>
      )}
      {stage === "done" && (
        <div className="pm-ok" data-testid="kb-sync-done">
          <span className="pm-ic">
            <Ico d={P.check} sw={2} />
          </span>
          {doneVersion ? `v${doneVersion} ` : ""}已装好，写新书时就能用上。
        </div>
      )}
      {stage === "failed" && (
        <p className="pm-warn" data-testid="kb-sync-fail-note">
          网络或服务暂时不可用，稍后可以再试；已有的知识不受影响。
        </p>
      )}
      {stage === "idle" && (
        <p className="pm-note" data-testid="kb-sync-manual-note">
          检查官方知识是否有更新；更新在后台自动完成，期间可以正常写作。
        </p>
      )}
    </Modal>
  );
}
