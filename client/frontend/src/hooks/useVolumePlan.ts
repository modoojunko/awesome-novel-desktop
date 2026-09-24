// useVolumePlan — 分卷规划状态机（c-volume-antagonist 终版，挂 NovelWorkspace 壳层）。
// 双路：付费＝三选一抽卡（打开即出卡、选中确认成卷——token 守卫可取消）；免费＝四问手写页。
// 四问已答 answers 跨弹窗互切保留，作 options/expand 约束（作家答过的不被改写）。
import { useCallback, useRef, useState } from "react";
import { track } from "@/lib/metrics";
import {
  EMPTY_ANSWERS,
  volumePlanApi,
  type PlanAnswers,
  type VolumeExpandDraft,
  type VolumePlanCard,
} from "@/lib/volumePlanApi";
import { appendExclude, clearDraw, drawKey, loadDraw, saveDraw, type DrawExcludeItem } from "@/lib/drawSession";

export type { VolumePlanCard };

export const GEN_STEPS = ["读主线与结局", "对齐题材节奏", "展开剧情层", "自查"] as const;

export type PickPhase = "idle" | "busy" | "error";
export type DeskPhase = "idle" | "generating" | "done";

export interface VolumePlanState {
  /** 抽卡弹窗（付费默认路径） */
  /** 入口来源（用户 2026-09-22）："manual"＝加号手动入口（手写页不出现任何 AI 动作）；
   *  "ai"＝右栏 AI 入口（手写页保留「让 AI 铺完剩下的问题」） */
  openMode: "ai" | "manual";
  pickOpen: boolean;
  pickPhase: PickPhase;
  pickError: string;
  plans: VolumePlanCard[];
  note: string;
  pickPick: number | null; // 选中卡 no
  confirming: boolean;
  /** 确认结果（落库后交外层：落点卡/自查条） */
  confirmResult: {
    volNo: number;
    draft: VolumeExpandDraft;
    warnings: string[];
  } | null;
  /** 四问手写页 */
  deskOpen: boolean;
  deskPhase: DeskPhase;
  answers: PlanAnswers;
  draft: VolumeExpandDraft | null;
  deskWarnings: string[];
  degradedText: string;
  hint: string;
  error: string;
  volNo: number;
  /** 手写路自动回填信号 */
  autoBackfill: boolean;
  /** 重抽排除清单（c-plan-draw-exclude）：跟目标卷走，SHALL NOT 落库 */
  exclude: DrawExcludeItem[];
}

const INITIAL: VolumePlanState = {
  openMode: "ai",
  pickOpen: false, pickPhase: "idle", pickError: "", plans: [], note: "",
  pickPick: null, confirming: false, confirmResult: null,
  deskOpen: false, deskPhase: "idle", answers: { ...EMPTY_ANSWERS },
  draft: null, deskWarnings: [], degradedText: "", hint: "", error: "",
  volNo: 1, autoBackfill: false, exclude: [],
};

