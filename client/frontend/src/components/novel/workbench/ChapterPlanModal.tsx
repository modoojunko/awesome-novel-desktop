// ChapterPlanModal — 卷下拆章弹窗（c-chapter-plan-ai）
// 手写四段（全档）与 AI 三方向（PRO）共用同一张卡面；AI 四态；角标与「剧情吸引力/差在哪」；
// 手写卡底条「AI 看一眼这一章」（免费只读例外）。落点卡由外层渲染（关窗后回中栏）。
import { useEffect, useState } from "react";
import Modal from "@/components/design/Modal";
import { cnNum } from "@/lib/nodeTitle";
import { STAGES, type ChapterPlanController } from "@/hooks/useChapterPlan";
import { useFeature } from "@/hooks/useTier";

// busy 态阶段进度（c-chapter-draw-retry-material，感知层）：前端计时推进的等待提示，
// 非后端真实进度——阶段全完成 SHALL NOT 提前结束 busy，出卡仍以响应回来为准。
const CH_STEPS = ["读卷纲与设定", "推演 3 个方向", "自查与评分"] as const;
const STEP_DONE_MS = [5000, 10000, 15000] as const;

export function ChapterPlanModal({
  plan,
  onAdopt,
  onClose,
}: {
  plan: ChapterPlanController;
  onAdopt: () => void;
  onClose: () => void;
}) {
  const { state, pickCard, patchDraft, toManual, draw, redraw, freshRedraw, runSelfcheck, openEdit } = plan;
  // 自检收 chapter-review（标准起，tier-plan-four-tiers 3.2——原「免费只读例外」收门）
  const chapterReview = useFeature("chapter-review");
  const cn = cnNum(state.volNo);
  // 章号单源＝服务端 anchor 的 next_no（原实现是常量占位，每章都写「拆第一章」）
  const chCn = cnNum(state.nextNo);
  const no2 = String(state.nextNo).padStart(2, "0");
  const isAi = state.entrySource === "ai";

  // 阶段计时：按 STEP_DONE_MS 逐段标完成；出卡（离开 busy）停表。
  // 归零放「离开 busy」侧（effect 重进 busy 的复位晚于首帧绘制，会闪一次「全完成」）——
  // 非 busy 态先把值清掉，重进 busy 的首帧必为 0；挂载初值本身是 0。
  const [stepsDone, setStepsDone] = useState(0);
  useEffect(() => {
    if (!(isAi && state.phase === "busy")) {
      setStepsDone(0);
      return;
    }
    const t0 = Date.now();
    const id = window.setInterval(() => {
      const el = Date.now() - t0;
      setStepsDone(STEP_DONE_MS.filter((ms) => el >= ms).length);
    }, 250);
    return () => window.clearInterval(id);
  }, [isAi, state.phase]);

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
          <div className="pick-busy col" data-testid="split-busy">
            <span className="ra-spin" aria-hidden="true" />
            <span aria-live="polite">正在想第{chCn}章的 3 个方向…</span>
            <span className="none">都按你的卷纲和上一章结尾推——3 个方向接的是同一句进场</span>
            {/* 阶段列表（.ex-steps 既有词汇；宽度内联取 genbox 同款 66ch，不新增 CSS 规则） */}
            <ul className="ex-steps" data-testid="split-steps" style={{ width: "100%", maxWidth: "66ch" }}>
              {CH_STEPS.map((s, i) => (
                <li key={s}>
                  <b>{s}</b>
                  {stepsDone > i ? (
                    <em className="ok">完成</em>
                  ) : (
                    <em>
                      <span className="ra-spin" aria-hidden="true" />进行中
                    </em>
                  )}
                </li>
              ))}
            </ul>
            <span className="no-close">AI 创作中，请勿关闭弹窗</span>
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
                  className={`pick-card${
                    /* v8 ignore start -- 死分支：④网格只在 pick==null 时渲染（点卡即整卡收起进本章卡），
                       渲染期间 pick===i 恒假，「on」选中高亮臂不可达（.on 类只为清场断言留空臂） */
                    state.pick === i ? " on" : ""
                    /* v8 ignore stop */}${state.grades[i] === "S" ? " top" : ""}`}
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
                  <div className="pk-row"><b>阶段</b><span>{d.stage}</span></div>
                  <div className="pk-read" data-testid={`pick-read-${i + 1}`}>
                    <p><b>剧情吸引力</b>{d.why}</p>
                    {d.gap && <p><b>差在哪</b>{d.gap}</p>}
                  </div>
                  {/* v8 ignore start -- 死分支：同上——网格只在 pick==null 时渲染（点卡即收起进本章卡），
                     「✓ 就要这个方向」选中角标臂不可达（选中态由本章卡的 pk-corner/pk-picked 位承接） */}
                  {state.pick === i && <span className="pk-picked">✓ 就要这个方向</span>}
                  {/* v8 ignore stop */}
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

        {/* 出口行——只在三卡态出现在网格下方（原型位）；选卡后两出口下沉到底条，不在卡面上方悬空 */}
        {isAi && state.phase === "idle" && state.pick == null && (
          <div className="pick-foot">
            <button className="btn btn-secondary btn-sm" data-testid="split-redraw" onClick={() => void redraw()}>
              ↻ 都不满意？换 3 个方向
            </button>
            {state.exclude.length > 0 && (
              <button className="btn btn-secondary btn-sm" data-testid="split-fresh" onClick={() => void freshRedraw()}>
                从头再来
              </button>
            )}
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
                <b>阶段</b>
                <select className="input" aria-label="阶段" data-testid="d-stage"
                  value={state.draft.stage} onChange={(e) => patchDraft({ stage: e.target.value })}>
                  {STAGES.map((st) => <option key={st} value={st}>{st}</option>)}
                </select>
              </div>
            </div>
          </div>
        )}

        {/* ⑥ 自检（手写卡；chapter-review 标准起——3.2 收门）——三组：衔接/配额（本地）＋剧情吸引力（AI 四维短评） */}
        {!isAi && (
          <details className="cfgset" open data-testid="selfcheck">
            <summary>
              AI 看一眼这一章
              {!chapterReview && <span className="pill pill-warn" data-testid="selfcheck-locked">需开通</span>}
            </summary>
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
            {/* 回改读卡失败的唯一出口：重试（未装载前保存禁用，防止脏草稿写进目标章） */}
            {state.editing && !state.cardLoaded && (
              <button
                className="btn btn-ghost btn-sm"
                data-testid="split-retry-load"
                onClick={() => state.editing && void openEdit(state.editing)}
              >
                重试
              </button>
            )}
          </p>
        )}

        {/* AI 选卡态＝落地提示独立行＋动作行归底（出口 ghost＋排上右对齐；挤一行会挤断按钮） */}
        {isAi && state.pick != null && state.phase !== "busy" && !state.editing && (
          <>
            <p className="hint">
              排上后章节列表多出这一章（拟定）；下一章的进场会自动接「{state.draft.ending || state.draft.plot || "本章结尾"}」。
            </p>
            <div className="pick-foot">
              <button className="btn btn-ghost btn-sm" data-testid="split-redraw" onClick={() => void redraw()}>
                ↻ 换 3 个方向
              </button>
              <button className="btn btn-ghost btn-sm" onClick={toManual}>
                自己写这一章
              </button>
              <button
                className="btn btn-primary btn-sm"
                data-testid="split-adopt"
                disabled={state.submitting}
                onClick={onAdopt}
              >
                {state.submitting ? "正在排上…" : `排上这一章（第 ${state.nextNo} 章）`}
              </button>
            </div>
          </>
        )}

        {/* 底条（照原型：AI 出卡失败/三卡未选＝空；手写/回改＝提示＋排上；busy＝转手写） */}
        <div className="mcard-foot" style={{ padding: 0, border: 0 }}>
          {isAi && state.phase === "busy" && (
            <button className="btn btn-ghost btn-sm" onClick={toManual}>自己写这一章</button>
          )}
          {!isAi && state.phase !== "busy" && (
            <>
              {/* v8 ignore start -- 死分支：外层条件已含 !isAi，内层 isAi 恒 false——AI 选卡态的
                  底条出口已由上方「pick-foot 独立块」（选卡态渲染段）承接，此处为提取时遗留，不可达 */}
              {isAi && state.pick != null && (
                <>
                  <button className="btn btn-ghost btn-sm" data-testid="split-redraw" onClick={() => void redraw()}>
                    ↻ 换 3 个方向
                  </button>
                  <button className="btn btn-ghost btn-sm" onClick={toManual}>
                    自己写这一章
                  </button>
                </>
              )}
              {/* v8 ignore stop */}
              {!isAi && (
                <button
                  className="btn btn-ghost btn-sm"
                  data-testid="selfcheck-run"
                  disabled={state.selfchecking}
                  onClick={() => void runSelfcheck()}
                >
                  {state.selfchecking ? "正在看…" : "AI 看一眼这一章"}
                </button>
              )}
              {!state.editing && (
                <span className="note">
                  排上后章节列表多出这一章（拟定）；下一章的进场会自动接「{state.draft.ending || state.draft.plot || "本章结尾"}」。
                </span>
              )}
              <button
                className="btn btn-primary btn-sm"
                data-testid="split-adopt"
                disabled={state.submitting || (state.editing != null && !state.cardLoaded)}
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
