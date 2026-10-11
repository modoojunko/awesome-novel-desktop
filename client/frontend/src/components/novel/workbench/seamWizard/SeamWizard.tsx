/** 章际衔接修复向导（c-seam-refill）：四步弹窗——
 *  ① 衔接检查报告（ai_check chapter_seam）② 重写方案三选一（知前后补中间，SSE draft）
 *  ③ 当前 vs 新方案对照取舍 ④ 应用（经 ProsePane 注入的 onApply，段号＋锚文校验）。
 *  向导内一切产出为候选态；唯一写正文口＝应用（作者确认制，旧稿在版本历史）。 */
import { useCallback, useEffect, useRef, useState } from "react";
import Modal from "@/components/design/Modal";
import { runAiCheck, type AiFinding } from "@/lib/aiCheck";
import { seamRefillDraft, type SeamOption } from "@/lib/seamRefill";

export interface SeamWizardProps {
  open: boolean;
  onClose: () => void;
  projectId: string;
  chapterRef: string;
  /** 替换段数（打开时按当前正文快照定下，默认 3、钳到现有段数） */
  paraCount: number;
  /** 打开时前 paraCount 段原文（对照展示＋应用前快照） */
  currentOpening: string;
  /** 打开时前 paraCount 段 folded 拼接（应用前锚文校验） */
  snapshotFolded: string;
  /** 应用（ProsePane 执行器：锚文校验＋单事务替换，返回是否成功） */
  onApply: (text: string) => boolean;
}

const STEP_LABELS = ["衔接检查", "重写方案（三选一）", "对照取舍", "已应用"];
/** 差异轴固定三版（互斥由策略分工保证，同 c-seam-refill 设计） */
const AXIS: Array<{ key: string; label: string }> = [
  { key: "直承", label: "A" },
  { key: "过渡", label: "B" },
  { key: "重排", label: "C" },
];
/** 卡片标题作家化（后端 approach 为轴名，展示层翻译） */
const AXIS_TEXT: Record<string, string> = {
  直承: "顺着上一章写",
  过渡: "垫一拍再接",
  重排: "换个顺序起笔",
};

