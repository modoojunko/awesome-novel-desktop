// 章对象工作台（storyline.html 章编辑器复刻）：
//   头部（卷名 kicker + 章标题 + 状态徽章；排版 seg/专注/版本历史/归档收在头部右侧，
//   页签条紧贴头部——与卷视图同位，原型 e-head→e-toolbar 两段式；AI 入口全部在右栏）
//   八页签（章纲/正文/提示词/设定/文风/角色关系/伏笔/操作）· 点章强制落章纲
//   正文常驻挂载 hidden 切换（脏状态/流式现场不丢）
//   底部状态栏（字数 + 保存四态聚合 + AI 流式指示 + 停止）
// 章纲表单状态提升于此（页签徽标 / 保存 / 3s 静默自动保存共用）。
// PR 5：归档/版本历史改弹窗（原型口径）；AI 按钮走页面级解锁链；
//   生成启动信号（aiWriteSignal）自动切正文页签（真 bug #2）；
//   排版偏好 per-book（pref.book.{pid}.*，全局兜底）。
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type RefObject,
} from "react";
import OgPane from "./OgPane";
import SimModal from "./SimModal";
import { charactersApi } from "@/lib/charactersApi";
import PromptPane from "./PromptPane";
import { StyleShadowPane } from "./StyleShadowPane";
import { SettingsChangelogPane } from "./SettingsChangelogPane";
import { HooksPane } from "./HooksPane";
import { RelationsGraphPane } from "./RelationsGraphPane";
import { ReconcilePane } from "./ReconcilePane";
import ProsePane, {
  INITIAL_PROSE_AI_STATE,
  type ProseAIState,
  type ProseHandle,
} from "./ProsePane";
import { ArchiveModal, HistoryModal, RewriteModal } from "./modals";
import type { RailChapterData } from "./Rail";
import {
  EMPTY_OG_FORM,
  GAP_TO_FILL_KEY,
  ogFormIssues,
  ogGaps,
  ogPatchFromFills,
  ogToForm,
  ogToPartial,
  type OgForm,
} from "./chapterForm";
import AiCheckModal from "./AiCheckModal";
import RefinePromptModal from "./RefinePromptModal";
import { useChapterData } from "@/hooks/useChapterData";
import { draftOutline } from "@/lib/ai";
import { fillOutlineGaps, type AiCheckKind, type RefineMode } from "@/lib/aiCheck";
import type { useOutline } from "@/hooks/useOutline";
import type { useWorkbench } from "@/hooks/useWorkbench";
import { api, request } from "@/lib/api";
import { nodeLabel } from "@/lib/nodeTitle";
import {
  getBookArchiveAiSummary,
  getBookFontSize,
  getBookLineHeight,
  setBookFontSize,
  setBookLineHeight,
  type FontSizePref,
  type LineHeightPref,
} from "@/lib/prefs";
import { toast } from "@/lib/toast";
import { chapterNoOf, volNoOf } from "@/lib/chapterRef";

type OutlineApi = ReturnType<typeof useOutline>;
type WorkbenchApi = ReturnType<typeof useWorkbench>;

interface ChapterWorkspaceProps {
  projectId: string;
  chapterRef: string;
  outline: OutlineApi;
  wb: WorkbenchApi;
  /** PRO 档位（提示词页签 PRO-only；AI 入口已全部收口右栏 AI 助手） */
  isPro: boolean;
  /** ProPane ref 由页面持有（右栏 AI 工具共用同一实例） */
  proseRef: RefObject<ProseHandle | null>;
  aiState: ProseAIState;
  onAIStateChange: (update: (prev: ProseAIState) => ProseAIState) => void;
  /** 本书总字数（右栏进度卡，由页面从树汇总） */
  bookWords: number;
  /** 右栏本章进度数据实时上抛（字数/目标/归档随 store 变化） */
  onRailData: (data: RailChapterData | null) => void;
  /** 生成启动信号（计数器递增）：切正文页签 + 聚焦（真 bug #2） */
  aiWriteSignal: number;
  /** 续写恢复信号（顶栏 CTA）：n 递增触发，落正文页签并滚回上次位置 */
  resumeSignal?: { ref: string; scroll: number; n: number };
  /** 写作进度上抛（顶栏 bar-here 跟随显示上次写到的章） */
  onWriteProgress?: (session: { ref: string; scroll: number; ts: number }) => void;
  /** 回退到本章（revert-ghost）：主线收回，其后章转旧稿支线 */
  onRevert: (ref: string) => void;
  /** chapter-rewrite：树刷新（useWorkbench.refresh——旧稿分组与角标只在树 hook 里） */
  onTreeRefresh: () => Promise<void> | void;
}

