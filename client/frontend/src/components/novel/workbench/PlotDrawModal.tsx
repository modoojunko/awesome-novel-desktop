// PlotDrawModal — 章剧情三版选一（c-plot-split，原型 #modalPlotDraw 逐字复刻）。
// 四态：busy / cards / error（失败三出口：去模型配置、再试一次、先自己写）；
// 卡面＝条目逐条预览（两行截断、title 看全文）＋右上 S/A/B 抓人程度角标（缺名次不出）；
// 卡序按抓人程度排（「越靠上越抓人」，缺角标的排最后、保持原序）；
// 「就填这版」整表替换，列表非空时按钮明示「将替换已写的 N 条」（拍板②）；
// 「自己写」「先自己写」＝关窗退回原列表（不丢已写内容）。
import Modal from "@/components/design/Modal";
import { Ico, P } from "@/components/icons";
import { cnNum } from "@/lib/nodeTitle";
import type { PlotDrawState } from "@/hooks/usePlotDraw";

const GRADE_ORDER: Record<string, number> = { S: 0, A: 1, B: 2, "": 3 };

export default function PlotDrawModal({
  state,
  chapterLabel,
  writtenCount,
  onPick,
  onAdopt,
  onRedraw,
  onManual,
  onClose,
  onOpenConfig,
}: {
  state: PlotDrawState;
  chapterLabel: string;
  /** 当前列表已写的非空条数（替换明示用；0＝不提示替换） */
  writtenCount: number;
  onPick: (i: number) => void;
  onAdopt: () => void;
  onRedraw: () => void;
  /** 自己写/先自己写：关窗退回原列表 */
  onManual: () => void;
  onClose: () => void;
  /** 去模型配置（失败三出口之一；HashRouter 跳转由上层做） */
  onOpenConfig: () => void;
}) {
  // 抓人程度排序（稳定）：S→A→B→无角标；「越靠上越抓人」与卡面标题口径一致
  const cards = state.versions
    .map((items, i) => ({ items, grade: state.grades[i] ?? "" }))
    .map((c, i) => ({ ...c, src: i }))
    .sort((a, b) => GRADE_ORDER[a.grade] - GRADE_ORDER[b.grade]);

  return (
    <Modal
      open={state.open}
      onClose={onClose}
      title={`挑一版剧情 · ${chapterLabel}`}
      width={940}
      wbStyle
    >
      <div className="plan-modal plot-draw" data-testid="plot-draw-modal">
        <p className="kicker">三选一 · 挑一版</p>
        <p className="draw-lead">
          3
          版都接着上一章的结尾写、到这一章的结尾收住——开头结尾都一样，只有中间怎么撞墙不同。挑一版填进去，之后能改、能删、能反悔。
        </p>

        {state.phase === "busy" && (
          <div className="pick-busy" data-testid="plot-busy">
            <span className="ra-spin" aria-hidden="true" />
            <span aria-live="polite">正在写{chapterLabel}的 3 版剧情…</span>
          </div>
        )}

        {state.phase === "error" && (
          <div className="pick-error" data-testid="plot-error">
            <p className="pv-error">AI 没写出来</p>
            <p className="ai-note">
              要么是还没设置 AI 模型——先去「模型配置」里加一个；要么是没凑满 3
              版——凑不满就不给挑。可以再试一次，或者自己写。
            </p>
            <div className="pick-error-acts">
              <button
                className="btn btn-primary btn-sm"
                data-testid="plot-config"
                onClick={onOpenConfig}
              >
                去模型配置
              </button>
              <button className="btn btn-secondary btn-sm" data-testid="plot-retry" onClick={onRedraw}>
                再试一次
              </button>
              <button className="btn btn-ghost btn-sm" data-testid="plot-manual" onClick={onManual}>
                先自己写
              </button>
            </div>
          </div>
        )}

        {state.phase === "cards" && (
          <>
            <p className="plans-h">3 版剧情 · 越靠上越抓人</p>
            <div className="pick-grid" data-testid="plot-grid">
              {cards.map((c, displayNo) => {
                const picked = state.pick === c.src;
                return (
                  <button
                    type="button"
                    key={c.src}
                    className={`pick-card${c.grade === "S" ? " top" : ""}${picked ? " on" : ""}`}
                    data-testid={`plot-card-${c.src}`}
                    aria-pressed={picked}
                    onClick={() => onPick(c.src)}
                  >
                    {c.grade && (
                      <span className={`pk-corner g-${c.grade}`} title={`抓人程度 ${c.grade}`}>
                        {c.grade}
                        {c.grade === "S" && <i>最抓人</i>}
                      </span>
                    )}
                    <span className="pk-axis">{`第${cnNum(displayNo + 1)}版`}</span>
                    {c.items.map((t, j) => (
                      <div className="pk-row pk-in" key={j}>
                        <b>第 {j + 1} 条</b>
                        <span title={t}>{t}</span>
                      </div>
                    ))}
                    {picked && (
                      <span className="pk-picked">
                        <Ico d={P.check} sw={2.4} size={10} />
                        就填这版
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
            <div className="pick-foot">
              <button className="link" data-testid="plot-redraw" onClick={onRedraw}>
                换一批
              </button>
              <button className="btn btn-ghost btn-sm" data-testid="plot-manual" onClick={onManual}>
                自己写
              </button>
              <button
                className="btn btn-primary btn-sm"
                data-testid="plot-adopt"
                disabled={state.pick == null}
                onClick={onAdopt}
              >
                {writtenCount > 0
                  ? `就填这版 · 将替换已写的 ${writtenCount} 条`
                  : "就填这版"}
              </button>
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}