export function useVolumePlan(projectId: string) {
  const [state, setState] = useState<VolumePlanState>(INITIAL);
  const tokenRef = useRef(0);
  const consumedRef = useRef(false);
  const answersRef = useRef<PlanAnswers>({ ...EMPTY_ANSWERS });
  answersRef.current = state.answers;
  const pickPickRef = useRef<number | null>(null);
  pickPickRef.current = state.pickPick;
  // 排除清单（c-plan-draw-exclude）：ref 供异步流程读写，state 供 UI/测试观察
  const excludeRef = useRef<DrawExcludeItem[]>([]);
  const stateRef = useRef(state);
  stateRef.current = state;
  const answersNow = () => answersRef.current;

  const nextToken = () => ++tokenRef.current;
  const cancelPending = () => { nextToken(); };

  /** 打开规划（统一入口）：付费出抽卡（自动拉卡）、免费出四问页 */
  const open = useCallback(
    (volNo: number, isPro: boolean, mode: "ai" | "manual" = "ai") => {
      consumedRef.current = false;
      // 开新一轮＝丢弃在飞请求（P3）：否则上一轮慢 expand 回来会置 done+autoBackfill，
      // 自动回填拿本轮 volNo 去建卷 → 把上一卷的卷纲写到这一卷上
      cancelPending();
      // 入口分叉（用户 2026-09-22 拍板）：手动入口（各处「＋ 新增一卷」）恒进**四问手写页**，
      // 让作家填空；三选一抽卡只从 AI 入口（右栏「规划第N卷（AI）」）进，并按档分流。
      const toPick = mode === "ai" && isPro;
      if (toPick) {
        const cur = stateRef.current;
        // 恢复①内存批：同卷号且存在未消费批（误关重开）——不重抽、不重复计量
        if (cur.volNo === volNo && cur.plans.length > 0 && cur.pickPhase === "idle") {
          // 恢复批次，但一次性载荷（落点/回填）不得复活
          setState((s) => ({ ...s, volNo, openMode: mode, pickOpen: true, confirmResult: null, autoBackfill: false }));
          return;
        }
        // 恢复②localStorage（页面刷新兜底）
        const stored = loadDraw<{ v: number; plans: VolumePlanCard[]; note: string; exclude: DrawExcludeItem[] }>(
          drawKey.volume(projectId, volNo));
        if (stored?.plans?.length) {
          excludeRef.current = stored.exclude ?? [];
          setState({
            ...INITIAL, volNo, openMode: mode, pickOpen: true,
            plans: stored.plans, note: stored.note ?? "", exclude: stored.exclude ?? [],
          });
          return;
        }
        excludeRef.current = [];
      }
      setState({
        ...INITIAL, volNo, openMode: mode,
        ...(toPick ? { pickOpen: true } : { deskOpen: true }),
      });
      if (toPick) void drawCards();
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [projectId],
  );

  const drawCards = useCallback(async (kind: "first" | "redraw" | "fresh" = "first") => {
    const token = nextToken();
    if (kind === "redraw") {
      // 当前批并入排除清单（作者按「换 3 套」＝这批不要了）
      const batch = stateRef.current.plans
        .map((p) => ({ axis: p.focus_axis, line: p.spine }))
        .filter((x) => x.axis && x.line);
      excludeRef.current = appendExclude(excludeRef.current, batch);
    }
    if (kind === "fresh") excludeRef.current = [];
    track(kind === "redraw" ? "pick_redraw" : "pick_drawn");
    setState((s) => ({ ...s, exclude: [...excludeRef.current], pickPhase: "busy", pickError: "", pickPick: null }));
    try {
      const d = await volumePlanApi.options(projectId, answersNow(), excludeRef.current);
      if (token !== tokenRef.current) return;
      if (d.degraded) {
        setState((s) => ({ ...s, pickPhase: "error", pickError: d.hint || "AI 的输出没法结构化——可重试，或自己答四个问题" }));
        return;
      }
      saveDraw(drawKey.volume(projectId, stateRef.current.volNo), {
        v: 1, plans: d.plans ?? [], note: d.note ?? "", exclude: excludeRef.current,
      });
      setState((s) => ({ ...s, pickPhase: "idle", plans: d.plans ?? [], note: d.note ?? "" }));
    } catch (e) {
      if (token !== tokenRef.current) return;
      const msg = (e as { message?: string })?.message || "";
      setState((s) => ({
        ...s, pickPhase: "error",
        pickError: msg.includes("模型") || msg.includes("503")
          ? "还没接模型——先去模型配置里接一个，或者自己答四个问题"
          : msg || "出卡失败，可重试",
      }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const selectCard = useCallback((no: number) => {
    // 埋点放 updater 外：updater 必须是纯函数（StrictMode dev 下会被调用两次 → 记两条）
    const next = pickPickRef.current === no ? null : no;
    if (next != null) track("pick_select", { no });
    setState((s) => ({ ...s, pickPick: next }));
  }, []);

  /** 确认成卷：expand（卡面四问胜出）→ 外层回调落库 → 关弹窗（token 守卫可取消）。
   *  `onPersist` 返回 false ＝ 落库失败：不关弹窗、不置 confirmResult、保留选中与三卡
   *  （PRD §6「expand/建卷/hooks 失败：保留选中与卡片、toast 可重试」）。 */
  const confirmCard = useCallback(
    async (
      card: VolumePlanCard,
      onPersist: (draft: VolumeExpandDraft, warnings: string[]) => Promise<boolean>,
    ): Promise<boolean> => {
      const token = nextToken();
      setState((s) => ({ ...s, confirming: true }));
      try {
        const d = await volumePlanApi.expand(
          projectId,
          {
            q1: card.spine,
            conflict: card.conflict,
            antagonist_type: card.antagonist_type,
            antagonist_line: card.antagonist_line,
            q4: card.ending,
          },
          state.volNo,
        );
        if (token !== tokenRef.current) return false; // 已取消
        if (!d.draft) {
          track("pick_confirm_fail", { reason: "degraded" });
          setState((s) => ({ ...s, confirming: false, pickPhase: "error", pickError: d.hint || "铺稿失败，可重试" }));
          return false;
        }
        const persisted = await onPersist(d.draft, d.warnings ?? []);
        if (token !== tokenRef.current) return false;
        if (!persisted) {
          track("pick_confirm_fail", { reason: "persist" });
          setState((s) => ({
            ...s, confirming: false, pickPhase: "error",
            pickError: "这一卷没落库（网络或服务异常）——选中还在，可重试确认",
          }));
          return false;
        }
        const done = d.draft;
        track("pick_confirm_ok", { vol_no: d.vol_no });
        // 成卷即清（c-plan-draw-exclude）：目标卷推进，抽卡会话与排除清单作废；
        // plans 一并清空——同卷再开规划＝全新一轮，不得「恢复」已成卷的旧批
        excludeRef.current = [];
        clearDraw(drawKey.volume(projectId, d.vol_no));
        setState((s) => ({
          ...s, confirming: false, pickOpen: false, exclude: [], plans: [],
          confirmResult: { volNo: d.vol_no, draft: done, warnings: d.warnings ?? [] },
        }));
        return true;
      } catch (e) {
        if (token !== tokenRef.current) return false;
        track("pick_confirm_fail", { reason: "error" });
        setState((s) => ({ ...s, confirming: false, pickError: (e as { message?: string })?.message || "确认失败，可重试" }));
        return false;
      }
      // eslint-disable-next-line react-hooks/exhaustive-deps
    },
    [projectId, state.volNo],
  );

  /** 取消（Esc/背景/关钮）：写请求发出前＝丢弃 pending；发出后由 confirming 锁 UI */
  const closePick = useCallback(() => {
    cancelPending();
    setState((s) => ({ ...s, pickOpen: false, confirming: false }));
  }, []);

  const toDesk = useCallback(() => {
    setState((s) => ({ ...s, pickOpen: false, deskOpen: true }));
  }, []);
  const closeDesk = useCallback(() => {
    setState((s) => ({ ...s, deskOpen: false }));
  }, []);

  const setAnswer = useCallback(<K extends keyof PlanAnswers>(key: K, value: string) => {
    setState((s) => ({ ...s, answers: { ...s.answers, [key]: value } }));
  }, []);

  /** 手写路：让 AI 铺完剩下的问题。
   *  四问取 answersNow()（ref 最新值）——闭包里的 state.answers 是首次渲染那份：
   *  本回调依赖只有 [projectId, state.volNo]，用户敲字期间不会重建，直接读闭包会发空答案，
   *  与「作家答过的它不改」（FR-5）正好相反。 */
  const expandDesk = useCallback(async () => {
    const token = nextToken();
    track("desk_expand", { vol_no: state.volNo });
    setState((s) => ({ ...s, deskPhase: "generating", error: "", degradedText: "" }));
    try {
      const d = await volumePlanApi.expand(projectId, answersNow(), state.volNo);
      if (token !== tokenRef.current) return;
      consumedRef.current = false;
      if (!d.draft) {
        setState((s) => ({ ...s, deskPhase: "idle", degradedText: d.text ?? "", hint: d.hint ?? "" }));
        return;
      }
      const fin = d.draft;
      setState((s) => ({
        ...s, deskPhase: "done", draft: fin,
        deskWarnings: d.warnings ?? [], autoBackfill: true,
      }));
    } catch (e) {
      if (token !== tokenRef.current) return;
      const msg = (e as { message?: string })?.message || "";
      setState((s) => ({
        ...s, deskPhase: "idle",
        error: msg.includes("主线") ? "主线还是空的——先到设定补主线，再回来拆卷" : msg || "生成失败，请重试",
      }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, state.volNo]);

  const takeAutoBackfill = useCallback(() => {
    if (consumedRef.current) return null;
    if (!state.autoBackfill || !state.draft) return null;
    consumedRef.current = true;
    setState((s) => ({ ...s, autoBackfill: false }));
    return { volNo: state.volNo, draft: state.draft };
  }, [state.autoBackfill, state.draft, state.volNo]);

  const consumeConfirm = useCallback(() => {
    const r = state.confirmResult;
    if (r) setState((s) => ({ ...s, confirmResult: null }));
    return r;
  }, [state.confirmResult]);

  const resetError = useCallback(() => setState((s) => ({ ...s, error: "" })), []);

  return {
    state, open, drawCards, selectCard, confirmCard, closePick, toDesk,
    closeDesk, setAnswer, expandDesk, takeAutoBackfill, consumeConfirm, resetError,
  };
}

export type VolumePlanController = ReturnType<typeof useVolumePlan>;
