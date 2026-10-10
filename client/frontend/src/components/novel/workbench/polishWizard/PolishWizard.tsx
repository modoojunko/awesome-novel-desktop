/** 去 AI 味修稿向导（c-deai-wizard）：四步弹窗——
 *  ① AI 味检查（本地规则＋读检测存档）② 选择段落 ③ 整体修改·逐段取舍 ④ 应用确认。
 *  向导内一切产出为候选态；唯一写正文口＝④应用（经 ProsePane 注入的 onApply）。
 *  收口＝顶栏朱雀条重检（作家自点，本组件不做复测）。 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Modal from "@/components/design/Modal";
import { aiFlavorScan, polishText } from "@/lib/ai";
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
  /** 写回执行器（ProsePane 注入；采用段逆序单事务替换，返回 false＝全部失配被拒） */
  onApply: (items: Array<{ paraIndex: number; from: string; text: string }>) => boolean;
}

const SEVERITY_TEXT: Record<string, string> = {
  blocking: "硬伤",
  advisory: "提示",
};

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
  const [decided, setDecided] = useState<Array<{ para: number; keep: boolean; label: string }>>([]);
  const [applying, setApplying] = useState(false);
  const scanReqId = useRef(0);

  const paragraphs = useMemo(
    () => prose.split("\n").filter((p) => p.trim()),
    [prose],
  );

  // ── 开窗即扫（①） ──
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
    setDecided([]);
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
  const queueParas = useMemo(() => queue.map((p) => p.para), [queue]);

  // ── ③ 逐段生成（串行：当前段无候选即生成） ──
  const segContext = useCallback(
    (para: number) => {
      const before = paragraphs.slice(0, para).join("\n");
      const after = paragraphs.slice(para + 1).join("\n");
      return {
        contextBefore: before.slice(-200),
        contextAfter: after.slice(0, 200),
      };
    },
    [paragraphs],
  );

  const generate = useCallback(
    (seg: ProblemSegment) => {
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
      polishText(projectId, chapterRef, seg.text, contextBefore, contextAfter)
        .then((after) => {
          setCands((prev) => {
            const next = new Map(prev);
            const cur = prev.get(seg.para);
            if (!cur) return prev;
            if (!after.trim()) {
              next.set(seg.para, { ...cur, status: "empty", error: "没有产出改稿" });
            } else {
              next.set(seg.para, { ...cur, status: "ready", after });
            }
            return next;
          });
        })
        .catch((e: { message?: string }) => {
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
    if (!cur || cur.status === "error" || cur.status === "empty") generate(seg);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, fixIdx]);

  const adoptedItems = useMemo(
    () =>
      decided
        .filter((d) => !d.keep)
        .map((d) => {
          const c = cands.get(d.para);
          return c?.after ? { paraIndex: d.para, from: c.seg.text, text: c.after } : null;
        })
        .filter((x): x is NonNullable<typeof x> => x !== null),
    [decided, cands],
  );

  // ── 步进 ──
  const step1Done = !loading && !loadErr && report !== null;
  const step2Done = queue.length > 0;
  const allDecided = queue.length > 0 && queue.every((s) => {
    const c = cands.get(s.para);
    return c && c.decision !== "undecided" && c.status === "ready";
  });
  const anyAdopted = decided.some((d) => !d.keep);
  const canApply = step === 4 && adoptedItems.length > 0 && !applying;

  function nextClick() {
    if (step === 1) { if (step1Done) setStep(2); return; }
    if (step === 2) { if (step2Done) setStep(3); return; }
    if (step === 3) {
      decide(false);  // 主按钮＝采用当前段；最后一段采用后自动进④
      return;
    }
    if (step === 4) {
      if (!canApply) return;
      setApplying(true);
      const ok = onApply(adoptedItems);
      setApplying(false);
      if (ok) {
        toast.success("已应用到正文——顶部重检一次看效果");
        onClose();
      } else {
        toast.error("段落与当前正文不一致（可能已改动），请重新生成");
      }
    }
  }

  function decide(keep: boolean) {
    const seg = queue[fixIdx];
    if (!seg) return;
    const c = cands.get(seg.para);
    if (!c || c.status !== "ready") return;
    setCands((prev) => {
      const next = new Map(prev);
      next.set(seg.para, { ...c, decision: keep ? "keep" : "adopt" });
      return next;
    });
    setDecided((prev) => [
      ...prev.filter((d) => d.para !== seg.para),
      { para: seg.para, keep, label: seg.suggested_fix },
    ]);
    if (fixIdx + 1 < queue.length) setFixIdx(fixIdx + 1);
    else setStep(4);
  }

  function requestClose() {
    const pending = Array.from(cands.values()).filter((c) => c.status === "ready").length;
    if (pending > 0 && adoptedItems.length === 0) {
      if (window.confirm(`已生成 ${pending} 段改稿尚未应用，关闭将丢弃。确定关闭？`)) onClose();
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
            <button className="btn btn-secondary" onClick={() => decide(true)}>
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
          <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--faint)" }} id="gl-foot-note">
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
                <span className="gl-tag">{SEVERITY_TEXT[f.severity]}</span>
                <span>
                  {f.detail}
                  {f.count > 1 && f.rule === "multi_period" ? `（${f.count} 处）` : ""}
                </span>
                <em>段 {f.para + 1}</em>
              </li>
            ))}
            {report.findings.length === 0 && <li><span>规则清单全绿——文字层没有可机查的违规。</span></li>}
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
            <span>{curSeg.para === 0 ? "段 1" : `段 ${curSeg.para + 1}`} · {curSeg.source === "detector" || curSeg.source === "both" ? `朱雀判定 ${Math.round((curSeg.confidence ?? 0) * 100)}%` : "规则命中"}</span>
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
            {decided.map((d) => (
              <li key={d.para} className={d.keep ? "down" : "up"}>
                <span>段 {d.para + 1}</span>
                <b>{d.keep ? "保留原文" : "采用改稿"}</b>
                <em>{d.label}</em>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* ④ 应用确认 */}
      {step === 4 && (
        <div className="gl-pane">
          <div className="gl-ratio-row">
            <b className="gl-big">{adoptedItems.length} 段</b>
            <span className="gl-sub">
              本轮处理完毕：采用 {adoptedItems.length} 段 · 保留原文 {decided.length - adoptedItems.length} 段<br />
              应用后正文更新，旧检测结果标为「已过期」——到顶部重检一次看效果
            </span>
          </div>
          {decided.map((d) => {
            const c = cands.get(d.para);
            return (
              <div key={d.para} className="gl-diff-row" style={{ opacity: d.keep ? 0.6 : 1 }}>
                <div className="gl-diff-head">
                  <span className="pill pill-tag">段 {d.para + 1}</span>
                  <span>{d.label}</span>
                  <span className="gl-tag" style={{ marginLeft: "auto" }}>
                    {d.keep ? "保留原文" : "已采用"}
                  </span>
                </div>
                {c?.after && !d.keep && (
                  <div className="gl-pair">
                    <div><p className="gl-col-k">原文</p><p>{c.seg.text}</p></div>
                    <div><p className="gl-col-k">改稿</p><p className="gl-new">{c.after}</p></div>
                  </div>
                )}
              </div>
            );
          })}
          <p className="gl-hint">
            最后的反悔口：这里还能逐段改主意；「应用到正文」后走顶部朱雀条重检收口。
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