export default function SeamWizard({
  open,
  onClose,
  projectId,
  chapterRef,
  paraCount,
  currentOpening,
  snapshotFolded,
  onApply,
}: SeamWizardProps) {
  const [step, setStep] = useState(0);
  const [checking, setChecking] = useState(false);
  const [checkErr, setCheckErr] = useState<string | null>(null);
  const [findings, setFindings] = useState<AiFinding[]>([]);

  const [drafting, setDrafting] = useState(false);
  const [draftErr, setDraftErr] = useState<string | null>(null);
  const [phaseText, setPhaseText] = useState("正在读上一章结尾与本章现状…");
  const [chars, setChars] = useState(0);
  const [options, setOptions] = useState<SeamOption[]>([]);
  const [selected, setSelected] = useState<SeamOption | null>(null);
  const [rejected, setRejected] = useState<Array<{ approach: string; text: string }>>([]);
  const [applying, setApplying] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const reqId = useRef(0);

  const runDraft = useCallback(
    (excluded: string[], rejectedOverride?: Array<{ approach: string; text: string }>) => {
      const id = ++reqId.current;
      setDrafting(true);
      setDraftErr(null);
      setOptions([]);
      setSelected(null);
      setChars(0);
      setPhaseText("正在读上一章结尾与本章现状…");
      const rejList = rejectedOverride ?? rejected;
      const controller = seamRefillDraft(
        projectId,
        chapterRef,
        {
          para_count: paraCount,
          findings: findings.map((f) => ({ title: f.title, detail: f.detail })),
          rejected: rejList.filter((r) => !excluded.includes(r.approach)),
        },
        {
          onPhase: (phase) => {
            if (id !== reqId.current) return;
            setPhaseText(phase === "model" ? "正在起草三种衔接方案…" : "正在读上一章结尾与本章现状…");
          },
          onChars: (n) => {
            if (id !== reqId.current) return;
            setChars(n);
            setPhaseText(n > 600 ? "好的接法需要一点时间，模型在思考…" : "正在起草三种衔接方案…");
          },
          onDone: (opts) => {
            if (id !== reqId.current) return;
            setOptions(opts);
            setDrafting(false);
          },
          onError: (msg) => {
            if (id !== reqId.current) return;
            setDraftErr(msg);
            setDrafting(false);
          },
        },
      );
      abortRef.current = controller;
    },
    [projectId, chapterRef, paraCount, findings, rejected],
  );

  // 打开即跑衔接检查（步 1）
  useEffect(() => {
    if (!open) return;
    setStep(0);
    setChecking(true);
    setCheckErr(null);
    setFindings([]);
    setOptions([]);
    setSelected(null);
    setRejected([]);
    setDrafting(false);
    setDraftErr(null);
    runAiCheck(projectId, chapterRef, "chapter_seam")
      .then((fs) => {
        setFindings(fs);
        setChecking(false);
      })
      .catch((e: Error) => {
        setCheckErr(e.message || "衔接检查失败");
        setChecking(false);
      });
  }, [open, projectId, chapterRef]);

  // 阶段文案随已用时间轮换（防「以为卡死」）
  useEffect(() => {
    if (!drafting) return;
    const t0 = Date.now();
    const timer = setInterval(() => {
      const sec = Math.floor((Date.now() - t0) / 1000);
      if (sec > 45) setPhaseText("好的接法需要一点时间，模型在思考…");
      else if (sec > 15) setPhaseText("正在起草三种衔接方案…");
    }, 3000);
    return () => clearInterval(timer);
  }, [drafting]);

  if (!open) return null;

  const hasProblems = findings.length > 0;

  const apply = () => {
    if (!selected) return;
    setApplying(true);
    const ok = onApply(selected.text);
    setApplying(false);
    if (ok) {
      setStep(3);
    } else {
      setDraftErr("正文已变动，与打开向导时不一致——请重开向导");
    }
  };

  const stepTitle =
    step === 0
      ? "章际衔接 · 检查报告"
      : step === 1
        ? drafting
          ? "重写方案起草中…"
          : "重写方案（三选一）"
        : step === 2
          ? "当前 vs 新方案对照"
          : "已应用";

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="接上一章 · 衔接修复"
      wbStyle
      width={840}
      locked={applying || drafting}
      footer={
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {step === 0 && !checking && hasProblems && (
            <button className="btn btn-primary" onClick={() => { setStep(1); runDraft([]); }}>
              下一步 · 起草重写方案
            </button>
          )}
          {step === 1 && !drafting && !draftErr && options.length > 0 && (
            <button
              className="btn btn-primary"
              disabled={!selected}
              onClick={() => { setSelected(selected); setStep(2); }}
            >
              下一步 · 对照取舍
            </button>
          )}
          {step === 2 && selected && !applying && (
            <button className="btn btn-primary" onClick={apply} disabled={applying}>
              应用到正文（替换开头 {paraCount} 段）
            </button>
          )}
          <button className="btn btn-ghost" onClick={onClose} disabled={drafting || applying}>
            {step === 3 ? "关闭" : "取消"}
          </button>
          <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--faint)" }}>
            {step === 0
              ? "只查本章开头与上一章结尾的衔接 · 其他问题不在本向导范围"
              : step === 1
                ? "知前后补中间 · 上章结尾与本章后文原样保留"
                : step === 2
                  ? "应用后旧稿在版本历史中可找回 · 建议重跑章际衔接检查复检"
                  : "衔接修复完成"}
          </span>
        </div>
      }
    >
      {step === 0 && (
        <div>
          {checking && <div>正在检查本章开头与上一章结尾的衔接…</div>}
          {!checking && checkErr && <div style={{ color: "crimson" }}>{checkErr}</div>}
          {!checking && !checkErr && !hasProblems && (
            <div>
              <b>这一章的开头接住了上一章，不用改。</b>
              <div style={{ color: "var(--faint)", fontSize: 12, marginTop: 6 }}>
                本章开头接住了上一章结尾（无另起炉灶、无过渡跳切、未重写上章画面）。可以直接关闭。
              </div>
            </div>
          )}
          {!checking && !checkErr && hasProblems && (
            <div>
              <div style={{ marginBottom: 8 }}>
                这一章的开头，有 <b>{findings.length}</b> 处没接住上一章的结尾：
              </div>
              {findings.map((f, i) => (
                <div key={i} style={{ marginBottom: 8 }}>
                  <b>{f.title}</b>
                  <div style={{ fontSize: 12.5, color: "var(--faint)" }}>{f.detail}</div>
                </div>
              ))}
              <div style={{ fontSize: 12, color: "var(--faint)", marginTop: 8 }}>
                下一步会给你三种改法挑：上一章的结尾和这一章后面的内容都原样保留，只重写中间接不上的开场。
              </div>
            </div>
          )}
        </div>
      )}

      {step === 1 && (
        <div>
          {drafting && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
                {AXIS.map((a) => (
                  <div key={a.key} className="card bg-base-200" style={{ flex: 1, padding: "10px 12px", animation: "pulse 1.6s ease-in-out infinite" }}>
                    <b>{a.label} · {AXIS_TEXT[a.key] || a.key}</b>
                    <div style={{ fontSize: 12, color: "var(--faint)" }}>起草中…</div>
                  </div>
                ))}
              </div>
              <div style={{ fontSize: 13 }}>
                {phaseText}
                {chars > 0 && <span style={{ color: "var(--faint)" }}> · 已生成 {chars.toLocaleString("zh-CN")} 字</span>}
              </div>
              <button className="btn btn-ghost btn-sm" style={{ marginTop: 8 }} onClick={() => { abortRef.current?.abort(); setDrafting(false); setDraftErr("已取消，可重新起草"); }}>
                取消
              </button>
            </div>
          )}
          {!drafting && draftErr && (
            <div style={{ color: "crimson", marginBottom: 8 }}>
              {draftErr}
              <button className="btn btn-sm" style={{ marginLeft: 8 }} onClick={() => runDraft([])}>重试</button>
            </div>
          )}
          {!drafting && options.length > 0 && (
            <div className="pick-grid" data-testid="seam-grid">
              {options.map((o) => (
                <button
                  type="button"
                  key={o.key}
                  className={`pick-card${selected?.key === o.key ? " on" : ""}`}
                  onClick={() => setSelected(o)}
                >
                  <span className="pk-axis">{AXIS_TEXT[o.key] || o.key}</span>
                  <p className="pk-title">{o.text}</p>
                  <div className="pk-row">
                    <b>怎么接</b>
                    <span>{o.how}</span>
                  </div>
                  {selected?.key === o.key && <span className="pk-picked">✓ 已选这一版</span>}
                </button>
              ))}
              <button
                className="btn btn-ghost btn-sm"
                style={{ alignSelf: "flex-start" }}
                onClick={() => {
                  const rej = [...rejected, ...options.map((o) => ({ approach: o.key, text: o.text }))];
                  setRejected(rej);
                  runDraft(rej.map((r) => r.approach), rej);
                }}
                disabled={!options.length}
              >
                都不满意 · 换一批（避开已否决）
              </button>
            </div>
          )}
        </div>
      )}

      {step === 2 && selected && draftErr && (
        <div style={{ color: "crimson", marginBottom: 8 }}>
          {draftErr}
          <button className="btn btn-sm" style={{ marginLeft: 8 }} onClick={onClose}>
            重开向导
          </button>
        </div>
      )}
      {step === 2 && selected && (
        <div>
          <div style={{ fontSize: 12, color: "var(--faint)", marginBottom: 8 }}>
            左＝当前正文开头（将替换）；右＝所选方案「{selected.key}」（落位后）。方案之外的后文原样保留。
          </div>
          <div style={{ display: "flex", gap: 12 }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 12, marginBottom: 4 }}>当前开头</div>
              <div className="card bg-base-200" style={{ padding: 10, whiteSpace: "pre-wrap", fontSize: 13 }}>
                {currentOpening}
              </div>
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 12, marginBottom: 4 }}>新方案（{selected.key}）</div>
              <div className="card bg-base-100" style={{ padding: 10, whiteSpace: "pre-wrap", fontSize: 13, outline: "1px solid var(--p)" }}>
                {selected.text}
              </div>
            </div>
          </div>
        </div>
      )}

      {step === 3 && (
        <div>
          <b>衔接修复已应用到正文。</b>
          <div style={{ fontSize: 12.5, color: "var(--faint)", marginTop: 6 }}>
            旧稿在「版本历史」可找回。建议点右栏「章际衔接检查」复检一次——空数组即闭环。
          </div>
        </div>
      )}
    </Modal>
  );
}
