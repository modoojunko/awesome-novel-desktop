// VolumePlanModal — 规划台弹出页（volume-plan-ai）。
// 结构逐件对齐原型 ai-novel-c端-整书拆纲.html 的 .plan-sheet：
//   kicker（分卷规划 · 第N卷）→ plan-anchor（引导语＋进场：上一卷结尾/全景起步；
//   首卷另带卷数估计）→ cfgset 分卷依据（dep-row 台账）→ plan-desk（写一句＋
//   按这一句展开/给我 3 套方案＋保证语）→ plans（3 套 .cand 卡）→ cfgset 七条规则
//   → plan-foot（先不规划 / 生成中关掉 / 回填 →）。
// 生成中/生成完成只换 plan-desk（genbox）；进度只在弹窗内——「弹窗开着背景静止」。
// 免费档：规划台可进、材料与规则可看、输入可写；两个生成动作禁用＋PRO 说明。
import { useEffect, useMemo, useState } from "react";
import Modal from "@/components/design/Modal";
import { api } from "@/lib/api";
import { GENRE_PENDING_LABEL } from "@/lib/genreVocab";
import { cnNum } from "@/lib/nodeTitle";
import type { WorkbenchVolume } from "@/hooks/useWorkbench";
import {
  GEN_STEPS,
  type VolumePlanController,
} from "@/hooks/useVolumePlan";

/** 界面七条＝作家语言（与提示词文本不同源，workbench delta 口径；原型 RULES 逐字） */
const RULES_FOR_AUTHOR = [
  "不凭空添人添事：只用你设定里已有的人物、势力、事件和地点。",
  "接着上一卷的结尾往下写，不跳空——第一卷从你写的起步开始。",
  "这一卷要解决的事，得是全书主线走到这一步该解决的事，不另开一条线。",
  "卷末要给读者一个交代，同时把故事朝你写的那个结局推近一步。",
  "不跟你的设定打架：人物性格、世界规矩、已经埋下的伏笔。",
  "伏笔不重复埋、不提前揭；埋下的说清打算哪一卷收。",
  "只把你的那句话铺成结构，不替你改走向——有冲突它会说出来。",
];

interface DepRowData {
  k: string;
  v: string;
  s: string;
  cls: string; // ''(ok) | 'muted' | 'warn'
}

/** 分卷依据 · 来自你的设定（dep-row 台账；缺口标出、点行回设定） */
function useDeps(
  projectId: string,
  active: boolean,
  volumes: WorkbenchVolume[],
  genreLabel: string,
): DepRowData[] {
  const [fullstory, setFull] = useState("");
  const [ending, setEnding] = useState("");
  const [chars, setChars] = useState<number | null>(null);
  useEffect(() => {
    if (!active || !projectId) return;
    let alive = true;
    (async () => {
      try {
        const arc = await api.fetchStoryArc(projectId);
        const e = arc?.ending ?? {};
        if (alive) {
          setFull(String(arc?.fullstory ?? "").trim());
          setEnding(
            [e?.scene, e?.hero, e?.tone].filter(Boolean).join("｜").trim(),
          );
        }
      } catch {
        /* 材料缺口只标出、不拦 */
      }
      try {
        const d = (await api.get(`/novels/${projectId}/characters`)) as {
          items?: unknown[];
        };
        if (alive) setChars(Array.isArray(d?.items) ? d.items.length : null);
      } catch {
        if (alive) setChars(null);
      }
    })();
    return () => {
      alive = false;
    };
  }, [projectId, active]);
  return useMemo(() => {
    const targetTotal = volumes.reduce(
      (a, v) => a + (v.chapter_target ?? 0),
      0,
    );
    const genreOk = !!genreLabel && genreLabel !== GENRE_PENDING_LABEL;
    return [
      {
        k: "主线全景",
        v: fullstory ? fullstory.slice(0, 80) : "缺口——先去设定补主线",
        s: fullstory ? "已填" : "缺口",
        cls: fullstory ? "" : "warn",
      },
      {
        k: "结局三问",
        v: ending ? ending.slice(0, 60) : "缺口——只作参照，不拦拆卷",
        s: ending ? "已填" : "缺口",
        cls: ending ? "" : "warn",
      },
      {
        k: "题材",
        v: genreOk ? genreLabel : "待定（不拦）",
        s: genreOk ? "已定" : "待定",
        cls: genreOk ? "" : "muted",
      },
      {
        k: "主要角色",
        v: chars ? `${chars} 人` : "还没有角色卡（不拦）",
        s: chars ? "已登记" : "缺口",
        cls: chars ? "" : "muted",
      },
      {
        k: "目标篇幅",
        v: targetTotal ? `已排卷合计约 ${targetTotal} 章` : "未设（可不设）",
        s: targetTotal ? "已设" : "未设",
        cls: targetTotal ? "" : "muted",
      },
    ];
  }, [fullstory, ending, chars, genreLabel, volumes]);
}

