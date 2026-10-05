// 章对象工作台（storyline.html 章编辑器复刻）：
//   头部（卷名 kicker + 章标题 + 状态/章纲统计徽章行；专注收在头部右侧，
//   页签条紧贴头部——与卷视图同位，原型 e-head→e-toolbar 两段式；AI 入口全部在右栏）
//   2026-09-27 用户拍板收敛：章纲统计（归档门槛/计划字数/剧情/出场角色）自右栏
//   AI 助手上移头部 meta 行；字号/行距 seg 撤（入口在账号菜单「本书偏好」）；
//   版本历史移页签行右端；归档移操作页签卡片；右栏「本章进度」卡退役，
//   完成度/本书总字数并入头部徽章行——右栏只承载 AI 相关功能（c-rail-ai-only）。
//   八页签（章纲/正文/提示词/设定/文风/角色关系/伏笔/操作）· 点章强制落章纲
//   正文常驻挂载 hidden 切换（脏状态/流式现场不丢）
//   底部状态栏（字数 + 保存四态聚合 + AI 流式指示 + 停止）
// 章纲表单状态提升于此（页签徽标 / 保存 / 3s 静默自动保存共用）。
// PR 5：归档/版本历史改弹窗（原型口径）；AI 按钮走页面级解锁链；
//   生成启动信号（aiWriteSignal）自动切正文页签（真 bug #2）；
//   排版偏好 per-book（pref.book.{pid}.*，全局兜底）。
import { useFeature } from "@/hooks/useTier";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type RefObject,
  useSyncExternalStore,
} from "react";
import OgPane, { flashField } from "./OgPane";
import ArchiveStages, { useElapsedSec } from "./ArchiveStages";
import SimModal from "./SimModal";
import { useNavigate } from "react-router-dom";
import { charactersApi } from "@/lib/charactersApi";
import { StyleShadowPane } from "./StyleShadowPane";
import { SettingsChangelogPane } from "./SettingsChangelogPane";
import { HooksPane } from "./HooksPane";
import { RelationsGraphPane } from "./RelationsGraphPane";
import { dossierApi } from "@/lib/dossierApi";
import {
  RelationChangesSection,
  SettingChangesSection,
} from "./ChangesSections";
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
  PLOT_MAX_ITEMS,
  REQ_FIELDS,
  ogFormIssues,
  ogGaps,
  ogPatchFromFills,
  ogToForm,
  ogToPartial,
  type OgForm,
} from "./chapterForm";
import PlotDrawModal from "./PlotDrawModal";
import AiCheckModal from "./AiCheckModal";
import CastReviewModal from "./CastReviewModal";
import { useChapterData } from "@/hooks/useChapterData";
import {
  registerZhuqueFlush,
  useZhuqueCheck,
} from "@/hooks/useZhuqueCheck";
import ZhuqueHeadStrip from "./zhuqueHeadStrip";
import { getZhuqueShow, subscribeZhuqueShow } from "@/lib/prefs";
import { useHooksLedger } from "@/hooks/useHooksLedger";
import { ogHookHints } from "@/lib/hookHints";
import { usePlotDraw } from "@/hooks/usePlotDraw";
import { useCastReview } from "@/hooks/useCastReview";
import {
  castBackgroundLine,
  type CastWriteOutcome,
  type CastWriteRequest,
} from "@/lib/castReviewApi";
import { isNameTaken } from "@/lib/charactersApi";
import { fillOutlineGaps, type AiCheckKind } from "@/lib/aiCheck";
import type { useOutline } from "@/hooks/useOutline";
import type { useWorkbench } from "@/hooks/useWorkbench";
import { api, errMessage, request } from "@/lib/api";
import { nodeLabel } from "@/lib/nodeTitle";
import {
  getBookArchiveAiSummary,
  getBookFontSize,
  getBookLineHeight,
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
  /** 拥有 ai-plan（标准起）——盘点/抽卡/补缺判据；缺省回落 useFeature("ai-plan")
   *  （测试夹具显式传档用，tier-plan-four-tiers 5.4） */
  hasAiPlan?: boolean;
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
  /** 提示词落库信号（c-prompt-tab-retire）：弹窗润色/存稿后右栏提示词状态行刷新 */
  promptSavedSignal?: number;
  /** 续写恢复信号（顶栏 CTA）：n 递增触发，落正文页签并滚回上次位置 */
  resumeSignal?: { ref: string; scroll: number; n: number };
  /** 写作进度上抛（顶栏 bar-here 跟随显示上次写到的章） */
  onWriteProgress?: (session: { ref: string; scroll: number; ts: number }) => void;
  /** 回退到本章（revert-ghost）：主线收回，其后章转旧稿支线 */
  onRevert: (ref: string) => void;
  /** chapter-rewrite：树刷新（useWorkbench.refresh——旧稿分组与角标只在树 hook 里） */
  onTreeRefresh: () => Promise<void> | void;
  /** 重新润色出口（已润色章改剧情软提示）：打开 AI 生成正文弹窗（内含 AI 润色） */
  onOpenAiModal?: () => void;
}

const fmt = (n: number) => n.toLocaleString("zh-CN");

