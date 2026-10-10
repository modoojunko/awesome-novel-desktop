/** 去 AI 味修稿向导（c-deai-wizard）：四步弹窗——
 *  ① AI 味检查（本地规则＋读检测存档）② 选择段落 ③ 整体修改·逐段取舍 ④ 应用确认。
 *  向导内一切产出为候选态；唯一写正文口＝④应用（经 ProsePane 注入的 onApply）。
 *  收口＝顶栏朱雀条重检（作家自点，本组件不做复测）。 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Modal from "@/components/design/Modal";
import { aiFlavorScan, polishTextDetail } from "@/lib/ai";
import { toast } from "@/lib/toast";
import type {
  AiFlavorScanResponse,
  FixCandidate,
  ProblemSegment,
  ScanReport,
  WizardStep,
} from "./types";

export interface PolishWizardProps {
  open: boolean;
  onClose: () => void;
  projectId: string;
  chapterRef: string;
  /** 编辑器当前正文（切段上下文＋应用前校验的事实源） */
  prose: string;
  /** 写回执行器（ProsePane 注入；采用段逆序单事务替换，返回实际应用/跳过数） */
  onApply: (items: Array<{ paraIndex: number; from: string; text: string }>) => {
    applied: number;
    skipped: number;
  };
}

const SEVERITY_TEXT: Record<string, string> = { blocking: "硬伤", advisory: "提示" };

