import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "@/lib/toast";
import { isLoggedIn } from "@/lib/auth";
import { useTier } from "@/hooks/useTier";
import type { PackStatus } from "@/lib/licenseCache";

/**
 * 写作能力（提示词包）四态卡（c-prompt-pack-client 4.2）。
 *
 * 口径（design D5 / design-language §5）：
 * - 已就绪 / 换版中 / min_client 跳过＝全静默（整卡不渲染）；
 * - 未登录→去登录；获取中→行内忙点；失败→重新获取＋复制诊断；档位不够→去升级。
 * 用户可见名词统一「写作能力」；「提示词包/manifest/验签」不出现在任何文案里。
 *
 * 数据面：`/auth/verify` 的 prompt_pack 字段（LicenseProvider 消费）。「重新获取」
 * 打本地 /api/prompt-pack/check（后台触发同步）并 1s 短轮询 status（≤90s），
 * 完成/变化后 refetch 权益上下文让整卡切换。
 */
const POLL_INTERVAL_MS = 1000;
const POLL_MAX_MS = 90_000;

export default function PromptPackCard() {
  const tier = useTier();
  const pack = tier?.pack ?? null;
  const [polling, setPolling] = useState(false);
  const pollStopRef = useRef<number | null>(null);

  const stopPoll = useCallback(() => {
    if (pollStopRef.current !== null) {
      window.clearTimeout(pollStopRef.current);
      pollStopRef.current = null;
    }
    setPolling(false);
  }, []);

  useEffect(() => stopPoll, [stopPoll]);

  const startCheck = useCallback(async () => {
    if (polling) return;
    setPolling(true);
    try {
      await api.post("/prompt-pack/check", undefined, { quiet: true });
    } catch {
      /* 触发失败走轮询兜底：状态不变则继续等 */
    }
    const deadline = Date.now() + POLL_MAX_MS;
    const tick = async () => {
      if (Date.now() > deadline) {
        stopPoll();
        toast.info("获取还没完成，稍后可再点「重新获取」");
        return;
      }
      try {
        const st = (await api.get("/prompt-pack/status", { quiet: true })) as PackStatus;
        if (st.phase === "ready" || st.phase === "tier_denied" || st.phase === "failed") {
          stopPoll();
          tier?.refetch?.();
          if (st.phase === "ready") toast.success("写作能力已就绪");
          return;
        }
      } catch {
        /* 本地接口瞬时失败：继续轮询 */
      }
      pollStopRef.current = window.setTimeout(() => void tick(), POLL_INTERVAL_MS);
    };
    pollStopRef.current = window.setTimeout(() => void tick(), POLL_INTERVAL_MS);
  }, [polling, stopPoll, tier]);

  const copyDiag = useCallback(async () => {
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
  }, [pack]);

  if (!pack || pack.phase === "ready" || pack.phase === "syncing") {
    // 获取中也不打扰（首启自动同步期间的点击由 BLOCK_TEXT 兜底提示）——
    // 仅当尚未就绪且已停下时才出卡面
    return null;
  }

  if (pack.phase === "tier_denied") {
    return (
      <div className="rail-pack" data-od-id="pack-card" data-testid="pack-card">
        <div className="lhead">
          <b>该能力随 MAX 提供</b>
        </div>
        <p>升级 MAX 解锁剧情推演、去 AI 味与文风蒸馏；你的书与稿子不受影响。</p>
        <button
          className="btn btn-primary btn-sm"
          data-od-id="pack-upgrade"
          onClick={() =>
            window.dispatchEvent(
              new CustomEvent("member-block", {
                detail: { message: "写作能力的高级按 MAX 提供——升级后解锁" },
              }),
            )
          }
        >
          去升级
        </button>
      </div>
    );
  }

  // missing（未装；可能未登录）与 failed（获取失败）
  const failed = pack.phase === "failed";
  return (
    <div className="rail-pack" data-od-id="pack-card" data-testid="pack-card">
      <div className="lhead">
        <b>{failed ? "写作能力没有就绪" : "登录后获取写作能力"}</b>
      </div>
      <p>
        {failed
          ? "上次获取没完成（网络或服务暂时不可用）。手写不受影响，随时重试。"
          : "登录一次，自动下载写作所需的全部能力；之后离线也能照常写。"}
      </p>
      {isLoggedIn() ? (
        <>
          <button
            className="btn btn-primary btn-sm"
            data-od-id="pack-retry"
            disabled={polling}
            onClick={() => void startCheck()}
          >
            {polling ? "正在重新获取…" : "重新获取"}
          </button>
          <button
            className="btn btn-ghost btn-sm"
            data-od-id="pack-diag"
            onClick={() => void copyDiag()}
          >
            复制诊断信息
          </button>
        </>
      ) : (
        <a className="btn btn-primary btn-sm" data-od-id="pack-go-login" href="#/login">
          去登录
        </a>
      )}
    </div>
  );
}
