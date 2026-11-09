// 知识提炼任务详情（原型定稿 2026-11-08）：执行过程时间线＋结果账＋归位明细。
// 与拆书任务详情同骨架（返回清单＋页头＋分区）；进行中 3s 轮询。
import { useEffect } from "react";
import { Link, useParams } from "react-router-dom";
import { useState } from "react";
import { kbApi, type RefineTaskRow } from "../../lib/kbApi";
import { markTasksSeen } from "../../lib/toolsBadgeSeen";
import { useQuery, useQueryClient } from "@tanstack/react-query";

const PILL: Record<RefineTaskRow["status"], { label: string; cls: string }> = {
  queued: { label: "排队中", cls: "pill pill-warn" },
  running: { label: "提炼中", cls: "pill pill-accent" },
  completed: { label: "已完成", cls: "pill pill-ok" },
  failed: { label: "已失败", cls: "pill pill-err" },
  cancelled: { label: "已取消", cls: "pill" },
};

export default function RefineTaskDetailPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const [cancelBusy, setCancelBusy] = useState(false);
  const [cancelErr, setCancelErr] = useState("");
  const { data, refetch } = useQuery({
    queryKey: ["refine-task", id],
    queryFn: () => kbApi.refineTasks.get(id!),
    enabled: !!id,
    refetchInterval: (q) => (q.state.data && q.state.data.status !== "completed" && q.state.data.status !== "failed" && q.state.data.status !== "cancelled" ? 3000 : false),
  });

  const doCancel = async () => {
    if (!id || cancelBusy) return;
    setCancelBusy(true);
    setCancelErr("");
    try {
      await kbApi.refineTasks.cancel(id);
      await refetch();
      void qc.invalidateQueries({ queryKey: ["refine-tasks"] });
    } catch (e) {
      setCancelErr(e instanceof Error ? e.message : "取消失败，稍后再试");
    } finally {
      setCancelBusy(false);
    }
  };

  // 任务从进行中转终态时刷一次任务清单徽标（下一挂载自然取新）
  useEffect(() => {
    if (data && (data.status === "completed" || data.status === "failed")) refetch();
  }, [data?.status, refetch]);
  // 看过详情＝消账（与拆书详情页同口径；评审 P2：不看清单页时徽标也能灭）
  useEffect(() => {
    if (data && (data.status === "completed" || data.status === "failed")) markTasksSeen([data.id]);
  }, [data?.id, data?.status]);

  if (!data) {
    return (
      <main className="main" data-od-id="refine-detail">
        <p className="sub">任务装载中…</p>
      </main>
    );
  }
  const t = data;
  const r = t.result;
  const pill = PILL[t.status];

  return (
    <main className="main" data-od-id="refine-detail">
      <Link className="back-link" to="/tools">← 返回任务清单</Link>
      <div className="page-head" style={{ marginBottom: 16 }}>
        <div>
          <h1 style={{ fontSize: 24 }}>
            知识提炼 · {t.genre}知识库 <span className={pill.cls} style={{ verticalAlign: 6, marginLeft: 8 }}>{pill.label}</span>
          </h1>
          <p className="sub">
            {t.status === "failed" && t.error ? `失败：${t.error}` : `今天发起${t.current_step ? ` · ${t.current_step}` : ""}`}
          </p>
        </div>
        <div className="actions">
          {(t.status === "running" || t.status === "queued") && (
            <button
              className="btn btn-secondary btn-sm"
              style={{ color: "var(--err)" }}
              disabled={cancelBusy}
              data-testid="refine-cancel"
              onClick={() => void doCancel()}
            >
              {cancelBusy ? "取消中…" : "取消任务"}
            </button>
          )}
          <Link className="btn btn-primary btn-sm" to="/knowledge?view=tree" data-testid="refine-to-tree">
            去知识树看变化
          </Link>
        </div>
        {cancelErr && <p className="sub" style={{ color: "var(--err)" }}>{cancelErr}</p>}
      </div>

      <section className="detail-sec">
        <h2>执行过程</h2>
        <div className="tk-list" data-testid="refine-timeline" style={{ border: "1px solid var(--border)", borderRadius: 16, padding: "6px 18px", background: "var(--surface)" }}>
          {(t.timeline ?? []).length === 0 && <p className="sub">排队等待，轮到自动开跑…</p>}
          {(t.timeline ?? []).map((s) => (
            <div key={s.key} style={{ display: "flex", gap: 12, padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
              <span style={{ flex: "none", width: 10, height: 10, borderRadius: 999, marginTop: 7, background: "var(--accent)" }} />
              <div style={{ minWidth: 0 }}>
                <h4 style={{ fontSize: 13.5, fontWeight: 600, margin: 0 }}>{s.title}</h4>
                <p style={{ fontSize: 12, color: "var(--muted)", margin: "2px 0 0" }}>{s.detail}</p>
              </div>
              <span className="num" style={{ marginLeft: "auto", fontSize: 11, color: "var(--faint)" }}>{s.time.slice(11)}</span>
            </div>
          ))}
        </div>
      </section>

      {t.status === "completed" && r && (
        <>
          <section className="detail-sec">
            <h2>结果</h2>
            <div className="result-grid" style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
              {[
                { n: r.moved, label: "归位" },
                { n: r.nodes_created, label: "新知识点" },
                { n: r.relations, label: "新关系" },
                { n: r.kept, label: "留守其他" },
              ].map((c) => (
                <div key={c.label} style={{ border: "1px solid var(--border)", borderRadius: 12, padding: 14, textAlign: "center", background: "var(--surface)" }}>
                  <b className="num" style={{ display: "block", fontSize: 22, color: "var(--accent-strong)" }}>{c.n}</b>
                  <span style={{ fontSize: 11.5, color: "var(--muted)" }}>{c.label}</span>
                </div>
              ))}
            </div>
            {(r.details?.new_nodes ?? []).map((n) => (
              <div key={n.title} style={{ marginTop: 10, border: "1px dashed var(--accent)", background: "var(--accent-soft)", borderRadius: 12, padding: "12px 15px", fontSize: 12.5 }} data-testid="refine-new-node">
                新知识点：<b style={{ color: "var(--accent-strong)" }}>{n.title}</b>
                {n.parent_title && <>（挂在 {n.parent_title} 之下）</>}
                ——定义：{n.definition}。AI 提了 {n.fields.length} 个格：{n.fields.join(" / ")}。
              </div>
            ))}
          </section>
          {(r.details?.moves ?? []).length > 0 && (
            <section className="detail-sec">
              <h2>归位明细</h2>
              <div style={{ border: "1px solid var(--border)", borderRadius: 12, overflow: "hidden", background: "var(--surface)" }}>
                {(r.details?.moves ?? []).map((m, i) => (
                  <div key={i} style={{ display: "flex", gap: 10, padding: "10px 14px", borderBottom: i === (r.details?.moves?.length ?? 0) - 1 ? 0 : 1, borderColor: "var(--border)", fontSize: 12.5, alignItems: "baseline" }}>
                    <span style={{ color: "var(--muted)", flex: 1, minWidth: 0 }}>「{m.from_text}」</span>
                    <span style={{ color: "var(--faint)" }}>→</span>
                    <span style={{ color: "var(--accent)", fontWeight: 500, flex: "none" }}>{m.to}</span>
                  </div>
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </main>
  );
}
