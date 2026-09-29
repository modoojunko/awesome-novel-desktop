// 归档卡三段进度条（c-ops-archive-stages）：提取 → 确认 → 完成。
// 数据全部前端已有：提取态＝archiveJob，待确认数＝dossier GET progress（归档卡常驻拉取）。
// 提取是一次 AI 调用（行落库前无中间量），诚实的进行中信号＝已运行秒数，不做假百分比。
import { useEffect, useState } from "react";

export type ArchiveExtractStage = "active" | "done" | "fail" | "skip";

/** 提取进行中的已运行秒数（active 时每秒走针） */
export function useElapsedSec(startedAt: number | undefined, active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [active]);
  return active && startedAt ? Math.max(0, Math.round((now - startedAt) / 1000)) : 0;
}

function Node({
  state,
  label,
  detail,
}: {
  state: "active" | "done" | "fail" | "skip" | "todo";
  label: string;
  detail?: string;
}) {
  return (
    <span className={`as-node is-${state}`}>
      <i className="as-dot" aria-hidden />
      <span className="as-label">
        {label}
        {detail ? <em className="as-detail">{detail}</em> : null}
      </span>
    </span>
  );
}

export default function ArchiveStages({
  extract,
  elapsedSec,
  confirmLabel,
  confirmActive,
  done,
}: {
  extract: ArchiveExtractStage;
  /** 提取已运行秒数（仅 active 时有效） */
  elapsedSec?: number;
  /** 确认阶段补充文案（如「待确认 3 条」「提案已处理」）；null＝未开始 */
  confirmLabel: string | null;
  confirmActive?: boolean;
  /** 已归档＝完成段点亮 */
  done: boolean;
}) {
  const extractDetail =
    extract === "active"
      ? ` · 已 ${elapsedSec ?? 0} 秒`
      : extract === "skip"
        ? " · 未提取"
        : extract === "fail"
          ? " · 失败"
          : "";
  return (
    <div className="arch-stages" data-testid="archive-stages">
      <Node
        state={extract}
        label={extract === "active" ? "提取中" : "提取"}
        detail={extractDetail}
      />
      <span className="as-line" aria-hidden />
      <Node
        state={confirmLabel == null ? "todo" : confirmActive ? "active" : "done"}
        label="确认"
        detail={confirmLabel ? ` · ${confirmLabel}` : ""}
      />
      <span className="as-line" aria-hidden />
      <Node state={done ? "done" : "todo"} label="完成" />
    </div>
  );
}
