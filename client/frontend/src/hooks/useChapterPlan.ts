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
  type DrawExcludeItem,
} from "@/lib/chapterPlanApi";
import { appendExclude, clearDraw, drawKey, loadDraw, saveDraw } from "@/lib/drawSession";

export type PlanPhase = "idle" | "busy" | "error";
export type DraftStage =
  | "开局铺垫" | "冲突初现" | "矛盾升级" | "重要转折" | "高潮爆发" | "卷末收束";

export const STAGES: DraftStage[] = [
  "开局铺垫", "冲突初现", "矛盾升级", "重要转折", "高潮爆发", "卷末收束",
];

/** 行动行展示拼接：剥每行行尾句读再以「；」相连——模型输出自带「。」时不出「。；」双标点 */
export const joinActs = (acts: string[]) =>
  acts.map((a) => a.replace(/[。;;．]+\s*$/u, "").trim()).filter(Boolean).join("；");

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
  landed: { ref: string; title: string; brought: number; items: string[] } | null;
  entry: ChapterEntry;
  directions: ChapterDirection[];
  grades: string[];
  checks: string[];
  note: string;
  warnings: string[];
  degradedText: string;
  pick: number | null;
  draft: ChapterDraft;
  /** 自检（手写卡底条触发；免费）——三组：衔接/配额（本地）＋剧情吸引力（AI 四维短评） */
  /** 下一章章号（服务端 anchor 单源；打开即取，标题/行号用） */
  nextNo: number;
  /** 回改目标（非空＝在改已有拟定章；排上按钮变「保存这一章」，不新建） */
  editing: string | null;
  /** 回改读卡是否成功装载（未装载不得提交——脏草稿守卫；手写/AI 路恒 true） */
  cardLoaded: boolean;
  selfchecked: boolean;
  /** 自检请求在途（按钮置忙；晚到响应由 token 守卫丢弃） */
  selfchecking: boolean;
  selfcheck: {
    link?: { ok: boolean; text: string };
    quota?: { ok: boolean; text: string };
    critiques?: Record<string, string>;
    weakest?: string;
    hint?: string;
    degraded?: boolean;
    failed?: boolean;
  } | null;
  /** 重抽排除清单（c-plan-draw-exclude）：跟目标章走，SHALL NOT 落库 */
  exclude: DrawExcludeItem[];
  /** 当前批各卡的一句话（与 directions 对齐；重抽排除用） */
  oneLiners: string[];
  /** 当前批的目标章号（恢复判定：与 nextNo 一致才算同章） */
  drawnNo: number | null;
}

const INITIAL = (): ChapterPlanState => ({
  entrySource: "manual", open: false, phase: "idle", error: "", submitting: false,
  landed: null, entry: { text: "", source: "" }, directions: [], grades: [], checks: [],
  note: "", warnings: [], degradedText: "", pick: null, draft: { ...EMPTY_DRAFT },
  nextNo: 1, editing: null, cardLoaded: false, selfchecked: false, selfchecking: false, selfcheck: null,
  exclude: [], oneLiners: [], drawnNo: null,
});

