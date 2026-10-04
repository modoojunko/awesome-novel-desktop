import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "@/lib/api";
import ProContainer from "@/components/novel/ProContainer";
import OnboardingCard from "@/components/novel/OnboardingCard";
import OutlineTree from "@/components/novel/workbench/OutlineTree";
import VolumeWorkspace, { type VolumeRailData } from "@/components/novel/workbench/VolumeWorkspace";
import ChapterWorkspace from "@/components/novel/workbench/ChapterWorkspace";
import SettingsView from "@/components/novel/workbench/SettingsView";
import PreviewView from "@/components/novel/workbench/PreviewView";
import ManuscriptDownloadModal from "@/components/novel/workbench/ManuscriptDownloadModal";
import Rail, { type RailChapterData } from "@/components/novel/workbench/Rail";
import { VolumePlanModal } from "@/components/novel/workbench/VolumePlanModal";
import { PickCardsModal } from "@/components/novel/workbench/PickCardsModal";
import type { VolumePlanCard } from "@/lib/volumePlanApi";
import { ChapterPlanModal } from "@/components/novel/workbench/ChapterPlanModal";
import { useChapterPlan } from "@/hooks/useChapterPlan";
import { useVolumePlan } from "@/hooks/useVolumePlan";
import type { VolumeExpandDraft } from "@/lib/volumePlanApi";
import { AiModal, UnlockModal } from "@/components/novel/workbench/modals";
import UpgradeModal from "@/components/novel/UpgradeModal";
import AcctMenu from "@/components/AcctMenu";
import BookPrefsModal from "@/components/novel/BookPrefsModal";
import type { SelectionCapture } from "@/lib/selection";
import {
  INITIAL_PROSE_AI_STATE,
  type ProseAIState,
  type ProseHandle,
} from "@/components/novel/workbench/ProsePane";
import { useWorkbench } from "@/hooks/useWorkbench";
import { useOutline } from "@/hooks/useOutline";
import { useProject } from "@/hooks/useProject";
import { useNovelState } from "@/hooks/useNovelState";
import { useOnboarding } from "@/hooks/useOnboarding";
import { GENRE_PENDING_LABEL } from "@/lib/genreVocab";
import { useTier } from "@/hooks/useTier";
import { toast } from "@/lib/toast";
import { BRAND } from "@/lib/brand";
import { isLoggedIn } from "@/lib/auth";
import { cnNum, isDefaultTitle } from "@/lib/nodeTitle";
import { track } from "@/lib/metrics";
import { getLastWriteSession, type LastWriteSession } from "@/lib/prefs";
import { revertToChapter } from "@/lib/reconcileApi";
import { chapterNoOf, nextVolNo as nextVolumeNo, parseChapterRef, volNoOf } from "@/lib/chapterRef";

// ---------------------------------------------------------------------------
// NovelWorkspace — book.html 复刻（PR 3：壳 + 大纲树 + 章对象工作台）
//   appbar（行头归一：logo 即返回 · 书名双击改名 · 题材 · 当前主线定位 · 账户胶囊）
//   modnav（设定 N/7 · 写作 N/N 章纲 · 预览，默认写作视图）
//   写作 = three-col（树 / 中栏 / 右栏）常驻挂载（.view.on 切换保正文脏状态）
//   设定 = two-col（SettingsView，PR 4 复刻 #viewSettings）
//   预览 = 只读树 + 只读排版（PR 4 复刻 #viewPreview）
// ---------------------------------------------------------------------------

