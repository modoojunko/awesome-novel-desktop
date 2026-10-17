/** 人味检测报告弹窗（c-renwei-check）：四拍——说明 → 运行 → 结果 → 标记到正文。
 *
 *  节奏交给作家（c-renwei-check）：结果不自动上屏，由结果页「标记到正文」显式触发；
 *  说明页用流程图讲清 验→查→改→再验 的循环。文案全部面向作家（设计说明 §3.0）：
 *  不说指纹/基线/权重/额度，说「哪里像 AI」「真人常见范围」「分量」。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import Modal from "@/components/design/Modal";
import { errMessage } from "@/lib/api";
import { renweiCheck, type RenweiReport } from "@/lib/renwei";

type Phase = "intro" | "running" | "result";

interface Props {
  open: boolean;
  projectId: string;
  chapterRef: string;
  onClose: () => void;
  /** 作家点「标记到正文」：把结果交给正文层上边注（父组件负责关弹窗） */
  onMarkToBody: (report: RenweiReport) => void;
}

const SEV_TEXT = { err: "一票否决", warn: "提示" } as const;

function Arrow() {
  return (
    <svg className="rw-farr" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} aria-hidden="true">
      <path d="M5 12h13M13 6l6 6-6 6" />
    </svg>
  );
}

function Intro() {
  return (
    <div className="rw-intro">
      <div className="rw-intro-k">这是做什么的</div>
      <p>
        写完一章，让它和几百章真人小说对一对：哪里读起来像机器写的，直接圈出来，并告诉你怎么改。
        只提建议，动不动笔由你。
      </p>
      <div className="rw-intro-k">怎么用——一轮四步，循环到满意</div>
      <div className="rw-flow">
        <div className="rw-fnode">
          <span className="fn-h"><span className="fn-n">1</span><b>验</b></span>
          <i>先让朱雀查一遍，看 AI 占比</i>
        </div>
        <Arrow />
        <div className="rw-fnode self">
          <span className="fn-h"><span className="fn-n">2</span><b>查</b></span>
          <i>这里圈出像 AI 的地方（免费，随便查）</i>
        </div>
        <Arrow />
        <div className="rw-fnode">
          <span className="fn-h"><span className="fn-n">3</span><b>改</b></span>
          <i>照着边注提示自己动手，改一段看一段</i>
        </div>
        <Arrow />
        <div className="rw-fnode">
          <span className="fn-h"><span className="fn-n">4</span><b>再验</b></span>
          <i>回朱雀再查一遍，看占比降了没</i>
        </div>
      </div>
      <div className="rw-floop">
        <span>不满意就再来一轮——改到你觉得可以为止</span>
      </div>
      <div className="rw-intro-k">放心</div>
      <p>免费，不花一分钱额度；正文不出你的电脑；太短的章节打不了分；只给建议，改不改你说了算。</p>
    </div>
  );
}

function Running() {
  return (
    <div className="rw-running">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
        <path d="M21 12a9 9 0 11-6.2-8.56" />
      </svg>
      <span>正在把这一章和真人小说对照…</span>
    </div>
  );
}