const fmt = (n: number) => n.toLocaleString("zh-CN");

export default function ChapterWorkspace({
  projectId,
  chapterRef,
  outline,
  wb,
  isPro,
  proseRef,
  aiState,
  onAIStateChange,
  bookWords,
  onRailData,
  aiWriteSignal,
  resumeSignal,
  onWriteProgress,
  onRevert,
  onTreeRefresh,
}: ChapterWorkspaceProps) {
  const store = useChapterData(projectId, chapterRef);
  const { wordCount, saveState, targetWords, setTargetWords } = store;
  // 旧稿支线（revert-ghost）：本章脱离主线，只读保留
  const ghostOf = store.chapter?.ghost_of ?? null;

  // 树结构里的章元数据（编号/标题/归档位；volumes 常驻已加载）。
  // WorkbenchVolume.chapters 无 ref 字段 → 按 vol-N/ch-N 对齐。
  // 排队门禁（workbench-frontier）：主线顺序上，本章之前存在「无正文且未归档」
  // 的章 → 本章为拟态排队章，不可写（后端 prose PUT 同规则 409 兜底）
  const frontierLocked = useMemo(() => {
    // 主线顺序上，本章之前存在「无正文且未归档」的章 → 本章在排队，不可写
    for (const v of outline.volumes) {
      for (const c of v.chapters) {
        const ref = `${v.ref}-ch-${c.chapter}`;
        if (ref === chapterRef) return false;
        if (!c.archived && !(c.has_prose ?? (c.word_count ?? 0) > 0)) return true;
      }
    }
    return false;
  }, [chapterRef, outline.volumes]);
  const writable = !frontierLocked;

  const chMeta = useMemo(() => {
    const volName = `vol-${volNoOf(chapterRef)}`;
    const chNo = chapterNoOf(chapterRef);
    if (!chNo) return null;
    const vol = wb.volumes.find((v) => v.name === volName);
    return vol?.chapters.find((c) => c.chapter === chNo) ?? null;
  }, [wb.volumes, chapterRef]);
  const label = nodeLabel("章", chMeta?.chapter ?? 0, chMeta?.title);
  const vol = wb.volumes.find((v) => v.name === `vol-${volNoOf(chapterRef)}`);
  const volLabel = vol ? nodeLabel("卷", volNoOf(chapterRef), vol.title) : `第${volNoOf(chapterRef)}卷`;
  const archived = !!chMeta?.archived;

  // 「信息差对齐」块随卷纲换代退役（c-volume-view-storyline：info_gap/chapter_plans
  // 为旧代字段，ADJUSTMENTS ⑤ 登记）。

  // ── 页签：点章强制落「章纲」（设计稿行为） ───────────────────────────
  const [chTab, setChTab] = useState<
    "og" | "prompt" | "prose" | "settings" | "relations" | "hooks" | "actions"
   | "style">("og");
  const [showArchive, setShowArchive] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  useEffect(() => {
    setChTab("og");
    setShowHistory(false);
  }, [chapterRef]);

  // 会员降级兜底：提示词页签 PRO-only，免费态强制回落章纲
  useEffect(() => {
    if (!isPro && chTab === "prompt") setChTab("og");
  }, [isPro, chTab]);

  // 生成启动信号（页面解锁链/AiModal 确认后递增）：切正文页签 + 聚焦（真 bug #2）
  useEffect(() => {
    if (!aiWriteSignal) return;
    setChTab("prose");
    setShowHistory(false);
    const t = setTimeout(() => proseRef.current?.focus(), 60);
    return () => clearTimeout(t);
  }, [aiWriteSignal, proseRef]);

  // 续写恢复信号（顶栏 CTA）：落正文页签，滚动位置由 ProsePane 按 resumeScroll 恢复
  useEffect(() => {
    if (!resumeSignal || !resumeSignal.n) return;
    setChTab("prose");
    setShowHistory(false);
  }, [resumeSignal]);

  // 稳定标识：按信号记忆化，避免每次渲染生成新对象触发 ProsePane 恢复 effect 重跑
  const resumeScrollMemo = useMemo(
    () =>
      resumeSignal && resumeSignal.ref === chapterRef
        ? { n: resumeSignal.n, pct: resumeSignal.scroll }
        : undefined,
    [resumeSignal, chapterRef],
  );

  // ── 章纲表单：加载 / 缺口 / 保存 / 3s 静默自动保存 ────────────────────
    // 本书角色名清单（character-settings-v2）：章纲出场角色多选候选
  const [characterNames, setCharacterNames] = useState<string[]>([]);
  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const data = await charactersApi.list(projectId);
        if (alive) setCharacterNames(data.items.map((i) => i.name)
            .filter((n) => n && !n.startsWith("\u0000")));
      } catch {
        /* 角色接口失败不阻塞章纲；textarea 兜底仍可用 */
      }
    })();
    return () => {
      alive = false;
    };
  }, [projectId]);

