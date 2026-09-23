// useChapterPlan — 拆章状态机（c-chapter-plan-ai；与 useVolumePlan 同构，不新造第二套模式）
// 双路：手写五段（中栏入口，全档）／AI 三方向（右栏入口，PRO）。
// AI 四态：idle｜busy｜error（三出口）；degraded 由出参 degraded 表达（只出两套）。
// token 守卫：busy 中关窗＝弃；submitting 中锁定（写请求在途，UI 锁＋服务端幂等双保险）。
import { useCallback, useRef, useState } from "react";
import {
  chapterPlanApi,
  type ChapterAdoptBody,
  type ChapterDirection,
  type ChapterDirectionsResult,
  type ChapterEntry,
} from "@/lib/chapterPlanApi";

export type PlanPhase = "idle" | "busy" | "error";
export type DraftStage =
  | "开局铺垫" | "冲突初现" | "矛盾升级" | "重要转折" | "高潮爆发" | "卷末收束";

export const STAGES: DraftStage[] = [
  "开局铺垫", "冲突初现", "矛盾升级", "重要转折", "高潮爆发", "卷末收束",
];

export interface ChapterDraft {
  title: string;
  plot: string;
  obstacle: string;
  ending: string;
  acts: string;
  stage: string;
  /** 来自 AI 卡（手写路为空）——角标与卡尾评语用 */
  grade?: string;
  why?: string;
  gap?: string;
  axis?: string;
}

export const EMPTY_DRAFT: ChapterDraft = {
  title: "", plot: "", obstacle: "", ending: "", acts: "", stage: "开局铺垫",
};

export interface ChapterPlanState {
  /** 打开路径：manual＝手写五段（中栏）｜ai＝三方向（右栏，PRO） */
  entrySource: "manual" | "ai";
  open: boolean;
  phase: PlanPhase;
  error: string;
  /** 排上写请求在途（Modal locked：Esc/遮罩/关闭钮失效） */
  submitting: boolean;
  /** 落点卡（排上成功后的桥） */
  landed: { ref: string; title: string; brought: number } | null;
  entry: ChapterEntry;
  directions: ChapterDirection[];
  grades: string[];
  checks: string[];
  note: string;
  warnings: string[];
  degradedText: string;
  pick: number | null;
  draft: ChapterDraft;
  /** 自检（手写卡底条触发；免费） */
  selfchecked: boolean;
  selfcheck: { critiques?: Record<string, string>; weakest?: string; failed?: boolean } | null;
  volNo: number;
  volRef: string;
}

const INITIAL = (volNo: number, volRef: string): ChapterPlanState => ({
  entrySource: "manual", open: false, phase: "idle", error: "", submitting: false,
  landed: null, entry: { text: "", source: "" }, directions: [], grades: [], checks: [],
  note: "", warnings: [], degradedText: "", pick: null, draft: { ...EMPTY_DRAFT },
  selfchecked: false, selfcheck: null, volNo, volRef,
});