/** 锚点：这一卷从哪里进场（后端 plan-anchor 单源，事实优先）＋首卷卷数估计 */
function useAnchor(projectId: string, volNo: number, active: boolean) {
  const [anchor, setAnchor] = useState<{
    text: string;
    source: string;
  } | null>(null);
  useEffect(() => {
    if (!active || !projectId) return;
    let alive = true;
    setAnchor(null);
    (async () => {
      try {
        const d = (await api.get(
          `/novels/${projectId}/volumes/plan-anchor?vol_no=${volNo}`,
        )) as { prev_ending?: { text?: string; source?: string } };
        if (alive)
          setAnchor({
            text: d?.prev_ending?.text ?? "",
            source: d?.prev_ending?.source ?? "",
          });
      } catch {
        if (alive) setAnchor({ text: "（取不到上一卷的记录）", source: "" });
      }
    })();
    return () => {
      alive = false;
    };
  }, [projectId, volNo, active]);
  return anchor;
}

export function VolumePlanModal({
  projectId,
  plan,
  isPro,
  onUpgrade,
  volumes,
  genreLabel,
  onBackfill,
  onClose,
  onGoSettings,
}: {
  projectId: string;
  plan: VolumePlanController;
  isPro: boolean;
  onUpgrade: () => void;
  volumes: WorkbenchVolume[];
  genreLabel: string;
  /** 点「回填 →」：外层关弹窗并开始中栏逐段回填 */
  onBackfill: () => void;
  onClose: () => void;
  /** 点分卷依据行：回设定页（原型 data-act="dep"） */
  onGoSettings?: () => void;
}) {
  const { state, setLine, generateOptions, generateExpand, adoptPlan, resetError } = plan;
  const deps = useDeps(projectId, state.open, volumes, genreLabel);
  const anchor = useAnchor(projectId, state.volNo, state.open);
  const first = state.volNo <= 1;
  const cn = cnNum(state.volNo);

  useEffect(() => {
    if (!state.open) resetError();
  }, [state.open, resetError]);

  const genExpandBusy = state.phase === "generating" && state.mode === "expand";
  const genDone =
    state.phase === "done" && state.mode === "expand" && !!state.draft && !state.degradedText;
  const showDesk = !genExpandBusy && !genDone;

  return (
    <Modal
      open={state.open}
      onClose={onClose}
      title={`规划第${cn}卷`}
      width={680}
      wbStyle
    >
      <div className="plan-modal" data-testid="volume-plan-modal">
        <p className="kicker">分卷规划 · 第{cn}卷</p>

        {/* 锚点块：引导语 ＋ 进场（上一卷结尾／全景起步）＋ 首卷卷数估计 */}
        <div className="plan-anchor">
          <p className="pa-lead">
            {first
              ? `规划第${cn}卷，从全景的起步开始——本卷讲什么、收在哪里。`
              : `规划第${cn}卷，就是接着第${cnNum(state.volNo - 1)}卷的结尾往下写——本卷讲什么、收在哪里。`}
          </p>
          <div className="pa-row">
            <span className="pa-k">{first ? "起点" : "上一卷的结尾"}</span>
            <span className="pa-v">
              {anchor?.text || "…"}
              {anchor?.source ? <span className="pa-src">{anchor.source}</span> : null}
            </span>
          </div>
          {first && (
            <div className="pa-row">
              <span className="pa-k">卷数</span>
              <span className="pa-v">
                {state.volumeEstimate ? (
                  <>
                    {state.volumeEstimate}——只是假设，拆到哪一卷都行。
                  </>
                ) : (
                  <>还没估——点「给我 3 套方案」时会按你的结局估给你（只是假设）。</>
                )}
              </span>
            </div>
          )}
        </div>

        {/* 分卷依据 · 来自你的设定（可折叠；点行回设定） */}
        <details className="cfgset">
          <summary>
            分卷依据 · 来自你的设定 <span className="note">全书结局也在这儿，只作参照</span>
          </summary>
          <div data-testid="plan-basis">
            {deps.map((d) => (
              <button
                className="dep-row"
                key={d.k}
                onClick={() => {
                  if (onGoSettings) {
                    onClose();
                    onGoSettings();
                  }
                }}
              >
                <span className="dep-k">{d.k}</span>
                <span className="dep-v">{d.v}</span>
                <span className={`dep-s ${d.cls}`}>{d.s}</span>
              </button>
            ))}
          </div>
        </details>

        {/* 台面：写一句（idle / options 结果）或 genbox（展开生成中/完成） */}
        {showDesk ? (
          <div className="plan-desk">
            <span className="plan-label">
              这一卷想看什么？ <span className="note">可写可不写——写了就按你的来</span>
            </span>
            <textarea
              className="textarea"
              rows={3}
              maxLength={150}
              spellCheck={false}
              data-testid="plan-line-input"
              placeholder={
                first
                  ? "例：她为追信号把坐标押给船队，欠下一条命——这一卷以她第一次主动骗人收尾"
                  : "一句话说清：谁想干什么、被什么拦住、最后落到哪"
              }
              value={state.line}
              onChange={(e) => setLine(e.target.value)}
            />
            <div className="plan-desk-acts">
              <button
                className="btn btn-primary"
                data-testid="plan-expand-btn"
                disabled={!isPro || !state.line.trim() || state.error.includes("主线")}
                onClick={() => void generateExpand()}
              >
                按这一句展开
              </button>
              <button
                className="btn btn-secondary"
                data-testid="plan-options-btn"
                disabled={!isPro}
                onClick={() => void generateOptions()}
              >
                给我 3 套方案
              </button>
              <span className="push">
                {isPro ? (
                  "走向由你定——AI 不替你改"
                ) : (
                  <>
                    <span className="pill-pro">PRO</span>
                    <span>生成需 PRO；依据、体检与手写不受限</span>
                    <button className="btn btn-ghost btn-sm" onClick={onUpgrade}>
                      了解升级
                    </button>
                  </>
                )}
              </span>
            </div>
            <p className="hint">
              3 套都忠于全书主线、世界观、核心人物和终极目标——不同的只是中间走向、冲突和侧重点。
            </p>

            {state.error && (
              <p className="ai-note" style={{ color: "var(--warn)" }} data-testid="plan-error">
                {state.error}
                {state.error.includes("主线") && "（回到设定 → 主线）"}
              </p>
            )}

            {/* 3 套可行走法（options 生成后摊开在台面下） */}
            {state.phase === "generating" && state.mode === "options" && (
              <div className="plans" data-testid="plan-options">
                <p className="plans-h">正在想 3 套可行走法…</p>
                <p className="ai-note">
                  <span className="ra-spin" aria-hidden="true" />
                  都按你的全书设定和上一卷的结尾推，只在中间走向、冲突和侧重点上不同。
                </p>
              </div>
            )}
            {state.phase === "done" &&
              state.mode === "options" &&
              state.plans.length > 0 &&
              !state.degradedText && (
                <div className="plans" data-testid="plan-options">
                  <p className="plans-h">3 套可行走法 · 都忠于全书设定与上一卷的结尾</p>
                  <div className="cand-list">
                    {state.plans.map((p) => (
                      <div className="cand" data-testid={`plan-card-${p.no}`} key={p.no}>
                        <p className="cand-dir">
                          <span className="cand-k">
                            方案{p.no}·{p.focus_axis}
                          </span>
                          {p.spine}
                        </p>
                        <p className="cand-line">
                          <b>冲突</b>
                          <span>{p.conflict || "（见展开）"}</span>
                        </p>
                        <p className="cand-line">
                          <b>卷末</b>
                          <span>{p.ending}</span>
                        </p>
                        <p className="cand-line">
                          <b>侧重</b>
                          <span>{p.focus}</span>
                        </p>
                        <div className="cand-foot">
                          <span className="note">选它 → 展开这一卷的卷纲，可改</span>
                          <button
                            className="btn btn-sm btn-primary"
                            onClick={() => adoptPlan(p)}
                          >
                            选它
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                  {state.similar && (
                    <p className="ai-note">有两套走向偏像——不满意可重新生成。</p>
                  )}
                  {state.warnings.length > 0 && (
                    <ul className="rp-list" data-testid="plan-warnings" style={{ marginTop: 8 }}>
                      {state.warnings.map((w) => (
                        <li className="rp-row warn" key={w}>
                          <span className="rp-dot" aria-hidden="true" />
                          <span className="rp-tx">{w}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                  {state.note && state.plans.length < 3 && (
                    <p className="ai-note">为什么只有两套：{state.note}</p>
                  )}
                </div>
              )}
            {state.phase === "done" && state.degradedText && (
              <div data-testid="plan-degraded" className="plans">
                <p className="plans-h">AI 的输出没法结构化</p>
                <p className="ai-note">{state.degradedText}</p>
                <p className="ai-note">{state.hint || "可重试，或按上面这段手动定走向"}</p>
              </div>
            )}

            {/* 七条规则（作家语言；可折叠） */}
            <details className="cfgset">
              <summary>展开时遵守的规则 · 每卷都带上</summary>
              <ul className="rp-list">
                {RULES_FOR_AUTHOR.map((r) => (
                  <li className="rp-row" key={r}>
                    <span className="rp-dot" aria-hidden="true" />
                    <span className="rp-tx">{r}</span>
                  </li>
                ))}
              </ul>
              <p className="ai-note" style={{ marginTop: 10 }}>
                每次展开都守着这七条；「卷纲体检」也是照它们复核。
              </p>
            </details>
          </div>
        ) : (
          <>
            {genExpandBusy && (
              <div className="genbox" data-testid="plan-generating">
                <p className="gen-k">正在展开第{cn}卷</p>
                <p className="gen-t">
                  按{state.line && state.plans.length > 0 ? "选的那一套走法" : "你写的那一句"}
                  ，把这一卷的卷纲填起来——冲突、卷末、埋与揭，最后自己先过一遍。
                </p>
                <div className="ex-bar">
                  <i
                    style={{
                      width: `${Math.round(((state.step + 1) / GEN_STEPS.length) * 100)}%`,
                    }}
                  />
                </div>
                <ul className="ex-steps">
                  {GEN_STEPS.map((s, i) => (
                    <li key={s}>
                      <span>{s}</span>
                      {i < state.step ? (
                        <em className="ok">✓ 完成</em>
                      ) : i === state.step ? (
                        <em>
                          <span className="ra-spin" aria-hidden="true" />
                          进行中
                        </em>
                      ) : (
                        <em>排队中</em>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {genDone && (
              <div className="genbox" data-testid="plan-done">
                <p className="gen-k">第{cn}卷的卷纲已备好</p>
                <p className="gen-t">
                  {state.draft!.name?.trim() || "（卷名待定）"} · 建议{" "}
                  {state.draft!.chapter_target > 0 ? state.draft!.chapter_target : "—"} 章 ·
                  自查 {state.draft!.checks.length} 处要留意。点「回填」，它会一条条写进中栏的卷纲表单——你改完再保存。
                </p>
                <ul className="ex-steps">
                  {GEN_STEPS.map((s) => (
                    <li key={s}>
                      <span>{s}</span>
                      <em className="ok">✓ 完成</em>
                    </li>
                  ))}
                </ul>
                {state.warnings.length > 0 && (
                  <ul className="rp-list" data-testid="plan-warnings" style={{ marginTop: 10 }}>
                    {state.warnings.map((w) => (
                      <li className="rp-row warn" key={w}>
                        <span className="rp-dot" aria-hidden="true" />
                        <span className="rp-tx">{w}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </>
        )}

        {/* 底条：先不规划 / 生成中关掉（后台继续跑）/ 回填 → */}
        <div className="plan-foot">
          {genDone ? (
            <>
              <span className="note">点「回填」，卷纲会在中栏一条条落下来</span>
              <button
                className="btn btn-sm btn-primary"
                data-testid="plan-backfill-btn"
                onClick={onBackfill}
              >
                回填 →
              </button>
            </>
          ) : genExpandBusy ? (
            <>
              <span className="note">生成在后台跑，关掉它也不影响</span>
              <button className="btn btn-sm btn-secondary" onClick={onClose}>
                关掉
              </button>
            </>
          ) : (
            <>
              <span className="note">
                规划台里的东西不会自己进书；卷名最后起；卷与卷之间留着没写到的部分，是正常的。
              </span>
              <button className="btn btn-sm btn-secondary" onClick={onClose}>
                先不规划
              </button>
            </>
          )}
        </div>
      </div>
    </Modal>
  );
}
