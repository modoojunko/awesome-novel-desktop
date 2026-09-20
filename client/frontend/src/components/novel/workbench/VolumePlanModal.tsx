// VolumePlanModal — 规划台弹出页（volume-plan-ai）。
// 材料自上而下：引导语 → 进场（上一卷的结尾/全景起步）→ 卷数（估）→
// 分卷依据（可折叠，缺口标出不拦）→ 展开时遵守的规则（可折叠，作家语言）。
// 进度只在弹窗内呈现——「弹窗开着背景静止」：中栏/右栏不随生成变化。
// 免费档：规划台可进、材料可看、输入可写；「按这一句展开」「给我 3 套方案」禁用＋PRO 说明。
import { useEffect, useMemo, useState } from "react";
import Modal from "@/components/design/Modal";
import { api } from "@/lib/api";
import { GENRE_PENDING_LABEL } from "@/lib/genreVocab";
import type { WorkbenchVolume } from "@/hooks/useWorkbench";
import {
  GEN_STEPS,
  type VolumePlanController,
} from "@/hooks/useVolumePlan";

/** 分卷依据 · 来自你的设定（5 行；缺口标出、不拦） */
interface PlanMaterial {
  hasFullstory: boolean;
  hasEnding: boolean;
  hasGenre: boolean;
  characterCount: number | null;
  targetTotal: number | null;
}

function usePlanMaterial(
  projectId: string,
  active: boolean,
  volumes: WorkbenchVolume[],
): PlanMaterial {
  const [mat, setMat] = useState<PlanMaterial>({
    hasFullstory: false,
    hasEnding: false,
    hasGenre: false,
    characterCount: null,
    /* v8 ignore next -- 防御兜底：空数组/全 0 时回落「未设」（语义由缺口行覆盖） */
    targetTotal: volumes.reduce((a, v) => a + (v.chapter_target ?? 0), 0) || null,
  });
  useEffect(() => {
    if (!active || !projectId) return;
    let alive = true;
    (async () => {
      try {
        const arc = await api.fetchStoryArc(projectId);
        const full = String(arc?.fullstory ?? "").trim();
        const e = arc?.ending ?? {};
        const chars = await api.get(`/novels/${projectId}/characters`);
        const items = (chars as { items?: unknown[] })?.items ?? [];
        if (alive) {
          setMat((m) => ({
            ...m,
            hasFullstory: !!full,
            hasEnding: !!(e?.scene || e?.hero || e?.tone),
            characterCount: Array.isArray(items) ? items.length : null,
          }));
        }
      } catch {
        /* 材料缺口只标出、不拦 */
      }
    })();
    return () => {
      alive = false;
    };
  }, [projectId, active]);
  return mat;
}

function MaterialRows({ mat }: { mat: PlanMaterial }) {
  const rows: Array<[string, string, boolean]> = [
    ["主线全景", mat.hasFullstory ? "已填" : "缺口 · 先去设定补主线", mat.hasFullstory],
    ["结局三问", mat.hasEnding ? "已填" : "缺口 · 只作参照，不拦拆卷", mat.hasEnding],
    ["题材阶段", mat.hasGenre ? "已定" : "待定（不拦）", mat.hasGenre],
    [
      "主要角色",
      mat.characterCount ? `${mat.characterCount} 人` : "还没有角色卡（不拦）",
      !!mat.characterCount,
    ],
    [
      "目标篇幅",
      mat.targetTotal ? `已排卷合计约 ${mat.targetTotal} 章` : "未设（可不设）",
      !!mat.targetTotal,
    ],
  ];
  return (
    <ul className="pv-mat">
      {rows.map(([k, v, ok]) => (
        <li key={k}>
          <span className="k">{k}</span>
          <span className={ok ? "v ok" : "v gap"}>{v}</span>
        </li>
      ))}
    </ul>
  );
}

/** 界面七条＝作家语言的有意改写（与提示词文本不同源，workbench delta 口径） */
const RULES_FOR_AUTHOR = [
  "不凭空添人添事——只用你设定里出现过的人物、势力、事件、地点",
  "接着上一卷的结尾往下写，不跳空（第一卷从全景的起步开始）",
  "本卷要解决的事，是主线走到这一步该解决的——不另开一条线",
  "卷末给读者一个交代，把故事朝你写的结局推近一步",
  "不跟设定打架：人物性格、世界规矩、已经埋下的伏笔",
  "伏笔不重复埋、不提前揭；埋下的写清打算哪一卷收",
  "只铺结构，不改你那句话——有张力的地方写进自查条",
];