export function useChapterPlan(projectId: string, volNo: number, volRef: string) {
  const [state, setState] = useState<ChapterPlanState>(() => INITIAL(volNo, volRef));
  const tokenRef = useRef(0);
  const nextToken = () => ++tokenRef.current;

  /** 打开：手写路直接空白五段；AI 路先拉进场再出卡（busy→idle/error） */
  const openManual = useCallback(() => {
    nextToken();
    setState((s) => ({ ...s, entrySource: "manual", open: true, phase: "idle", error: "",
      draft: { ...EMPTY_DRAFT }, pick: null, selfchecked: false, selfcheck: null, degradedText: "", warnings: [] }));
    void loadAnchor();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, volRef]);

  const openAi = useCallback(() => {
    nextToken();
    setState((s) => ({ ...s, entrySource: "ai", open: true, pick: null, checks: [],
      warnings: [], degradedText: "", selfchecked: false, selfcheck: null }));
    void draw();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, volRef]);

  const loadAnchor = useCallback(async () => {
    const token = nextToken();
    try {
      const d = await chapterPlanApi.anchor(projectId, volRef);
      if (token !== tokenRef.current) return;
      setState((s) => ({ ...s, entry: { text: d.text, source: d.source } }));
    } catch {
      if (token !== tokenRef.current) return;
      setState((s) => ({ ...s, entry: { text: "（进场读不到）", source: "" } }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, volRef]);

  const draw = useCallback(async () => {
    const token = nextToken();
    setState((s) => ({ ...s, phase: "busy", error: "" }));
    try {
      const d: ChapterDirectionsResult = await chapterPlanApi.directions(projectId, volRef);
      if (token !== tokenRef.current) return;
      if (d.degraded) {
        setState((s) => ({ ...s, phase: "error",
          error: d.hint || "出卡失败，可重试",
          degradedText: d.text || "" }));
        return;
      }
      setState((s) => ({ ...s, phase: "idle", entry: d.entry, directions: d.directions,
        grades: d.grades ?? [], checks: d.checks ?? [], note: d.note ?? "",
        warnings: d.warnings ?? [] }));
    } catch (e) {
      if (token !== tokenRef.current) return;
      const msg = (e as { message?: string })?.message || "";
      setState((s) => ({ ...s, phase: "error",
        error: msg.includes("模型") || msg.includes("503")
          ? "还没接模型——先去模型配置里接一个"
          : msg.includes("卷纲") ? msg : "出卡失败，可重试" }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, volRef]);

  /** 点卡：把卡面内容装进 draft 并进入本章卡（grade 供角标/卡尾） */
  const pickCard = useCallback((i: number) => {
    setState((s) => {
      const d = s.directions[i];
      if (!d) return s;
      return { ...s, pick: i, draft: {
        title: d.title, plot: d.plot, obstacle: d.obstacle, ending: d.ending,
        acts: d.acts.join("；"), stage: d.stage, grade: s.grades[i], why: d.why, gap: d.gap, axis: d.axis,
      } };
    });
  }, []);

  const patchDraft = useCallback((patch: Partial<ChapterDraft>) => {
    setState((s) => ({ ...s, draft: { ...s.draft, ...patch } }));
  }, []);

  /** 切手写（AI 失败出口之一；已填内容保留） */
  const toManual = useCallback(() => {
    nextToken();
    setState((s) => ({ ...s, entrySource: "manual", phase: "idle", error: "" }));
  }, []);

  /** 自检（手写卡底条；免费） */
  const runSelfcheck = useCallback(async (chapterRef: string) => {
    setState((s) => ({ ...s, selfchecked: true, selfcheck: null }));
    try {
      const d = await chapterPlanApi.selfcheck(projectId, chapterRef);
      setState((s) => ({ ...s, selfcheck: d.degraded ? { failed: true } : d }));
    } catch {
      setState((s) => ({ ...s, selfcheck: { failed: true } }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  /** 排上：建章＋五段（同一事务）；成功 → 关弹窗＋落点卡数据 */
  const adopt = useCallback(async (): Promise<{ ok: boolean; error?: string }> => {
    const d = state.draft;
    if (!d.title.trim() && !d.plot.trim()) {
      return { ok: false, error: "至少写个标题或一句「本章剧情」" };
    }
    const title = d.title.trim() || `第${state.directions.length ? "" : ""}章`;
    const body: ChapterAdoptBody = {
      title: title || "新章节",
      plot: d.plot.trim() || undefined,
      challenge: d.obstacle.trim() || undefined,
      ending: d.ending.trim() || undefined,
      acts: d.acts.split(/[；;\n]/).map((x) => x.trim()).filter(Boolean).slice(0, 4),
      stage: d.stage || undefined,
    };
    setState((s) => ({ ...s, submitting: true, error: "" }));
    try {
      const r = await chapterPlanApi.adopt(projectId, volRef, body);
      const brought = [d.plot, d.obstacle, d.ending, d.acts, d.stage].filter((x) => String(x || "").trim()).length;
      setState((s) => ({ ...s, submitting: false, open: false, landed: { ref: r.ref, title: body.title, brought } }));
      return { ok: true };
    } catch (e) {
      const msg = (e as { message?: string })?.message || "排上失败，可重试";
      setState((s) => ({ ...s, submitting: false, error: msg }));
      return { ok: false, error: msg };
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, volRef, state.draft]);

  /** 关窗（submitting 中由 Modal locked 挡住，这里兜底） */
  const close = useCallback(() => {
    nextToken();
    setState((s) => (s.submitting ? s : { ...s, open: false, phase: "idle", error: "" }));
  }, []);

  const consumeLanded = useCallback(() => {
    const l = state.landed;
    if (l) setState((s) => ({ ...s, landed: null }));
    return l;
  }, [state.landed]);

  return {
    state, openManual, openAi, draw, pickCard, patchDraft, toManual,
    runSelfcheck, adopt, close, consumeLanded,
  };
}

export type ChapterPlanController = ReturnType<typeof useChapterPlan>;
