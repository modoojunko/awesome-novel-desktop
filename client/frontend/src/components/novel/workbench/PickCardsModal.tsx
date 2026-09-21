// PickCardsModal — 三选一抽卡（c-volume-antagonist 付费默认路径）。
// 原型 #pick-modal 直译：940 宽横排三卡（窄屏纵排）、每卡四问答案＋侧重轴、busy/error 态、
// 选中→「确认这一套，成卷」（token 守卫：写请求前可取消）、「↻ 换 3 套」重抽、
// 「自己答四个问题」切手写页（已答保留）。
import Modal from "@/components/design/Modal";
import { cnNum } from "@/lib/nodeTitle";
import type { VolumePlanCard, VolumePlanController } from "@/hooks/useVolumePlan";

export function PickCardsModal({
  plan,
  onConfirm,
  onToDesk,
  onClose,
}: {
  plan: VolumePlanController;
  /** 确认＝外层执行落库（建/更卷＋hooks/batch＋落点卡） */
  onConfirm: (card: VolumePlanCard) => void;
  onToDesk: () => void;
  onClose: () => void;
}) {
  const { state, selectCard } = plan;
  const cn = cnNum(state.volNo);

  return (
    <Modal
      open={state.pickOpen}
      onClose={onClose}
      title={`规划第${cn}卷 · 三选一`}
      width={940}
      wbStyle
      // 写请求发出后 locked（P1-4）：卷已落库却不置 confirmResult 会让自查条永远不出现
      locked={state.confirming}
    >
      <div className="pick-modal" data-testid="pick-modal">
        <p className="kicker">规划第{cn}卷 · 三选一</p>
        <p className="pa-lead" data-testid="pick-lead">
          都按你的全书设定和上一卷的结尾推——四个问题的答案各不相同，选一套，这一卷的卷纲就成了。
        </p>

        {state.pickPhase === "busy" && (
          <div className="pick-busy" data-testid="pick-busy">
            <span className="ra-spin" aria-hidden="true" />
            <span aria-live="polite">正在想三套思路…</span>
          </div>
        )}

        {state.pickPhase === "error" && (
          <div className="pick-error" data-testid="pick-error">
            <p className="pv-error">{state.pickError}</p>
            <div className="pick-error-acts">
              <button className="btn btn-sm" onClick={() => void plan.drawCards()}>
                重试
              </button>
              <button className="btn btn-sm" onClick={onToDesk}>
                自己答四个问题
              </button>
            </div>
          </div>
        )}

        {state.pickPhase === "idle" && (
          <>
            {state.note && state.plans.length < 3 && (
              <p className="ai-note" data-testid="pick-note">
                只想出两套：{state.note}
              </p>
            )}
            <div className="pick-grid" data-testid="pick-grid">
              {state.plans.map((p) => (
                <button
                  type="button"
                  key={p.no}
                  className={`pick-card${state.pickPick === p.no ? " on" : ""}`}
                  data-testid={`pick-card-${p.no}`}
                  aria-checked={state.pickPick === p.no}
                  role="radio"
                  disabled={state.confirming}
                  onClick={() => selectCard(p.no)}
                >
                  <span className="pk-axis">{p.focus_axis || "走向"}</span>
                  <p className="pk-title">{p.spine}</p>
                  <div className="pk-row">
                    <b>主要冲突</b>
                    <span>{p.conflict}</span>
                  </div>
                  {(p.antagonist_line || p.antagonist_type) && (
                    <div className="pk-row">
                      <b>这一卷的坎</b>
                      <span>
                        {[p.antagonist_type, p.antagonist_line].filter(Boolean).join(" · ")}
                      </span>
                    </div>
                  )}
                  <div className="pk-row">
                    <b>卷末</b>
                    <span>{p.ending}</span>
                  </div>
                  {state.pickPick === p.no && <span className="pk-picked">✓ 已选这一套</span>}
                </button>
              ))}
            </div>
            <div className="pick-foot">
              <button
                className="btn btn-sm"
                data-testid="pick-redraw"
                disabled={state.confirming}
                onClick={() => void plan.drawCards("redraw")}
              >
                ↻ 都不满意？换 3 套
              </button>
              <span className="note">
                换一批新思路——或
                <button className="link" onClick={onToDesk}>
                  自己答四个问题
                </button>
                （答多少 AI 铺多少）
              </span>
              {state.confirming ? (
                <button className="btn btn-sm btn-primary" disabled>
                  <span className="ra-spin" aria-hidden="true" />
                  正在铺这一卷…
                </button>
              ) : (
                <button
                  className="btn btn-sm btn-primary"
                  data-testid="pick-confirm"
                  disabled={state.pickPick == null}
                  onClick={() => {
                    const card = state.plans.find((p) => p.no === state.pickPick);
                    if (card) onConfirm(card);
                  }}
                >
                  确认这一套，成卷 →
                </button>
              )}
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}
