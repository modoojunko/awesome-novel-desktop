// 章剧情三版抽卡（c-plot-split）：一次请求出 3 版候选，代际守卫照 useChapterPlan
// 先例——换一批/再试一次都换代（上一批候选作废、清选中），关窗也换代（晚到响应丢弃、
// 绝不落表）。采纳/撤销语义不在此层：弹层把选中版交给上层，上层拿当前列表快照替换。
import { useCallback, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";

export interface PlotDrawState {
  open: boolean;
  phase: "busy" | "cards" | "error";
  /** 3 版候选，每版＝一套条目（首条接进场、末条收章末落点，三版共用首尾） */
  versions: string[][];
  /** 与 versions 对位的 S/A/B 角标（空串＝模型没给名次，不出角标） */
  grades: string[];
  warnings: string[];
  /** 选中版下标（单选；换一批即清空） */
  pick: number | null;
}

const INITIAL: PlotDrawState = {
  open: false,
  phase: "busy",
  versions: [],
  grades: [],
  warnings: [],
  pick: null,
};

export interface PlotDrawController {
  state: PlotDrawState;
  /** 打开并开抽（忙碌态起手）。wordTarget＝章纲表单「本章目标字数」现值
   *（c-scene-density 联动：随请求直发，素材建议条数与页面显示同一数）——
   * 传 number＝设为本批字数；传 null＝清空（请求体不带键，服务端回退存值链）。
   * 勿裸绑 onClick：防线在被调方 typeof 守卫，事件会静默丢弃（评审阻断修） */
  openDraw: (wordTarget?: number | null) => void;
  /** 换一批 / 再试一次：作废上一批候选后重抽（沿用开抽时设的字数，不接受事件参数） */
  redraw: () => void;
  /** 关窗：换代丢晚到响应 */
  close: () => void;
  pickCard: (i: number) => void;
}

export function usePlotDraw(projectId: string, chapterRef: string): PlotDrawController {
  const [state, setState] = useState<PlotDrawState>(INITIAL);
  // 代际守卫：换一批/关窗/重抽都换代，晚到响应凭 token 不相等丢弃
  const genRef = useRef(0);
  // 开抽时携带的表单字数（c-scene-density）：换一批沿用，不重读表单
  const wtRef = useRef<number | null>(null);

  const draw = useCallback(
    (wordTarget?: number | null) => {
      // typeof 守卫（评审阻断修）：裸绑 onClick 时 MouseEvent 会当首参进来污染 wtRef
      // ——「换一批/再试一次」会把事件对象当字数发给后端（422 必挂）。防线设在被调方：
      // 只认 number/null，其余（事件、undefined）一概不动 wtRef。
      if (typeof wordTarget === "number" || wordTarget === null) {
        wtRef.current = wordTarget;
      }
      const gen = ++genRef.current;
      setState((s) => ({ ...s, open: true, phase: "busy", versions: [], grades: [], warnings: [], pick: null }));
      void (async () => {
        try {
          const r = (await api.post(
            `/novels/${projectId}/chapters/${chapterRef}/plot/ai-draw`,
            wtRef.current != null ? { word_target: wtRef.current } : {},
          )) as {
          ok?: boolean;
          versions?: Array<{ items?: unknown }>;
          grades?: unknown[];
          warnings?: unknown[];
        };
        if (gen !== genRef.current) return; // 关窗/换一批后的晚到响应：丢
        const versions = (Array.isArray(r?.versions) ? r.versions : [])
          .map((v) => (Array.isArray(v?.items) ? v.items.map((x) => String(x)) : []))
          .filter((items) => items.length > 0);
        // 拍板⑤：必须凑满 3 版，凑不满＝本次失败，绝不给 2 版将就挑
        if (!r?.ok || versions.length < 3) {
          setState((s) => ({ ...s, phase: "error" }));
          return;
        }
        setState((s) => ({
          ...s,
          phase: "cards",
          versions: versions.slice(0, 3),
          grades: [0, 1, 2].map((i) => {
            const g = Array.isArray(r?.grades) ? String(r.grades[i] ?? "") : "";
            return g === "S" || g === "A" || g === "B" ? g : "";
          }),
          warnings: (Array.isArray(r?.warnings) ? r.warnings : []).map((w) => String(w)),
        }));
      } catch {
        if (gen !== genRef.current) return;
        setState((s) => ({ ...s, phase: "error" }));
      }
    })();
  }, [projectId, chapterRef]);

  const close = useCallback(() => {
    genRef.current++; // 换代：晚到响应不再落表
    setState((s) => ({ ...s, open: false, pick: null }));
  }, []);

  const pickCard = useCallback((i: number) => {
    setState((s) => ({ ...s, pick: i }));
  }, []);

  // 控制器对象 memo 化：消费方（ChapterWorkspace 的 onRailData effect）把它当依赖，
  // 每渲染新对象会引发「setState→重渲→依赖变」循环（e2e 真栈暴露，vitest 打桩不触发）
  return useMemo(
    () => ({
      state,
      openDraw: draw,
      // redraw 与 draw 拆开（评审阻断修）：无参转调＝只沿用 wtRef，永不会收到事件参数
      redraw: () => draw(),
      close,
      pickCard,
    }),
    [state, draw, close, pickCard],
  );
}