export default function NovelWorkspace() {
  const { id } = useParams<{ id: string }>();
  const wb = useWorkbench();
  const {
    view,
    setView,
    project,
    volumes,
    selectedId,
    selectedRef,
    viewPayload,
    focusNode,
    clearSelection,
    selectVolume,
    refresh,
    createVolume,
    createChapter,
  } = wb;
  const { updateProject } = useProject();
  const { isPro } = useTier();
  const projectId = project?.id ?? "";

  const outline = useOutline(projectId);
  const { settingsDone, settingsStatus, confirmedStatus, charStale, confirmSetting } = useOnboarding(projectId, []);

  const settingsDirtyRef = useRef(false);
  const handleSettingsDirty = useCallback((v: boolean) => {
    settingsDirtyRef.current = v;
  }, []);

  // 设定确认后刷新 PRO phase-status（ProPhaseSurface 常驻于 ProContainer）
  const phaseRefetchRef = useRef<() => void>(() => {});
  const registerPhaseRefetch = useCallback((fn: () => void) => {
    phaseRefetchRef.current = fn;
  }, []);
  const handleConfirmSetting = useCallback(
    async (type: string) => {
      const ok = await confirmSetting(type);
      if (ok) phaseRefetchRef.current();
      return ok;
    },
    [confirmSetting],
  );

  // ── 卷编辑态脏守卫（VolumePanel 上抛 ref；切节点/跳章前拦截） ────────
  const volumeDirtyRef = useRef(false);
  const guardedLeave = useCallback(() => {
    if (!volumeDirtyRef.current) return true;
    if (!window.confirm("卷信息有未保存的修改，确定离开吗？")) return false;
    volumeDirtyRef.current = false;
    return true;
  }, []);
  const handleVolumeDirty = useCallback((dirty: boolean) => {
    volumeDirtyRef.current = dirty;
  }, []);
  const handleChapterJump = useCallback(
    (ref: string) => {
      if (!guardedLeave()) return;
      focusNode(ref);
    },
    [focusNode, guardedLeave],
  );

  // ── 卷视图（四页签整页）＋右栏卷语境数据通路（onRailData 同构；卸载即清空） ──
  const [volumeRailData, setVolumeRailData] = useState<VolumeRailData | null>(null);
  const handleVolumeRail = useCallback((d: VolumeRailData | null) => {
    setVolumeRailData(d);
  }, []);

  // ── 选中节点解析：章 → 章对象工作台；卷 → 卷视图（四页签） ──────────────
  // ref 语法单源（chapterRef）：主线与旧稿 `-r{8hex}` 双形制都算「章对象」
  const chapterRef =
    selectedRef && parseChapterRef(selectedRef) ? selectedRef : null;
  const volumeSelId =
    !chapterRef && selectedId && /^vol-\d+$/.test(selectedId) ? selectedId : null;

  // 未选中卷（空书/章选中态）时清残留，防右栏出现已卸载卷的统计
  useEffect(() => {
    if (!volumeSelId) setVolumeRailData(null);
  }, [volumeSelId]);

  // 右栏「去补卷纲」→ 中栏切回卷纲页签（c-split-to-chapters-tab；autoCheckSeq 同款信号）
  const [goOutlineSeq, setGoOutlineSeq] = useState(0);

  // ── novelbar：书名双击改名（#164 口径：名称即标题且必填） ─────────────
  const [nameDraft, setNameDraft] = useState<string | null>(null);
  const commitRename = useCallback(async () => {
    const next = (nameDraft ?? "").trim();
    setNameDraft(null);
    if (!project?.id || !next || next === project.name) return;
    try {
      const updated = await api.renameNovel(project.id, next);
      updateProject({ name: updated.name });
    } catch {
      toast.error("重命名失败，请重试");
    }
  }, [nameDraft, project, updateProject]);
  // 题材标签与书架卡片胶囊同源（后端 `genre_label`：新契约核心承诺 → 老书历史来源）；
  // 空值＝题材未设定 → 「待定题材」占位（用户 2026-09-10 拍板），标签位恒在。
  const genreLabel = (project?.genre_label || GENRE_PENDING_LABEL) as string;

  // ── AI ref 链：正文编辑器实例 + 状态（右栏 AI 工具与中栏共用） ─────────
  const proseRef = useRef<ProseHandle | null>(null);
  const [aiState, setAIState] = useState<ProseAIState>(INITIAL_PROSE_AI_STATE);

  // ── 页签回默认主页（c-write-home-rail-anchor）：三个 modnav 页签都是「回该页默认落点」──
  //   写作＝书主页（清选中）；设定＝默认面板（第一项「简介」）；预览＝全书首章。
  //   重复点当前页签也回默认（不是无操作）；任一路径先过守卫，取消则留在原位。
  const [settingsHomeSeq, setSettingsHomeSeq] = useState(0);
  const [previewHomeSeq, setPreviewHomeSeq] = useState(0);
  const goTab = useCallback(
    (next: "workbench" | "advanced-settings" | "archives") => {
      const leavingSettings = view === "advanced-settings" && next !== "advanced-settings";
      if (leavingSettings && settingsDirtyRef.current) {
        const ok = window.confirm(
          "当前设定有未保存的修改，离开将丢失这些修改。确定继续吗？",
        );
        if (!ok) return;
      }

      if (next === "advanced-settings") {
        if (view === "advanced-settings") {
          // 已在设定 → 拨回默认面板（脏表单先确认，与离开设定同一套守卫）
          if (
            settingsDirtyRef.current &&
            !window.confirm("当前设定有未保存的修改，回到默认面板将丢失这些修改。确定继续吗？")
          )
            return;
          settingsDirtyRef.current = false;
          setSettingsHomeSeq((n) => n + 1);
          return;
        }
        settingsDirtyRef.current = false;
        setView(next);
        return;
      }

      if (next === "archives") {
        // 进预览：定档一律首章（PreviewView 不再继承写作页当前章）
        if (view === "archives") setPreviewHomeSeq((n) => n + 1);
        setView(next);
        return;
      }

      // 写作 → 书主页：卷纲脏 / 正文 AI 流式中先确认
      if (!guardedLeave()) return;
      if (
        aiState.streaming &&
        !window.confirm("AI 正在生成正文，回书主页会中断这次生成。确定继续吗？")
      )
        return;
      clearSelection();
      setView("workbench");
    },
    [view, setView, guardedLeave, clearSelection, aiState.streaming],
  );

  // ── 右栏本章进度数据（ChapterWorkspace 实时上抛；含 target 编辑器） ────
  const [railData, setRailData] = useState<RailChapterData | null>(null);
  const bookWords = useMemo(
    () =>
      volumes.reduce(
        (sum, v) =>
          sum + v.chapters.reduce((s, c) => s + (c.word_count ?? 0), 0),
        0,
      ),
    [volumes],
  );
  /** 全书已归档章数（书主页卡进度眉标） */
  const archivedTotal = useMemo(
    () => volumes.reduce((a, v) => a + v.chapters.filter((c) => c.archived).length, 0),
    [volumes],
  );

  // chapter-rewrite：当前章之后的主线「基于旧设定」章计数（右栏操作页签统计）
  const staleDownstream = useMemo(() => {
    if (!chapterRef) return undefined;
    const vol = volNoOf(chapterRef);
    const ch = chapterNoOf(chapterRef);
    if (!ch) return undefined;
    let n = 0;
    for (const v of volumes) {
      for (const c of v.chapters) {
        const cv = volNoOf(`${v.name}-ch-${c.chapter}`);
        const after = cv > vol || (cv === vol && c.chapter > ch);
        if (after && c.stale) n += 1;
      }
    }
    return n;
  }, [volumes, chapterRef]);

  const sideText =
    view === "advanced-settings"
      ? "设定 · 若干项，确认即作为 AI 上下文（可选）"
      : view === "archives"
        ? "预览 · 只读正文，通读全篇"
        : "写作 · 卷有卷纲；点章即可配章纲、提示词并写正文";

  // ── 升级 PRO 弹窗（novelbar / 右栏 locked 卡共用） ────────────────────
  const [showUpgrade, setShowUpgrade] = useState(false);
  // 下载成稿弹层（manuscript-download）：挂壳层——预览视图条件挂载，挂预览内切视图会丢轮询/会话记忆
  const [showDownload, setShowDownload] = useState(false);
  const onUpgrade = useCallback(() => setShowUpgrade(true), []);

  // ── 只读章 AI 解锁链（真 bug #1/#2 修复，book.html openAiModal 链） ────
  // 归档章点任意 AI 写入工具 → 先弹「解除只读」→ 确认后 unarchive 并续跑原动作；
  // 生成正文经 AiModal（提示词预览/编辑），其余工具直接执行。
  type AiAction =
    | { kind: "write" }
    | { kind: "selection"; mode: "polish" | "expand" | "compress"; capture: SelectionCapture | null };

  const [showUnlock, setShowUnlock] = useState(false);
  const [showAiModal, setShowAiModal] = useState(false);
  // 生成已启动的信号（计数器）：ChapterWorkspace 收到即切正文页签 + 聚焦（真 bug #2）
  const [aiWriteSignal, setAiWriteSignal] = useState(0);
  // 提示词落库信号（c-prompt-tab-retire）：弹窗润色/存稿后右栏提示词状态行刷新
  const [promptSavedSignal, setPromptSavedSignal] = useState(0);
  // 弹窗确认回调读取最新待续跑动作（闭包防串态）
  const pendingAiRef = useRef<AiAction | null>(null);

  const runAiAction = useCallback((action: AiAction) => {
    if (action.kind === "write") {
      setShowAiModal(true);
      return;
    }
    if (action.capture) {
      if (action.mode === "polish") proseRef.current?.polish(action.capture);
      else if (action.mode === "expand") proseRef.current?.expand(action.capture);
      else proseRef.current?.compress(action.capture);
    } else {
      toast.info("请先在正文中选中一段文字");
    }
  }, []);

  const requestAi = useCallback(
    (action: AiAction) => {
      if (railData?.archived) {
        pendingAiRef.current = action;
        setShowUnlock(true);
        return;
      }
      runAiAction(action);
    },
    [railData?.archived, runAiAction],
  );

  const handleUnlockConfirm = useCallback(async () => {
    const action = pendingAiRef.current;
    pendingAiRef.current = null;
    if (railData?.archived) await railData.unarchive();
    if (action) runAiAction(action);
  }, [railData, runAiAction]);

  const handleAiConfirm = useCallback((prompt: string) => {
    setAiWriteSignal((n) => n + 1);
    proseRef.current?.startWriting(prompt || undefined);
  }, []);

  // PreviewView 挂载即调 onRefresh 且以它为 effect 依赖——内联箭头每次渲染都是
  // 新引用，会与 refresh→setVolumes→重渲染结成死循环（预览态每 ~9ms 打一次
  // GET /volumes）。必须 memo 住引用，只在 refresh 本身变化时才换新。
  const handleArchivesRefresh = useCallback(() => void refresh(), [refresh]);

  // ── 顶栏「本书偏好」：账户面板入口项（原全局 Navbar 挂点随行头归一迁入） ──
  const [showBookPrefs, setShowBookPrefs] = useState(false);

  // ── 顶栏主线定位（行头归一，book.html updateBarHere 同口径）：
  //    续写口径（用户拍板 09-16）＝「上次写到的章」优先（本机 last_write 会话），
  //    无记录回落「主线端点＝首个未归档章」（#383 frontier），再回落全归档的
  //    「待写」占位；卷面进度 = 该卷已归档/总章数。
  //    数据源 wb.volumes（chapter:archived 事件即刷新）。
  const [lastWrite, setLastWrite] = useState<LastWriteSession | null>(() =>
    getLastWriteSession(id ?? ""),
  );
  const [resumeSignal, setResumeSignal] = useState<{
    ref: string;
    scroll: number;
    n: number;
  } | null>(null);

  interface HereTarget {
    ref: string;
    no: number;
    title: string;
    state: "draft" | "planned" | "pending";
    writable: boolean;
    scroll: number;
    volNo: number;
    archivedN: number;
    total: number;
  }
  // 主线统计（下载成稿摘要用）：下载口径 = 有正文的章（后端装配只收 has_prose，
  // spec「空章跳过：下载摘要的章数等于有正文的章数」——与预览概览的全量口径不同源）
  const msStats = useMemo(
    () => ({
      chapters: volumes.reduce(
        (a, v) => a + v.chapters.filter((c) => c.has_prose ?? c.word_count > 0).length,
        0,
      ),
      words: volumes.reduce(
        (a, v) =>
          a +
          v.chapters
            .filter((c) => c.has_prose ?? c.word_count > 0)
            .reduce((b, c) => b + (c.word_count || 0), 0),
        0,
      ),
    }),
    [volumes],
  );

  const hereTarget = useMemo<HereTarget | null>(() => {
    type Ch = (typeof volumes)[number]["chapters"][number];
    type Hit = { v: (typeof volumes)[number]; c: Ch };
    type Pick = Hit & { pending: boolean };
    const findByRef = (ref: string): Hit | null => {
      const volName = `vol-${volNoOf(ref)}`;
      const chNo = chapterNoOf(ref);
      if (!volName || !chNo) return null;
      const v = volumes.find((x) => x.name === volName);
      const c = v?.chapters.find((x) => x.chapter === chNo);
      return v && c ? { v, c } : null;
    };
    let pick: Pick | null = null;
    let fromLastWrite = false;
    // 选中章的实时字数（railData）：树上 has_prose 只在归档/增删时刷新，
    // 正在写的章用它补判「草稿」
    const liveWords =
      selectedRef && railData && railData.wordCount > 0 ? selectedRef : null;
    // ① 上次写作会话的章仍「活着」（存在且未归档）→ 端点优先回到那里（#370）
    if (lastWrite) {
      const hit = findByRef(lastWrite.ref);
      if (hit && !hit.c.archived) {
        pick = { ...hit, pending: false };
        fromLastWrite = true;
      }
    }
    // ② 回落：主线上第一个未归档章（草稿/拟定）
    if (!pick) {
      for (const v of volumes) {
        for (const c of v.chapters) {
          if (!c.archived) {
            pick = { v, c, pending: false };
            break;
          }
        }
        if (pick) break;
      }
    }
    // ③ 全归档：主线末端「待写」占位（不落库，续写时创建）
    if (!pick && volumes.length) {
      const last = volumes[volumes.length - 1];
      if (last.chapters.length) {
        const no = (last.chapters[last.chapters.length - 1].chapter ?? 0) + 1;
        pick = {
          v: last,
          c: { chapter: no, title: "待写", word_count: 0, status: "outline" },
          pending: true,
        };
      }
    }
    if (!pick) return null;
    const volNo = Number((pick.v.name.match(/^vol-(\d+)$/) ?? [])[1] ?? 1);
    const no = pick.pending ? (pick.c.chapter as number) : (pick.c.chapter ?? 0);
    const refNow = `${pick.v.name}-ch-${pick.pending ? "" : (pick.c.chapter ?? 0)}`;
    const draft =
      (!pick.pending && !!pick.c.has_prose) ||
      (!pick.pending && liveWords !== null && refNow === liveWords);
    return {
      ref: refNow,
      no,
      title: pick.pending ? "待写" : pick.c.title,
      state: pick.pending ? "pending" : draft ? "draft" : "planned",
      writable: true, // 端点章恒可写
      // 草稿端点＝上次写作章：续写仍回到上次退出前的滚动位置（#370 口径在端点内保留）
      scroll:
        fromLastWrite && lastWrite?.ref === refNow ? (lastWrite?.scroll ?? 0) : 0,
      volNo,
      archivedN: pick.v.chapters.filter((c) => c.archived).length,
      total: pick.v.chapters.length,
    };
  }, [volumes, lastWrite, selectedRef, railData]);

  const handleRevert = useCallback(
    async (ref: string) => {
      await revertToChapter(projectId, ref);
      await refresh();
      toast.success("已回退：之后的章节转入旧稿支线");
    },
    [projectId, refresh],
  );
  const handleRevertRef = useRef(handleRevert);
  handleRevertRef.current = handleRevert;
  const onRevert = useCallback(
    (ref: string) => void handleRevertRef.current(ref),
    [],  // 稳定引用：内部经 ref 取最新
  );

  const onResume = useCallback(async () => {
    if (!hereTarget) return;
    if (!guardedLeave()) return;
    // 「待写」占位章：先创建（prototype：新增一章＝拟定，先进章纲），再打开
    if (hereTarget.state === "pending") {
      const created = await createChapter(
        `第${cnNum(hereTarget.no)}章`,
        `vol-${hereTarget.volNo}`,
      );
      if (created) {
        focusNode(created);
        toast.info(`第 ${hereTarget.no} 章已创建，先进章纲`);
      }
      return;
    }
    // 已在该章时不再重设选中（省一次整链重渲染），只走恢复信号
    if (selectedRef !== hereTarget.ref) focusNode(hereTarget.ref);
    setResumeSignal((s) => ({
      ref: hereTarget.ref,
      scroll: hereTarget.scroll,
      n: (s?.n ?? 0) + 1,
    }));
  }, [hereTarget, guardedLeave, focusNode, selectedRef, createChapter]);

  const pct = hereTarget
    ? Math.round(Math.min(1, hereTarget.archivedN / hereTarget.total) * 100)
    : 0;
  /** 「续写」按钮文案说明：顶栏与书主页卡同源（同判据、同 title） */
  const resumeTitle = hereTarget
    ? hereTarget.state === "draft"
      ? "回到上次退出前的位置"
      : hereTarget.state === "pending"
        ? "创建本章并开始写作"
        : "打开这一章的章纲"
    : "";

  // ── 空书起手（c-0vol0ch-empty-state）：零卷零章时给明确起点 ──────────────
  // 建卷两条入口（用户 2026-09-22 拍板）：
  //   ① 手动入口（各处「＋ 新增一卷」＋树头「＋」）→ 四问手写页，让作家填空，不分档位；
  //   ② AI 入口（右栏「规划第N卷（AI）」）→ 按档分流：付费＝三选一抽卡，免费＝四问页。
  /** 右栏「未选中」态数据（volume-plan-ai：卷的验证行单源；四格全书统计已退役） */
  const railIdle = useMemo(
    () => ({
      volumes,
      chapters: volumes.reduce((a, v) => a + v.chapters.length, 0),
    }),
    [volumes],
  );

  // ── 卷下拆章（c-chapter-plan-ai）：双路状态机挂壳层（中栏＝手写；右栏＝AI 三方向）──
  // 目标卷＝此刻的写作位上下文：选中卷用它；选中章用章所属卷；都没选（书主页）用末卷。
  // 打开时**钉住**（planVolRef）：否则左树点章会把 volumeSelId 置空，落点卡「继续拆下一章」
  // 会静默排进第 1 卷（拆章流程必须落回作者正在拆的那一卷）。
  const activeVolRef =
    volumeSelId ??
    (chapterRef ? `vol-${volNoOf(chapterRef)}` : null) ??
    wb.volumes[wb.volumes.length - 1]?.name ??
    "vol-1";
  const [planVolRef, setPlanVolRef] = useState<string | null>(null);
  const planTargetVolRef = planVolRef ?? activeVolRef;
  const chapterPlan = useChapterPlan(
    projectId,
    Number(planTargetVolRef.replace("vol-", "")) || 1,
    planTargetVolRef,
  );
  /** 拆章入口统一走这里：先把目标卷钉住，再开对应卡面 */
  const openChapterPlan = useCallback(
    (src: "manual" | "ai") => {
      setPlanVolRef(activeVolRef);
      if (src === "manual") chapterPlan.openManual();
      else chapterPlan.openAi();
    },
    [activeVolRef, chapterPlan],
  );
  /** 回改入口（spec 5.6）：左树 hover／派生视图行／落点卡三处共用同一张本章卡 */
  const openChapterEdit = useCallback(
    (ref: string) => {
      setPlanVolRef(`vol-${volNoOf(ref)}`);
      void chapterPlan.openEdit(ref);
    },
    [chapterPlan],
  );
  const closeChapterPlan = useCallback(() => {
    setPlanVolRef(null);
    chapterPlan.close();
  }, [chapterPlan]);

  // ── 分卷规划（c-volume-antagonist 终版）：双路状态机挂壳层 ──
  const plan = useVolumePlan(projectId);
  const openPlanVolume = useCallback(
    (volNo: number) => {
      backfillFiredRef.current = false;
      track("plan_entry_open", { tier: isPro ? "pro" : "free" });
      plan.open(volNo, isPro);
    },
    [plan, isPro],
  );
  /** 手动建卷入口：加号一律进四问手写页（作家填空），AI 抽卡只在右栏 */
  const openPlanVolumeManual = useCallback(
    (volNo: number) => {
      backfillFiredRef.current = false;
      track("plan_entry_open", { tier: isPro ? "pro" : "free" });
      plan.open(volNo, isPro, "manual");
    },
    [plan, isPro],
  );
  const handleChapterUnsplit = useCallback(async () => {
    const l = chapterPlan.state.landed;
    if (!l) return;
    try {
      await api.delete(`/novels/${projectId}/chapters/${l.ref}`);
      toast.success("已撤销排上（章号可复用）");
      chapterPlan.consumeLanded();
      void refresh();
    } catch (e) {
      toast.error((e as { message?: string })?.message || "撤销失败");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chapterPlan, projectId]);

  const handleChapterAdopt = useCallback(async () => {
    const r = await chapterPlan.adopt();
    if (r.ok) {
      // 回执与实际动作一致：回改＝保存（没有新章），排上＝新章落列表（c-chapter-plan-guards）
      toast.success(
        r.mode === "edit" ? "已保存——这一章已更新" : "已排上（拟定）——先补章纲再写正文",
      );
      void refresh();
    } else if (r.error) {
      toast.error(r.error);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chapterPlan]);
  const [autoCheck, setAutoCheck] = useState<{ ref: string; seq: number }>({ ref: "", seq: 0 });
  /** 自查条「展开全部」（P1-9：checks 逐条可读，不静默丢弃） */
  const [showChecks, setShowChecks] = useState(false);
  const handleSelectVolume = useCallback(
    (ref: string) => {
      if (!guardedLeave()) return;
      selectVolume(ref);
      setAutoCheck((s) => ({ ref, seq: s.seq + 1 }));
    },
    [selectVolume, guardedLeave],
  );

  const [backfill, setBackfill] = useState<{
    seq: number;
    draft: VolumeExpandDraft;
  } | null>(null);
  const backfillSeqRef = useRef(0);
  const landAfterSaveRef = useRef(false);
  const backfillFiredRef = useRef(false);

  /** 落库三件套：建/更卷（四问＋antagonist＋章数一次写入）＋伏笔入台账（查重） */
  const persistVolume = useCallback(
    async (volNo: number, draft: VolumeExpandDraft) => {
      const target = `vol-${volNo}`;
      const isNew = !volumes.some((v) => v.name === target);
      const title = draft.name?.trim() || `第${cnNum(volNo)}卷`;
      try {
        if (isNew) {
          await api.post(`/novels/${projectId}/volumes`, {
            title, summary: draft.summary, core_conflict: draft.conflict,
            ending: draft.ending, antagonist_type: draft.antagonist_type || null,
            antagonist_line: draft.antagonist_line, chapter_target: draft.chapter_target || null,
          });
        } else {
          await api.put(`/novels/${projectId}/volumes/${target}`, {
            summary: draft.summary, core_conflict: draft.conflict,
            ending: draft.ending, antagonist_type: draft.antagonist_type || null,
            antagonist_line: draft.antagonist_line, chapter_target: draft.chapter_target || null,
          });
        }
      } catch (e: unknown) {
        toast.error((e as { message?: string })?.message || "落卷失败，可重试");
        return false;
      }
      // 伏笔建议入台账（best-effort：失败不回滚卷，提示可补登记）
      const items = [...(draft.plants ?? []).map((d) => ({ description: d, planned_volume_no: volNo })),
                     ...(draft.reveals ?? []).map((d) => ({ description: "揭：" + d, planned_volume_no: volNo }))];
      if (items.length) {
        try {
          const r = (await api.post(`/novels/${projectId}/hooks/batch`, { items })) as {
            data?: { created?: Array<{ code: string }>; skipped?: Array<{ existing_code?: string }> };
          };
          const made = r?.data?.created?.length ?? 0;
          const dup = r?.data?.skipped?.filter((x) => x.existing_code).length ?? 0;
          if (made || dup) {
            toast.success(`第${cnNum(volNo)}卷「${title}」已生成 · ${made} 条伏笔入台账${dup ? ` · ${dup} 条与台账重复已对齐` : ""}`);
          } else {
            toast.success(`第${cnNum(volNo)}卷「${title}」已生成`);
          }
        } catch {
          toast.info(`第${cnNum(volNo)}卷已生成 · 伏笔建议登记失败——卷纲页可补登记`);
        }
      } else {
        toast.success(`第${cnNum(volNo)}卷「${title}」已生成`);
      }
      track("volume_saved", { vol_no: volNo, source: "ai" });
      void outline.refetchTree();
      void refresh();
      return true;
    },
    [projectId, volumes, outline, refresh],
  );

  /** 抽卡确认（付费路）：落库→清选中→落点卡＋自查条可关闭提示。
   *  落库失败（persistVolume 返 false）由 confirmCard 承接：不关弹窗、保留选中可重试
   *  （PRD §6），故此处只在成功时清选中。 */
  const handlePickConfirm = useCallback(
    async (card: VolumePlanCard) => {
      const volNo = plan.state.volNo;
      // 不置 landAfterSaveRef：本路径自己 clearSelection（卷页不挂载 → 该标志无人消费，
      // 留成 true 会让用户下一次在卷页点「保存」时被 handleVolumeSaved 弹出去）
      const ok = await plan.confirmCard(card, (draft) => persistVolume(volNo, draft));
      if (ok) clearSelection();
    },
    [plan, persistVolume, clearSelection],
  );

  /** 免费直建（四问手写页）：答多少建多少。in-flight 闸防双击双发（c-silent-data-guards） */
  const directCreatingRef = useRef(false);
  const [directCreating, setDirectCreating] = useState(false);
  const handleDirectCreate = useCallback(async () => {
    if (directCreatingRef.current) return;
    const a = plan.state.answers;
    const volNo = plan.state.volNo;
    // 同上：本路径自己 clearSelection，不置 landAfterSaveRef
    directCreatingRef.current = true;
    setDirectCreating(true);
    try {
      await api.post(`/novels/${projectId}/volumes`, {
        title: `第${cnNum(volNo)}卷`,
        summary: a.q1.trim(), core_conflict: a.conflict.trim(),
        ending: a.q4.trim(),
        antagonist_type: a.antagonist_type || null,
        antagonist_line: a.antagonist_line.trim(),
      });
      track("desk_manual_create", { vol_no: volNo });
      track("volume_saved", { vol_no: volNo, source: "manual" });
      plan.closeDesk(); // 成功后才关：失败时四问留在弹窗里可直接重试（P2-3）
      toast.success(`第${cnNum(volNo)}卷已建好——进卷纲可改，排第一章就能开写`);
      void outline.refetchTree();
      void refresh();
    } catch (e: unknown) {
      toast.error((e as { message?: string })?.message || "建卷失败，请重试");
      return;
    } finally {
      directCreatingRef.current = false;
      setDirectCreating(false);
    }
    clearSelection();
  }, [plan, projectId, outline, refresh, clearSelection]);

  /** 手写路回填 */
  const startBackfill = useCallback(
    (draft: VolumeExpandDraft) => {
      if (backfillFiredRef.current) return;
      backfillFiredRef.current = true;
      const volNo = plan.state.volNo;
      const target = `vol-${volNo}`;
      if (!volumes.some((v) => v.name === target)) {
        landAfterSaveRef.current = true;
        void (async () => {
          const ref = await createVolume(draft.name?.trim() || `第${cnNum(volNo)}卷`);
          if (!ref) {
            toast.error("建卷失败，请重试——卷纲草稿还留在规划台里");
            return;
          }
          void outline.refetchTree();
        })();
      } else if (selectedId !== target) {
        selectVolume(target);
      }
      backfillSeqRef.current += 1;
      setBackfill({ seq: backfillSeqRef.current, draft });
    },
    [plan.state.volNo, volumes, selectedId, focusNode, createVolume, outline],
  );
  const handlePlanBackfill = useCallback(() => {
    const payload = plan.takeAutoBackfill();
    plan.closeDesk();
    if (payload) startBackfill(payload.draft);
  }, [plan, startBackfill]);
  useEffect(() => {
    if (plan.state.deskOpen || plan.state.deskPhase !== "done") return;
    const payload = plan.takeAutoBackfill();
    if (payload) startBackfill(payload.draft);
  }, [plan.state.deskOpen, plan.state.deskPhase, plan, startBackfill]);
  const handleVolumeSaved = useCallback(() => {
    if (landAfterSaveRef.current) {
      landAfterSaveRef.current = false;
      clearSelection();
    }
  }, [clearSelection]);
  const nextVolNo = nextVolumeNo(volumes); // 最大卷号+1（勿用 length+1：删过中间卷会撞号）
  /** 「＋ 新增一章」：空书先垫第一卷（原型 firstVol 口径），再在主线末端排第一章 */
  const addFirstChapter = useCallback(async () => {
    const last = volumes[volumes.length - 1]?.name;
    if (!last) {
      const volRef = await createVolume(`第${cnNum(1)}卷`);
      if (!volRef) return;
      if (await createChapter(`第${cnNum(1)}章`, volRef)) {
        track("first_chapter_in_vol", { vol_no: 1 });
        toast.success("已垫好第一卷并排上第一章，先写章纲");
      }
      return;
    }
    await createChapter(`第${cnNum(1)}章`, last);
  }, [volumes, createVolume, createChapter]);
  /** 书主页卡「＋ 新增一章」：排到主线末端（末卷的下一章号；零卷回落到先垫第一卷） */
  const addChapterAtEnd = useCallback(async () => {
    const last = volumes[volumes.length - 1];
    if (!last) {
      await addFirstChapter();
      return;
    }
    const no = (last.chapters[last.chapters.length - 1]?.chapter ?? 0) + 1;
    await createChapter(`第${cnNum(no)}章`, last.name);
  }, [volumes, createChapter, addFirstChapter]);

  // 落点卡（volume-plan-ai）：最后一卷就绪态——仅「从未排过章」；曾排过章的书
  // 删空后仍回选章引导（规格判据：localStorage 排章标记，e2e 钉死该口径）
  const totalChapters = railIdle.chapters;
  const everPlanned =
    totalChapters > 0 ||
    localStorage.getItem(`pref.book.${id}.ever_planned`) === "1";
  const lastVol = volumes[volumes.length - 1];
  const lastVolName = lastVol?.name ?? "vol-1";
  const lastVolNo = Number((lastVolName.match(/^vol-(\d+)$/) ?? [])[1] ?? 1);
  const lastVolTitle = lastVol?.title || `第${cnNum(lastVolNo)}卷`;
  /** 在指定卷排第一章（落点卡主入口） */
  const addFirstChapterIn = useCallback(
    async (volName: string) => {
      if (await createChapter(`第${cnNum(1)}章`, volName)) {
        track("first_chapter_in_vol", { vol_no: lastVolNo });
        toast.success("第一章已排上，先写章纲");
      }
    },
    [createChapter, lastVolNo],
  );

  const hereBar = hereTarget ? (
    <>
      <p className="bh-k">当前主线</p>
      <span className="bh-rule" aria-hidden="true" />
      <p className="bh-t">
        <span className="n">第 {hereTarget.no} 章</span>
        {/* 默认名（序号形态）与端点占位「待写」不拼名称——占位已有 bh-tag 徽，避免「第 3 章待写 待写」 */}
        {hereTarget.state === "pending" ||
        isDefaultTitle("章", hereTarget.no, hereTarget.title)
          ? null
          : hereTarget.title}
      </p>
      {hereTarget.state === "draft" && (
        <span className="bh-tag bh-tag-live">草稿</span>
      )}
      {hereTarget.state === "planned" && <span className="bh-tag">拟定</span>}
      {hereTarget.state === "pending" && <span className="bh-tag">待写</span>}
      <div className="bh-prog">
        <span className="bh-vol">
          第{cnNum(hereTarget.volNo)}卷 · {hereTarget.archivedN}/{hereTarget.total}
        </span>
        <span className="prog-bar">
          <span style={{ width: `${pct}%` }} />
        </span>
      </div>
      <button
        className="btn btn-primary btn-sm"
        data-od-id="resume-cta"
        title={resumeTitle}
        onClick={() => void onResume()}
      >
        续写
      </button>
    </>
  ) : volumes.length === 0 ? (
    /* 状态零：空书（原型 hereBarHTML 空书分支）——还没有卷与章节，起手只有建第一卷 */
    <>
      <p className="bh-k">空书</p>
      <span className="bh-rule" aria-hidden="true" />
      <p className="bh-t">
        <span className="n">第 1 章</span>待写
      </p>
      <span className="bh-tag">未开始</span>
      <div className="bh-prog">
        <span className="bh-vol">还没有卷与章节</span>
      </div>
      <button
        className="btn btn-primary btn-sm"
        data-od-id="empty-add-vol"
        title="从一卷卷纲开始这本书"
        onClick={() => openPlanVolumeManual(nextVolNo)}
      >
        ＋ 新增一卷
      </button>
    </>
  ) : null;

  return (
    <div className="wb">
      {/* 应用栏（行头归一，storyline.html 口径）：logo 即返回 · 书名 · 题材 · 当前主线 · 账户 */}
      <header className="appbar appbar-wb">
        <Link className="logo" to="/novels" title="返回我的小说" data-od-id="appbar-logo">
          <span className="logo-mark">{BRAND.mark}</span>
          {BRAND.name}
        </Link>
        <span className="sep" />
        {nameDraft === null ? (
          <span
            className="novel-title serif"
            title="双击重命名"
            onDoubleClick={() => setNameDraft(project?.name ?? "")}
          >
            {project?.name ?? "…"}
          </span>
        ) : (
          <input
            className="input"
            style={{ width: 200, fontWeight: 600 }}
            value={nameDraft}
            autoFocus
            onChange={(e) => setNameDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void commitRename();
              else if (e.key === "Escape") setNameDraft(null);
            }}
            onBlur={() => void commitRename()}
          />
        )}
        <span
          className={`genre-tag${project?.genre_label ? "" : " pending"}`}
          title={genreLabel}
        >
          {genreLabel}
        </span>
        <span className="sep" />
        <div className="bar-here" data-od-id="current-position">
          {hereBar}
        </div>
        {isLoggedIn() && <AcctMenu onBookPrefs={() => setShowBookPrefs(true)} />}
        <BookPrefsModal
          open={showBookPrefs && !!projectId}
          onClose={() => setShowBookPrefs(false)}
          projectId={projectId}
        />
      </header>

      {/* PRO 阶段催促子树：免费态整棵不渲染、零 phase-status 请求 */}
      <ProContainer>
        <ProPhaseSurface
          projectId={projectId}
          source={project?.source}
          onGoSettings={() => goTab("advanced-settings")}
          registerRefetch={registerPhaseRefetch}
          inSettings={view === "advanced-settings"}
        />
      </ProContainer>

      {/* 书内模块导航：设定 / 写作 / 预览（默认写作） */}
      <nav className="modnav">
        <button
          className={`mtab${view === "advanced-settings" ? " on" : ""}`}
          onClick={() => goTab("advanced-settings")}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" width="15" height="15">
            <path d="M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4L16.5 3.5z" />
          </svg>
          设定 <span className="cnt">{settingsDone}/7</span>
        </button>
        <button
          className={`mtab${view === "workbench" ? " on" : ""}`}
          onClick={() => goTab("workbench")}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" width="15" height="15">
            <path d="M4 6h16M4 12h16M4 18h10" />
          </svg>
          写作{" "}
          <span className="cnt">
            {outline.confirmedCount}/{outline.totalChapters} 章纲
          </span>
        </button>
        <button
          className={`mtab${view === "archives" ? " on" : ""}`}
          onClick={() => goTab("archives")}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" width="15" height="15">
            <path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12z" />
            <circle cx="12" cy="12" r="2.5" />
          </svg>
          预览
        </button>
        <span className="spacer" />
        <span className="side">{sideText}</span>
      </nav>

      {/* 写作：three-col 常驻挂载（.view.on 切换，正文脏状态/流式现场不丢） */}
      <div className={`view three-col${view === "workbench" ? " on" : ""}`}>
        {/* 生成中树锁定（c-prose-stream-guard）：捕获层拦一切树内点击（切章/切卷/
            行内新建改名删除都会摧毁流式现场），置灰＋title 指路「停止」；出口＝页签行徽章上的「停止」 */}
        <aside
          className={`col-tree${volumes.length === 0 ? " empty-book" : ""}${aiState.streaming ? " ai-lock" : ""}`}
          title={aiState.streaming ? "生成中 · 点「停止」后再切换" : undefined}
          onClickCapture={(e) => {
            if (!aiState.streaming) return;
            const t = e.target as HTMLElement;
            if (!t.closest("button, .vol-head, .ch")) return;
            e.preventDefault();
            e.stopPropagation();
            toast.info("生成中 · 点「停止」后再切换");
          }}
        >
          <OutlineTree
            wb={wb}
            outline={outline}
            projectId={projectId}
            guardedLeave={guardedLeave}
            // 选中章的实时字数（store 上抛）：删除盘点取 live 数——树的 word_count
            // 只在归档/建删节点时刷新，刚写完就删会用旧值漏报「正文 N 字」
            liveWords={
              chapterRef && railData
                ? { ref: chapterRef, words: railData.wordCount }
                : null
            }
            onAddVolume={() => openPlanVolumeManual(nextVolNo)}
            onAddChapter={() => void addFirstChapter()}
            onEditChapter={openChapterEdit}
          />
        </aside>

        <main className="col-middle">
          {chapterPlan.state.landed ? (
            <div className="e-empty" data-testid="chapter-landing-card">
              <p className="be-k">
                「{chapterPlan.state.landed.title}」已排上（拟定）
              </p>
              <p className="be-desc">
                已带入 {chapterPlan.state.landed.brought} 项
                {chapterPlan.state.landed.items.length > 0 &&
                  `：${chapterPlan.state.landed.items.join("、")}`}
                ；下一章的进场会自动接本章结尾。
                还差 2 项才能开写：必须完成的变化、主情绪。
              </p>
              <p className="be-acts">
                <button
                  className="btn btn-primary"
                  data-testid="chapter-landing-outline"
                  onClick={() => {
                    const l = chapterPlan.consumeLanded();
                    if (l) handleChapterJump(l.ref);
                  }}
                >
                  补这 2 项，开始写
                </button>
                <button
                  className="btn btn-secondary"
                  data-testid="chapter-landing-next"
                  onClick={() => {
                    chapterPlan.consumeLanded();
                    openChapterPlan("manual");
                  }}
                >
                  继续拆下一章
                </button>
                <button
                  className="btn btn-ghost"
                  data-testid="chapter-landing-edit"
                  onClick={() => {
                    const l = chapterPlan.consumeLanded();
                    if (l) openChapterEdit(l.ref);
                  }}
                >
                  改这一章
                </button>
                <button
                  className="btn btn-ghost"
                  data-testid="chapter-landing-unsplit"
                  onClick={() => void handleChapterUnsplit()}
                >
                  撤销排上
                </button>
              </p>
            </div>
          ) : chapterRef ? (
            <ChapterWorkspace
              projectId={projectId}
              chapterRef={chapterRef}
              outline={outline}
              wb={wb}
              isPro={isPro}
              proseRef={proseRef}
              aiState={aiState}
              onAIStateChange={setAIState}
              bookWords={bookWords}
              onRailData={setRailData}
              onWriteProgress={setLastWrite}
              resumeSignal={resumeSignal ?? undefined}
              onRevert={onRevert}
              onTreeRefresh={refresh}
              aiWriteSignal={aiWriteSignal}
              promptSavedSignal={promptSavedSignal}
              onOpenAiModal={() => requestAi({ kind: "write" })}
            />
          ) : volumeSelId ? (
            <VolumeWorkspace
              projectId={projectId}
              volumeRef={volumeSelId}
              wb={wb}
              onGoChapter={handleChapterJump}
              onVolumeMutated={() => void refresh()}
              onDirtyChange={handleVolumeDirty}
              onRailData={handleVolumeRail}
              onSplitManual={() => openChapterPlan("manual")}
              onEditChapter={openChapterEdit}
              outlineSeq={goOutlineSeq}
              backfill={backfill}
              onSaved={handleVolumeSaved}
            />
          ) : (
            <div className="col-panel">
              {volumes.length === 0 ? (
                /* 空书起手卡（作家口径）：自己动手双入口；AI 入口只在右栏 */
                <div className="e-empty" data-od-id="book-empty">
                  <p className="be-mark">设定 {settingsDone}/7 已确认</p>
                  <p className="be-k">这本书怎么开始？</p>
                  <p className="be-t">
                    自己动手：先建一卷、排上第一章就能开写；想让 AI
                    按主线拆分卷，用右侧的 AI 助手。
                  </p>
                  <p className="be-acts">
                    <button
                      className="btn btn-primary"
                      data-od-id="empty-cta-vol"
                      onClick={() => openPlanVolumeManual(nextVolNo)}
                    >
                      ＋ 新增一卷
                    </button>
                    <button
                      className="btn btn-secondary"
                      data-od-id="empty-cta-ch"
                      disabled={wb.creating}
                      onClick={() => void addFirstChapter()}
                    >
                      ＋ 新增一章
                    </button>
                  </p>
                </div>
              ) : totalChapters === 0 && !everPlanned ? (
                /* 落点卡（volume-plan-ai）：有卷从未排章——规划完卷落这里 */
                <div className="e-empty" data-testid="landing-card">
                  <p className="be-mark">
                    第{lastVolNo}卷 · {lastVolTitle} 已就绪
                  </p>
                  <p className="be-k">开始写第一章？</p>
                  <p className="be-t">点左栏的卷排第一章；卷纲随时能回来改。</p>
                  <p className="be-acts">
                    <button
                      className="btn btn-primary"
                      data-testid="landing-add-chapter"
                      disabled={wb.creating}
                      onClick={() => void addFirstChapterIn(lastVolName)}
                    >
                      ＋ 在本卷排第一章
                    </button>
                    <button
                      className="btn btn-secondary"
                      data-testid="landing-open-outline"
                      onClick={() => selectVolume(lastVolName)}
                    >
                      看第{lastVolNo}卷的卷纲
                    </button>
                    <button
                      className="btn btn-secondary"
                      data-testid="landing-add-volume"
                      onClick={() => openPlanVolumeManual(nextVolNo)}
                    >
                      ＋ 新增一卷
                    </button>
                  </p>
                </div>
              ) : (
                /* 书主页卡（页签回默认主页）：有章时的默认落点——进度眉标＋续写＋建书双入口
                   四档角色与同容器另两态一致：be-mark 眉标 / be-k 主句 / be-t 说明 / be-acts 动作 */
                <div className="e-empty" data-testid="write-home">
                  <p className="be-mark" data-testid="home-progress">
                    {volumes.length} 卷 · {totalChapters} 章 · 已归档 {archivedTotal} 章 · 共{" "}
                    {bookWords.toLocaleString("zh-CN")} 字
                  </p>
                  {hereTarget ? (
                    <p className="be-k">
                      接着写第 {hereTarget.no} 章？
                      {/* 「待写」是端点占位不是章名，不拼进问句（顶栏同款口径） */}
                      {hereTarget.state === "pending" ||
                      isDefaultTitle("章", hereTarget.no, hereTarget.title)
                        ? null
                        : hereTarget.title}
                    </p>
                  ) : (
                    <p className="be-k">这本书怎么继续？</p>
                  )}
                  <p className="be-t">
                    在左侧目录里选一章，上面一行页签会展开它的章纲、正文、提示词、设定与关系伏笔，重写与回退收在「操作」页签里。
                  </p>
                  <p className="be-acts">
                    {hereTarget && (
                      <button
                        className="btn btn-primary"
                        data-testid="home-resume"
                        title={resumeTitle}
                        onClick={() => void onResume()}
                      >
                        续写
                      </button>
                    )}
                    <button
                      className="btn btn-secondary"
                      data-testid="home-add-volume"
                      onClick={() => openPlanVolumeManual(nextVolNo)}
                    >
                      ＋ 新增一卷
                    </button>
                    <button
                      className="btn btn-secondary"
                      data-testid="home-add-chapter"
                      disabled={wb.creating}
                      onClick={() => void addChapterAtEnd()}
                    >
                      ＋ 新增一章
                    </button>
                  </p>
                </div>
              )}
            </div>
          )}
        </main>

        <aside className="col-ai">
          <Rail
            mode={chapterRef ? "chapter" : "volume"}
            projectId={projectId}
            isPro={isPro}
            onUpgrade={onUpgrade}
            proseRef={proseRef}
            aiState={aiState}
            data={
              chapterRef
                ? railData
                  ? { ...railData, staleDownstream }
                  : undefined
                : undefined
            }
            volumeData={volumeRailData}
            railIdle={railIdle}
            genreLabel={genreLabel}
            onPlanVolume={openPlanVolume}
            onSplitAi={() => openChapterPlan("ai")}
            onGoOutline={() => setGoOutlineSeq((n) => n + 1)}
            onSelectVolume={handleSelectVolume}
            autoCheckSeq={autoCheck.seq}
            onAiWrite={() => requestAi({ kind: "write" })}
            onAiSelection={(mode, capture) => requestAi({ kind: "selection", mode, capture })}
          />
        </aside>
      </div>

      {/* 设定：two-col（SettingsView 复刻 #viewSettings） */}
      {view === "advanced-settings" && (
        <SettingsView
          projectId={projectId}
          initialPanel={wb.viewPayload?.panel as string | undefined}
          /** 重复点「设定」回默认面板的信号（页签回默认主页） */
          homeSeq={settingsHomeSeq}
          settingsStatus={settingsStatus}
          confirmedStatus={confirmedStatus}
          charStale={charStale}
          confirmSetting={handleConfirmSetting}
          onDirtyChange={handleSettingsDirty}
          onGoWrite={() => goTab("workbench")}
          novelName={project?.name ?? ""}
        />
      )}
      {/* 预览：三栏阅读器（preview-reader，c-preview-reader） */}
      {view === "archives" && (
        <PreviewView
          projectId={projectId}
          volumes={volumes}
          /** 定档一律首章：不继承写作页当前章（页签回默认主页）；重复点「预览」回首章 */
          homeSeq={previewHomeSeq}
          onRefresh={handleArchivesRefresh}
          onGoWrite={() => goTab("workbench")}
          onDownload={() => setShowDownload(true)}
        />
      )}

      {/* 下载成稿（manuscript-download）：弹层在壳层，跨视图轮询保活 */}
      <ManuscriptDownloadModal
        open={showDownload}
        onClose={() => setShowDownload(false)}
        projectId={projectId}
        bookName={project?.name ?? ""}
        stats={msStats}
      />

      {/* 分卷规划双路（c-volume-antagonist）：抽卡（付费默认）＋四问手写页——状态在壳层 */}
      <PickCardsModal
        projectId={projectId}
        plan={plan}
        onConfirm={(card) => void handlePickConfirm(card)}
        onToDesk={plan.toDesk}
        onClose={plan.closePick}
      />
      <VolumePlanModal
        projectId={projectId}
        plan={plan}
        isPro={isPro}
        onUpgrade={onUpgrade}
        onDirectCreate={() => void handleDirectCreate()}
        creating={directCreating}
        onBackfill={handlePlanBackfill}
        onClose={plan.closeDesk}
        onGoSettings={() => goTab("advanced-settings")}
      />

      {/* 卷下拆章（c-chapter-plan-ai）：弹窗＋落点卡（关窗后中栏呈现） */}
      <ChapterPlanModal plan={chapterPlan} onAdopt={() => void handleChapterAdopt()} onClose={closeChapterPlan} />
      {/* 抽卡确认结果：自查条可关闭提示（落点卡已由 clearSelection 承接）。
          checks **逐条可读**（P1-9：只给第一条前 30 字＝静默丢弃其余）——「展开全部」就地看。 */}
      {(() => {
        const r = plan.state.confirmResult;
        if (!r) return null;
        const checks = r.draft.checks;
        return (
          <div className="selfcheck-toast" data-testid="confirm-checks">
            <span>
              AI 自查 {checks.length} 条 ·{" "}
              {checks[0]?.slice(0, 30) ?? "无"}
              {checks.length > 1 ? "…" : ""}
            </span>
            {checks.length > 1 && (
              <button
                className="btn btn-ghost btn-sm"
                data-testid="confirm-checks-all"
                onClick={() => setShowChecks((v) => !v)}
              >
                {showChecks ? "收起" : "展开全部"}
              </button>
            )}
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => {
                setShowChecks(false); // 复位：下一次确认不该自动展开（P3）
                plan.consumeConfirm();
              }}
            >
              知道了
            </button>
          </div>
        );
      })()}
      {showChecks && plan.state.confirmResult && (
        <div className="selfcheck-list" data-testid="confirm-checks-list">
          <ol>
            {plan.state.confirmResult.draft.checks.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ol>
        </div>
      )}


      {/* PR 5 弹窗群：升级 PRO / 只读章 AI 解锁链 / AI 生成（提示词预览） */}
      <UpgradeModal open={showUpgrade} onClose={() => setShowUpgrade(false)} />
      {chapterRef && (
        <>
          <UnlockModal
            open={showUnlock}
            onClose={() => setShowUnlock(false)}
            onConfirm={() => void handleUnlockConfirm()}
          />
          <AiModal
            open={showAiModal}
            onClose={() => setShowAiModal(false)}
            projectId={projectId}
            chapterRef={chapterRef}
            onConfirm={handleAiConfirm}
            onPromptSaved={() => setPromptSavedSignal((n) => n + 1)}
          />
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ProPhaseSurface — PRO 阶段催促子树（免费态不挂载 → useNovelState 零请求）
// ---------------------------------------------------------------------------

function ProPhaseSurface({
  projectId,
  source,
  onGoSettings,
  registerRefetch,
  inSettings,
}: {
  projectId: string;
  source: string | undefined;
  onGoSettings: () => void;
  registerRefetch: (fn: () => void) => void;
  /** 当前是否已在设定页（空书默认落设定 → 不再叠「开始设定」引导卡）。 */
  inSettings: boolean;
}) {
  const { phaseStatus, refetch } = useNovelState(projectId || undefined);

  useEffect(() => {
    registerRefetch(refetch);
    return () => registerRefetch(() => {});
  }, [refetch, registerRefetch]);

  const [onboardingDismissed, setOnboardingDismissed] = useState(() => {
    if (!projectId) return true;
    return localStorage.getItem(`onboarding-dismissed-${projectId}`) === "true";
  });
  const handleDismissOnboarding = useCallback(() => {
    if (!projectId) return;
    setOnboardingDismissed(true);
    localStorage.setItem(`onboarding-dismissed-${projectId}`, "true");
  }, [projectId]);

  const allPhasesPending =
    phaseStatus !== null && Object.values(phaseStatus).every((s) => s === "pending");
  // 已在设定页时不叠引导卡（卡片唯一作用是把人送到设定；空书已默认落设定）
  const showOnboarding = allPhasesPending && !onboardingDismissed && !inSettings;

  return (
    <>
      {showOnboarding && (
        <OnboardingCard
          novelId={projectId}
          source={(source as "ai" | "manual" | "import") ?? "manual"}
          variant={source === "import" ? "imported-novel" : "empty-novel"}
          onDismiss={handleDismissOnboarding}
          onStart={() => {
            handleDismissOnboarding();
            onGoSettings();
          }}
        />
      )}
    </>
  );
}