export function VolumePlanModal({
  projectId,
  plan,
  isPro,
  onUpgrade,
  volumes,
  genreLabel,
  onBackfill,
  onClose,
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
}) {
  const { state, setLine, generateOptions, generateExpand, adoptPlan, resetError } = plan;
  const mat = usePlanMaterial(projectId, state.open, volumes);
  const [showRules, setShowRules] = useState(false);
  const first = state.volNo <= 1;
  const lead = first
    ? "从全景的起步开始——第一卷讲什么、收在哪里？"
    : `规划第${state.volNo}卷，就是接着第${state.volNo - 1}卷的结尾往下写——本卷讲什么、收在哪里？`;
  const genLabel = useMemo(
    () => GEN_STEPS[Math.min(state.step, GEN_STEPS.length - 1)],
    [state.step],
  );

  useEffect(() => {
    if (!state.open) resetError();
  }, [state.open, resetError]);

  return (
    <Modal
      open={state.open}
      onClose={onClose}
      title={`规划第${state.volNo}卷（AI）`}
      width={520}
      wbStyle
    >
      <div className="vp-modal" data-testid="volume-plan-modal">
        <p className="pv-lead">{lead}</p>

        {state.phase === "generating" ? (
          <div className="pv-gen" data-testid="plan-generating">
            <p className="pv-gen-t">生成中…</p>
            <ol className="pv-gen-steps">
              {GEN_STEPS.map((s, i) => (
                <li key={s} className={i <= state.step ? "on" : ""}>
                  {s}
                </li>
              ))}
            </ol>
          </div>
        ) : state.phase === "done" && state.degradedText ? (
          <div className="pv-degraded" data-testid="plan-degraded">
            <p className="pv-degraded-t">AI 没能给出结构化的结果</p>
            <p className="pv-degraded-x">{state.degradedText}</p>
            <p className="none">{state.hint || "可重试，或按上面这段手动定走向"}</p>
          </div>
        ) : state.phase === "done" && state.plans.length > 0 ? (
          <div data-testid="plan-options">
            <p className="pv-guarantee">
              3 套都忠于全书主线、世界观、核心人物和终极目标——不同的只是中间走向、冲突和侧重点。
            </p>
            {state.volumeEstimate && (
              <p className="none">卷数（按结局估的，只是假设）：{state.volumeEstimate}</p>
            )}
            <div className="pv-cards">
              {state.plans.map((p) => (
                <button
                  key={p.no}
                  className="pv-card"
                  data-testid={`plan-card-${p.no}`}
                  onClick={() => adoptPlan(p)}
                  title="选这一套：填回输入框并直接展开"
                >
                  <span className="pv-card-no">方案 {p.no} · {p.focus_axis}</span>
                  <span className="pv-card-row"><em>走向</em>{p.spine}</span>
                  <span className="pv-card-row"><em>冲突</em>{p.conflict}</span>
                  <span className="pv-card-row"><em>卷末</em>{p.ending}</span>
                  <span className="pv-card-row"><em>侧重</em>{p.focus}</span>
                </button>
              ))}
            </div>
            {state.similar && (
              <p className="none">有两套走向偏像——不满意可重新生成。</p>
            )}
            {state.warnings.length > 0 && (
              <ul className="pv-warn" data-testid="plan-warnings">
                {state.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            )}
            {state.note && state.plans.length < 3 && (
              <p className="none">为什么只有两套：{state.note}</p>
            )}
          </div>
        ) : state.phase === "done" && state.draft ? (
          <div data-testid="plan-done">
            <p className="pv-done-t">
              生成完成 · {state.draft.name || `第${state.volNo}卷`} · 建议章数{" "}
              {state.draft.chapter_target > 0 ? state.draft.chapter_target : "不设"} · 自查{" "}
              {state.draft.checks.length} 条
            </p>
            {state.draft.checks.length > 0 && (
              <ul className="pv-checks">
                {state.draft.checks.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            )}
            {state.warnings.length > 0 && (
              <ul className="pv-warn">
                {state.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            )}
            <p className="none">回填不会自动保存——填好后你改完再点「保存卷纲」。</p>
          </div>
        ) : (
          <>
            <label className="pv-line">
              <em>这一卷想看什么？（可写可不写；写了就以它为准）</em>
              <textarea
                className="textarea"
                rows={2}
                maxLength={150}
                data-testid="plan-line-input"
                placeholder="例：林野为查身世，跟旧贵族做交易拿情报，代价是替他们清掉一个叛徒"
                value={state.line}
                onChange={(e) => setLine(e.target.value)}
              />
            </label>
            <div className="pv-acts">
              <button
                className="btn btn-primary"
                data-testid="plan-expand-btn"
                disabled={!isPro || !state.line.trim() || state.error.includes("主线")}
                title={isPro ? undefined : "生成类是 PRO 功能——升级后可用"}
                onClick={() => void generateExpand()}
              >
                按这一句展开
              </button>
              <button
                className="btn btn-secondary"
                data-testid="plan-options-btn"
                disabled={!isPro}
                title={isPro ? undefined : "生成类是 PRO 功能——升级后可用"}
                onClick={() => void generateOptions()}
              >
                给我 3 套方案
              </button>
              {!isPro && (
                <span className="pv-pro-note">
                  生成类是 PRO 功能
                  <button className="btn btn-ghost btn-sm" onClick={onUpgrade}>
                    了解升级
                  </button>
                </span>
              )}
            </div>
            {state.error && (
              <p className="pv-error" data-testid="plan-error">
                {state.error}
                {state.error.includes("主线") && "（回到设定 → 主线）"}
              </p>
            )}
          </>
        )}

        {/* 生成完成（展开）态的回填动作 */}
        {state.phase === "done" && state.draft && !state.degradedText && (
          <div className="pv-backfill-bar">
            <button
              className="btn btn-primary"
              data-testid="plan-backfill-btn"
              onClick={onBackfill}
            >
              回填 →
            </button>
            <span className="none">弹窗关闭后，卷纲表单会逐段落下</span>
          </div>
        )}

        <details className="cfg" open={false}>
          <summary>分卷依据 · 来自你的设定</summary>
          <MaterialRows mat={{ ...mat, hasGenre: !!genreLabel && genreLabel !== GENRE_PENDING_LABEL }} />
        </details>
        <details className="cfg" open={showRules}>
          <summary>展开时遵守的规则（七条）</summary>
          <ol className="pv-rules">
            {RULES_FOR_AUTHOR.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ol>
        </details>
      </div>
    </Modal>
  );
}