function Result({ report }: { report: RenweiReport }) {
  const rate = report.score;
  const nErr = report.findings.filter((f) => f.sev === "err").length;
  const nWarn = report.findings.length - nErr;
  return (
    <>
      <div className="rw-score" data-testid="rw-score">
        <span className="num">
          {rate ? rate.rate.toFixed(1) : "—"}
          {rate ? <span className="pct">%</span> : null}
        </span>
        <span className="k">人味率<br />越高越像人</span>
        <span className={`rw-band ${rate ? rate.cls : "ref"}`}>{rate ? rate.band : "打不了分"}</span>
        <span className="exp">
          这一章和真人写作的距离——分越高越像人：70 以上就很不错，40 以下就是明显的机器腔。
          免费自查，改完再让朱雀复核，平时不必花那个额度。本章 {report.chars} 字。
          {rate ? "" : "（这一章还太短，先写完再打一次分。）"}
        </span>
      </div>

      {rate && rate.rate < 70 && report.priorities.length > 0 && (
        <div className="rw-prio" data-testid="rw-priorities">
          <p className="rw-sec" style={{ margin: "0 0 7px" }}>先改这几处——见效最快</p>
          {report.priorities.map((p) => (
            <div className="rw-prio-item" key={p.k}>
              <span className="pw">{p.w === 3 ? "最见效" : "也见效"}</span>
              <b>{p.k}</b>
              <span>{p.fix}</span>
            </div>
          ))}
          <p className="rw-prio-note">偷个懒：补对话、换具体物件、拆并句子——一个动作能同时改善好几项</p>
        </div>
      )}

      {report.findings.length > 0 ? (
        <>
          <p className="rw-sec">
            定位到的问题 · <b>{report.findings.length} 处</b>（红 {nErr} · 黄 {nWarn}）
          </p>
          <div className="rw-filist">
            {report.findings.map((f, i) => (
              <div className={`rw-fi ${f.sev}`} key={`${f.rule_id}-${f.para}-${i}`}>
                <span className="dot" />
                <span className="fx">
                  <span className="l1">
                    <span className="rl">{f.rule}</span>
                    <span className="pg">段 {f.para + 1}</span>
                    <span className="sv">{SEV_TEXT[f.sev]}</span>
                  </span>
                  <span className="l2">
                    {f.before}
                    <mark>{f.hit}</mark>
                    {f.after}
                  </span>
                  <span className="l3">
                    {f.why} <b>改法　</b>
                    {f.fix}
                  </span>
                </span>
              </div>
            ))}
          </div>
        </>
      ) : (
        <div className="rw-empty">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
            <path d="M5 13l4 4L19 7" />
          </svg>
          <span>没有发现明显问题——句子参差、用词具体、标点习惯都在真人区间内。</span>
        </div>
      )}

      <p className="rw-sec">整章对照 · 「真人常见范围」是几百章真人小说的常见范围，落在里面就正常</p>
      <table className="rw-mtable">
        <thead>
          <tr>
            <th>指标</th><th>本章</th><th>达标线</th><th>真人常见范围</th><th>分量</th><th>判定</th>
          </tr>
        </thead>
        <tbody>
          {report.metrics.map((m) => (
            <tr className={m.ok === true ? "is-ok" : m.ok === false ? "is-warn" : "is-ref"} key={m.k}>
              <td>{m.k}</td>
              <td className="v">{m.v}</td>
              <td className="t">{m.t}</td>
              <td className="h">{m.h}</td>
              <td className="w">{m.w === 3 ? "高" : m.w === 2 ? "中" : m.w === 1 ? "低" : "—"}</td>
              <td>
                {m.ok === true ? (
                  <span className="jd ok"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><path d="M5 13l4 4L19 7" /></svg></span>
                ) : m.ok === false ? (
                  <span className="jd warn"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><circle cx="12" cy="12" r="9" /><path d="M12 7.5v5M12 16.5h.01" /></svg></span>
                ) : (
                  <span className="jd ref"><span className="dot-ref" /></span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="rw-cta-note">逻辑硬伤、人物走形、节奏失衡这类问题，用右栏「章节体检」再看一遍。</p>
    </>
  );
}

export default function RenweiCheckModal({ open, projectId, chapterRef, onClose, onMarkToBody }: Props) {
  const [phase, setPhase] = useState<Phase>("intro");
  const [report, setReport] = useState<RenweiReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const bodyRef = useRef<HTMLDivElement>(null);

  // 每次开窗从说明页开始（节奏归作家：先读、再开始）
  useEffect(() => {
    if (open) {
      setPhase("intro");
      setReport(null);
      setError(null);
    }
  }, [open]);

  const run = useCallback(async () => {
    setPhase("running");
    setError(null);
    try {
      const r = await renweiCheck(projectId, chapterRef);
      setReport(r);
      setPhase("result");
    } catch (e) {
      setError(errMessage(e, "体检没跑起来，请稍后重试"));
      setPhase("result");
    }
  }, [projectId, chapterRef]);

  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = 0;
  }, [phase, report]);

  const note =
    phase === "intro"
      ? "免费 · 正文不出你的电脑 · 只提建议，不动稿子"
      : phase === "running"
        ? "正在对照真人小说的常见范围…"
        : error
          ? "没跑起来"
          : report && report.findings.length
            ? "红＝一票否决 · 黄＝提示；改不改、怎么改，作家定夺"
            : "这里没发现毛病，不代表朱雀也放行——发布前不妨再让朱雀看一遍";

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="人味检测"
      wbStyle
      width={700}
      locked={phase === "running"}
      footer={
        <>
          <span className="note">{note}</span>
          {phase === "intro" && (
            <button className="btn btn-primary" data-testid="renwei-start" onClick={() => void run()}>
              了解了，开始检测
            </button>
          )}
          {phase === "result" && !error && (
            <>
              <button className="btn btn-secondary" data-testid="renwei-rerun" onClick={() => void run()}>
                重新检测
              </button>
              <button
                className="btn btn-primary"
                data-testid="renwei-mark"
                disabled={!report || report.findings.length === 0}
                onClick={() => report && onMarkToBody(report)}
              >
                标记到正文
              </button>
            </>
          )}
          {phase === "result" && error && (
            <button className="btn btn-secondary" onClick={() => void run()}>重试</button>
          )}
        </>
      }
    >
      <div ref={bodyRef} style={{ maxHeight: "min(66vh, 620px)", overflowY: "auto" }}>
        {phase === "intro" && <Intro />}
        {phase === "running" && <Running />}
        {phase === "result" && (error ? <p className="rw-error">{error}</p> : report && <Result report={report} />)}
      </div>
    </Modal>
  );
}
