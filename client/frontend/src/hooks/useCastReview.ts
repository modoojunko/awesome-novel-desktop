// 章纲人物精盘状态机（c-character-intro 3.2）：盘点→三选一→抽卡→写入回程。
// phase 枚举与设计稿 11 态一一映射：reviewing（②）/result（③结果·④零新增·⑥免费锁·⑧写入回程）
// /cards（⑤）/drawing（⑩）/picked（⑦确认页两形态）/error（⑨盘点失败·⑪抽卡失败，error.kind 分流）。
// 会话跟章走（drawKey.cast，localStorage 兜刷新）：载荷＝盘点结果＋三选一＋输入指纹（只盖剧情
// 输入，落账写名字不失效）＋gapId 批次；恢复按档位裁剪（免费档丢 cards 载荷）；指纹不符弃用并
// 重跑；「重新盘点」＝全量重跑＋按段 idx 对回合并。并发双击在途互斥（busyRef，state 重渲染
// 窗口挡不住连点）。落账回执＝toast（3 秒自动消失，c-toast-dismiss）＋结果页 aria-live 回执行。
import { useCallback, useMemo, useRef, useState } from "react";
import {
  castChoice,
  castReviewApi,
  classifyCastError,
  gapIdOf,
  verdictKind,
  type CastCard,
  type CastChoice,
  type CastExcludeItem,
  type CastReviewBody,
  type CastReviewResponse,
  type CastWriteOutcome,
  type CastWriteRequest,
} from "@/lib/castReviewApi";
import {
  appendCastExclude,
  castInputFingerprint,
  clearCastSession,
  drawKey,
  loadCastSession,
  mergeCastGaps,
  pruneCastGap,
  saveCastSession,
  trimCastSessionForTier,
  type CastGapSession,
} from "@/lib/drawSession";
import { toast } from "@/lib/toast";

export type CastPhase = "reviewing" | "result" | "cards" | "drawing" | "picked" | "error";
export type CastErrorKind = "review" | "draw";

export interface CastGapView extends CastGapSession {
  gapId: string;
  idx: number | null;
  /** 显示行号（剧情 N／整章） */
  label: string;
  echo: string;
  need: string;
  whyNotOld: string;
  /** suggest 出界缺省＝true → 不打「AI 建议」标（打「默认」） */
  defaulted: boolean;
}

export interface CastState {
  open: boolean;
  phase: CastPhase;
  error: { kind: CastErrorKind; message: string; noModel: boolean } | null;
  review: CastReviewResponse | null;
  rows: CastReviewResponse["rows"];
  gaps: CastGapView[];
  activeGapId: string | null;
  /** 当前批卡（cards 态展示） */
  cards: CastCard[];
  /** 选卡下标（picked 态；手填＝null） */
  pickIndex: number | null;
  /** 确认页入口形态：选卡进＝预填＋返回换一张；手填进＝空格无返回、不露 AI 预填 */
  pickFrom: "card" | "manual" | null;
  writing: boolean;
  /** picked 态内的写入失败（格内改动保留；created=true → 重试只走名单写入） */
  writeError: { kind: "create_failed" | "save_failed"; message: string; created: boolean } | null;
  /** 落账回执（aria-live done-notice；「还有 N 个」/全清两分支） */
  notice: string | null;
}

const INITIAL: CastState = {
  open: false,
  phase: "result", // 空闲初值：挂载即「reviewing」会被 castBusy 派生成在跑（e2e 实锤：全行禁点）
  error: null,
  review: null,
  rows: [],
  gaps: [],
  activeGapId: null,
  cards: [],
  pickIndex: null,
  pickFrom: null,
  writing: false,
  writeError: null,
  notice: null,
};

export interface CastReviewInput {
  /** 盘点请求体（表单快照，ogToPartial 同源归一） */
  body: CastReviewBody;
  /** ogToPartial 输出（指纹只取其剧情子集） */
  partial: Record<string, unknown>;
}

