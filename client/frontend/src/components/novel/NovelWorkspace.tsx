import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "@/lib/api";
import ProContainer from "@/components/novel/ProContainer";
import OnboardingCard from "@/components/novel/OnboardingCard";
import OutlineTree from "@/components/novel/workbench/OutlineTree";
import VolumePanel from "@/components/novel/workbench/VolumePanel";
import ChapterWorkspace from "@/components/novel/workbench/ChapterWorkspace";
import SettingsView from "@/components/novel/workbench/SettingsView";
import PreviewView from "@/components/novel/workbench/PreviewView";
import Rail, { type RailChapterData } from "@/components/novel/workbench/Rail";
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
import { getLastWriteSession, type LastWriteSession } from "@/lib/prefs";

// ---------------------------------------------------------------------------
// NovelWorkspace — book.html 复刻（PR 3：壳 + 大纲树 + 章对象工作台）
//   appbar（行头归一：logo 即返回 · 书名双击改名 · 题材 · 当前主线定位 · 账户胶囊）
//   modnav（设定 N/8 · 写作 N/N 章纲 · 预览，默认写作视图）
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
    refresh,
  } = wb;
  const { updateProject } = useProject();
  const { isPro } = useTier();
  const projectId = project?.id ?? "";

  const outline = useOutline(projectId);
  const { settingsDone, settingsStatus, confirmedStatus, charStale, confirmSetting } = useOnboarding(projectId, []);

  // ── 视图映射：modnav 三态 ↔ 内部视图名（默认 workbench = 写作） ──────
  const go = useCallback(
    (
      next: "workbench" | "advanced-settings" | "archives",
      payload?: Record<string, any>,
    ) => {
      if (
        view === "advanced-settings" &&
        next !== "advanced-settings" &&
        settingsDirtyRef.current
      ) {
        const ok = window.confirm(
          "当前设定有未保存的修改，离开将丢失这些修改。确定继续吗？",
        );
        if (!ok) return;
      }
      if (next === "advanced-settings" && view !== "advanced-settings")
        settingsDirtyRef.current = false;
      setView(next, payload);
    },
    [view, setView],
  );
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

  // ── 选中节点解析：章 → 章对象工作台；卷 → 卷纲面板 ────────────────────
  const chapterRef =
    selectedRef && /^vol-\d+-ch-\d+$/.test(selectedRef) ? selectedRef : null;
  const volumeSelId =
    !chapterRef && selectedId && /^vol-\d+$/.test(selectedId) ? selectedId : null;

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

  const sideText =
    view === "advanced-settings"
      ? "设定 · 若干项，确认即作为 AI 上下文（可选）"
      : view === "archives"
        ? "预览 · 只读正文，通读全篇"
        : "写作 · 卷有卷纲；点章即可配章纲、提示词并写正文";

  // ── 升级 PRO 弹窗（novelbar / 右栏 locked 卡共用） ────────────────────
  const [showUpgrade, setShowUpgrade] = useState(false);
  const onUpgrade = useCallback(() => setShowUpgrade(true), []);

  // ── 只读章 AI 解锁链（真 bug #1/#2 修复，book.html openAiModal 链） ────
  // 归档章点任意 AI 写入工具 → 先弹「解除只读」→ 确认后 unarchive 并续跑原动作；
  // 生成正文经 AiModal（提示词预览/编辑），其余工具直接执行。
  type AiAction =
    | { kind: "write" }
    | { kind: "continue"; capture?: SelectionCapture | null }
    | { kind: "selection"; mode: "polish" | "expand"; capture: SelectionCapture | null };

  const [showUnlock, setShowUnlock] = useState(false);
  const [showAiModal, setShowAiModal] = useState(false);
  // 生成已启动的信号（计数器）：ChapterWorkspace 收到即切正文页签 + 聚焦（真 bug #2）
  const [aiWriteSignal, setAiWriteSignal] = useState(0);
  // 弹窗确认回调读取最新待续跑动作（闭包防串态）
  const pendingAiRef = useRef<AiAction | null>(null);

  const runAiAction = useCallback((action: AiAction) => {
    if (action.kind === "write") {
      setShowAiModal(true);
      return;
    }
    if (action.kind === "continue") {
      proseRef.current?.continueWriting(action.capture ?? undefined);
      return;
    }
    if (action.capture) {
      if (action.mode === "polish") proseRef.current?.polish(action.capture);
      else proseRef.current?.expand(action.capture);
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
  //    无记录回落「最新归档章」，再回落首章；卷面进度 = 该卷已归档/总章数。
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
    draft: boolean;
    fromLastWrite: boolean;
    scroll: number;
    volNo: number;
    archivedN: number;
    total: number;
  }
  const hereTarget = useMemo<HereTarget | null>(() => {
    const findByRef = (ref: string) => {
      const m = ref.match(/^(vol-\d+)-ch-(\d+)$/);
      if (!m) return null;
      const v = volumes.find((x) => x.name === m[1]);
      const c = v?.chapters.find((x) => x.chapter === Number(m[2]));
      return v && c ? { v, c } : null;
    };
    type Hit = { v: (typeof volumes)[number]; c: (typeof volumes)[number]["chapters"][number] };
    let pick: Hit | null = null;
    let fromLastWrite = false;
    if (lastWrite) {
      const hit = findByRef(lastWrite.ref);
      if (hit) {
        pick = hit;
        fromLastWrite = true;
      }
    }
    if (!pick) {
      for (const v of volumes) {
        for (const c of v.chapters) {
          if (c.archived) pick = { v, c };
        }
      }
    }
    if (!pick) {
      for (const v of volumes) {
        if (v.chapters.length) {
          pick = { v, c: v.chapters[0] };
          break;
        }
      }
    }
    if (!pick) return null;
    const volNo = Number((pick.v.name.match(/^vol-(\d+)$/) ?? [])[1] ?? 1);
    const no = pick.c.chapter ?? pick.v.chapters.indexOf(pick.c) + 1;
    return {
      ref: `${pick.v.name}-ch-${no}`,
      no,
      title: pick.c.title,
      draft:
        !pick.c.archived &&
        ((pick.c.has_prose ?? (pick.c.word_count ?? 0) > 0) ||
          // 树上的字数只在归档/增删时刷新：正在写的章用 railData 实时字数补判
          (selectedRef === `${pick.v.name}-ch-${pick.c.chapter}` &&
            (railData?.wordCount ?? 0) > 0)),
      fromLastWrite,
      scroll: fromLastWrite ? (lastWrite?.scroll ?? 0) : 0,
      volNo,
      archivedN: pick.v.chapters.filter((c) => c.archived).length,
      total: pick.v.chapters.length,
    };
  }, [volumes, lastWrite, selectedRef, railData]);

  const onResume = useCallback(() => {
    if (!hereTarget) return;
    if (!guardedLeave()) return;
    focusNode(hereTarget.ref);
    setResumeSignal((s) => ({
      ref: hereTarget.ref,
      scroll: hereTarget.scroll,
      n: (s?.n ?? 0) + 1,
    }));
  }, [hereTarget, guardedLeave, focusNode]);

  const pct = hereTarget
    ? Math.round(Math.min(1, hereTarget.archivedN / hereTarget.total) * 100)
    : 0;
  const hereBar = hereTarget ? (
    <>
      <p className="bh-k">当前主线</p>
      <span className="bh-rule" aria-hidden="true" />
      <p className="bh-t">
        <span className="n">第 {hereTarget.no} 章</span>
        {/* 默认名（「第一章」等序号形态）不再拼名称，避免「第 1 章第一章」（nodeLabel 同口径） */}
        {isDefaultTitle("章", hereTarget.no, hereTarget.title) ? null : hereTarget.title}
      </p>
      {hereTarget.draft && (
        <span className="bh-tag bh-tag-live">草稿</span>
      )}
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
        title="回到上次退出前的位置"
        onClick={onResume}
      >
        续写
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
          onGoSettings={() => go("advanced-settings")}
          registerRefetch={registerPhaseRefetch}
          inSettings={view === "advanced-settings"}
        />
      </ProContainer>

      {/* 书内模块导航：设定 / 写作 / 预览（默认写作） */}
      <nav className="modnav">
        <button
          className={`mtab${view === "advanced-settings" ? " on" : ""}`}
          onClick={() => go("advanced-settings")}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" width="15" height="15">
            <path d="M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4L16.5 3.5z" />
          </svg>
          设定 <span className="cnt">{settingsDone}/8</span>
        </button>
        <button
          className={`mtab${view === "workbench" ? " on" : ""}`}
          onClick={() => go("workbench")}
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
          onClick={() => go("archives")}
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
        <aside className="col-tree">
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
          />
        </aside>

        <main className="col-middle">
          {chapterRef ? (
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
              onAiWrite={() => requestAi({ kind: "write" })}
              aiWriteSignal={aiWriteSignal}
            />
          ) : volumeSelId ? (
            <VolumePanel
              projectId={projectId}
              volumeRef={volumeSelId}
              onGoChapter={handleChapterJump}
              onVolumeMutated={() => void refresh()}
              onDirtyChange={handleVolumeDirty}
            />
          ) : (
            <div className="col-panel">
              <div className="panel">
                <div className="panel-head">
                  <h2>开始创作</h2>
                </div>
                <p className="desc">
                  在左侧树头点「＋」添加第一卷，再为每卷添加章节，点章即可配章纲并写正文。
                </p>
              </div>
            </div>
          )}
        </main>

        <aside className="col-ai">
          <Rail
            mode={chapterRef ? "chapter" : "volume"}
            isPro={isPro}
            onUpgrade={onUpgrade}
            proseRef={proseRef}
            aiState={aiState}
            data={chapterRef ? (railData ?? undefined) : undefined}
            onAiWrite={() => requestAi({ kind: "write" })}
            onAiContinue={() =>
              requestAi({ kind: "continue", capture: proseRef.current?.captureNow() ?? null })
            }
            onAiSelection={(mode, capture) => requestAi({ kind: "selection", mode, capture })}
          />
        </aside>
      </div>

      {/* 设定：two-col（SettingsView 复刻 #viewSettings） */}
      {view === "advanced-settings" && (
        <SettingsView
          projectId={projectId}
          initialPanel={wb.viewPayload?.panel as string | undefined}
          settingsStatus={settingsStatus}
          confirmedStatus={confirmedStatus}
          charStale={charStale}
          confirmSetting={handleConfirmSetting}
          onDirtyChange={handleSettingsDirty}
          onGoWrite={() => setView("workbench")}
          novelName={project?.name ?? ""}
        />
      )}
      {/* 预览：只读树 + 只读排版（PreviewView 复刻 #viewPreview） */}
      {view === "archives" && (
        <PreviewView
          projectId={projectId}
          volumes={volumes}
          outline={outline}
          initialRef={chapterRef}
          onRefresh={handleArchivesRefresh}
        />
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

