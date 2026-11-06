// 知识整理面板（c-kb-organize 批D）：运行状态行＋手动整理＋待确认清单
// （pending 关系：生效/否决/这条不对；四类建议：采纳/忽略）。作家确认制。
import { useCallback, useEffect, useState } from "react";
import { kbApi, type KbPendingFinding, type KbPendingRelation } from "@/lib/kbApi";
import { REL_TYPE_LABELS as REL_LABEL } from "@/lib/kbRelations";

const KIND_LABEL: Record<KbPendingFinding["kind"], string> = {
  merge: "疑似重复",
  reclass: "概念放错",
  subconcept: "子概念提案",
  quality: "待清理",
};

interface Props {
  genre: string;
  onClose: () => void;
  onChanged?: () => void;
}

interface SummarizeCandidate {
  id: string;
  genre: string;
  concept: string;
  proposed_title: string;
  proposed_definition: string;
  materials: { id: string; title: string; available: boolean }[];
}

export default function KbOrganizePanel({ genre, onClose, onChanged }: Props) {
  const [status, setStatus] = useState<Awaited<ReturnType<typeof kbApi.organize.status>> | null>(null);
  const [cands, setCands] = useState<SummarizeCandidate[]>([]);
  const [relations, setRelations] = useState<KbPendingRelation[]>([]);
  const [findings, setFindings] = useState<KbPendingFinding[]>([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ tone: "info" | "ok" | "warn" | "err"; text: string } | null>(null);
  const [running, setRunning] = useState(false);

  const loadCands = useCallback(async () => {
    try {
      const r = await kbApi.summarize.candidates(genre);
      setCands(r.candidates);
    } catch {
      setCands([]);
    }
  }, [genre]);

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const [st, list] = await Promise.all([kbApi.organize.status(genre), kbApi.organize.findings(genre)]);
      setStatus(st);
      setRelations(list.relations);
      setFindings(list.findings);
    } catch (e: unknown) {
      setNotice({ tone: "err", text: (e as { message?: string }).message || "加载失败" });
    } finally {
      setBusy(false);
    }
  }, [genre]);

  useEffect(() => {
    void load();
    void loadCands();
  }, [load, loadCands]);

  const doRun = async () => {
    setRunning(true);
    setNotice({ tone: "info", text: "整理中——按题材扫描知识、产关系与建议…" });
    try {
      const r = await kbApi.organize.run(genre);
      if (r.skipped) {
        setNotice({ tone: "warn", text: r.message || "正在整理中" });
      } else {
        setNotice({ tone: "ok", text: `整理完成：新增关系 ${r.relations_added ?? 0} 条` });
      }
      await load();
      onChanged?.();
    } catch (e: unknown) {
      setNotice({ tone: "err", text: (e as { message?: string }).message || "整理失败" });
    } finally {
      setRunning(false);
    }
  };

  const act = async (fn: () => Promise<{ message: string }>, tone: "ok" | "warn") => {
    try {
      const r = await fn();
      setNotice({ tone, text: r.message });
      await load();
      onChanged?.();
    } catch (e: unknown) {
      setNotice({ tone: "err", text: (e as { message?: string }).message || "操作失败" });
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" data-testid="kb-organize-panel">
      <div className="max-h-[80vh] w-[640px] overflow-y-auto rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
        <div className="flex items-center justify-between">
          <h2 className="font-[var(--font-display)] text-xl font-semibold">知识整理</h2>
          <button onClick={onClose} className="text-[var(--muted)] hover:text-[var(--fg)]" aria-label="关闭">✕</button>
        </div>
        <p className="mt-1 text-[12px] text-[var(--muted)]">
          题材「{genre}」· AI 只建议，动不动你的知识——采纳才生效。
        </p>

        {/* 运行状态行 */}
        <div className="mt-3 rounded-lg border border-[var(--border)] px-3 py-2 text-[12px]">
          {status ? (
            <>
              <span className="text-[var(--muted)]">
                上次整理：{status.last_run ? status.last_run.status === "completed" ? "完成" : status.last_run.status === "error" ? "失败" : status.last_run.status : "还没跑过"}
                {status.last_run && status.last_run.status === "completed" && ` · 扫 ${status.last_run.entries_scanned} 条 · 新增关系 ${status.last_run.relations_added} 条`}
              </span>
              <span className="ml-2 text-[var(--accent)]">待确认 {status.pending_relations + status.proposed_findings} 项</span>
            </>
          ) : (
            <span className="text-[var(--muted)]">状态加载中…</span>
          )}
        </div>

        {notice && (
          <p className={`mt-2 text-[12px] ${notice.tone === "ok" ? "text-[var(--accent)]" : notice.tone === "err" ? "text-red-500" : notice.tone === "warn" ? "text-amber-500" : "text-[var(--muted)]"}`}>
            {notice.text}
          </p>
        )}

        <button
          onClick={() => void doRun()}
          disabled={running || busy}
          className="mt-3 rounded-md bg-[var(--accent)] px-3 py-1.5 text-[12px] text-white disabled:opacity-50"
        >
          {running ? "整理中…" : "立即整理"}
        </button>

        {/* 知识总结（c-kb-summarize）：素材 → 候选知识点 → 确认采纳 */}
        <button
          onClick={async () => {
            setBusy(true);
            setNotice({ tone: "info", text: "总结中——把素材提炼成候选知识点…" });
            try {
              const r = await kbApi.summarize.run(genre);
              if (r.skipped) {
                setNotice({ tone: "warn", text: r.message || "正在总结中" });
              } else {
                setNotice({ tone: "ok", text: `总结完成：提炼候选知识点 ${r.candidates} 个（素材 ${r.collected} 条）` });
              }
              await loadCands();
              onChanged?.();
            } catch (e: unknown) {
              setNotice({ tone: "err", text: (e as { message?: string }).message || "总结失败" });
            } finally {
              setBusy(false);
            }
          }}
          disabled={busy}
          className="mt-3 rounded-md border border-[var(--accent)] px-3 py-1.5 text-[12px] text-[var(--accent)] hover:bg-[var(--accent-soft)] disabled:opacity-50"
        >
          总结知识点
        </button>
        <div className="mt-3">
          <p className="font-mono text-[10px] tracking-[0.14em] text-[var(--muted)]">候选知识点（待确认）</p>
          {cands.length === 0 ? (
            <p className="mt-1 text-[12px] text-[var(--muted)]">没有待确认的知识点。</p>
          ) : (
            <ul className="mt-1 space-y-1">
              {cands.map((c) => (
                <li key={c.id} className="rounded-md border border-[var(--border)] px-3 py-2 text-[12px]">
                  <span className="font-medium">{c.proposed_title}</span>
                  <span className="ml-1 text-[var(--muted)]">· {c.concept}</span>
                  <p className="mt-0.5 leading-relaxed">{c.proposed_definition}</p>
                  <p className="mt-0.5 text-[11px] text-[var(--faint)]">
                    来自素材：{c.materials.map((m) => m.title).join("、")}
                  </p>
                  <div className="mt-1 flex gap-2">
                    <button
                      onClick={async () => {
                        try {
                          const r = await kbApi.summarize.adopt(c.id);
                          setNotice({ tone: "ok", text: r.message || "已采纳" });
                        } catch (e: unknown) {
                          setNotice({ tone: "err", text: (e as { message?: string }).message || "采纳失败" });
                        }
                        await loadCands();
                        onChanged?.();
                      }}
                      className="rounded-md border border-[var(--accent)] px-2 py-0.5 text-[11px] text-[var(--accent)]"
                    >
                      采纳为知识
                    </button>
                    <button
                      onClick={async () => {
                        try {
                          await kbApi.summarize.dismiss(c.id);
                        } catch { /* 忽略失败静默（清单刷新即回真态） */ }
                        await loadCands();
                      }}
                      className="rounded-md border border-[var(--border)] px-2 py-0.5 text-[11px] text-[var(--muted)]"
                    >
                      忽略
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* 待确认关系 */}
        <div className="mt-4">
          <p className="font-mono text-[10px] tracking-[0.14em] text-[var(--muted)]">待确认关系</p>
          {relations.length === 0 ? (
            <p className="mt-1 text-[12px] text-[var(--muted)]">没有待确认的关系。</p>
          ) : (
            <ul className="mt-1 space-y-1">
              {relations.map((r) => (
                <li key={r.id} className="rounded-md border border-[var(--border)] px-3 py-2 text-[12px]">
                  <span className="font-medium">{REL_LABEL[r.rel_type] || r.rel_type}</span>
                  ：{r.from_title} → {r.to_title}
                  <span className="ml-1 text-[var(--muted)]">（置信 {Math.round(r.confidence * 100)}%）</span>
                  {r.note && <p className="text-[var(--muted)]">{r.note}</p>}
                  <div className="mt-1 flex gap-2">
                    <button onClick={() => void act(() => kbApi.organize.adoptRelation(r.id), "ok")}
                            className="rounded border border-[var(--accent)] px-2 text-[11px] text-[var(--accent)]">生效</button>
                    <button onClick={() => void act(() => kbApi.organize.rejectRelation(r.id), "warn")}
                            className="rounded border border-[var(--border)] px-2 text-[11px] text-[var(--muted)]">否决</button>
                    <button onClick={() => void act(() => kbApi.organize.relationFeedback(r.id), "warn")}
                            className="text-[11px] text-[var(--muted)] underline">这条不对</button>
                  </div>
                </li>
              ))}
            </ul>
          )}

          <p className="mt-3 font-mono text-[10px] tracking-[0.14em] text-[var(--muted)]">待确认建议</p>
          {findings.length === 0 ? (
            <p className="mt-1 text-[12px] text-[var(--muted)]">没有待确认的建议。</p>
          ) : (
            <ul className="mt-1 space-y-1">
              {findings.map((f) => (
                <li key={f.id} className="rounded-md border border-[var(--border)] px-3 py-2 text-[12px]">
                  <span className="font-medium">{KIND_LABEL[f.kind]}</span>
                  ：{f.subject_title}
                  {typeof f.payload.reason === "string" && (
                    <span className="text-[var(--muted)]">（{f.payload.reason}）</span>
                  )}
                  <div className="mt-1 flex gap-2">
                    <button onClick={() => void act(() => kbApi.organize.adoptFinding(f.id), "ok")}
                            className="rounded border border-[var(--accent)] px-2 text-[11px] text-[var(--accent)]">采纳</button>
                    <button onClick={() => void act(() => kbApi.organize.ignoreFinding(f.id), "warn")}
                            className="rounded border border-[var(--border)] px-2 text-[11px] text-[var(--muted)]">忽略</button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