export interface CastReviewController {
  state: CastState;
  /** 打开弹窗：会话有效即恢复（按档位裁剪），指纹不符弃用并重新盘点 */
  open: () => void;
  /** 关窗：丢格子改动（弹窗内表单态），批次随会话保留 */
  close: () => void;
  /** 重新盘点：全量重跑＋按段 idx 对回合并 */
  recheck: () => void;
  setChoice: (gapId: string, choice: CastChoice) => void;
  /** 抽卡选人（PRO）：有批次直接见同一批（不重新生成），否则开抽 */
  startDraw: (gapId: string) => void;
  /** 换一批（带 exclude 避开已出人物路数） */
  redraw: (gapId: string) => void;
  /** 从头再来（清批次记录重出） */
  freshRedraw: (gapId: string) => void;
  pickCard: (gapId: string, index: number) => void;
  fillManual: (gapId: string) => void;
  /** 选已有角色：卡已在书里，名字直接进本章名单（零 AI 全免费；不建卡不抽卡） */
  pickExisting: (gapId: string, name: string) => Promise<void>;
  /** ‹ 返回盘点结果 */
  backToReview: () => void;
  /** ‹ 返回换一张（回抽卡态，同批卡保留） */
  backToCards: () => void;
  /** 写入两出口（建卡并写入／只加名单）：在途互斥 */
  submitWrite: (req: CastWriteRequest) => Promise<CastWriteOutcome | null>;
  /** 写入成功落账：缺口转已处理、剩余继续、全部处理完收场；回执 toast（3 秒自动消失） */
  markWritten: (gapId: string, outcome: Extract<CastWriteOutcome, { ok: true }>) => void;
}

const toRecord = (g: CastGapView): CastGapSession => ({
  anchor: g.anchor,
  choice: g.choice,
  touched: g.touched,
  status: g.status,
  writtenName: g.writtenName,
  writtenWithCard: g.writtenWithCard,
  writtenExisting: g.writtenExisting,
  batches: g.batches,
  exclude: g.exclude,
});

