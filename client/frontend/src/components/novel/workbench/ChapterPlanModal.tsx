// ChapterPlanModal — 卷下拆章弹窗（c-chapter-plan-ai）
// 手写五段（全档）与 AI 三方向（PRO）共用同一张卡面；AI 四态；角标与「剧情吸引力/差在哪」；
// 手写卡底条「AI 看一眼这一章」（免费只读例外）。落点卡由外层渲染（关窗后回中栏）。
import Modal from "@/components/design/Modal";
import { cnNum } from "@/lib/nodeTitle";
import { STAGES, type ChapterPlanController } from "@/hooks/useChapterPlan";

export function ChapterPlanModal({
  plan,
  onAdopt,
  onClose,
}: {
  plan: ChapterPlanController;
  onAdopt: () => void;
  onClose: () => void;
}) {
  const { state, pickCard, patchDraft, toManual, draw, runSelfcheck } = plan;
  const cn = cnNum(state.volNo);
  // 章号单源＝服务端 anchor 的 next_no（原实现是常量占位，每章都写「拆第一章」）
  const chCn = cnNum(state.nextNo);
  const no2 = String(state.nextNo).padStart(2, "0");
  const isAi = state.entrySource === "ai";

  return (
    <Modal
      open={state.open}
      onClose={onClose}
      title={state.editing ? `改第${chCn}章` : `拆第${chCn}章`}
      width={940}
      wbStyle
      locked={state.submitting}
    >
      <div className="chapter-plan" data-testid="chapter-plan-modal">
        <p className="kicker">
          卷下拆章 · 第{cn}卷 · 第{state.nextNo}章
        </p>

        {/* ① 正在想 */}
        {isAi && state.phase === "busy" && (
          <div className="pick-busy" data-testid="split-busy">
            <span className="ra-spin" aria-hidden="true" />
            <span aria-live="polite">正在想第{chCn}章的 3 个方向…</span>
            <span className="none">都按你的卷纲和上一章结尾推——3 个方向接的是同一句进场</span>
          </div>
        )}

        {/* ② 出卡失败（三出口） */}
        {isAi && state.phase === "error" && (
          <div className="pick-error" data-testid="split-error">
            <p className="pv-error">{state.error}</p>
            <div className="edit-bar">
              <button className="btn btn-secondary btn-sm" data-testid="split-retry" onClick={() => void draw()}>
                重试
              </button>
              <button className="btn btn-ghost btn-sm" data-testid="split-to-manual" onClick={toManual}>
                自己写这一章
              </button>
              <button className="btn btn-ghost btn-sm" data-testid="split-close" onClick={onClose}>
                先不拆，回卷页
              </button>
            </div>
            {state.degradedText && (
              <div className="pick-degraded" data-testid="split-degraded">
                <p className="ai-note">{state.degradedText}</p>
              </div>
            )}
          </div>
        )}

        {/* ③ 只出两套（降级说明） */}
        {isAi && state.phase === "idle" && state.directions.length < 3 && state.note && (
          <p className="hint" data-testid="split-note">
            只想出两套：{state.note}
          </p>
        )}

        {/* ④ 三方向卡（点卡切本章卡——三卡收起，同原型「点卡进入本章卡」） */}
        {isAi && state.phase === "idle" && state.pick == null && (
          <>
            <p className="plans-h" data-testid="split-entry-line">
              第{chCn}章的 3 个剧情方向 · 进场已接上：{state.entry.text}（{state.entry.source}）
            </p>
            <div className="pick-grid" data-testid="pick-grid">
              {state.directions.map((d, i) => (
                <button
                  type="button"
                  key={i}
                  className={`pick-card${state.pick === i ? " on" : ""}${state.grades[i] === "S" ? " top" : ""}`}
                  data-testid={`pick-card-${i + 1}`}
                  role="radio"
                  aria-checked={state.pick === i}
                  onClick={() => pickCard(i)}
                >
                  <span
                    className={`pk-corner g-${state.grades[i] || ""}`}
                    data-testid={`pick-corner-${i + 1}`}
                    title={`剧情吸引力 ${state.grades[i]}`}
                  >
                    {state.grades[i]}
                    {state.grades[i] === "S" && <i>最吸引</i>}
                  </span>
                  <span className="pk-axis">{d.axis}</span>
                  <p className="pk-title">{d.title}</p>
                  <div className="pk-row"><b>上一章结尾 · 接上</b><span>{state.entry.text}</span></div>
                  <div className="pk-row"><b>本章剧情</b><span>{d.plot}</span></div>
                  <div className="pk-row"><b>碰到的挑战</b><span>{d.obstacle}</span></div>
                  <div className="pk-row"><b>本章结尾</b><span>{d.ending}</span></div>
                  <div className="pk-row"><b>本章行动</b><span>{d.acts.join("；")}</span></div>
                  <div className="pk-row"><b>阶段</b><span>{d.stage}</span></div>
                  <div className="pk-read" data-testid={`pick-read-${i + 1}`}>
                    <p><b>剧情吸引力</b>{d.why}</p>
                    {d.gap && <p><b>差在哪</b>{d.gap}</p>}
                  </div>
                  {state.pick === i && <span className="pk-picked">✓ 就要这个方向</span>}
                </button>
              ))}
            </div>
            {state.warnings.length > 0 && (
              <p className="ai-note" data-testid="split-warnings">{state.warnings.join("；")}</p>
            )}
            {state.checks.length > 0 && (
              <ul className="rp-list" data-testid="split-checks">
                {state.checks.map((c, i) => (
                  <li className="rp-row warn" key={i}>
                    <span className="rp-dot" aria-hidden="true" />
                    <span className="rp-tx">{c}</span>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}

        {/* 出口行恒在（三卡态与选卡后都可换一批/转手写——原型选卡后无回头路，产品侧留此出口） */}
        {isAi && state.phase === "idle" && (
          <div className="pick-foot">
            <button className="btn btn-secondary btn-sm" data-testid="split-redraw" onClick={() => void draw()}>
              ↻ 都不满意？换 3 个方向
            </button>
            <button className="btn btn-ghost btn-sm" onClick={toManual}>
              自己写这一章
            </button>
          </div>
        )}

        {/* ⑤ 本章卡 / 手写五段（同一张卡面） */}
        {(!isAi || state.pick != null) && state.phase !== "busy" && (
          <div className="split-row" data-testid="chapter-card">
            {state.draft.grade && (
              <span
                className={`pk-corner g-${state.draft.grade}`}
                data-testid="chapter-card-grade"
                title={`剧情吸引力 ${state.draft.grade}`}
              >
                {state.draft.grade}
                {state.draft.grade === "S" && <i>最吸引</i>}
              </span>
            )}
            <span className="s-no">{no2}</span>
            <div className="s-main">
              <div className="s-lab entry">
                <b>上一章结尾</b>
                <span className="s-entry" data-testid="d-prev">
                  {state.entry.text}（{state.entry.source} · 只读）
                </span>
              </div>
              <div className="s-lab">
                <b>章标题</b>
                <input className="input" aria-label="章标题" data-testid="d-title" maxLength={12}
                  value={state.draft.title} onChange={(e) => patchDraft({ title: e.target.value })} />
              </div>
              <div className="s-lab">
                <b>本章剧情</b>
                <input className="input" aria-label="本章剧情" data-testid="d-plot" maxLength={150}
                  value={state.draft.plot} onChange={(e) => patchDraft({ plot: e.target.value })} />
              </div>
              <div className="s-lab">
                <b>碰到的挑战</b>
                <input className="input" aria-label="碰到的挑战" data-testid="d-obstacle" maxLength={60}
                  value={state.draft.obstacle} onChange={(e) => patchDraft({ obstacle: e.target.value })} />
              </div>
              <div className="s-lab">
                <b>本章结尾</b>
                <input className="input" aria-label="本章结尾" data-testid="d-ending" maxLength={80}
                  value={state.draft.ending} onChange={(e) => patchDraft({ ending: e.target.value })} />
              </div>
              <div className="s-lab">
                <b>本章行动</b>
                <input className="input" aria-label="本章行动" data-testid="d-acts" maxLength={240}
                  value={state.draft.acts} onChange={(e) => patchDraft({ acts: e.target.value })} />
              </div>
              <div className="s-lab">
                <b>阶段</b>
                <select className="input" aria-label="阶段" data-testid="d-stage"
                  value={state.draft.stage} onChange={(e) => patchDraft({ stage: e.target.value })}>
                  {STAGES.map((st) => <option key={st} value={st}>{st}</option>)}
                </select>
              </div>
            </div>
          </div>
        )}

        {/* ⑥ 自检（手写卡；免费）——三组：衔接/配额（本地）＋剧情吸引力（AI 四维短评） */}
        {!isAi && (
          <details className="cfgset" open data-testid="selfcheck">
            <summary>AI 看一眼这一章</summary>
            <div className="inner">
              <ul className="rp-list">
                {state.selfcheck?.link ? (
                  <li className={"rp-row " + (state.selfcheck.link.ok ? "ok" : "warn")}>
                    <span className="rp-dot" aria-hidden="true" />
                    <span className="rp-tx">衔接：{state.selfcheck.link.text}</span>
                  </li>
                ) : (
                  <li className="rp-row ok">
                    <span className="rp-dot" aria-hidden="true" />
                    <span className="rp-tx">衔接：本章进场已自动接上上一章结尾</span>
                  </li>
                )}
                {state.selfcheck?.quota && (
                  <li className={"rp-row " + (state.selfcheck.quota.ok ? "ok" : "warn")}>
                    <span className="rp-dot" aria-hidden="true" />
                    <span className="rp-tx">配额：{state.selfcheck.quota.text}</span>
                  </li>
                )}
                {state.selfcheck && !state.selfcheck.failed && state.selfcheck.critiques &&
                  Object.entries(state.selfcheck.critiques).map(([k, v]) => (
                    <li className="rp-row warn" key={k}>
                      <span className="rp-dot" aria-hidden="true" />
                      <span className="rp-tx">剧情吸引力 · {k}：{v}</span>
                    </li>
                  ))}
                {(state.selfcheck?.failed || state.selfcheck?.degraded) && (
                  <li className="rp-row warn">
                    <span className="rp-dot" aria-hidden="true" />
                    <span className="rp-tx">{state.selfcheck?.hint || "AI 这一眼没看成，可再试"}</span>
                  </li>
                )}
              </ul>
              {state.selfcheck?.weakest && (
                <p className="ai-note">最弱一维：{state.selfcheck.weakest}</p>
              )}
            </div>
          </details>
        )}

        {/* 卡面就地错误（读卡失败／排上 422／保存失败）：不静默——手写与选卡后都算 */}
        {(!isAi || state.pick != null) && state.error && (
          <p className="pv-error" data-testid="chapter-card-error">
            {state.error}
          </p>
        )}

        {/* 底条（照原型：AI 出卡失败/三卡未选＝空；卡面在＝落地提示＋排上；手写另挂自检） */}
        <div className="mcard-foot" style={{ padding: 0, border: 0 }}>
          {isAi && state.phase === "busy" && (
            <button className="btn btn-ghost btn-sm" onClick={toManual}>自己写这一章</button>
          )}
          {(!isAi || state.pick != null) && state.phase !== "busy" && (
            <>
              {!state.editing && (
                <span className="note">
                  排上后章节列表多出这一章（拟定）；下一章的进场会自动接「{state.draft.ending || state.draft.plot || "本章结尾"}」。
                </span>
              )}
              {!isAi && (
                <button
                  className="btn btn-ghost btn-sm"
                  data-testid="selfcheck-run"
                  onClick={() => void runSelfcheck()}
                >
                  AI 看一眼这一章
                </button>
              )}
              <button
                className="btn btn-primary btn-sm"
                data-testid="split-adopt"
                disabled={state.submitting}
                onClick={onAdopt}
              >
                {state.submitting
                  ? state.editing ? "正在保存…" : "正在排上…"
                  : state.editing ? "保存这一章" : `排上这一章（第 ${state.nextNo} 章）`}
              </button>
            </>
          )}
        </div>
      </div>
    </Modal>
  );
}
