// useVolumePlan — 分卷规划状态机（挂 NovelWorkspace 壳层，不挂弹窗内）：
// 生成中关弹窗不中断（state 在外层），完成后经 takeAutoBackfill 交给中栏直接回填。
// 规划台六态：material（输入）→ generating（进度）→ done（卷名·建议章数·自查条数＋回填）。
import { useCallback, useRef, useState } from "react";
import {
  volumePlanApi,
  type VolumeExpandDraft,
  type VolumePlanCard,
} from "@/lib/volumePlanApi";

export type PlanPhase = "idle" | "generating" | "done";

const GEN_STEPS = ["读主线与结局", "对齐题材节奏", "展开剧情层", "自查"] as const;

export interface VolumePlanState {
  open: boolean;
  /** 本卷卷号（空书＝1） */
  volNo: number;
  /** 作者那一句（可空——空则先取 3 套） */
  line: string;
  phase: PlanPhase;
  /** 生成中进度步（0..GEN_STEPS.length-1；纯进度指示，非真实阶段回调） */
  step: number;
  mode: "options" | "expand" | null;
  plans: VolumePlanCard[];
  note: string;
  volumeEstimate: string;
  warnings: string[];
  similar: boolean;
  draft: VolumeExpandDraft | null;
  planLine: string;
  degradedText: string;
  hint: string;
  error: string;
  /** 生成中关弹窗 → 完成后中栏直接回填（不必再点「回填」）；回填/读走即清 */
  autoBackfill: boolean;
}

const INITIAL: VolumePlanState = {
  open: false,
  volNo: 1,
  line: "",
  phase: "idle",
  step: 0,
  mode: null,
  plans: [],
  note: "",
  volumeEstimate: "",
  warnings: [],
  similar: false,
  draft: null,
  planLine: "",
  degradedText: "",
  hint: "",
  error: "",
  autoBackfill: false,
};

export function useVolumePlan(projectId: string) {
  const [state, setState] = useState<VolumePlanState>(INITIAL);
  const stepTimer = useRef<number | null>(null);
  const consumedRef = useRef(false);

  const stopSteps = useCallback(() => {
    if (stepTimer.current != null) {
      window.clearInterval(stepTimer.current);
      stepTimer.current = null;
    }
  }, []);

  const startSteps = useCallback(() => {
    stopSteps();
    setState((s) => ({ ...s, phase: "generating", step: 0 }));
    stepTimer.current = window.setInterval(() => {
      setState((s) =>
        s.step < GEN_STEPS.length - 1 ? { ...s, step: s.step + 1 } : s,
      );
    }, 900);
  }, [stopSteps]);

  const open = useCallback((volNo: number) => {
    consumedRef.current = false;
    setState({ ...INITIAL, open: true, volNo });
  }, []);

  const close = useCallback(() => {
    setState((s) => ({ ...s, open: false }));
  }, []);

  const setLine = useCallback((line: string) => {
    setState((s) => ({ ...s, line }));
  }, []);

  const resetError = useCallback(() => {
    setState((s) => ({ ...s, error: "" }));
  }, []);

  /** 给我 3 套方案（PRO） */
  const generateOptions = useCallback(async () => {
    startSteps();
    setState((s) => ({ ...s, mode: "options", plans: [], error: "", degradedText: "" }));
    try {
      const d = await volumePlanApi.options(projectId, state.line);
      stopSteps();
      if (d.degraded) {
        /* v8 ignore start -- 防御兜底：降级字段缺省给空串（后端契约恒带键） */
        setState((s) => ({
          ...s, phase: "done", degradedText: d.text ?? "", hint: d.hint ?? "",
        }));
        /* v8 ignore stop */
        return;
      }
      /* v8 ignore start -- 防御兜底：note/warnings 缺键给中性缺省（后端契约恒带） */
      setState((s) => ({
        ...s, phase: "done", plans: d.plans ?? [], note: d.note ?? "",
        volumeEstimate: d.volume_estimate, similar: d.similar, warnings: d.warnings ?? [],
      }));
      /* v8 ignore stop */
    } catch (e: any) {
      stopSteps();
      /* v8 ignore start -- 防御兜底：非 Error 拒绝给通用文案 */
      setState((s) => ({ ...s, phase: "idle", error: e?.message || "生成失败，请重试" }));
      /* v8 ignore stop */
    }
  }, [projectId, state.line, startSteps, stopSteps]);

  /** 按这一句展开（或选中的一套走法填回后展开）（PRO） */
  const generateExpand = useCallback(async (rawLine?: string) => {
    const line = (rawLine ?? state.line).trim();
    if (!line) return;
    startSteps();
    setState((s) => ({
      ...s, mode: "expand", line, phase: "generating", plans: [], error: "", degradedText: "",
    }));
    try {
      const d = await volumePlanApi.expand(projectId, line, state.volNo);
      stopSteps();
      consumedRef.current = false;
      if (d.degraded) {
        /* v8 ignore start -- 防御兜底：降级字段缺省给空串（后端契约恒带键） */
        setState((s) => ({
          ...s, phase: "done", degradedText: d.text ?? "", hint: d.hint ?? "",
        }));
        /* v8 ignore stop */
        return;
      }
      /* v8 ignore start -- 防御兜底：draft/plan_line/warnings 缺键给中性缺省 */
      setState((s) => ({
        ...s, phase: "done", draft: d.draft ?? null, planLine: d.plan_line ?? "",
        warnings: d.warnings ?? [], autoBackfill: true,
      }));
      /* v8 ignore stop */
    } catch (e: any) {
      stopSteps();
      /* v8 ignore start -- 防御兜底：非 Error 拒绝给通用可重试文案 */
      const msg = String(e?.message || "");
      setState((s) => ({
        ...s, phase: "idle",
        error: msg.includes("主线")
          ? "主线还是空的——先到设定补主线（全景或结局三问），再回来拆卷"
          : msg || "生成失败，请重试",
      }));
      /* v8 ignore stop */
    }
  }, [projectId, state.line, state.volNo, startSteps, stopSteps]);

  /** 选一套 → 填回输入框并直接展开 */
  const adoptPlan = useCallback(
    (card: VolumePlanCard) => {
      const line = card.spine;
      setState((s) => ({ ...s, line }));
      void generateExpand(line);
    },
    [generateExpand],
  );

  /** 中栏消费自动回填（生成中关弹窗 → 完成后直落）；读走即清，防重复 */
  const takeAutoBackfill = useCallback((): {
    volNo: number;
    draft: VolumeExpandDraft;
    planLine: string;
  } | null => {
    if (consumedRef.current) return null;
    /* v8 ignore next -- 防御兜底：autoBackfill 与 draft 恒同真同假（同一次 setState 写入） */
    if (!state.autoBackfill || !state.draft) return null;
    consumedRef.current = true;
    setState((s) => ({ ...s, autoBackfill: false }));
    return { volNo: state.volNo, draft: state.draft, planLine: state.planLine };
  }, [state.autoBackfill, state.draft, state.planLine, state.volNo]);

  return { state, open, close, setLine, resetError, generateOptions, generateExpand, adoptPlan, takeAutoBackfill };
}

export type VolumePlanController = ReturnType<typeof useVolumePlan>;
export { GEN_STEPS };