const [ogForm, setOgForm] = useState<OgForm>(EMPTY_OG_FORM);
  const [ogStatus, setOgStatus] = useState("");
  const ogStatusRef = useRef(ogStatus);
  useEffect(() => {
    ogStatusRef.current = ogStatus;
  }, [ogStatus]);
  const [ogLoading, setOgLoading] = useState(true);
  const [ogSaving, setOgSaving] = useState(false);
  const ogSnapRef = useRef<string>(JSON.stringify(EMPTY_OG_FORM));
  const ogLoadingRef = useRef(true);

  useEffect(() => {
    let cancelled = false;
    ogLoadingRef.current = true;
    setOgLoading(true);
    outline
      .loadChapterData(chapterRef)
      .then((d) => {
        if (cancelled) return;
        const f = ogToForm(d);
        setOgForm(f);
        ogSnapRef.current = JSON.stringify(f);
        setOgStatus(d.status ?? "");
      })
      .catch(() => {
        if (!cancelled) toast.error("章纲加载失败");
      })
      .finally(() => {
        if (!cancelled) {
          ogLoadingRef.current = false;
          setOgLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
    // outline 容器每次渲染都是新对象 → 依赖稳定的成员函数
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chapterRef, outline.loadChapterData]);

  const gaps = ogGaps(ogForm);
  const confirmed = ogStatus === "confirmed";

  /** 回改「本章结尾」不静默（c-chapter-plan-ai D14）：下一章已排上 → 一次性提示，
   *  并刷新树让下一章的「基于旧设定」标记上屏（置位在服务端章保存事务内完成）。 */
  const notifyExitChange = useCallback(
    (beforeExit: string) => {
      const afterExit = String(ogForm.ladder ?? "").trim();
      const hasNext = (vol?.chapters ?? []).some((c) => c.chapter > (chMeta?.chapter ?? 0));
      if (hasNext && afterExit !== beforeExit) {
        toast.info("下一章的进场会跟着变——它已标上「基于旧设定」");
        void wb.refresh();
      }
    },
    [ogForm.ladder, vol, chMeta, wb],
  );

  const saveOg = useCallback(async (): Promise<boolean> => {
    if (ogLoadingRef.current) return false;
    const issues = ogFormIssues(ogForm);
    if (issues.length > 0) {
      toast.error(issues[0]);
      return false;
    }
    setOgSaving(true);
    try {
      const beforeExit = String(outline.chaptersMap.get(chapterRef)?.ladder_exit ?? "").trim();
      await outline.saveChapter(
        chapterRef,
        ogToPartial(ogForm, outline.chaptersMap.get(chapterRef)),
      );
      ogSnapRef.current = JSON.stringify(ogForm);
      notifyExitChange(beforeExit);
      return true;
    } catch {
      toast.error("章纲保存失败，请重试");
      return false;
    } finally {
      setOgSaving(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [outline.saveChapter, outline.chaptersMap, chapterRef, ogForm, vol, chMeta, wb]);

  // 3s 静默后台保存（不改 status；设计稿之外的应用侧扩展，已登记 ADJUSTMENTS）
  const ogKey = JSON.stringify(ogForm);
  useEffect(() => {
    if (ogLoadingRef.current) return;
    if (ogKey === ogSnapRef.current) return;
    // 校验不过时静默跳过（不打扰），待用户补齐后下一次输入触发重试
    if (ogFormIssues(ogForm).length > 0) return;
    const t = setTimeout(() => {
      const beforeExit = String(outline.chaptersMap.get(chapterRef)?.ladder_exit ?? "").trim();
      outline
        .saveChapter(chapterRef, ogToPartial(ogForm, outline.chaptersMap.get(chapterRef)))
        .then(() => {
          ogSnapRef.current = ogKey;
          notifyExitChange(beforeExit);
        })
        .catch(() => {
          /* 静默：失败不打扰，下一次输入重试 */
        });
    }, 3000);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ogKey, chapterRef, outline.saveChapter, outline.chaptersMap, ogForm]);

  /** 确认后以服务端为准回读 status（失败则徽标停在草稿）；返回最新 status */
  const reloadStatus = useCallback(async (): Promise<string> => {
    try {
      const d = await outline.loadChapterData(chapterRef);
      setOgStatus(d.status ?? "");
      return d.status ?? "";
    } catch {
      return ogStatusRef.current;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [outline.loadChapterData, chapterRef]);

  const handleSaveDraft = useCallback(async () => {
    if (!(await saveOg())) return;
    // 草稿保存无缺项 → 自动确认（设计稿行为）
    if (ogGaps(ogForm).length === 0 && ogStatus !== "confirmed") {
      await outline.confirmChapter(chapterRef);
      await reloadStatus();
    }
    toast.success("草稿已保存");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [saveOg, outline.confirmChapter, chapterRef, ogForm, ogStatus, reloadStatus]);

  const handleConfirm = useCallback(async () => {
    if (confirmed || gaps.length > 0) return;
    if (!(await saveOg())) return;
    await outline.confirmChapter(chapterRef);
    const st = await reloadStatus();
    if (st === "confirmed") toast.success(`《${label}》章纲已确认`);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [confirmed, gaps.length, saveOg, outline.confirmChapter, chapterRef, reloadStatus, label]);

  const handleGoWrite = useCallback(async () => {
    void saveOg();
    setChTab("prose");
    // 切页签重渲后才可聚焦
    setTimeout(() => proseRef.current?.focus(), 60);
  }, [saveOg, proseRef]);

  // ── AI 起草章纲（outline-ai-draft）：草稿回填表单不落库，3s 自动保存/手动保存承接 ──
  const [aiDrafting, setAiDrafting] = useState(false);
  const handleAiDraft = useCallback(async () => {
    // 覆盖确认判定覆盖全部章纲格子（含 ai-prompt-crafting 新格子）
    const hasContent =
      [ogForm.summary, ogForm.mood, ogForm.rstrat, ogForm.changes, ogForm.ladder, ogForm.wt].some(
        (v) => String(v ?? "").trim() !== "",
      ) ||
      ogForm.segs.length > 0 ||
      ogForm.scenes.some((sc) =>
        [sc.n, sc.g, sc.o, sc.h].some((v) => v.trim() !== "") || sc.w !== "" || sc.f !== "",
      ) ||
      ogForm.payoffs.some((p) => p.d.trim() !== "");
    if (hasContent && !window.confirm("AI 起草将覆盖当前表单内容（未保存的修改会丢失），继续？")) {
      return;
    }
    setAiDrafting(true);
    try {
      const draft = await draftOutline(projectId, chapterRef);
      const serverData = outline.chaptersMap.get(chapterRef);
      // 以服务端数据为底、草稿覆盖章纲格子；title 保留服务端值
      setOgForm(ogToForm({ ...(serverData ?? {}), ...draft } as never));
      toast.success("AI 草稿已填入表单，检查修改后保存");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "AI 起草失败，请重试");
    } finally {
      setAiDrafting(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, chapterRef, ogForm, outline.chaptersMap]);

  // ── 右栏 AI 辅助·检测族（ai-check）与提示词精修（提案制） ─────────────
  const [aiCheckKind, setAiCheckKind] = useState<AiCheckKind | null>(null);
  const [refineMode, setRefineMode] = useState<RefineMode | null>(null);
  const [gapsLoading, setGapsLoading] = useState(false);
  // 精修采纳后提示词页签需换 key 重挂（内部状态自持，无外部刷新口）
  const [promptReload, setPromptReload] = useState(0);

  /** 章纲缺项补全：缺口清单 → AI 产物回填表单；落库走 3s 自动保存/手动保存。 */
  const handleFillGaps = useCallback(async () => {
    const missing = ogGaps(ogForm)
      .map((g) => GAP_TO_FILL_KEY[g.key])
      .filter(Boolean);
    if (missing.length === 0) return;
    setGapsLoading(true);
    try {
      const fills = await fillOutlineGaps(projectId, chapterRef, missing);
      const patch = ogPatchFromFills(fills);
      const n = Object.keys(patch).length;
      if (n === 0) {
        toast.info("没补出可用的字段，可重试");
        return;
      }
      setOgForm((f) => ({ ...f, ...patch }));
      toast.success(`已补 ${n} 项，检查后保存`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "补全失败，请重试");
    } finally {
      setGapsLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, chapterRef, ogForm]);

  // ── 剧情推演（plot-sim）：弹窗按回合走一遍；收进章纲＝写预期策略后走既有保存链 ──
  const [showSim, setShowSim] = useState(false);
  const handleSimAdopt = useCallback(
    async (line: string): Promise<boolean> => {
      const patched: OgForm = { ...ogForm, rstrat: line };
      const issues = ogFormIssues(patched);
      if (issues.length > 0) {
        toast.error(issues[0]);
        return false;
      }
      try {
        await outline.saveChapter(
          chapterRef,
          ogToPartial(patched, outline.chaptersMap.get(chapterRef)),
        );
        setOgForm(patched);
        ogSnapRef.current = JSON.stringify(patched);
        return true;
      } catch {
        toast.error("章纲保存失败，请重试");
        return false;
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [chapterRef, ogForm, outline.saveChapter, outline.chaptersMap],
  );

  // ── 提示词能力探测（tab 徽标 + PromptPane 共用；quiet：403 不弹升级） ──
  // 提示词子 label PRO-only（ai-prompt-crafting spec：免费隐藏 → 探测也只跑 PRO）
  const [hasPrompts, setHasPrompts] = useState<boolean | null>(null);
  useEffect(() => {
    if (!isPro) {
      setHasPrompts(null);
      return;
    }
    let cancelled = false;
    setHasPrompts(null);
    request(`/novels/${projectId}/chapters/${chapterRef}/prompts`, {
      quiet: true,
    })
      .then((files: unknown) => {
        if (!cancelled)
          setHasPrompts(Array.isArray(files) && files.length > 0);
      })
      .catch(() => {
        if (!cancelled) setHasPrompts(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, chapterRef, isPro]);

  // ── 排版偏好（per-book：pref.book.{pid}.*，全局默认兜底） ─────────────
  const [fs, setFs] = useState<FontSizePref>(() => getBookFontSize(projectId));
  const [lh, setLh] = useState<LineHeightPref>(() => getBookLineHeight(projectId));
  useEffect(() => {
    setFs(getBookFontSize(projectId));
    setLh(getBookLineHeight(projectId));
  }, [projectId]);

  // ── 专注模式：body.focus + Esc 退出（卸载兜底清 class） ───────────────
  const [focusMode, setFocusMode] = useState(false);
  useEffect(() => {
    document.body.classList.toggle("focus", focusMode);
    if (!focusMode) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setFocusMode(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [focusMode]);
  useEffect(() => () => document.body.classList.remove("focus"), []);

  // ── 归档（弹窗确认，#modalArchive 口径；摘要开关 per-book） ───────────
  const handleArchive = useCallback(async () => {
    if (archived || wordCount === 0) return;
    const ok = await store.archive({ aiSummary: getBookArchiveAiSummary(projectId) });
    if (ok) {
      // chapter-rewrite：存在下游「基于旧设定」章时在归档提示里点名（原型口径）
      const hasStaleDownstream = outline.volumes.some((v) =>
        v.chapters.some((c) => c.stale),
      );
      toast.success(
        hasStaleDownstream
          ? `《${label}》已归档 · 只读（下游章节标记「基于旧设定」）`
          : `《${label}》已归档 · 只读`,
      );
    }
  }, [archived, wordCount, projectId, label, store]);

  // ── chapter-rewrite：本章保存成功且仍带「基于旧设定」→ 刷新树让角标消失
  //    （后端在单写入口已清 stale；树只在归档/增删事件刷新，这里补一次）
  useEffect(() => {
    if (store.saveState === "saved" && chMeta?.stale) {
      void onTreeRefresh();
      void outline.refetchTree();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [store.saveState, chMeta?.stale]);

  // ── 重写这一章（chapter-rewrite）：flush → 合成端点（快照+解锁+下游置位）
  //    → 正文页签聚焦改写；树刷新承接旧稿分组与「基于旧设定」角标 ──────────
  const [showRewrite, setShowRewrite] = useState(false);
  const [rewriting, setRewriting] = useState(false);
  const handleRewriteConfirm = useCallback(async () => {
    setRewriting(true);
    try {
      await store.flush(); // 旧稿快照必须先于存盘（防 1.5s 防抖窗口丢最后一段）
      const d = (await api.post(
        `/novels/${projectId}/chapters/${chapterRef}/rewrite`,
        {},
      )) as { ghost_ref: string; unarchived: boolean; stale_marked: number };
      setShowRewrite(false);
      await store.reload(); // 源章解锁后的状态（归档→可写）
      await onTreeRefresh(); // 左树（useWorkbench）：旧稿分组 + 下游角标
      await outline.refetchTree(); // chMeta/落点树（useOutline）
      setChTab("prose");
      toast.success(
        d.unarchived
          ? "旧稿已留存 · 本章已解锁：改完归档即写回主线"
          : "旧稿已留存：改完归档即写回主线",
      );
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "重写失败，请重试");
    } finally {
      setRewriting(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, chapterRef, store, onTreeRefresh, outline.refetchTree]);

  // ── 恢复编辑（退出归档只读；换皮不减功能——banner 内入口） ────────────
  const handleUnarchive = useCallback(async () => {
    if (!window.confirm(`确定恢复《${label}》的编辑吗？恢复后本章退出归档只读状态。`))
      return;
    await store.unarchive();
  }, [label, store]);

  // ── 右栏进度数据上抛（ref 防 effect 依赖抖动；切章/卸载置空） ──────────
  const onRailDataRef = useRef(onRailData);
  useEffect(() => {
    onRailDataRef.current = onRailData;
  }, [onRailData]);
  // useChapterData 每渲染返回新对象：unarchive 走 ref，依赖保持原基元集
  // （否则 effect 每渲染必跑 → onRailData setState → 无限循环）
  const unarchiveRef = useRef(store.unarchive);
  unarchiveRef.current = store.unarchive;
  useEffect(() => {
    // 章纲统计（右栏 AI 辅助·章纲页签）：归档门槛/计划字数/关键事件/出场角色
    const keyLines = ogForm.keys.split("\n").filter((x) => x.trim());
    const castLines = ogForm.chars.split("\n").filter((x) => x.trim());
    const wtParsed = parseInt(ogForm.wt, 10);
    onRailDataRef.current({
      wordCount,
      targetWords,
      setTargetWords,
      archived,
      bookWords,
      unarchive: unarchiveRef.current,
      // storyline col-ai：右栏 AI 辅助随页签切换
      tab: chTab,
      chapterRef,
      ogStats: {
        reqOk: 6 - ogGaps(ogForm).length,
        planWords: Number.isFinite(wtParsed) && wtParsed > 0 ? wtParsed : (targetWords ?? null),
        keyCount: keyLines.length,
        castCount: castLines.length,
        missingLabels: ogGaps(ogForm).map((g) => g.label),
      },
      canAiDraft: isPro && !archived,
      aiDrafting,
      onAiDraft: () => void handleAiDraft(),
      onSimulate: () => setShowSim(true),
      onStyleSuggest: () => setStyleSuggestSignal((n) => n + 1),
      onFillGaps: () => void handleFillGaps(),
      gapsLoading,
      onAiCheck: setAiCheckKind,
      onPromptRefine: setRefineMode,
    });
    return () => onRailDataRef.current(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wordCount, targetWords, setTargetWords, archived, bookWords, chTab, ogForm, chapterRef, aiDrafting, gapsLoading, handleFillGaps]);

  // ── 文风建议信号（右栏 AI 助手触发 → StyleShadowPane 内执行拉取；2026-09-20
  //    AI 入口收口右栏：页签 body 不再设 AI 按钮，建议结果仍在页签内逐项采纳） ──
  const [styleSuggestSignal, setStyleSuggestSignal] = useState(0);

  // ── 页签徽标 ──────────────────────────────────────────────────────────
  const ogCnt =
    confirmed
      ? { cls: "cnt ok", text: "已确认" }
      : gaps.length
        ? { cls: "cnt err", text: `缺 ${gaps.length} 项` }
        : { cls: "cnt warn", text: "草稿" };
  const promptCnt = hasPrompts
    ? { cls: "cnt warn", text: "已自定义" }
    : { cls: "cnt ok", text: "自动组装" };
  const proseCnt = {
    cls: "cnt",
    text: wordCount ? `${fmt(wordCount)} 字` : "空章",
  };

  const saveView =
    saveState === "autosaving"
      ? { cls: "save-state saving", text: "保存中…" }
      : saveState === "unsaved"
        ? { cls: "save-state dirty", text: "未保存" }
        : saveState === "failed"
          ? { cls: "save-state dirty", text: "保存失败" }
          : { cls: "save-state saved", text: "已自动保存" };

  return (
    <div className="col-editor">
      <header className="e-head e-head-row">
        <div className="e-head-main">
          <p className="e-kicker">{volLabel}</p>
          <h2 className="e-title">{label}</h2>
          <div className="e-meta">
            <span className="tag">{archived ? "已归档" : wordCount ? "草稿" : "拟定"}</span>
            <span className="tag">{fmt(wordCount)} 字</span>
          </div>
        </div>
        <span className="prose-ctrls">
          <span className="seg" role="group" aria-label="字号">
            {(
              [
                ["fs-s", "小"],
                ["fs-m", "中"],
                ["fs-l", "大"],
              ] as [FontSizePref, string][]
            ).map(([v, t]) => (
              <button
                key={v}
                className={fs === v ? "on" : undefined}
                onClick={() => {
                  setFs(v);
                  setBookFontSize(projectId, v);
                }}
              >
                {t}
              </button>
            ))}
          </span>
          <span className="seg" role="group" aria-label="行距">
            {(
              [
                ["lh-tight", "紧凑"],
                ["lh-comfy", "舒适"],
                ["lh-loose", "宽松"],
              ] as [LineHeightPref, string][]
            ).map(([v, t]) => (
              <button
                key={v}
                className={lh === v ? "on" : undefined}
                onClick={() => {
                  setLh(v);
                  setBookLineHeight(projectId, v);
                }}
              >
                {t}
              </button>
            ))}
          </span>
          <span className="tsep" />
          <button
            className="icon-btn"
            title="专注模式"
            onClick={() => {
              const next = !focusMode;
              setFocusMode(next);
              toast.info(next ? "专注模式 · 按 Esc 退出" : "已退出专注模式");
            }}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5" />
            </svg>
          </button>
          <button className="btn btn-ghost btn-sm" onClick={() => setShowHistory(true)}>
            版本历史
          </button>
          <button
            className="btn btn-secondary btn-sm"
            disabled={archived || wordCount === 0}
            title={archived ? "本章已归档" : wordCount === 0 ? "空章无需归档" : undefined}
            onClick={() => setShowArchive(true)}
          >
            归档本章
          </button>
        </span>
      </header>

      <div className="ch-tabs" role="tablist" aria-label="章节对象">
        {(
          [
            ["og", "章纲", ogCnt],
            ["prose", "正文", proseCnt],
            // 提示词子 label PRO-only：免费态隐藏（workbench-3-label spec）
            ...(isPro ? ([["prompt", "提示词", promptCnt]] as const) : []),
            ["settings", "设定", { text: "", cls: "" }],
            ["style", "文风", { text: "", cls: "" }],
            ["relations", "角色关系", { text: "", cls: "" }],
            ["hooks", "伏笔", { text: "", cls: "" }],
            ["actions", "操作", { text: "", cls: "" }],
          ] as const
        ).map(([key, text, cnt]) => (
          <button
            key={key}
            className={`chtab${chTab === key ? " on" : ""}`}
            role="tab"
            aria-selected={chTab === key}
            onClick={() => setChTab(key)}
          >
            {text} <span className={cnt.cls}>{cnt.text}</span>
          </button>
        ))}
      </div>

      {chTab === "prose" && archived && (
        <div className="readonly-banner">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <rect x="4" y="10" width="16" height="10" rx="2" />
            <path d="M8 10V7a4 4 0 018 0v3" />
          </svg>
          <span>
            本章已归档 · <b>只读</b>。如需修改，可在版本历史中恢复后重新归档。
          </span>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => void handleUnarchive()}
          >
            恢复编辑
          </button>
        </div>
      )}

      <ProsePane
        ref={proseRef}
        projectId={projectId}
        chapterRef={chapterRef}
        fs={fs}
        lh={lh}
        hidden={chTab !== "prose"}
        onAIStateChange={onAIStateChange}
        resumeScroll={resumeScrollMemo}
        onWriteProgress={onWriteProgress}
        locked={
          ghostOf
            ? { reason: "旧稿支线 · 只读" }
            : frontierLocked && chTab === "prose"
              ? { reason: "还不能写这一章——先完成前面的章节" }
              : undefined
        }
      />

      {chTab === "settings" && (
        <div className="settings-pane" data-od-id="settings-pane">
          <SettingsChangelogPane
            projectId={projectId}
            chapterRef={chapterRef}
          />
        </div>
      )}

      {chTab === "style" && (
        <div className="style-pane" data-od-id="style-pane">
          <StyleShadowPane
            projectId={projectId}
            chapterRef={chapterRef}
            archived={archived}
            suggestSignal={styleSuggestSignal}
          />
        </div>
      )}

      {chTab === "relations" && (
        <div className="relations-pane" data-od-id="relations-pane">
          <RelationsGraphPane projectId={projectId} chapterRef={chapterRef} />
        </div>
      )}

      {chTab === "hooks" && (
        <div className="hooks-wrap" data-od-id="hooks-wrap">
          <HooksPane projectId={projectId} chapterRef={chapterRef} />
        </div>
      )}

      {chTab === "actions" && (
        <div className="actions-pane" data-od-id="actions-pane">
          {!ghostOf && (store.chapter?.prose ?? "").trim().length > 0 && (
            <div className="revert-card" data-od-id="rewrite-card">
              <p className="rc-title">重写这一章</p>
              <p className="rc-desc">
                打开写作窗口就地替换本章。旧稿转入旧稿支线（只读留存，可随时点开查看）；其后章节挂「基于旧设定」角标。
              </p>
              <button
                className="btn btn-secondary btn-sm"
                data-od-id="rewrite-btn"
                data-testid="rewrite-btn"
                disabled={rewriting}
                onClick={() => setShowRewrite(true)}
              >
                重写这一章
              </button>
            </div>
          )}
          {!ghostOf && (
            <div className="revert-card" data-od-id="revert-card">
              <p className="rc-title">回退到这里</p>
              <p className="rc-desc">
                把主线收回本章：之后的章节转入旧稿支线只读保留，其派生的设定、关系与伏笔按章序清除。不可撤销。
              </p>
              <button
                className="btn btn-secondary btn-sm"
                data-od-id="revert-btn"
                onClick={() => {
                  if (
                    window.confirm(
                      "回退后，本章之后的章节将转入旧稿支线（只读保留），其派生的设定/关系/伏笔会被清除。确定回退？",
                    )
                  ) {
                    onRevert(chapterRef);
                  }
                }}
              >
                回退到这里
              </button>
            </div>
          )}
          <ReconcilePane
            projectId={projectId}
            chapterRef={chapterRef}
            archived={archived}
            isPro={isPro}
          />
        </div>
      )}

      <ArchiveModal
        open={showArchive}
        onClose={() => setShowArchive(false)}
        onConfirm={() => void handleArchive()}
        isPro={isPro}
      />
      <RewriteModal
        open={showRewrite}
        onClose={() => setShowRewrite(false)}
        chapterLabel={label}
        busy={rewriting}
        onConfirm={() => void handleRewriteConfirm()}
      />
      <HistoryModal
        open={showHistory}
        onClose={() => setShowHistory(false)}
        projectId={projectId}
        chapterRef={chapterRef}
        label={label}
        onRestored={() => {
          void store.reload();
          void wb.refresh();
        }}
      />

      {chTab === "og" && (
        <OgPane
          form={ogForm}
          characterNames={characterNames}
          label={label}
          onPatch={(patch) => setOgForm((f) => ({ ...f, ...patch }))}
          gaps={gaps}
          confirmed={confirmed}
          saving={ogLoading || ogSaving}
          onSaveDraft={() => void handleSaveDraft()}
          onConfirm={() => void handleConfirm()}
          onGoWrite={() => void handleGoWrite()}
        />
      )}

      <SimModal
        open={showSim}
        onClose={() => setShowSim(false)}
        projectId={projectId}
        chapterRef={chapterRef}
        chapterLabel={label}
        planWords={parseInt(ogForm.wt, 10) || targetWords || undefined}
        onAdopt={handleSimAdopt}
      />

      {chTab === "prompt" && (
        <PromptPane
          key={promptReload}
          projectId={projectId}
          chapterRef={chapterRef}
          title={label}
          hasPrompts={hasPrompts}
        />
      )}

      <AiCheckModal
        open={aiCheckKind !== null}
        onClose={() => setAiCheckKind(null)}
        projectId={projectId}
        chapterRef={chapterRef}
        chapterLabel={label}
        kind={aiCheckKind}
      />
      <RefinePromptModal
        open={refineMode !== null}
        onClose={() => setRefineMode(null)}
        projectId={projectId}
        chapterRef={chapterRef}
        chapterLabel={label}
        mode={refineMode}
        onAdopted={() => setPromptReload((n) => n + 1)}
      />

      <div className="editor-status" hidden={chTab !== "prose"}>
        <span className="num">{fmt(wordCount)} 字</span>
        <span className="right">
          {saveState === "failed" ? (
            <button
              className="save-state dirty"
              style={{ padding: 0, border: "none", background: "none", font: "inherit", cursor: "pointer" }}
              onClick={() => void store.retry()}
              data-testid="save-retry"
            >
              <span className="num">保存失败 · 重试</span>
            </button>
          ) : (
            <span className={saveView.cls}>
              <span className="num">{saveView.text}</span>
            </span>
          )}
          {aiState.streaming && (
            <span className="ai-streaming">
              <span className="pulse" />
              AI 正在生成…
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => proseRef.current?.stopWriting()}
              >
                停止
              </button>
            </span>
          )}
        </span>
      </div>
    </div>
  );
}