export default function ChapterWorkspace({
  projectId,
  chapterRef,
  outline,
  wb,
  hasAiPlan,
  isPro,
  proseRef,
  aiState,
  onAIStateChange,
  bookWords,
  onRailData,
  aiWriteSignal,
  promptSavedSignal,
  resumeSignal,
  onWriteProgress,
  onRevert,
  onTreeRefresh,
  onOpenAiModal,
}: ChapterWorkspaceProps) {
  const store = useChapterData(projectId, chapterRef);
  const { wordCount, saveState, targetWords, setTargetWords } = store;
  // c-zhuque-ai-detect：检测编排单源（状态仓在模块层；flush 由本章 store 提供——
  // 送检前落盘由前端保证，后端只读盘上文本）
  const zq = useZhuqueCheck(projectId, chapterRef);
  // 显示开关响应式（配置页拨动经 prefs 订阅到达；否则结果条残留到下次无关重渲）
  const zqShow = useSyncExternalStore(subscribeZhuqueShow, getZhuqueShow, getZhuqueShow);
  useEffect(() => {
    registerZhuqueFlush(() => store.flush());
    return () => registerZhuqueFlush(null);
  }, [store]);
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
  const archived = !!chMeta?.archived;

  // 伏笔台账投影（c-og-hooks-projection）：章纲回收/悬念两格空时的投影与勾选候选。
  // 加载失败时 hints 为 undefined，OgPane 回落「（未填）」占位。
  const { hooks: ledgerHooks, chapters: ledgerChapters, error: ledgerError } =
    useHooksLedger(projectId);
  const hookHints = useMemo(() => {
    if (ledgerError) return undefined;
    const chNo = chapterNoOf(chapterRef);
    const currentId =
      ledgerChapters.find((c) => c.chapter === chNo && c.ref === chapterRef)?.id ??
      ledgerChapters.find((c) => c.chapter === chNo)?.id ??
      null;
    return ogHookHints(ledgerHooks, ledgerChapters, currentId, chNo);
  }, [ledgerError, ledgerHooks, ledgerChapters, chapterRef]);
  // c-chapter-dossier：归档提取中——本章全程软锁（编辑/归档/取消归档/重写/回退禁用）
  const archiving = store.archiveJob?.state === "extracting";
  // 三段进度条的提取已运行秒数（c-ops-archive-stages；顶层调 hook，禁进 JSX）
  const extractElapsed = useElapsedSec(store.archiveJob?.startedAt, archiving);

  // 「信息差对齐」块随卷纲换代退役（c-volume-view-storyline：info_gap/chapter_plans
  // 为旧代字段，ADJUSTMENTS ⑤ 登记）。

  // ── 页签：点章强制落「章纲」（设计稿行为） ───────────────────────────
  const [chTab, setChTab] = useState<
    "og" | "prose" | "settings" | "relations" | "hooks" | "actions"
   | "style">("og");
  const [showArchive, setShowArchive] = useState(false);
  // 章级变化轻量元数据（c-chapter-dossier）：归档态常驻一次＋弹窗打开时刷新——
  // 供重归档覆盖警示、归档卡「未提取」态（not_extracted）与三段进度条的待确认计数
  const [rearchive, setRearchive] = useState<{
    rows: number;
    accepted: number;
    pending: number;
  } | null>(null);
  const [dossierEmpty, setDossierEmpty] = useState(false);
  useEffect(() => {
    if (!showArchive && !archived) return;
    let cancelled = false;
    void (async () => {
      try {
        const d = await dossierApi.get(projectId, chapterRef);
        if (cancelled) return;
        const n = d.progress.pending + d.progress.accepted + d.progress.rejected;
        setRearchive(
          n > 0
            ? {
                rows: n,
                accepted: d.progress.accepted,
                pending: d.progress.pending,
              }
            : null,
        );
        setDossierEmpty(d.not_extracted);
      } catch {
        if (!cancelled) {
          setRearchive(null);
          setDossierEmpty(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [showArchive, archived, store.archiveJob?.state, projectId, chapterRef]);
  const [showHistory, setShowHistory] = useState(false);
  // 章纲查看/编辑两态（对齐卷纲）：默认查看态，切章回落查看
  const [ogEditing, setOgEditing] = useState(false);
  // 正文查看/编辑两态（c-prose-edit-gate）：默认只读阅读，切章回落查看
  const [proseEditing, setProseEditing] = useState(false);
  useEffect(() => {
    setChTab("og");
    setShowHistory(false);
    setOgEditing(false);
    setProseEditing(false);
  }, [chapterRef]);

  // 生成启动信号（页面解锁链/AiModal 确认后递增）：切正文页签 + 进编辑态 + 聚焦（真 bug #2）
  useEffect(() => {
    if (!aiWriteSignal) return;
    setChTab("prose");
    setShowHistory(false);
    setProseEditing(true);
    const t = setTimeout(() => proseRef.current?.focus(), 60);
    return () => clearTimeout(t);
  }, [aiWriteSignal, proseRef]);

  // 续写恢复信号（顶栏 CTA）：落正文页签 + 进编辑态（续写＝写作意图），
  // 滚动位置由 ProsePane 按 resumeScroll 恢复
  useEffect(() => {
    if (!resumeSignal || !resumeSignal.n) return;
    setChTab("prose");
    setShowHistory(false);
    setProseEditing(true);
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
  /** 本书角色卡名（不含别名）：盘点「选已有角色」候选清单（c-character-intro 6.x） */
  const [cardNames, setCardNames] = useState<string[]>([]);
  /** 本书主角名（role=主角的主卡名；名单缺人探测置顶标，c-character-intro 6.x） */
  const [protagonistName, setProtagonistName] = useState("");
  /** 拉取角色名（含别名展开——别名不误标没卡，c-character-intro 4.1）；
   *  建卡成功后显式刷新（3.5；原 effect deps 仅 projectId）。 */
  const refreshCharacterNames = useCallback(async () => {
    try {
      const data = await charactersApi.list(projectId);
      const names = new Set<string>();
      const cards: string[] = [];
      for (const item of data.items) {
        if (item.name && !item.name.startsWith("\u0000")) {
          names.add(item.name);
          cards.push(item.name);
        }
        for (const a of item.aliases ?? []) {
          if (a && !a.startsWith("\u0000")) names.add(a);
        }
      }
      setCharacterNames([...names]);
      setCardNames(cards);
      setProtagonistName(
        data.items.find((i) => i.role === "主角")?.name ?? "",
      );
    } catch {
      /* 角色接口失败不阻塞章纲；textarea 兜底仍可用 */
    }
  }, [projectId]);
  useEffect(() => {
    void refreshCharacterNames();
  }, [refreshCharacterNames]);

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
  // 自动保存 timer 提升为 ref（c-character-intro 3.4）：落账链写入前显式清，
  // 防旧闭包在写入后 PUT 旧表单把新名字删掉；epoch 挡已插队的旧自动保存回写快照。
  const ogAutoSaveTimerRef = useRef<number | null>(null);
  const ogSaveEpochRef = useRef(0);
  const clearOgAutoSave = useCallback(() => {
    if (ogAutoSaveTimerRef.current !== null) {
      clearTimeout(ogAutoSaveTimerRef.current);
      ogAutoSaveTimerRef.current = null;
    }
  }, []);

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
  // 章纲统计（头部 meta 行徽章；口径与 onRailData 上抛右栏的一致——一处算头、一处算栏）。
  // 完成度/本书总字数自右栏「本章进度」卡收编（c-rail-ai-only），右栏现只承载 AI 功能。
  const plotCount = ogForm.plots.filter((x) => x.trim()).length;
  const castLines = ogForm.chars.split("\n").filter((x) => x.trim());
  const wtParsed = parseInt(ogForm.wt, 10);
  const planWords =
    Number.isFinite(wtParsed) && wtParsed > 0 ? wtParsed : (targetWords ?? null);
  const progressPct = planWords
    ? Math.min(100, Math.round((wordCount / planWords) * 100))
    : null;

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

  /** 保存警告上屏（保存/自动保存/写入三路径都消费；自动保存 warnings 存在才打扰） */
  const consumeWarnings = useCallback((warnings?: string[]) => {
    if (warnings && warnings.length > 0) toast.info(warnings.join("；"));
  }, []);

  const saveOg = useCallback(async (): Promise<boolean> => {
    if (ogLoadingRef.current) return false;
    const issues = ogFormIssues(ogForm);
    if (issues.length > 0) {
      toast.error(issues[0]);
      return false;
    }
    setOgSaving(true);
    ogSaveEpochRef.current++; // 手动保存插队：旧自动保存不再回写快照
    clearOgAutoSave();
    try {
      const beforeExit = String(outline.chaptersMap.get(chapterRef)?.ladder_exit ?? "").trim();
      const res = await outline.saveChapter(
        chapterRef,
        ogToPartial(ogForm, outline.chaptersMap.get(chapterRef)),
      );
      ogSnapRef.current = JSON.stringify(ogForm);
      consumeWarnings(res?.warnings);
      notifyExitChange(beforeExit);
      return true;
    } catch {
      toast.error("章纲保存失败，请重试");
      return false;
    } finally {
      setOgSaving(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [outline.saveChapter, outline.chaptersMap, chapterRef, ogForm, vol, chMeta, wb, consumeWarnings]);

  // 3s 静默后台保存（不改 status；设计稿之外的应用侧扩展，已登记 ADJUSTMENTS）。
  // timer 提升为 ref（c-character-intro 3.4）：落账链写入前显式清，防旧闭包 PUT 旧表单删掉新名字。
  const ogKey = JSON.stringify(ogForm);
  useEffect(() => {
    if (ogLoadingRef.current) return;
    if (ogKey === ogSnapRef.current) return;
    // 校验不过时静默跳过（不打扰），待用户补齐后下一次输入触发重试
    if (ogFormIssues(ogForm).length > 0) return;
    ogAutoSaveTimerRef.current = window.setTimeout(() => {
      ogAutoSaveTimerRef.current = null;
      const epoch = ogSaveEpochRef.current;
      const beforeExit = String(outline.chaptersMap.get(chapterRef)?.ladder_exit ?? "").trim();
      outline
        .saveChapter(chapterRef, ogToPartial(ogForm, outline.chaptersMap.get(chapterRef)))
        .then((res) => {
          // 手动/写入保存插队后旧自动保存不再回写快照（防旧闭包覆盖新落库值）
          if (ogSaveEpochRef.current === epoch) ogSnapRef.current = ogKey;
          consumeWarnings(res?.warnings); // warnings 存在才打扰
          notifyExitChange(beforeExit);
        })
        .catch(() => {
          /* 静默：失败不打扰，下一次输入重试 */
        });
    }, 3000);
    return () => clearOgAutoSave();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ogKey, chapterRef, outline.saveChapter, outline.chaptersMap, ogForm]);

  // ── 章纲查看/编辑两态（对齐卷纲）：进编辑＝表单可写（3s 自动保存只认快照差）；
  //    取消＝回退到最近一次落库值（ogSnapRef 恒等于已持久化内容，含自动保存）。
  //    编辑入口：编辑章纲按钮／查看态缺口 chip／右栏缺项补全（产物要在表单里过目）。──
  // 归档章一律哑火（c-archived-readonly）：OgPane 恒查看态，编辑态不得经 chip 溜进。
  const startOgEdit = useCallback(() => {
    if (!archived) setOgEditing(true);
  }, [archived]);
  const cancelOgEdit = useCallback(() => {
    try {
      setOgForm(JSON.parse(ogSnapRef.current) as OgForm);
    } catch {
      /* 快照损坏不回填（保守保留当前表单） */
    }
    setOgEditing(false);
  }, []);
  /** 进编辑态并滚动聚焦指定格子（查看态缺口 chip／剧情抽卡的「去补填」共用） */
  const editAndFlash = useCallback(
    (key: string) => {
      if (archived) return;
      setOgEditing(true);
      // 切编辑态重渲后 wf-* 控件才存在（与 handleGoWrite 聚焦同款时序）
      window.setTimeout(() => flashField(key), 80);
    },
    [archived],
  );

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
    // 只保存不改确认状态（c-og-draft-no-autconfirm）：确认只走「确认章纲」显式触发，
    // 旧「无缺项自动确认」退役——必填砍到两项后它让保存草稿几乎恒确认，按钮语义打架。
    toast.success("草稿已保存");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [saveOg]);

  /** 撤回确认（c-og-draft-no-autconfirm）：确认态退回草稿，树上计数随批回落 */
  const handleUnconfirm = useCallback(async () => {
    await outline.unconfirmChapter(chapterRef);
    const st = await reloadStatus();
    if (st !== "confirmed") {
      await outline.refetchTree();
      toast.success("已撤回确认，章纲回到草稿态");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [outline.unconfirmChapter, outline.refetchTree, chapterRef, reloadStatus]);

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
    setProseEditing(true); // 去写正文＝写作意图，直接进编辑态
    // 切页签重渲后才可聚焦
    setTimeout(() => proseRef.current?.focus(), 60);
  }, [saveOg, proseRef]);

  // ── 右栏 AI 辅助·检测族（ai-check） ─────────────
  const [aiCheckKind, setAiCheckKind] = useState<AiCheckKind | null>(null);
  const [gapsLoading, setGapsLoading] = useState(false);

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
      setOgEditing(true); // 补全产物要在表单里过目——直接落到编辑态
      toast.success(`已补 ${n} 项，检查后保存`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "补全失败，请重试");
    } finally {
      setGapsLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, chapterRef, ogForm]);

  // ── 章内剧情（c-plot-split）：门槛拦截 → 三版抽卡 → 采纳/撤销 → 润色软提示 ──
  const plotDraw = usePlotDraw(projectId, chapterRef);
  const navigate = useNavigate();
  /** 替换明示 N＝已写的非空条数（拍板②） */
  const writtenCount = ogForm.plots.filter((s) => s.trim() !== "").length;

  // 采纳回执（常驻到下次编辑，拍板②）：撤销快照＝采纳前列表
  const plotReceiptRef = useRef<{ id: number; prev: string[] } | null>(null);
  const killPlotReceipt = useCallback(() => {
    const r = plotReceiptRef.current;
    if (!r) return;
    plotReceiptRef.current = null;
    toast.dismiss(r.id);
  }, []);
  // 切章/卸载即收（回执的撤销只对当章有意义）
  useEffect(() => () => killPlotReceipt(), [chapterRef, killPlotReceipt]);

  const handlePlotUndo = useCallback(() => {
    const r = plotReceiptRef.current;
    if (!r) return;
    killPlotReceipt();
    // 只回滚 plots（函数式，别的格子不碰）；借 3s 自动保存回写（design.md 既定口径）
    setOgForm((f) => ({ ...f, plots: r.prev.slice() }));
    toast.info("已恢复到 AI 填写前的列表");
  }, [killPlotReceipt]);

  // 已润色章改剧情软提示（拍板⑥）：quiet 探提示词，润色产物才提示，不自动重算
  const polishHintShownRef = useRef(false);
  const polishHintTimerRef = useRef<number | null>(null);
  // 切章/卸载：清挂起的软提示 timer、重置「已提示」（新章要重新判定）
  useEffect(() => {
    polishHintShownRef.current = false;
    return () => {
      if (polishHintTimerRef.current) clearTimeout(polishHintTimerRef.current);
      polishHintTimerRef.current = null;
    };
  }, [chapterRef]);
  const maybeHintPolish = useCallback(() => {
    if (!isPro || polishHintShownRef.current) return;
    if (polishHintTimerRef.current) clearTimeout(polishHintTimerRef.current);
    polishHintTimerRef.current = window.setTimeout(() => {
      void (async () => {
        try {
          const d = (await request(
            `/novels/${projectId}/chapters/${chapterRef}/write/prompt`,
            { quiet: true },
          )) as { polished?: boolean };
          if (!d?.polished || polishHintShownRef.current) return;
          polishHintShownRef.current = true;
          toast.info("提示词还是旧版、没带上新剧情——可以重新润色", {
            action: {
              label: "去重新润色",
              onClick: () => {
                polishHintShownRef.current = false; // 重润后下次改动还能再提示
                onOpenAiModal?.();
              },
            },
          });
        } catch {
          /* 静默：探测失败不打扰 */
        }
      })();
    }, 1200);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, chapterRef, isPro, onOpenAiModal]);

  // 剧情编辑（输入/加/删任一动作，OgPane 上抛）：下次编辑即收回执（拍板②）＋润色软提示
  const saveOgRef = useRef(saveOg);
  saveOgRef.current = saveOg;
  const outlineRef = useRef(outline);
  outlineRef.current = outline;
  const ogFormRef = useRef(ogForm);
  ogFormRef.current = ogForm;
  const handlePlotEdit = useCallback(() => {
    killPlotReceipt();
    maybeHintPolish();
  }, [killPlotReceipt, maybeHintPolish]);

  /** 「剧情抽卡」（右栏动作）：先 flush 表单，门槛读服务端值（拍板⑦三样） */
  const handlePlotDraw = useCallback(async () => {
    // saveOg/outline 走 ref 读最新值——其身份随渲染变（wb 每渲染新建），进依赖会经
    // onRailData effect → setRailData → 父重渲 → wb 又新 → 无限循环（e2e 不炸但空转
    // 烧 CPU；vitest jsdom 里表现为 worker 堆 OOM，NovelWorkspace.test 曾 16 分钟不归）。
    const flushed = await saveOgRef.current(); // 尽力 flush：失败也继续——门槛读服务端值，缺就拦
    // flush 成功 ⇒ 服务端此刻==表单（saveOg 刚 PUT 全量）→ 门槛读表单值：setChaptersMap
    // 只调度重渲、outlineRef 仍是旧 map，读它会把刚补完的格子误拦成「还没填」（评审 P2）；
    // flush 失败（loading/issues/网络）才回落 map——最后已知服务端态，与端点 422 同源。
    const server = outlineRef.current.chaptersMap.get(chapterRef);
    const val = (formVal: string, srvVal: string | undefined) =>
      flushed ? formVal : String(srvVal ?? "").trim();
    const missing = [
      { key: "summary", label: "章纲概要", val: val(ogFormRef.current.summary, server?.outline?.summary) },
      { key: "challenge", label: "碰到的挑战", val: val(ogFormRef.current.challenge, server?.challenge) },
      { key: "ladder", label: "章末落点", val: val(ogFormRef.current.ladder, server?.ladder_exit) },
    ].filter((m) => !m.val.trim());
    if (missing.length > 0) {
      for (const m of missing) {
        toast.error(`AI 写剧情要有依据：「${m.label}」还没填`, {
          action: { label: "去补填", onClick: () => editAndFlash(m.key) },
        });
      }
      return;
    }
    plotDraw.openDraw();
  }, [chapterRef, plotDraw]);

  /** 「就填这版」：整表替换（拍板②）＋常驻回执（撤销恢复填写前列表，含非空）。
   *  关窗在落库成功之后——保存失败时弹层留在原地、选中版还在，直接再点即可重试
   *  （先关后存会把失败变成「重抽一次烧 tokens」，评审 P3）；adoptingRef 挡落库期间重入。 */
  const adoptingRef = useRef(false);
  const handlePlotAdopt = useCallback(async () => {
    if (adoptingRef.current) return;
    const { pick, versions } = plotDraw.state;
    if (pick == null) return;
    const items = versions[pick].slice();
    const prev = ogForm.plots.slice();
    const patched: OgForm = { ...ogForm, plots: items };
    adoptingRef.current = true;
    try {
      await outline.saveChapter(
        chapterRef,
        ogToPartial(patched, outline.chaptersMap.get(chapterRef)),
      );
    } catch {
      adoptingRef.current = false;
      toast.error("章纲保存失败，请重试");
      return;
    }
    plotDraw.close();
    setOgForm(patched);
    ogSnapRef.current = JSON.stringify(patched);
    killPlotReceipt();
    plotReceiptRef.current = {
      prev,
      id: toast.success(`剧情已由 AI 填好（${items.length} 条）`, {
        sticky: true,
        action: { label: "撤销 · 恢复填写前的列表", onClick: handlePlotUndo },
      }),
    };
    adoptingRef.current = false;
    maybeHintPolish();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plotDraw, ogForm, outline.saveChapter, outline.chaptersMap, chapterRef,
      killPlotReceipt, handlePlotUndo, maybeHintPolish]);

  // ── 剧情推演（plot-sim）：弹窗按回合走一遍；收进章纲＝追加一条剧情条目后走既有保存链
  // （c-og-slim-v2：原落点「预期策略」已退役，改追加剧情条目，既有条目不动）──
  const [showSim, setShowSim] = useState(false);
  const handleSimAdopt = useCallback(
    async (line: string): Promise<boolean> => {
      const walking = line.trim();
      if (!walking) return false;
      const plots = [...ogForm.plots, walking].slice(0, PLOT_MAX_ITEMS);
      const patched: OgForm = { ...ogForm, plots };
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


  // ── 章纲人物精盘（c-character-intro）：盘点（免费）→缺人三选一→抽卡（PRO）→
  //    写入两出口落账。弹窗挂本层（NovelWorkspace 零改动）；申报输入受控态在弹窗内。 ──
  const castInput = useMemo(() => {
    const partial = ogToPartial(ogForm, outline.chaptersMap.get(chapterRef)) as Record<string, unknown>;
    return {
      body: {
        summary: ogForm.summary,
        challenge: ogForm.challenge,
        plot_stage: ogForm.stage,
        ladder_exit: ogForm.ladder,
        plot_items: (partial.plot_items as string[] | undefined) ?? [],
        characters: ogForm.chars.split("\n").map((x) => x.trim()).filter(Boolean),
      },
      partial,
    };
  }, [ogForm, outline.chaptersMap, chapterRef]);

  /** 空章防呆：剧情条目零条且梗概/挑战/章末落点全空（阶段有默认值不计入） */
  const castEmpty = useMemo(() => {
    const hasPlot = ogForm.plots.some((x) => x.trim());
    const hasRest = !!(
      ogForm.summary.trim() ||
      ogForm.challenge.trim() ||
      ogForm.ladder.trim()
    );
    return !hasPlot && !hasRest;
  }, [ogForm.plots, ogForm.summary, ogForm.challenge, ogForm.ladder]);

  /** 建卡已成功的名字（保存失败重试只走名单写入；409 且 created 给「卡已建好」提示） */
  const castCreatedRef = useRef(new Set<string>());

  /** 写入两出口落账（3.4，正确性顺序照 handlePlotAdopt）：
   *  chars 按行去重并入 → ogFormIssues 预检 → 主出口先建卡 → 清自动保存 timer →
   *  立即 saveChapter → 成功 setOgForm(patched)＋ogSnapRef 双同步（不等 3s）→ 回结果页。 */
  const handleCastWrite = useCallback(
    async (req: CastWriteRequest): Promise<CastWriteOutcome> => {
      const name = req.fields.name.trim();
      const cur = ogFormRef.current;
      const lines = cur.chars.split("\n").map((x) => x.trim()).filter(Boolean);
      const dedup = [...new Set(lines)];
      const castBefore = dedup.length;
      if (!dedup.includes(name)) dedup.push(name);
      const patched: OgForm = { ...cur, chars: dedup.join("\n") };
      const issues = ogFormIssues(patched);
      if (issues.length > 0) {
        return {
          ok: false,
          kind: "save_failed",
          message: issues[0],
          created: castCreatedRef.current.has(name),
        };
      }
      let created = castCreatedRef.current.has(name);
      let note: string | undefined;
      // 主出口先建卡（listOnlyAfterCreate/次出口不建）；409 撞名回落只加名单
      if (req.mode === "with-card" && !req.listOnlyAfterCreate && !created) {
        try {
          await charactersApi.create(projectId, name, {
            persona: req.fields.persona.trim() || undefined,
            prefill: {
              plot: req.fields.duty.trim() || undefined,
              background: castBackgroundLine(req.fields) || undefined,
            },
          });
          created = true;
          castCreatedRef.current.add(name);
          void refreshCharacterNames();
        } catch (e) {
          if (isNameTaken(e)) {
            created = castCreatedRef.current.has(name);
            note = created
              ? "卡已建好，这就把名字写进名单。"
              : "已有同名卡，名单会自动挂上。";
          } else {
            return {
              ok: false,
              kind: "create_failed",
              message: errMessage(e, "建卡失败，请重试"),
              created: false,
            };
          }
        }
      } else if (req.listOnlyAfterCreate && created) {
        note = "卡已建好，这就把名字写进名单。";
      }
      // 落账前显式清自动保存 timer（防旧闭包 PUT 旧表单删掉新名字）
      clearOgAutoSave();
      ogSaveEpochRef.current++;
      try {
        const res = await outlineRef.current.saveChapter(
          chapterRef,
          ogToPartial(patched, outlineRef.current.chaptersMap.get(chapterRef)),
        );
        // 双同步缺一不可（照 handlePlotAdopt）：setOgForm＋ogSnapRef
        setOgForm(patched);
        ogSnapRef.current = JSON.stringify(patched);
        consumeWarnings(res?.warnings);
        return {
          ok: true,
          // created＝「本次写入建了卡」（outcome 字段语义）：选已有角色零建卡，
          // 即便本会话早前为该名建过卡（castCreatedRef），本次也 MUST NOT 报「多一卡」
          created: req.existing === true ? false : created,
          name,
          castBefore,
          castAfter: dedup.length,
          warnings: res?.warnings ?? [],
          note,
          existing: req.existing === true,
        };
      } catch {
        return {
          ok: false,
          kind: "save_failed",
          message: "名单保存失败，请重试",
          created,
        };
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [projectId, chapterRef, consumeWarnings, clearOgAutoSave, refreshCharacterNames],
  );

  const featureAiPlan = useFeature("ai-plan");
  const aiPlan = hasAiPlan ?? featureAiPlan;
  const castReview = useCastReview({
    projectId,
    chapterRef,
    hasAiPlan: aiPlan,
    input: castInput,
    onWrite: handleCastWrite,
    // 统一升级出口（member-block 全局升级引导；NovelWorkspace 零改动）
    onUpgrade: () =>
      window.dispatchEvent(
        new CustomEvent("member-block", { detail: { message: "AI 抽人是 PRO 功能——升级后一次给 3 个方向" } }),
      ),
    onOpenConfig: () => navigate("/config"),
  });

  /** 行级/软提示建卡入口：只预填称呼（提案字段零新存储不留存，卡面回头在设定页补） */
  const handleQuickCreateChar = useCallback(
    async (name: string) => {
      try {
        await charactersApi.create(projectId, name.trim(), {});
        toast.success(`已建卡「${name.trim()}」——只带名字，卡面回头在设定页补`);
        void refreshCharacterNames();
      } catch (e) {
        if (isNameTaken(e)) toast.info("已有同名卡，名字会自动挂上");
        else toast.error(errMessage(e, "建卡失败，请重试"));
      }
    },
    [projectId, refreshCharacterNames],
  );

  // onRailData 死循环纪律：回调 useCallback＋saveOg 走 ref＋deps 只含 chapterRef
  const castOpenRef = useRef(castReview.open);
  castOpenRef.current = castReview.open;
  const openCastReview = useCallback(() => {
    void saveOgRef.current(); // 尽力 flush（失败也继续——盘点输入是表单快照）
    castOpenRef.current();
  }, [chapterRef]);

  // ── 排版偏好（per-book：pref.book.{pid}.*，全局默认兜底）。
  //    页内字号/行距切换控件已撤（2026-09-27）：只读回显供 ProsePane 排版，
  //    改值入口在账号菜单「本书偏好」（BookPrefsModal，切书时重读）。 ─────────────
  const [typo, setTypo] = useState(() => ({
    fs: getBookFontSize(projectId),
    lh: getBookLineHeight(projectId),
  }));
  useEffect(() => {
    setTypo({ fs: getBookFontSize(projectId), lh: getBookLineHeight(projectId) });
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

  // ── 归档受理（c-chapter-dossier）：模型就绪→后台提取（archiveJob 跟踪）；
  //    模型未就绪→服务端同步归档（store 内直接落 archived，沿用旧 toast） ──
  const handleArchive = useCallback(async () => {
    if (archived || wordCount === 0) return;
    const ok = await store.archive({ aiSummary: getBookArchiveAiSummary(projectId) });
    if (!ok) return;
    if (store.archiveJob?.state === "extracting") {
      toast.info("已受理 · AI 提取中（本章已锁定；产出在设定/角色关系页签，进度见归档卡）");
      return;
    }
    // chapter-rewrite：存在下游「基于旧设定」章时在归档提示里点名（原型口径）
    const hasStaleDownstream = outline.volumes.some((v) =>
      v.chapters.some((c) => c.stale),
    );
    toast.success(
      hasStaleDownstream
        ? `《${label}》已归档 · 只读（下游章节标记「基于旧设定」）`
        : `《${label}》已归档 · 只读`,
    );
  }, [archived, wordCount, projectId, label, store]);

  // 归档任务终态提示（后台提取完成/失败；切页签也不丢）
  const prevJobRef = useRef(store.archiveJob?.state ?? null);
  useEffect(() => {
    const st = store.archiveJob?.state ?? null;
    const was = prevJobRef.current;
    prevJobRef.current = st;
    if (was === "extracting" && st === "done") {
      toast.success(`《${label}》提取完成 · 已归档，变化待确认（设定/角色关系页签）`);
      void onTreeRefresh();
    } else if (was === "extracting" && st === "failed") {
      toast.error(`《${label}》提取失败——章未归档，可重试或跳过（归档卡）`);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [store.archiveJob?.state]);

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
      setProseEditing(true); // 重写＝就地改写意图，直接进编辑态
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

  // ── 恢复编辑（c-archived-readonly 小改路径：横幅出口，unarchive 直改不转存旧稿；
  //    整体重写走「操作」页签「重写本章」——旧稿转支线＋下游角标） ────────────
  const handleUnarchive = useCallback(async () => {
    if (!window.confirm(`确定恢复《${label}》的编辑吗？恢复后本章退出归档只读状态。`))
      return;
    await store.unarchive();
  }, [label, store]);

  // 归档只读横幅（c-archived-readonly）：正文/章纲两页签共用同一块。
  // 两条修改路径＝小改「恢复编辑」（本横幅出口）／整体重写「重写本章」（操作页签）。
  const archivedBanner = archived ? (
    <div className="readonly-banner">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <rect x="4" y="10" width="16" height="10" rx="2" />
        <path d="M8 10V7a4 4 0 018 0v3" />
      </svg>
      <span>
        本章已归档 · <b>只读</b>。小改可恢复编辑；整体重写走「操作」页签「重写本章」（旧稿自动转存支线）。
      </span>
      <button
        className="btn btn-ghost btn-sm"
        onClick={() => void handleUnarchive()}
      >
        恢复编辑
      </button>
    </div>
  ) : null;

  // ── 右栏进度数据上抛（ref 防 effect 依赖抖动；切章/卸载置空） ──────────
  const onRailDataRef = useRef(onRailData);
  useEffect(() => {
    onRailDataRef.current = onRailData;
  }, [onRailData]);
  useEffect(() => {
    // 章纲统计（右栏 AI 辅助·章纲页签）：归档门槛/计划字数/关键事件/出场角色
    // 章纲统计（右栏 AI 辅助·章纲页签）：归档门槛/计划字数/剧情/出场角色
    // c-og-slim-v2：门槛分母由必填项数派生（原 6 是六改四时遗留的错值）；
    // 「关键事件」计数随该格退役，改报剧情条目数。
    const plotCount = ogForm.plots.filter((x) => x.trim()).length;
    const castLines = ogForm.chars.split("\n").filter((x) => x.trim());
    const wtParsed = parseInt(ogForm.wt, 10);
    onRailDataRef.current({
      wordCount,
      targetWords,
      setTargetWords,
      archived,
      bookWords,
      // storyline col-ai：右栏 AI 辅助随页签切换
      tab: chTab,
      chapterRef,
      ogStats: {
        reqOk: REQ_FIELDS.length - ogGaps(ogForm).length,
        planWords: Number.isFinite(wtParsed) && wtParsed > 0 ? wtParsed : (targetWords ?? null),
        plotCount,
        castCount: castLines.length,
        missingLabels: ogGaps(ogForm).map((g) => g.label),
      },
      promptSavedSignal,
      onSimulate: () => setShowSim(true),
      onPlotDraw: () => void handlePlotDraw(),
      onCastReview: () => openCastReview(),
      castEmpty,
      castBusy:
        castReview.state.phase === "reviewing" ||
        castReview.state.phase === "drawing" ||
        castReview.state.writing,
      onStyleSuggest: () => setStyleSuggestSignal((n) => n + 1),
      onFillGaps: () => void handleFillGaps(),
      gapsLoading,
      onAiCheck: setAiCheckKind,
    });
    return () => onRailDataRef.current(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wordCount, targetWords, setTargetWords, archived, bookWords, chTab, ogForm, chapterRef, gapsLoading, promptSavedSignal, handleFillGaps, handlePlotDraw, openCastReview, castEmpty, castReview.state.phase, castReview.state.writing]);

  // ── 文风建议信号（右栏 AI 助手触发 → StyleShadowPane 内执行拉取；2026-09-20
  //    AI 入口收口右栏：页签 body 不再设 AI 按钮，建议结果仍在页签内逐项采纳） ──
  const [styleSuggestSignal, setStyleSuggestSignal] = useState(0);

  // ── 页签徽标（状态机：起草→确认→正文→归档；归档＝终态，章纲徽不再报阶段态） ──
  const ogCnt = archived
    ? { cls: "cnt", text: "已归档" }
    : confirmed
      ? { cls: "cnt ok", text: "已确认" }
      : gaps.length
        ? { cls: "cnt err", text: `缺 ${gaps.length} 项` }
        : { cls: "cnt warn", text: "草稿" };
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
          {/* 密度重排（c-workbench-density）：卷名 kicker 退役（左树承载卷归属）；
              计划字数/完成度/本书总字数三枚重复徽章退役（唯一承载位＝页签行右端 ch-progress） */}
          <h2 className="e-title">{label}</h2>
          <div className="e-meta">
            <span className="tag">{archived ? "已归档" : wordCount ? "草稿" : "拟定"}</span>
            <span className="tag">{fmt(wordCount)} 字</span>
            <span className="tag">
              归档门槛 {REQ_FIELDS.length - gaps.length}/{REQ_FIELDS.length}
            </span>
            <span className="tag">剧情 {plotCount} 条</span>
            <span className="tag">出场角色 {castLines.length} 人</span>
          </div>
        </div>
        {zqShow && chTab === "prose" && (
          <ZhuqueHeadStrip
            state={zq.state}
            onRerun={() => void zq.run({ flush: () => store.flush() })}
            onClear={zq.clear}
          />
        )}
        <span className="prose-ctrls">
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
        </span>
      </header>

      <div className="ch-tabs" role="tablist" aria-label="章节对象">
        {(
          [
            ["og", "章纲", ogCnt],
            ["prose", "正文", proseCnt],
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
        {/* 生成中徽章（c-prose-stream-guard）：提升到页签行——离开正文页签
            （editor-status 隐藏在 chTab 作用域内）仍可见可停；正文页签下状态条不再重复 */}
        {aiState.streaming && (
          <span className="ai-streaming" data-testid="ai-streaming-badge">
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
        {/* 密度重排（c-workbench-density）：完成度/总字数的唯一承载位（自头部徽章行迁入） */}
        <span className="ch-progress" data-testid="ch-progress">
          {progressPct != null && <>完成度 {progressPct}% · </>}总字数 {fmt(bookWords)}
        </span>
        {/* 版本历史（2026-09-27 自头部右侧移入页签行右端；弹窗不变） */}
        <button className="btn btn-ghost btn-sm ch-history" onClick={() => setShowHistory(true)}>
          版本历史
        </button>
      </div>

      {chTab === "prose" && archivedBanner}

      <ProsePane
        ref={proseRef}
        projectId={projectId}
        chapterRef={chapterRef}
        fs={typo.fs}
        lh={typo.lh}
        hidden={chTab !== "prose"}
        onAIStateChange={onAIStateChange}
        resumeScroll={resumeScrollMemo}
        onWriteProgress={onWriteProgress}
        editing={proseEditing}
        onStartEdit={() => {
          setProseEditing(true);
          // 进编辑态聚焦、光标落文末（c-prose-edit-affordance）：切态重渲后编辑器才就绪
          window.setTimeout(() => proseRef.current?.focus(), 80);
        }}
        onEndEdit={() => setProseEditing(false)}
        locked={
          ghostOf
            ? { reason: "旧稿支线 · 只读" }
            : archiving
              ? { reason: "归档提取中 · 本章已锁定" }
              : frontierLocked && chTab === "prose"
                ? { reason: "还不能写这一章——先完成前面的章节" }
                : undefined
        }
      />

      {chTab === "settings" && (
        <div className="settings-pane" data-od-id="settings-pane">
          <SettingChangesSection projectId={projectId} chapterRef={chapterRef} />
          {/* 世界要素提案各归各的页签（c-ops-tab-progress-only）：与写回目标同位 */}
          <ReconcilePane
            projectId={projectId}
            chapterRef={chapterRef}
            archived={archived}
            kinds={["lore"]}
          />
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
          {/* 关系图为主表达（09-28 用户拍板），变化行是确认工作流，置于图下 */}
          <RelationsGraphPane projectId={projectId} chapterRef={chapterRef} />
          <RelationChangesSection projectId={projectId} chapterRef={chapterRef} />
        </div>
      )}

      {chTab === "hooks" && (
        <div className="hooks-wrap" data-od-id="hooks-wrap">
          {/* 伏笔登记提案各归各的页签（c-ops-tab-progress-only）：与写回目标同位 */}
          <ReconcilePane
            projectId={projectId}
            chapterRef={chapterRef}
            archived={archived}
            isPro={isPro}
            kinds={["hooks"]}
          />
          <HooksPane projectId={projectId} chapterRef={chapterRef} />
        </div>
      )}



      {chTab === "actions" && (
        <div className="actions-pane" data-od-id="actions-pane">
          {/* 归档（2026-09-27 自头部移入操作页签；弹窗与守卫不变；旧稿支线无归档语义） */}
          {!ghostOf && (
            <div className="revert-card" data-od-id="archive-card">
              <p className="rc-title">归档本章</p>
              <p className="rc-desc">
                {archived
                  ? "本章已归档 · 变化与提案在「设定 / 角色关系 / 伏笔」页签确认；需要时可重新归档重提。"
                  : "点归档后先 AI 提取本章变化（设定/关系/物品/认知，用你配置的模型），提取成功本章才正式归档；提取期间本章锁定。"}
              </p>
              {(archiving || archived || store.archiveJob?.state === "failed") && (
                <ArchiveStages
                  extract={
                    archiving
                      ? "active"
                      : store.archiveJob?.state === "failed"
                        ? "fail"
                        : dossierEmpty
                          ? "skip"
                          : "done"
                  }
                  elapsedSec={extractElapsed}
                  confirmLabel={
                    archived
                      ? rearchive?.pending
                        ? `待确认 ${rearchive.pending} 条`
                        : "提案已处理"
                      : null
                  }
                  confirmActive={!!rearchive?.pending}
                  done={archived}
                />
              )}
              {archiving ? (
                <p className="rc-desc" data-testid="archive-extracting">
                  本章已锁定 · 完成后产出落「设定 / 角色关系」页签，逐条确认后才写进全书设定
                </p>
              ) : store.archiveJob?.state === "failed" ? (
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <button
                    className="btn btn-secondary btn-sm"
                    data-testid="archive-retry"
                    onClick={() =>
                      void store.retryExtraction().then((err) => err && toast.error(err))
                    }
                  >
                    重试提取
                  </button>
                  {!archived && (
                    <button
                      className="btn btn-ghost btn-sm"
                      data-testid="archive-skip"
                      onClick={() => {
                        if (
                          window.confirm(
                            "跳过提取后本章直接归档，但本章状态不会进入下一章前情（之后可在归档卡补提取）。确定跳过？",
                          )
                        )
                          void store.skipArchive();
                      }}
                    >
                      跳过提取，仍要归档
                    </button>
                  )}
                </div>
              ) : archived && dossierEmpty ? (
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                  <span className="rc-desc">本章已归档但未提取变化（归档时未配置模型 / 跳过提取）。</span>
                  <button
                    className="btn btn-secondary btn-sm"
                    data-testid="archive-backfill"
                    onClick={() =>
                      void store.retryExtraction().then((err) => err && toast.error(err))
                    }
                  >
                    补提取本章变化
                  </button>
                  <a href="#/config">去「模型配置」</a>
                </div>
              ) : archived ? (
                /* 多次归档（c-ops-tab-progress-only）：已归档已提取章可重提变化（rows_only） */
                <button
                  className="btn btn-secondary btn-sm"
                  data-testid="archive-reextract"
                  disabled={wordCount === 0}
                  onClick={() => setShowArchive(true)}
                >
                  重新归档 · 重提本章变化
                </button>
              ) : (
                <button
                  className="btn btn-secondary btn-sm"
                  data-od-id="archive-btn"
                  data-testid="archive-btn"
                  disabled={wordCount === 0}
                  title={wordCount === 0 ? "空章无需归档" : undefined}
                  onClick={() => setShowArchive(true)}
                >
                  归档本章
                </button>
              )}
            </div>
          )}
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
                disabled={rewriting || archiving}
                title={archiving ? "归档提取中" : undefined}
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
          {/* 收尾提案区已各归各的页签（伏笔→伏笔页签 / 世界要素→设定页签，
              c-ops-tab-progress-only）：操作页签只留生命周期卡与归档进度 */}
        </div>
      )}

      <ArchiveModal
        open={showArchive}
        onClose={() => setShowArchive(false)}
        onConfirm={() => {
          // 已归档章＝重新归档：rows_only 重提本章变化（不重跑收尾提案）；
          // 拒收（409 model_not_ready 等）须就地报错——store.error 无渲染面
          if (archived)
            void store.retryExtraction().then((err) => err && toast.error(err));
          else void handleArchive();
        }}
        isPro={isPro}
        rearchiveMode={archived}
        rearchive={rearchive}
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

      {chTab === "og" && archivedBanner}
      {chTab === "og" && (
        <OgPane
          form={ogForm}
          characterNames={characterNames}
          protagonistName={protagonistName}
          label={label}
          editing={ogEditing}
          loading={ogLoading}
          hookHints={hookHints}
          onPatch={(patch) => setOgForm((f) => ({ ...f, ...patch }))}
          onPlotEdit={handlePlotEdit}
          gaps={gaps}
          confirmed={confirmed}
          archived={archived}
          saving={ogLoading || ogSaving}
          onStartEdit={startOgEdit}
          onCancelEdit={cancelOgEdit}
          onGapClick={editAndFlash}
          onSaveDraft={() => void handleSaveDraft()}
          onConfirm={() => void handleConfirm()}
          onUnconfirm={() => void handleUnconfirm()}
          onGoWrite={() => void handleGoWrite()}
          onQuickCreateChar={(name) => void handleQuickCreateChar(name)}
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

      <PlotDrawModal
        state={plotDraw.state}
        chapterLabel={label}
        writtenCount={writtenCount}
        onPick={plotDraw.pickCard}
        onAdopt={() => void handlePlotAdopt()}
        onRedraw={plotDraw.redraw}
        onManual={plotDraw.close}
        onClose={plotDraw.close}
        onOpenConfig={() => navigate("/config")}
      />

      <CastReviewModal
        cast={castReview}
        chapterLabel={label}
        plotItems={castInput.body.plot_items}
        roster={cardNames}
        castLines={ogForm.chars.split("\n").map((x) => x.trim()).filter(Boolean)}
        hasAiPlan={aiPlan}
        onUpgrade={() =>
          window.dispatchEvent(
            new CustomEvent("member-block", { detail: { message: "AI 抽人是 PRO 功能——升级后一次给 3 个方向" } }),
          )
        }
        onOpenConfig={() => navigate("/config")}
        onQuickCreateChar={(name) => void handleQuickCreateChar(name)}
      />

      <AiCheckModal
        open={aiCheckKind !== null}
        onClose={() => setAiCheckKind(null)}
        projectId={projectId}
        chapterRef={chapterRef}
        chapterLabel={label}
        kind={aiCheckKind}
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
        </span>
      </div>
    </div>
  );
}
