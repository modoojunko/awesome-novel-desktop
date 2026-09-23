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
  selfchecked: boolean;
  selfcheck: {
    link?: { ok: boolean; text: string };
    quota?: { ok: boolean; text: string };
    critiques?: Record<string, string>;
    weakest?: string;
    hint?: string;
    degraded?: boolean;
    failed?: boolean;
  } | null;
}

const INITIAL = (): ChapterPlanState => ({
  entrySource: "manual", open: false, phase: "idle", error: "", submitting: false,
  landed: null, entry: { text: "", source: "" }, directions: [], grades: [], checks: [],
  note: "", warnings: [], degradedText: "", pick: null, draft: { ...EMPTY_DRAFT },
  nextNo: 1, editing: null, selfchecked: false, selfcheck: null,
});

export function useChapterPlan(projectId: string, volNo: number, volRef: string) {
  const [state, setState] = useState<ChapterPlanState>(() => INITIAL());
  const tokenRef = useRef(0);
  const nextToken = () => ++tokenRef.current;
  // 进场锚独立 token：它是「当前上下文」的读，不该被同一开的 draw/adopt 作废
  const anchorTokenRef = useRef(0);
  // 排上幂等键：每次打开卡面生成一个，重发/双击同 token（服务端据此返回同一章）
  const clientTokenRef = useRef<string>("");

  /** 打开：手写路直接空白五段；AI 路先拉进场再出卡（busy→idle/error） */
  const openManual = useCallback(() => {
    nextToken();
    clientTokenRef.current = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
    setState((s) => ({ ...s, entrySource: "manual", open: true, phase: "idle", error: "",
      draft: { ...EMPTY_DRAFT }, pick: null, selfchecked: false, selfcheck: null, degradedText: "", warnings: [] }));
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
        editing: ref, pick: null, selfchecked: false, selfcheck: null,
        degradedText: "", warnings: [],
      }));
      const token = nextToken();
      try {
        const d = await chapterPlanApi.chapter(projectId, ref);
        if (token !== tokenRef.current) return;
        setState((s) => ({
          ...s,
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
        setState((s) => ({ ...s, error: "这一章读不出来，可重试" }));
      }
    },
    [projectId],
  );

  const openAi = useCallback(() => {
    nextToken();
    clientTokenRef.current = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
    setState((s) => ({ ...s, entrySource: "ai", open: true, pick: null, checks: [],
      warnings: [], degradedText: "", selfchecked: false, selfcheck: null }));
    void loadAnchor(); // 章号/进场先就位（忙碌态文案与卡面标题都用它）
    void draw();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, volRef]);

  const loadAnchor = useCallback(async () => {
    const token = ++anchorTokenRef.current;
    try {
      const d = await chapterPlanApi.anchor(projectId, volRef);
      if (token !== anchorTokenRef.current) return;
      setState((s) => ({
        ...s,
        entry: { text: d.text, source: d.source },
        nextNo: d.next_no ?? s.nextNo,
      }));
    } catch {
      if (token !== tokenRef.current) return;
      setState((s) => ({ ...s, entry: { text: "（进场读不到）", source: "" } }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, volRef]);

  const draw = useCallback(async () => {
    const token = nextToken();
    // 换一批不累积：先前的选择与卡面草稿不再显示（否则新批里第 i 张仍显选中，
    // 排上会落库上一批方向的五段）
    setState((s) => ({ ...s, phase: "busy", error: "", pick: null, draft: { ...EMPTY_DRAFT } }));
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
    const d = state.draft;
    setState((s) => ({ ...s, selfchecked: true, selfcheck: null }));
    // 衔接组要拿「卡面当前显示进场」比对：进场是异步载入的，还没到就先补一次
    let entryText = state.entry.text;
    if (!entryText) {
      try {
        const a = await chapterPlanApi.anchor(projectId, volRef);
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
      setState((s) => ({ ...s, selfcheck: r }));
    } catch {
      setState((s) => ({ ...s, selfcheck: { ok: false, failed: true } }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, volRef, state.draft, state.entry, state.landed]);

  /** 排上：建章＋五段（同一事务）；成功 → 关弹窗＋落点卡数据 */
  const adopt = useCallback(async (): Promise<{ ok: boolean; error?: string }> => {
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
        return { ok: true };
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
      setState((s) => ({
        ...s,
        submitting: false,
        open: false,
        landed: { ref: r.ref, title: body.title, brought: items.length, items },
      }));
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
    openManual, openAi, openEdit, draw, pickCard, patchDraft, toManual,
    runSelfcheck, adopt, close, consumeLanded,
  };
}

export type ChapterPlanController = ReturnType<typeof useChapterPlan>;