export function useCastReview(opts: {
  projectId: string;
  chapterRef: string;
  /** 拥有 ai-plan（标准起）——抽卡/恢复判据（tier-plan-four-tiers 5.4） */
  hasAiPlan: boolean;
  /** 盘点输入（表单快照；引用稳定即可，调用时读最新） */
  input: CastReviewInput;
  onWrite: (req: CastWriteRequest) => Promise<CastWriteOutcome>;
  onUpgrade: () => void;
  onOpenConfig: () => void;
}): CastReviewController {
  const { projectId, chapterRef, hasAiPlan, onWrite, onUpgrade } = opts;
  const [state, setState] = useState<CastState>(INITIAL);
  // 在途互斥（ref 同步判定）＋代际守卫（关窗/重跑换代，晚到响应丢弃）
  const busyRef = useRef(false);
  const genRef = useRef(0);
  const inputRef = useRef(opts.input);
  inputRef.current = opts.input;
  const gapsRef = useRef<CastGapView[]>([]);
  gapsRef.current = state.gaps;

  const sessionKey = drawKey.cast(projectId, chapterRef);

  /** review.rows + 三选一/批次记录 → 缺口视图（gapId=f(段 idx)） */
  const buildGaps = useCallback(
    (review: CastReviewResponse, records: Record<string, CastGapSession>): CastGapView[] => {
      const items = inputRef.current.body.plot_items;
      const out: CastGapView[] = [];
      for (const row of review.rows) {
        if (verdictKind(row.verdict) !== "new" || !row.gap) continue;
        const gapId = gapIdOf(row.idx);
        const anchor =
          row.idx != null ? items[row.idx] ?? row.echo : inputRef.current.body.summary;
        const rec: CastGapSession = records[gapId] ?? {
          anchor,
          choice: castChoice(row.gap.suggest),
          touched: false,
          // 预填只是 AI 建议（可改），未点按不算处理——「处理完的行标已处理」只认作者点按
          // （旧实现把预填 延后/改段 直接置已处理＝AI 代点，违 R3/R5，e2e 实锤）
          status: "open",
          batches: [],
          exclude: [],
        };
        out.push({
          ...rec,
          anchor,
          gapId,
          idx: row.idx,
          label: row.idx == null ? "整章" : `剧情 ${row.idx + 1}`,
          echo: row.echo,
          need: row.gap.need,
          whyNotOld: row.gap.why_not_old,
          defaulted: !!row.defaulted,
        });
      }
      return out;
    },
    [],
  );

  const persistGaps = useCallback(
    (gaps: CastGapView[]) => {
      const s = loadCastSession(sessionKey);
      const records: Record<string, CastGapSession> = {};
      for (const g of gaps) records[g.gapId] = toRecord(g);
      saveCastSession(sessionKey, {
        fp: s?.fp ?? castInputFingerprint(inputRef.current.partial as never),
        review: s?.review ?? { rows: [], quota: { named_count: 0, regime: "open" }, hints: [] },
        gaps: records,
      });
    },
    [sessionKey],
  );

  /** 盘点（isRecheck＝全量重跑＋按段 idx 对回合并：未改条目处理记录与批次沿用） */
  const runReview = useCallback(
    (isRecheck: boolean) => {
      if (busyRef.current) return;
      busyRef.current = true;
      const gen = ++genRef.current;
      setState((s) => ({
        ...s,
        open: true,
        phase: "reviewing",
        error: null,
        notice: null,
        writeError: null,
      }));
      void (async () => {
        try {
          const resp = await castReviewApi.review(
            projectId,
            chapterRef,
            inputRef.current.body,
          );
          if (gen !== genRef.current) return;
          const fp = castInputFingerprint(inputRef.current.partial as never);
          const prev = isRecheck ? (loadCastSession(sessionKey)?.gaps ?? {}) : {};
          const fresh = buildGaps(resp, {});
          const merged = mergeCastGaps(
            prev,
            Object.fromEntries(fresh.map((g) => [g.gapId, toRecord(g)])),
          );
          const gaps = fresh.map((g) => ({
            ...g,
            ...merged[g.gapId],
            anchor: g.anchor,
            gapId: g.gapId,
            idx: g.idx,
            label: g.label,
            echo: g.echo,
            need: g.need,
            whyNotOld: g.whyNotOld,
            defaulted: g.defaulted,
          }));
          const records: Record<string, CastGapSession> = {};
          for (const g of gaps) records[g.gapId] = toRecord(g);
          saveCastSession(sessionKey, { fp, review: resp, gaps: records });
          setState((s) => ({
            ...s,
            phase: "result",
            review: resp,
            rows: resp.rows,
            gaps,
            activeGapId: null,
            cards: [],
            pickIndex: null,
            pickFrom: null,
          }));
        } catch (e) {
          if (gen !== genRef.current) return;
          const c = classifyCastError(e);
          setState((s) => ({
            ...s,
            phase: "error",
            error: {
              kind: "review",
              message: c.emptyChapter
                ? "先写剧情再盘点——这一章还没有剧情条目，也没有留存格内容。"
                : c.noModel
                  ? "还没接模型——先在模型配置里接一个，再回来盘点。"
                  : c.message,
              noModel: c.noModel,
            },
          }));
        } finally {
          busyRef.current = false;
        }
      })();
    },
    [projectId, chapterRef, sessionKey, buildGaps],
  );

  const open = useCallback(() => {
    const fp = castInputFingerprint(inputRef.current.partial as never);
    const s = loadCastSession(sessionKey);
    if (s && s.fp === fp) {
      // 会话恢复按档位裁剪（免费档丢 cards 载荷——不展示任何 AI 生成卡面）；只在内存裁剪
      const trimmed = trimCastSessionForTier(s, hasAiPlan);
      setState((prev) => ({
        ...prev,
        open: true,
        phase: "result",
        error: null,
        writeError: null,
        notice: null,
        review: trimmed.review,
        rows: trimmed.review.rows,
        gaps: buildGaps(trimmed.review, trimmed.gaps),
        activeGapId: null,
        cards: [],
        pickIndex: null,
        pickFrom: null,
      }));
      return;
    }
    if (s) {
      // 指纹不符（剧情输入改过）：弃用会话，整章重新盘点
      clearCastSession(sessionKey);
      toast.info("剧情改过了，重新盘点");
    }
    runReview(false);
  }, [sessionKey, hasAiPlan, buildGaps, runReview]);

  const close = useCallback(() => {
    genRef.current++; // 晚到响应不再落表
    setState((s) => ({ ...s, open: false, pickIndex: null, pickFrom: null, writeError: null }));
  }, []);

  const recheck = useCallback(() => {
    if (busyRef.current) return;
    persistGaps(gapsRef.current); // 先把处理记录落会话，重盘后按段 idx 对回
    runReview(true);
  }, [persistGaps, runReview]);

  const setChoice = useCallback(
    (gapId: string, choice: CastChoice) => {
      setState((s) => {
        const gaps = s.gaps.map((g) =>
          g.gapId === gapId
            ? {
                ...g,
                choice,
                touched: true,
                // 改段/延后＝本次算处理过（零请求零落库）；切回加人＝恢复待处理
                status:
                  choice === "改段" ? ("edited" as const)
                  : choice === "延后" ? ("deferred" as const)
                  : ("open" as const),
              }
            : g,
        );
        persistGaps(gaps);
        return { ...s, gaps };
      });
    },
    [persistGaps],
  );

  /** 真抽一批（在途互斥＋代际守卫；exclude 重抽不降温由服务端管） */
  const drawBatch = useCallback(
    (gapId: string, exclude: CastExcludeItem[]) => {
      if (busyRef.current) return;
      busyRef.current = true;
      const gen = ++genRef.current;
      const gap = gapsRef.current.find((g) => g.gapId === gapId);
      setState((s) => ({
        ...s,
        phase: "drawing",
        activeGapId: gapId,
        cards: [],
        pickIndex: null,
        pickFrom: null,
        error: null,
      }));
      void (async () => {
        try {
          const resp = await castReviewApi.draw(projectId, chapterRef, {
            gap: {
              idx: gap?.idx ?? null,
              need: gap?.need ?? "",
              why_not_old: gap?.whyNotOld ?? "",
            },
            characters: inputRef.current.body.characters,
            exclude,
          });
          if (gen !== genRef.current) return;
          const cards = Array.isArray(resp?.cards) ? resp.cards : [];
          if (cards.length === 0) {
            setState((s) => ({
              ...s,
              phase: "error",
              error: {
                kind: "draw",
                message: "出卡失败，可再试——这一章缺的人还列着，什么都没变。",
                noModel: false,
              },
            }));
            return;
          }
          setState((s) => {
            const gaps = s.gaps.map((g) =>
              g.gapId === gapId ? { ...g, exclude, batches: [...g.batches, cards] } : g,
            );
            persistGaps(gaps);
            return { ...s, gaps, phase: "cards", cards };
          });
        } catch (e) {
          if (gen !== genRef.current) return;
          const c = classifyCastError(e);
          if (c.memberRequired) {
            setState((s) => ({ ...s, phase: "result" }));
            onUpgrade();
            return;
          }
          setState((s) => ({
            ...s,
            phase: "error",
            error: {
              kind: "draw",
              message: c.noModel
                ? "还没接模型——先去模型配置接一个，再回来抽卡。"
                : "出卡失败，可再试——这一章缺的人还列着，什么都没变。",
              noModel: c.noModel,
            },
          }));
        } finally {
          busyRef.current = false;
        }
      })();
    },
    [projectId, chapterRef, persistGaps, onUpgrade],
  );

  const startDraw = useCallback(
    (gapId: string) => {
      if (busyRef.current) return;
      if (!hasAiPlan) {
        onUpgrade();
        return;
      }
      const gap = gapsRef.current.find((g) => g.gapId === gapId);
      if (!gap) return;
      // 已有批次：直接见同一批（不重新生成、不重复计量）；免费档恢复已被裁剪
      const last = gap.batches[gap.batches.length - 1];
      if (last && last.length > 0) {
        setState((s) => ({
          ...s,
          phase: "cards",
          activeGapId: gapId,
          cards: last,
          pickIndex: null,
          pickFrom: null,
          error: null,
        }));
        return;
      }
      drawBatch(gapId, gap.exclude);
    },
    [hasAiPlan, onUpgrade, drawBatch],
  );

  const redraw = useCallback(
    (gapId: string) => {
      if (busyRef.current) return;
      const gap = gapsRef.current.find((g) => g.gapId === gapId);
      if (!gap) return;
      const last = gap.batches[gap.batches.length - 1] ?? [];
      const exclude = appendCastExclude(
        gap.exclude,
        last.map((c) => ({ axis: c.axis, name: c.name, persona: c.persona })),
      );
      drawBatch(gapId, exclude);
    },
    [drawBatch],
  );

  const freshRedraw = useCallback(
    (gapId: string) => {
      if (busyRef.current) return;
      // 从头再来：清掉批次记录重出（可能再遇到之前的方向）；gapId 粒度，其他缺口不动
      setState((s) => ({
        ...s,
        gaps: s.gaps.map((g) =>
          g.gapId === gapId ? { ...g, batches: [], exclude: [] } : g,
        ),
      }));
      pruneCastGap(sessionKey, gapId);
      drawBatch(gapId, []);
    },
    [sessionKey, drawBatch],
  );

  const pickCard = useCallback((gapId: string, index: number) => {
    setState((s) => ({
      ...s,
      phase: "picked",
      activeGapId: gapId,
      pickIndex: index,
      pickFrom: "card",
      writeError: null,
    }));
  }, []);

  const fillManual = useCallback((gapId: string) => {
    setState((s) => ({
      ...s,
      phase: "picked",
      activeGapId: gapId,
      pickIndex: null,
      pickFrom: "manual",
      writeError: null,
    }));
  }, []);

  const backToReview = useCallback(() => {
    setState((s) => ({ ...s, phase: "result", pickIndex: null, pickFrom: null, writeError: null }));
  }, []);

  const backToCards = useCallback(() => {
    setState((s) => ({ ...s, phase: "cards", pickIndex: null, pickFrom: null, writeError: null }));
  }, []);

  const markWritten = useCallback(
    (gapId: string, outcome: Extract<CastWriteOutcome, { ok: true }>) => {
      const gaps = gapsRef.current.map((g) =>
        g.gapId === gapId
          ? {
              ...g,
              status: "written" as const,
              writtenName: outcome.name,
              writtenWithCard: outcome.created,
              writtenExisting: outcome.existing === true,
              batches: [],
              exclude: [],
            }
          : g,
      );
      persistGaps(gaps);
      const remaining = gaps.filter((g) => g.status === "open").length;
      if (remaining === 0) clearCastSession(sessionKey); // 全部处理完收场：全键只在此刻清理
      const donePart =
        remaining > 0
          ? `本章还有 ${remaining} 个缺的人没处理`
          : "本章的缺的人都处理完了，可以关掉弹窗。";
      const writePart = outcome.created
        ? `已写入。角色表多一卡「${outcome.name}」，本章出场角色 ${outcome.castBefore}→${outcome.castAfter} 人（本卷出场清单自动汇总）`
        : outcome.existing === true
          ? `已写入名单。「${outcome.name}」用的是书里已有的角色卡，名字进本章出场角色（不重复建卡）`
          : `已写入名单。「${outcome.name}」暂未建卡，名字旁随时可点「建卡」补一张，只带名字`;
      const notice = `${outcome.note ? `${outcome.note} ` : ""}${writePart} · ${donePart}`;
      setState((s) => ({
        ...s,
        gaps,
        phase: "result",
        activeGapId: null,
        pickIndex: null,
        pickFrom: null,
        writeError: null,
        notice,
      }));
      toast.success(notice);
    },
    [persistGaps, sessionKey],
  );

  const submitWrite = useCallback(
    async (req: CastWriteRequest): Promise<CastWriteOutcome | null> => {
      if (busyRef.current) return null;
      busyRef.current = true;
      setState((s) => ({ ...s, writing: true, writeError: null }));
      try {
        const out = await onWrite(req);
        if (!out.ok) {
          setState((s) => ({
            ...s,
            writing: false,
            writeError: { kind: out.kind, message: out.message, created: out.created },
          }));
          return out;
        }
        setState((s) => ({ ...s, writing: false }));
        return out;
      } catch {
        setState((s) => ({
          ...s,
          writing: false,
          writeError: {
            kind: "save_failed",
            message: "写入失败，请重试",
            created: req.listOnlyAfterCreate === true,
          },
        }));
        return null;
      } finally {
        busyRef.current = false;
      }
    },
    [onWrite],
  );

  /** 选已有角色：不建卡不抽卡，名字直接进本章名单（零 AI 全免费）。
   *  失败＝缺口保持 open，toast 报错（与自动保存失败同哲学，不弹格内错）。 */
  const pickExisting = useCallback(
    async (gapId: string, name: string) => {
      const out = await submitWrite({
        mode: "list-only",
        existing: true,
        fields: { name, duty: "", persona: "", entrance: "", exitKind: "", exitNote: "" },
      });
      if (out && out.ok) markWritten(gapId, out);
      else if (out) toast.error(out.message);
    },
    [submitWrite, markWritten],
  );

  // 控制器对象 memo 化：进 onRailData/弹窗 props 依赖面，避免每渲染新对象引发循环
  return useMemo(
    () => ({
      state,
      open,
      close,
      recheck,
      setChoice,
      startDraw,
      redraw,
      freshRedraw,
      pickCard,
      fillManual,
      pickExisting,
      backToReview,
      backToCards,
      submitWrite,
      markWritten,
    }),
    [
      state,
      open,
      close,
      recheck,
      setChoice,
      startDraw,
      redraw,
      freshRedraw,
      pickCard,
      fillManual,
      pickExisting,
      backToReview,
      backToCards,
      submitWrite,
      markWritten,
    ],
  );
}
