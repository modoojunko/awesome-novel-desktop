/** 归档收尾提案区（archive-reconcile）：按写回目标各归各的页签——
 *  伏笔登记提案在「伏笔」页签、世界要素提案在「设定」页签（kinds 过滤）。
 *  「操作」页签只留生命周期卡与归档进度（c-ops-tab-progress-only）；
 *  免费档不渲染收尾区（PRO 信号由归档弹窗收尾计划承载）。 */
import { useCallback, useEffect, useState } from "react";
import {
  acceptReconcile,
  fetchReconcile,
  KIND_LABEL,
  rejectReconcile,
  retryReconcile,
  type ReconcileKind,
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

function ReconcileRowView({
  row,
  projectId,
  chapterRef,
  busy,
  act,
}: {
  row: ReconcileRow;
  projectId: string;
  chapterRef: string;
  busy: string | null;
  act: (fn: () => Promise<void>, key: string) => void;
}) {
  return (
    <div className={`reconcile-row rc-${row.status}`} data-od-id={`reconcile-${row.id}`}>
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
      {row.error && (
        <p className="rc-error" title={row.error}>
          {row.error}
        </p>
      )}
    </div>
  );
}

export function ReconcilePane({
  projectId,
  chapterRef,
  archived,
  kinds,
}: {
  projectId: string;
  chapterRef: string;
  archived: boolean;
  /** 本页签承载的收尾类别（各归各的页签）：伏笔页签传 ["hooks"]、设定页签传 ["lore"] */
  kinds: ReconcileKind[];
}) {
  const [rows, setRows] = useState<ReconcileRow[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    // 归档后拉取（收尾提案全档免费——tier-plan-four-tiers 3.3 后端已撤门）
    if (!archived) return;
    try {
      const data = await fetchReconcile(projectId, chapterRef);
      setRows(data.rows);
      setError(null);
    } catch {
      setError("收尾进度获取失败，稍后自动重试");
    }
  }, [archived, chapterRef, projectId]);

  // 归档章：挂载即拉一次，之后 5s 轮询（后台产出推进可见）
  useEffect(() => {
    if (!archived) return;
    void refresh();
    const t = setInterval(() => void refresh(), 5000);
    return () => clearInterval(t);
  }, [archived, refresh]);

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

  const title = `归档收尾 · ${kinds.map((k) => KIND_LABEL[k] ?? k).join("／")}提案`;

  if (error) {
    return (
      <div className="reconcile-pane">
        <p className="reconcile-lead">{title}</p>
        <p className="reconcile-note">{error}</p>
      </div>
    );
  }

  const mine = rows.filter((r) => kinds.includes(r.kind));
  const pending = mine.filter((r) => r.status === "pending");
  const failed = mine.filter((r) => r.status === "failed");
  const decided = mine.filter(
    (r) => r.status === "accepted" || r.status === "rejected",
  );
  const counts = [
    pending.length > 0 ? `待确认 ${pending.length}` : "",
    failed.length > 0 ? `失败 ${failed.length}` : "",
    decided.length > 0 ? `已处理 ${decided.length}` : "",
  ].filter(Boolean).join(" · ");

  return (
    <div className="reconcile-pane" data-od-id="reconcile-pane">
      <p className="reconcile-lead">
        {title}
        {counts && <span className="reconcile-count">{counts}</span>}
      </p>

      {[...pending, ...failed].length === 0 && decided.length === 0 && (
        <p className="reconcile-note">收尾进行中，产出的建议会出现在这里……</p>
      )}

      {[...pending, ...failed].map((row) => (
        <ReconcileRowView
          key={row.id}
          row={row}
          projectId={projectId}
          chapterRef={chapterRef}
          busy={busy}
          act={act}
        />
      ))}

      {decided.length > 0 && (
        <details className="rc-decided">
          <summary>已处理 {decided.length} 条（点开留痕）</summary>
          {decided.map((row) => (
            <ReconcileRowView
              key={row.id}
              row={row}
              projectId={projectId}
              chapterRef={chapterRef}
              busy={busy}
              act={act}
            />
          ))}
        </details>
      )}

      {[...pending, ...failed].length > 0 && (
        <p className="reconcile-note">
          未确认的提案不参与后续章节的写作参考；不处理也不影响继续写作。
        </p>
      )}
    </div>
  );
}