export function useChapterPlan(projectId: string, volNo: number, volRef: string) {
  const [state, setState] = useState<ChapterPlanState>(() => INITIAL());
  const tokenRef = useRef(0);
  const nextToken = () => ++tokenRef.current;
  // 进场锚独立 token：它是「当前上下文」的读，不该被同一开的 draw/adopt 作废
  const anchorTokenRef = useRef(0);
  // 排上幂等键：每次打开卡面生成一个，重发/双击同 token（服务端据此返回同一章）
  const clientTokenRef = useRef<string>("");
  // 自检独立 token：晚到响应不得覆盖当前卡面（draw/anchor 都有守卫，唯此处曾缺）
  const selfcheckTokenRef = useRef(0);
  // 排除清单（c-plan-draw-exclude）：ref 供异步流程读写，state 供 UI/测试观察
  const excludeRef = useRef<DrawExcludeItem[]>([]);
  const stateRef = useRef(state);
  stateRef.current = state;

  /** 打开：手写路直接空白五段；AI 路先拉进场再出卡（busy→idle/error） */
  const openManual = useCallback(() => {
    nextToken();
    clientTokenRef.current = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
    setState((s) => ({ ...s, entrySource: "manual", open: true, phase: "idle", error: "",
      entry: { text: "", source: "" }, editing: null, cardLoaded: true,
      draft: { ...EMPTY_DRAFT }, pick: null, selfchecked: false, selfchecking: false, selfcheck: null,
      degradedText: "", warnings: [] }));
    void loadAnchor();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, volRef]);

  /** 回改：把已有拟定章的五段读进同一张卡面（左树 hover／派生视图行／落点卡三处共用） */
  const openEdit = useCallback(
    async (ref: string) => {
      nextToken();
      clientTokenRef.current = "";
      setState((s) => ({
        ...s, entrySource: "manual", open: true, phase: "idle", error: "",
        editing: ref, pick: null, selfchecked: false, selfchecking: false, selfcheck: null,
        // 未装载前草稿必须为空且保存禁用（脏草稿守卫——上一章内容不得被提交到目标章）
        cardLoaded: false, draft: { ...EMPTY_DRAFT }, entry: { text: "", source: "" },
        degradedText: "", warnings: [],
      }));
      const token = nextToken();
      try {
        const d = await chapterPlanApi.chapter(projectId, ref);
        if (token !== tokenRef.current) return;
        setState((s) => ({
          ...s,
          cardLoaded: true,
          entry: { text: d.entry_text || "", source: d.entry_source || "" },
          nextNo: d.next_no ?? s.nextNo,
          draft: {
            title: d.title || "",
            plot: d.plot || "",
            obstacle: d.challenge || "",
            ending: d.ending || "",
        acts: joinActs(d.acts || []),
        stage: d.stage || "开局铺垫",
          },
        }));
      } catch {
        if (token !== tokenRef.current) return;
        setState((s) => ({
          ...s, error: "这一章读不出来，可重试", cardLoaded: false,
          draft: { ...EMPTY_DRAFT }, entry: { text: "（进场读不到）", source: "" },
        }));
      }
    },
    [projectId],
  );

  const openAi = useCallback(() => {
    const gen = nextToken();
    clientTokenRef.current = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
    setState((s) => ({ ...s, entrySource: "ai", open: true, pick: null, checks: [],
      entry: { text: "", source: "" }, editing: null, cardLoaded: true, phase: "busy",
      warnings: [], degradedText: "", selfchecked: false, selfchecking: false, selfcheck: null }));
    // 章号/进场先就位（忙碌态文案与卡面标题都用它），再决定恢复还是重抽（c-plan-draw-exclude）
    void (async () => {
      const anchor = await loadAnchor();
      // 代际守卫只拦「更新的打开」——draw() 自身的 nextToken 不算换代（否则异步链被自己误杀）
      if (gen !== tokenRef.current) return;
      const nextNo = anchor?.next_no ?? stateRef.current.nextNo;
      const cur = stateRef.current;
      const key = drawKey.chapter(projectId, volRef);
      // ① 内存批恢复：同目标章存在未消费批（误关重开）——不重抽、不重复计量；
      // 且必须把 upfront busy 拨回 idle（否则恢复批永远显示「正在想」）
      if (cur.directions.length > 0 && cur.drawnNo !== null && cur.drawnNo === nextNo) {
        setState((x) => ({ ...x, phase: "idle" }));
        return;
      }
      // ② localStorage 恢复（页面刷新兜底）
      const stored = loadDraw<{ v: number; nextNo: number; directions: ChapterDirection[];
        grades: string[]; oneLiners: string[]; checks: string[]; note: string;
        exclude: DrawExcludeItem[] }>(key);
      if (stored && stored.nextNo === nextNo && stored.directions?.length) {
        excludeRef.current = stored.exclude ?? [];
        setState((x) => ({ ...x, phase: "idle", directions: stored.directions,
          grades: stored.grades ?? [], oneLiners: stored.oneLiners ?? [],
          checks: stored.checks ?? [], note: stored.note ?? "",
          exclude: stored.exclude ?? [], drawnNo: stored.nextNo }));
        return;
      }
      // ③ 目标章变化：排除清单清零后重抽
      if (cur.drawnNo !== null && cur.drawnNo !== nextNo) {
        excludeRef.current = [];
        setState((x) => ({ ...x, exclude: [] }));
      }
      await draw();
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, volRef]);

  const loadAnchor = useCallback(async (): Promise<ChapterEntry & { next_no?: number } | null> => {
    const token = ++anchorTokenRef.current;
    try {
      const d = await chapterPlanApi.anchor(projectId, volRef);
      if (token !== anchorTokenRef.current) return null;
      setState((s) => ({
        ...s,
        entry: { text: d.text, source: d.source },
        nextNo: d.next_no ?? s.nextNo,
      }));
      return { text: d.text, source: d.source, next_no: d.next_no };
    } catch {
      // 同一代际守卫：晚到的失败不得覆盖新开的卡面（原实现在这里比错了计数器，
      // 兜底文案被 return 掉 → 换卷残留上一卷进场）
      if (token !== anchorTokenRef.current) return null;
      setState((s) => ({ ...s, entry: { text: "（进场读不到）", source: "" } }));
      return null;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, volRef]);

  const draw = useCallback(async () => {
    const token = nextToken();
    // 换一批不累积：先前的选择与卡面草稿不再显示（否则新批里第 i 张仍显选中，
    // 排上会落库上一批方向的五段）
    setState((s) => ({ ...s, phase: "busy", error: "", pick: null, draft: { ...EMPTY_DRAFT } }));
    try {
      const d: ChapterDirectionsResult = await chapterPlanApi.directions(projectId, volRef, excludeRef.current);
      if (token !== tokenRef.current) return;
      if (d.degraded) {
        setState((s) => ({ ...s, phase: "error",
          error: d.hint || "出卡失败，可重试",
          degradedText: d.text || "" }));
        return;
      }
      const oneLiners = d.diff?.one_liner ?? [];
      const drawnNo = d.entry?.next_no ?? stateRef.current.nextNo;
      saveDraw(drawKey.chapter(projectId, volRef), { v: 1, nextNo: drawnNo,
        directions: d.directions, grades: d.grades ?? [], oneLiners,
        checks: d.checks ?? [], note: d.note ?? "", exclude: excludeRef.current });
      setState((s) => ({ ...s, phase: "idle", entry: d.entry, directions: d.directions,
        grades: d.grades ?? [], oneLiners, checks: d.checks ?? [], note: d.note ?? "",
        warnings: d.warnings ?? [], drawnNo }));
    } catch (e) {
      if (token !== tokenRef.current) return;
      const msg = (e as { message?: string })?.message || "";
      // 三类可操作前置给就地引导，其余（含 5xx）落通用可重试：
      // 未配模型（503「AI 服务未配置 — 请先…API Key」）／卷纲为空（422 门槛）
      const noModel =
        msg.includes("模型") || msg.includes("API Key") || msg.includes("未配置") || msg.includes("503");
      setState((s) => ({ ...s, phase: "error",
        error: noModel ? "还没接模型——先去模型配置里接一个"
          : msg.includes("卷纲") ? msg : "出卡失败，可重试" }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, volRef]);

  /** 换 3 个方向（D21）：当前批并入排除清单后重抽——请求携带 exclude，服务端对拍丢撞车卡 */
  const redraw = useCallback((): Promise<void> => {
    const s = stateRef.current;
    const batch = s.directions
      .map((dd, i) => ({ axis: dd.axis, line: s.oneLiners[i] || "" }))
      .filter((x) => x.axis && x.line);
    excludeRef.current = appendExclude(excludeRef.current, batch);
    setState((x) => ({ ...x, exclude: [...excludeRef.current] }));
    return draw();
  }, [draw]);

  /** 从头再来（D21 逃生口）：清空排除清单后重抽——防转一圈又想要第一批 */
  const freshRedraw = useCallback((): Promise<void> => {
    excludeRef.current = [];
    clearDraw(drawKey.chapter(projectId, volRef));
    setState((x) => ({ ...x, exclude: [] }));
    return draw();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, volRef, draw]);

  /** 点卡：把卡面内容装进 draft 并进入本章卡（grade 供角标/卡尾） */
  const pickCard = useCallback((i: number) => {
    setState((s) => {
      const d = s.directions[i];
      if (!d) return s;
      return { ...s, pick: i, draft: {
        title: d.title, plot: d.plot, obstacle: d.obstacle, ending: d.ending,
        acts: joinActs(d.acts), stage: d.stage, grade: s.grades[i], why: d.why, gap: d.gap, axis: d.axis,
      } };
    });
  }, []);

  const patchDraft = useCallback((patch: Partial<ChapterDraft>) => {
    setState((s) => ({ ...s, error: "", draft: { ...s.draft, ...patch } }));
  }, []);

  /** 切手写（AI 失败出口之一；已填内容保留） */
  const toManual = useCallback(() => {
    nextToken();
    setState((s) => ({ ...s, entrySource: "manual", phase: "idle", error: "" }));
  }, []);

  /** 自检（手写卡底条；免费）——卡面草稿随请求携带（排上之前章未落库） */
  const runSelfcheck = useCallback(async () => {
    const token = ++selfcheckTokenRef.current;
    const d = state.draft;
    setState((s) => ({ ...s, selfchecked: true, selfchecking: true, selfcheck: null }));
    // 衔接组要拿「卡面当前显示进场」比对：进场是异步载入的，还没到就先补一次
    let entryText = state.entry.text;
    if (!entryText) {
      try {
        const a = await chapterPlanApi.anchor(projectId, volRef);
        if (token !== selfcheckTokenRef.current) return;
        entryText = a.text;
        setState((s) => ({ ...s, entry: { text: a.text, source: a.source } }));
      } catch {
        // 取不到就不带进场——服务端按「无可比对」不判漂移（不误报 warn）
      }
    }
    try {
      const r = await chapterPlanApi.selfcheck(projectId, {
        vol_ref: volRef,
        entry_text: entryText,
        chapter_ref: state.landed?.ref,
        title: d.title,
        plot: d.plot,
        challenge: d.obstacle,
        ending: d.ending,
        acts: d.acts.split(/[；;\n]/).map((x) => x.trim()).filter(Boolean).slice(0, 4),
        stage: d.stage,
      });
      if (token !== selfcheckTokenRef.current) return;
      setState((s) => ({ ...s, selfchecking: false, selfcheck: r }));
    } catch {
      if (token !== selfcheckTokenRef.current) return;
      setState((s) => ({ ...s, selfchecking: false, selfcheck: { ok: false, failed: true } }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, volRef, state.draft, state.entry, state.landed]);

  /** 排上：建章＋五段（同一事务）；成功 → 关弹窗＋落点卡数据。
   *  mode 区分实际动作（edit＝回改保存 / adopt＝排上新建），回执文案据此分流。 */
  const adopt = useCallback(async (): Promise<{
    ok: boolean; mode?: "adopt" | "edit"; error?: string;
  }> => {
    const d = state.draft;
    if (!d.title.trim() && !d.plot.trim()) {
      const msg = "至少写个标题或一句「本章剧情」";
      setState((s) => ({ ...s, error: msg }));  // 就地提示：不能只 return 让作者看不见
      return { ok: false, error: msg };
    }
    // 默认标题＝「第N章」（N 由 anchor 单源给出；原实现三元两支皆空 → 恒落「第章」）
    const title = d.title.trim() || `第${state.nextNo}章`;
    const body: ChapterAdoptBody = {
      title,
      plot: d.plot.trim() || undefined,
      challenge: d.obstacle.trim() || undefined,
      ending: d.ending.trim() || undefined,
      acts: d.acts.split(/[；;\n]/).map((x) => x.trim()).filter(Boolean).slice(0, 4),
      stage: d.stage || undefined,
    };
    setState((s) => ({ ...s, submitting: true, error: "" }));
    try {
      // 回改：同一张卡面走章保存链（不新建章、不落落点卡）
      if (state.editing) {
        await chapterPlanApi.saveEdit(projectId, state.editing, body);
        setState((s) => ({ ...s, submitting: false, open: false, editing: null }));
        return { ok: true, mode: "edit" };
      }
      const r = await chapterPlanApi.adopt(projectId, volRef, {
        ...body,
        client_token: clientTokenRef.current,
      });
      // 逐项列出实际带入的五段（spec：空项 SHALL NOT 冒充——手写最小可排时 N 可小于 5）
      const pairs: Array<[string, string]> = [
        ["本章剧情", d.plot],
        ["碰到的挑战", d.obstacle],
        ["本章结尾", d.ending],
        ["本章行动", d.acts],
        ["阶段", d.stage],
      ];
      const items = pairs.filter(([, v]) => String(v || "").trim()).map(([k]) => k);
      // 排上即清（c-plan-draw-exclude）：目标章推进，抽卡会话与排除清单作废
      excludeRef.current = [];
      clearDraw(drawKey.chapter(projectId, volRef));
      setState((s) => ({
        ...s,
        submitting: false,
        open: false,
        exclude: [], oneLiners: [], drawnNo: null,
        landed: { ref: r.ref, title: body.title, brought: items.length, items },
      }));
      return { ok: true, mode: "adopt" };
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
    setState((s) =>
      s.submitting ? s : { ...s, open: false, phase: "idle", error: "", editing: null },
    );
  }, []);

  const consumeLanded = useCallback(() => {
    const l = state.landed;
    if (l) setState((s) => ({ ...s, landed: null }));
    return l;
  }, [state.landed]);

  return {
    // 卷号/卷 ref 以**当前入参**为准（打开时由壳层钉住——见 NovelWorkspace.openChapterPlan）
    state: { ...state, volNo, volRef },
    openManual, openAi, openEdit, draw, redraw, freshRedraw, pickCard, patchDraft, toManual,
    runSelfcheck, adopt, close, consumeLanded,
  };
}

export type ChapterPlanController = ReturnType<typeof useChapterPlan>;
