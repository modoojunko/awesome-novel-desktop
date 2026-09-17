/** 「操作」页签 · 归档收尾区（archive-reconcile）：
 *  收尾进度（行聚合轮询）＋逐条采纳/驳回/重试。免费档无提案——占位提示。 */
import { useCallback, useEffect, useState } from "react";
import {
  acceptReconcile,
  fetchReconcile,
  KIND_LABEL,
  rejectReconcile,
  retryReconcile,
  type ReconcileProgress,
  type ReconcileRow,
} from "@/lib/reconcileApi";

const STATUS_TEXT: Record<ReconcileRow["status"], string> = {
  pending: "待确认",
  accepted: "已采纳",
  rejected: "已驳回",
  failed: "失败",
};

/** 摘要一行：按类别给出提案的可读描述。 */
function rowSummary(row: ReconcileRow): string {
  const p = row.payload ?? {};
  const parts: string[] = [];
  for (const it of p.items ?? []) {
    if (it.key) parts.push(`${it.key}：${it.value ?? ""}`);
    else if (it.name) parts.push(`${it.name}：${it.state_change ?? ""}`);
    else if (it.owner) parts.push(`${it.owner}↔${it.other}（${it.rel_type ?? ""}·${it.stance ?? ""}）`);
  }
  for (const it of p.planted ?? []) parts.push(`埋下：${it.description ?? ""}`);
  for (const it of p.resolved ?? []) parts.push(`收束：${it.description ?? ""}`);
  return parts.join("；") || "（无明细）";
}

export function ReconcilePane({
  projectId,
  chapterRef,
  archived,
  isPro,
  onRowsChanged,
}: {
  projectId: string;
  chapterRef: string;
  archived: boolean;
  isPro: boolean;
  onRowsChanged?: (rows: ReconcileRow[]) => void;
}) {
  const [rows, setRows] = useState<ReconcileRow[]>([]);
  const [progress, setProgress] = useState<ReconcileProgress | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    // 免费档不产生收尾行（占位态）：不发请求、不轮询
    if (!archived || !isPro) return;
    try {
      const data = await fetchReconcile(projectId, chapterRef);
      setRows(data.rows);
      setProgress(data.progress);
      onRowsChanged?.(data.rows);
      setError(null);
    } catch {
      setError("收尾进度获取失败，稍后自动重试");
    }
  }, [archived, isPro, chapterRef, projectId, onRowsChanged]);

  // 归档章：挂载即拉一次，之后 5s 轮询（后台产出推进可见）
  useEffect(() => {
    if (!archived || !isPro) return;
    void refresh();
    const t = setInterval(() => void refresh(), 5000);
    return () => clearInterval(t);
  }, [archived, isPro, refresh]);

  const act = useCallback(
    async (fn: () => Promise<void>, key: string) => {
      setBusy(key);
      try {
        await fn();
      } finally {
        setBusy(null);
        void refresh();
      }
    },
    [refresh],
  );

  if (!archived) return null;

  if (!isPro) {
    return (
      <div className="reconcile-pane" data-od-id="reconcile-pro-free">
        <p className="reconcile-lead">归档收尾（提取设定变化 / 关系建议 / 伏笔登记）</p>
        <p className="reconcile-note">PRO 可用 · 免费版归档即刻生效</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="reconcile-pane">
        <p className="reconcile-note">{error}</p>
      </div>
    );
  }

  const pending = rows.filter((r) => r.status === "pending");
  const failed = rows.filter((r) => r.status === "failed");
  const decided = rows.filter((r) => r.status === "accepted" || r.status === "rejected");

  return (
    <div className="reconcile-pane" data-od-id="reconcile-pane">
      <p className="reconcile-lead">
        归档收尾
        {progress && (
          <span className="reconcile-count">
            待确认 {progress.pending} · 失败 {progress.failed} · 已处理{" "}
            {progress.accepted + progress.rejected}
          </span>
        )}
      </p>

      {[...pending, ...failed, ...decided].length === 0 && (
        <p className="reconcile-note">收尾进行中，产出的建议会出现在这里……</p>
      )}

      {[...pending, ...failed, ...decided].map((row) => (
        <div
          key={row.id}
          className={`reconcile-row rc-${row.status}`}
          data-od-id={`reconcile-${row.id}`}
        >
          <span className={`rc-status rc-${row.status}`}>
            {STATUS_TEXT[row.status] ?? row.status}
          </span>
          <span className="rc-kind">{KIND_LABEL[row.kind] ?? row.kind}</span>
          <span className="rc-summary" title={rowSummary(row)}>
            {rowSummary(row)}
          </span>
          <span className="rc-acts">
            {row.status === "pending" && (
              <>
                <button
                  className="btn btn-primary btn-sm"
                  disabled={busy === row.id}
                  onClick={() =>
                    void act(
                      () => acceptReconcile(projectId, chapterRef, row.id),
                      row.id,
                    )
                  }
                >
                  采纳
                </button>
                <button
                  className="btn btn-ghost btn-sm"
                  disabled={busy === row.id}
                  onClick={() =>
                    void act(
                      () => rejectReconcile(projectId, chapterRef, row.id),
                      row.id,
                    )
                  }
                >
                  驳回
                </button>
              </>
            )}
            {row.status === "failed" && (
              <button
                className="btn btn-secondary btn-sm"
                disabled={busy === row.id}
                onClick={() =>
                  void act(
                    () => retryReconcile(projectId, chapterRef, row.id),
                    row.id,
                  )
                }
              >
                重试
              </button>
            )}
          </span>
          {row.error && <p className="rc-error">{row.error}</p>}
        </div>
      ))}

      {[...pending, ...failed].length > 0 && (
        <p className="reconcile-note">
          未确认的提案不参与后续章节的写作参考；不处理也不影响继续写作。
        </p>
      )}
    </div>
  );
}