export default function PolishWizard({
  open,
  onClose,
  projectId,
  chapterRef,
  prose,
  onApply,
}: PolishWizardProps) {
  const [loading, setLoading] = useState(false);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [report, setReport] = useState<ScanReport | null>(null);
  const [problems, setProblems] = useState<ProblemSegment[]>([]);
  const [detector, setDetector] = useState<AiFlavorScanResponse["detector"] | null>(null);
  const [excluded, setExcluded] = useState<Set<number>>(new Set());
  const [step, setStep] = useState<WizardStep>(1);
  const [cands, setCands] = useState<Map<number, FixCandidate>>(new Map());
  const [fixIdx, setFixIdx] = useState(0);
  const [applying, setApplying] = useState(false);
  const scanReqId = useRef(0);

  const paragraphs = useMemo(
    () => prose.split("\n").filter((p) => p.trim()),
    [prose],
  );

  // ── 开窗即扫（①）；重置全部会话态 ──
  useEffect(() => {
    if (!open) return;
    const reqId = ++scanReqId.current;
    setLoading(true);
    setLoadErr(null);
    setReport(null);
    setProblems([]);
    setDetector(null);
    setExcluded(new Set());
    setStep(1);
    setCands(new Map());
    setFixIdx(0);
    inflightRef.current.clear();
    aiFlavorScan(projectId, chapterRef)
      .then((d) => {
        if (reqId !== scanReqId.current) return;
        setReport(d.report);
        setProblems(d.problems);
        setDetector(d.detector);
      })
      .catch((e: { message?: string }) => {
        if (reqId !== scanReqId.current) return;
        setLoadErr(e?.message || "AI 味检查失败，请重试");
      })
      .finally(() => {
        if (reqId === scanReqId.current) setLoading(false);
      });
  }, [open, projectId, chapterRef]);

  const queue = useMemo(
    () => problems.filter((p) => !excluded.has(p.para)),
    [problems, excluded],
  );

  // ── ③ 上下文保鲜：已采用候选替换进段落副本，后续段的改写看得见前序定稿 ──
  const effective = useMemo(() => {
    const base = [...paragraphs];
    for (const [para, c] of cands) {
      if (c.decision === "adopt" && c.after && para >= 0 && para < base.length) {
        base[para] = c.after;
      }
    }
    return base;
  }, [paragraphs, cands]);

  const segContext = useCallback(
    (para: number) => {
      const before = effective.slice(0, para).join("\n");
      const after = effective.slice(para + 1).join("\n");
      return { contextBefore: before.slice(-200), contextAfter: after.slice(0, 200) };
    },
    [effective],
  );

  const inflightRef = useRef<Set<number>>(new Set());

  const generate = useCallback(
    (seg: ProblemSegment) => {
      if (inflightRef.current.has(seg.para)) return; // StrictMode 双触发防重入
      inflightRef.current.add(seg.para);
      setCands((prev) => {
        const next = new Map(prev);
        next.set(seg.para, {
          seg,
          status: "loading",
          attempts: (prev.get(seg.para)?.attempts ?? 0) + 1,
          decision: "undecided",
        });
        return next;
      });
      const { contextBefore, contextAfter } = segContext(seg.para);
      polishTextDetail(projectId, chapterRef, seg.text, contextBefore, contextAfter)
        .then((d) => {
          inflightRef.current.delete(seg.para);
          setCands((prev) => {
            const next = new Map(prev);
            const cur = prev.get(seg.para);
            if (!cur) return prev;
            if (!d.changed) {
              // 确诊为零＝逐字原样输出：合法的无操作，不是失败（PE 评审 A）
              next.set(seg.para, {
                ...cur,
                status: "ready",
                after: d.polished_text,
                changed: false,
                flagsBlocking: false,
                flags: d.flags,
                decision: "keep",
                notice: "未查出可修的硬伤——原样保留是合规结果。",
              });
            } else {
              const blocking = d.flags.filter((f) => f.level === "block");
              next.set(seg.para, {
                ...cur,
                status: "ready",
                after: d.polished_text,
                changed: true,
                flagsBlocking: d.flags_blocking,
                flags: d.flags,
                notice: d.flags_blocking
                  ? `改稿命中红线：${blocking.map((f) => f.detail).join("；")}——建议保留原文或重新生成。`
                  : undefined,
                decision: d.flags_blocking ? "keep" : "undecided",
              });
            }
            return next;
          });
        })
        .catch((e: { message?: string }) => {
          inflightRef.current.delete(seg.para);
          setCands((prev) => {
            const next = new Map(prev);
            const cur = prev.get(seg.para);
            if (!cur) return prev;
            next.set(seg.para, { ...cur, status: "error", error: e?.message || "生成失败" });
            return next;
          });
        });
    },
    [projectId, chapterRef, segContext],
  );

  // 步骤③进入/换段：当前段候选未生成则自动生成
  useEffect(() => {
    if (step !== 3) return;
    const seg = queue[fixIdx];
    if (!seg) return;
    const cur = cands.get(seg.para);
    if (!cur || (cur.status === "error" && !inflightRef.current.has(seg.para))) generate(seg);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, fixIdx]);

  const adoptedItems = useMemo(
    () =>
      queue
        .map((s) => cands.get(s.para))
        .filter((c): c is FixCandidate => !!c && c.decision === "adopt" && !!c.after)
        .map((c) => ({ paraIndex: c.seg.para, from: c.seg.text, text: c.after as string })),
    [queue, cands],
  );
  const keptCount = useMemo(
    () => queue.filter((s) => cands.get(s.para)?.decision === "keep").length,
    [queue, cands],
  );

  const allDecided = queue.length > 0 && queue.every((s) => {
    const c = cands.get(s.para);
    return c && c.status === "ready" && c.decision !== "undecided";
  });
  const step1Done = !loading && !loadErr && report !== null;
  const step2Done = queue.length > 0;
  const canApply = step === 4 && adoptedItems.length > 0 && !applying;

  function nextClick() {
    if (step === 1) { if (step1Done) setStep(2); return; }
    if (step === 2) { if (step2Done) setStep(3); return; }
    if (step === 3) {
      const seg = queue[fixIdx];
      if (seg) adopt(seg);
      return;
    }
    if (step === 4) {
      if (!canApply) return;
      setApplying(true);
      const r = onApply(adoptedItems);
      setApplying(false);
      if (r.applied > 0) {
        toast.success(
          r.skipped > 0
            ? `已应用 ${r.applied} 段；${r.skipped} 段因正文已变动未应用——顶部重检一次看效果`
            : "已应用到正文——顶部重检一次看效果",
        );
        onClose();
      } else {
        toast.error("段落与当前正文不一致（可能已改动），请重新打开向导");
      }
    }
  }

  function adopt(seg: ProblemSegment) {
    const c = cands.get(seg.para);
    if (!c || c.status !== "ready" || c.decision !== "undecided") return;
    setCands((prev) => {
      const next = new Map(prev);
      next.set(seg.para, { ...c, decision: "adopt" });
      return next;
    });
    if (fixIdx + 1 < queue.length) setFixIdx(fixIdx + 1);
    else setStep(4);
  }

  function keep(seg: ProblemSegment) {
    const c = cands.get(seg.para);
    if (!c || c.decision !== "undecided") return;
    setCands((prev) => {
      const next = new Map(prev);
      next.set(seg.para, { ...c, decision: "keep" });
      return next;
    });
    if (fixIdx + 1 < queue.length) setFixIdx(fixIdx + 1);
    else setStep(4);
  }

  function flip(seg: ProblemSegment) {
    setCands((prev) => {
      const next = new Map(prev);
      const c = next.get(seg.para);
      if (c) next.set(seg.para, { ...c, decision: c.decision === "adopt" ? "keep" : "adopt" });
      return next;
    });
  }

  function requestClose() {
    const undecided = Array.from(cands.values()).filter(
      (c) => c.status === "ready" && c.decision === "undecided",
    ).length;
    if (adoptedItems.length > 0) {
      if (window.confirm(`已采用 ${adoptedItems.length} 段但未应用，关闭将丢弃这些取舍。确定关闭？`)) onClose();
      return;
    }
    if (undecided > 0) {
      if (window.confirm(`有 ${undecided} 段已生成改稿尚未取舍，关闭将丢弃。确定关闭？`)) onClose();
      return;
    }
    onClose();
  }

  const nextLabel =
    step === 1 ? "下一步：选择段落"
    : step === 2 ? `开始修改（${queue.length} 段）`
    : step === 3 ? (allDecided ? "下一步：应用确认" : "采用改稿，看下一段")
    : "应用到正文";

  const curSeg = queue[fixIdx];
  const curCand = curSeg ? cands.get(curSeg.para) : undefined;

  return (
    <Modal
      open={open}
      onClose={requestClose}
      title="去 AI 味 · 修稿向导"
      wbStyle
      width={840}
      locked={applying}
      footer={
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <button
            className="btn btn-primary"
            onClick={nextClick}
            disabled={applying
              || (step === 2 && queue.length === 0)
              || (step === 3 && (!curCand || curCand.status !== "ready" || curCand.decision !== "undecided"))
              || (step === 4 && adoptedItems.length === 0)}
          >
            {nextLabel}
          </button>
          {step === 3 && curCand && curCand.status === "ready" && curCand.decision === "undecided" && (
            <button className="btn btn-secondary" onClick={() => keep(curSeg)}>
              这段保留原文
            </button>
          )}
          {step === 3 && curCand && curCand.status !== "loading" && (
            <button className="btn btn-ghost" onClick={() => generate(curSeg)}>
              重新生成{curCand.attempts > 0 ? `（已 ${curCand.attempts} 次）` : ""}
            </button>
          )}
          <button className="btn btn-ghost" onClick={requestClose}>
            取消
          </button>
          <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--faint)" }}>
            {step === 1
              ? "AI 味检查不耗检测额度 · 收口重检 1 次"
              : step === 3
                ? "修改全程为候选 · 应用前不写正文、不花检测额度"
                : step === 4
                  ? "应用后旧检测标为过期 · 顶部重检一次收口"
                  : "勾选要修的段落 · 不修的取消勾选"}
          </span>
        </div>
      }
    >
      <div className="gl-steps" role="list">
        <span className={`gl-step${step === 1 ? " on" : step > 1 ? " done" : ""}`}>① AI 味检查</span>
        <i />
        <span className={`gl-step${step === 2 ? " on" : step > 2 ? " done" : ""}`}>② 选择段落</span>
        <i />
        <span className={`gl-step${step === 3 ? " on" : step > 3 ? " done" : ""}`}>③ 整体修改</span>
        <i />
        <span className={`gl-step${step === 4 ? " on" : ""}`}>④ 应用确认</span>
      </div>

      {loading && <p className="hint" style={{ margin: 0 }}>AI 味检查中…</p>}
      {loadErr && <p className="hint" style={{ margin: 0, color: "var(--err)" }}>{loadErr}</p>}

      {/* ① AI 味检查 */}
      {step === 1 && report && (
        <div className="gl-pane">
          <div className="gl-ratio-row">
            <b className="gl-big">{report.para_count}</b>
            <span className="gl-sub">
              段 · 规则扫描完成（0 额度）
              {detector && !detector.stored && " · 本章未做朱雀检测：以下为规则清单，检测后判定段会一起进向导"}
            </span>
          </div>
          <ul className="gl-checks">
            {report.findings.map((f, i) => (
              <li key={i}>
                <span className="gl-tag">{SEVERITY_TEXT[f.severity] || f.severity}</span>
                <span>{f.detail}</span>
                <em>段 {f.para + 1}</em>
              </li>
            ))}
            {report.findings.length === 0 && (
              <li><span>规则清单全绿——文字层没有可机查的违规。</span></li>
            )}
          </ul>
          {report.metrics.comma_period_ratio !== null && (
            <p className="gl-hint">
              逗句比 {report.metrics.comma_period_ratio}（目标 ≥ 2.3）
              {report.metrics.short_para_ratio !== null && ` · 极短段占比 ${Math.round(report.metrics.short_para_ratio * 100)}%`}
              {report.metrics.dialogue_ratio !== null && ` · 对白段占比 ${Math.round(report.metrics.dialogue_ratio * 100)}%`}
            </p>
          )}
        </div>
      )}

      {/* ② 选择段落 */}
      {step === 2 && (
        <div className="gl-pane">
          <p className="gl-sec-title">问题清单 · 勾选要修的段落（{queue.length} 段）</p>
          {detector && detector.stored && detector.human_ratio !== null && (
            <div className="gl-ratio-row">
              <b className="gl-big">{Math.round(detector.human_ratio * 100)}%</b>
              <span className="gl-sub">人味占比（检测存档）· 达标线 50%<br />朱雀判定段与规则命中段都列在下面</span>
            </div>
          )}
          <ul className="gl-heats">
            {problems.map((p) => (
              <li key={p.para} className={`gl-heat${excluded.has(p.para) ? "" : " on"}`}>
                <input
                  type="checkbox"
                  checked={!excluded.has(p.para)}
                  onChange={() =>
                    setExcluded((prev) => {
                      const next = new Set(prev);
                      if (next.has(p.para)) next.delete(p.para);
                      else next.add(p.para);
                      return next;
                    })
                  }
                />
                <span className="gl-conf m-warn">
                  {p.source === "detector" || p.source === "both"
                    ? `${Math.round((p.confidence ?? 0) * 100)}%`
                    : "规则"}
                </span>
                <span className="gl-heat-t">
                  段 {p.para + 1} · {p.reasons.join("；")}
                  <em>{p.suggested_fix}</em>
                </span>
              </li>
            ))}
            {problems.length === 0 && (
              <li className="gl-heat"><span className="gl-heat-t">规则清单与检测判定都没有命中——这一章很干净。</span></li>
            )}
          </ul>
        </div>
      )}

      {/* ③ 整体修改 */}
      {step === 3 && curSeg && (
        <div className="gl-pane">
          <p className="gl-meta">
            <b>第 {fixIdx + 1} / {queue.length} 段</b>
            <span>段 {curSeg.para + 1} · {curSeg.source === "detector" || curSeg.source === "both" ? `朱雀判定 ${Math.round((curSeg.confidence ?? 0) * 100)}%` : "规则命中"}</span>
          </p>
          <p className="gl-meta"><b>问题：</b><span>{curSeg.reasons.join("；") || "无具体定位——按整段指纹处理"}</span></p>
          {curCand?.status === "loading" && <p className="gl-meta">生成改稿中…</p>}
          {curCand?.status === "error" && (
            <p className="gl-meta" style={{ color: "var(--err)" }}>生成失败：{curCand.error}</p>
          )}
          {curCand?.status === "empty" && (
            <p className="gl-meta">没有产出改稿——可重新生成，或保留原文。</p>
          )}
          {curCand?.status === "ready" && (
            <>
              {curCand.notice && (
                <p className="gl-meta" style={{ color: curCand.flagsBlocking ? "var(--err)" : "var(--muted)" }}>
                  {curCand.notice}
                </p>
              )}
              {!curCand.flagsBlocking && (curCand.flags?.length ?? 0) > 0 && (
                <p className="gl-hint">
                  改稿快扫提示：{curCand.flags?.map((f) => f.detail).join("；")}——请核对。
                </p>
              )}
              <blockquote className="gl-quote">{curSeg.text}</blockquote>
              <div className="gl-ab">
                <p className="gl-ab-a">{curCand.after}</p>
              </div>
              <p className="gl-hint">
                {SUGGEST_TEXT[curSeg.suggested_fix] || "按问题清单逐段清 AI 味；动不动以改稿实际产出为准。"}
                {curCand.attempts > 1 && `（已重新生成 ${curCand.attempts - 1} 次）`}
              </p>
            </>
          )}
          <ul className="gl-runs">
            {queue.slice(0, fixIdx + 1).map((s) => {
              const c = cands.get(s.para);
              if (!c || c.decision === "undecided") return null;
              return (
                <li key={s.para} className={c.decision === "adopt" ? "up" : "down"}>
                  <span>段 {s.para + 1}</span>
                  <b>{c.decision === "adopt" ? "采用改稿" : "保留原文"}</b>
                  <em>{s.suggested_fix}</em>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* ④ 应用确认（终选可翻转） */}
      {step === 4 && (
        <div className="gl-pane">
          <div className="gl-ratio-row">
            <b className="gl-big">{adoptedItems.length} 段</b>
            <span className="gl-sub">
              本轮处理完毕：采用 {adoptedItems.length} 段 · 保留原文 {keptCount} 段<br />
              应用后正文更新，旧检测结果标为「已过期」——到顶部重检一次看效果
            </span>
          </div>
          {queue.map((s) => {
            const c = cands.get(s.para);
            if (!c) return null;
            return (
              <div key={s.para} className="gl-diff-row" style={{ opacity: c.decision === "keep" ? 0.6 : 1 }}>
                <div className="gl-diff-head">
                  <span className="pill pill-tag">段 {s.para + 1}</span>
                  <span>{s.suggested_fix}</span>
                  <span className="gl-tag" style={{ marginLeft: "auto" }}>
                    {c.decision === "adopt" ? "已采用" : "保留原文"}
                  </span>
                </div>
                {c.decision === "adopt" && c.after && (
                  <div className="gl-pair">
                    <div><p className="gl-col-k">原文</p><p>{c.seg.text}</p></div>
                    <div><p className="gl-col-k">改稿</p><p className="gl-new">{c.after}</p></div>
                  </div>
                )}
                <div className="gl-pick" style={{ marginTop: 6 }}>
                  <button
                    className={c.decision === "adopt" ? "on" : ""}
                    onClick={() => flip(s)}
                  >
                    采用改稿
                  </button>
                  <button
                    className={c.decision === "keep" ? "on" : ""}
                    onClick={() => flip(s)}
                  >
                    保留原文
                  </button>
                </div>
              </div>
            );
          })}
          <p className="gl-hint">
            终选翻转即时生效；「应用到正文」后走顶部朱雀条重检收口。
          </p>
        </div>
      )}
    </Modal>
  );
}

const SUGGEST_TEXT: Record<string, string> = {
  monologue_dequote: "建议改法：独白去引号化——整段独白改成叙述句带出，全章留最狠的一两处就够。",
  info_to_dialogue: "建议改法：信息入对白——条款数字类信息拆成人物一问一答。",
  merge_periods: "建议改法：句号合并——一口气读完的动作之间用逗号。",
  delete_or_concretize: "建议改法：删解释尾巴，罐装反应换成具体动作。",
  thin_stacking: "建议改法：削堆叠——删修饰词与重复生理描写。",
  rough_shorten: "建议改法：糙短化——删修饰、删解释尾巴、删重复。",
};
