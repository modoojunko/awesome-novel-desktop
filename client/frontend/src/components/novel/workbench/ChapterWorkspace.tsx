// 章对象工作台（book.html #chWorkspace 复刻）：
//   工具栏（章名 + 归档标 + 排版 seg + 专注 + 版本历史 + 归档 + AI 生成正文）
//   三页签（章纲/提示词/正文，cnt 徽标）· 点章强制落章纲
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
import { charactersApi } from "@/lib/charactersApi";
import PromptPane from "./PromptPane";
import ProsePane, {
  INITIAL_PROSE_AI_STATE,
  type ProseAIState,
  type ProseHandle,
} from "./ProsePane";
import { ArchiveModal, HistoryModal } from "./modals";
import type { RailChapterData } from "./Rail";
import {
  EMPTY_OG_FORM,
  ogFormIssues,
  ogGaps,
  ogToForm,
  ogToPartial,
  type OgForm,
} from "./chapterForm";
import { useChapterData } from "@/hooks/useChapterData";
import { draftOutline } from "@/lib/ai";
import type { useOutline } from "@/hooks/useOutline";
import type { useWorkbench } from "@/hooks/useWorkbench";
import { api, request } from "@/lib/api";
import type { VolumeDetail } from "@/components/novel/volume/types";
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

type OutlineApi = ReturnType<typeof useOutline>;
type WorkbenchApi = ReturnType<typeof useWorkbench>;

interface ChapterWorkspaceProps {
  projectId: string;
  chapterRef: string;
  outline: OutlineApi;
  wb: WorkbenchApi;
  /** PRO 才渲染「AI 生成正文」按钮（右栏同口径；免费态见 ai-locked 卡） */
  isPro: boolean;
  /** ProPane ref 由页面持有（右栏 AI 工具共用同一实例） */
  proseRef: RefObject<ProseHandle | null>;
  aiState: ProseAIState;
  onAIStateChange: (update: (prev: ProseAIState) => ProseAIState) => void;
  /** 本书总字数（右栏进度卡，由页面从树汇总） */
  bookWords: number;
  /** 右栏本章进度数据实时上抛（字数/目标/归档随 store 变化） */
  onRailData: (data: RailChapterData | null) => void;
  /** AI 生成正文（页面级解锁链入口：归档章先弹「解除只读」→ AiModal） */
  onAiWrite: () => void;
  /** 生成启动信号（计数器递增）：切正文页签 + 聚焦（真 bug #2） */
  aiWriteSignal: number;
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
  onAiWrite,
  aiWriteSignal,
}: ChapterWorkspaceProps) {
  const store = useChapterData(projectId, chapterRef);
  const { wordCount, saveState, targetWords, setTargetWords } = store;

  // 树结构里的章元数据（编号/标题/归档位；volumes 常驻已加载）。
  // WorkbenchVolume.chapters 无 ref 字段 → 按 vol-N/ch-N 对齐。
  const chMeta = useMemo(() => {
    const m = chapterRef.match(/^vol-(\d+)-ch-(\d+)$/);
    if (!m) return null;
    const volName = `vol-${parseInt(m[1], 10)}`;
    const chNo = parseInt(m[2], 10);
    const vol = wb.volumes.find((v) => v.name === volName);
    return vol?.chapters.find((c) => c.chapter === chNo) ?? null;
  }, [wb.volumes, chapterRef]);
  const label = nodeLabel("章", chMeta?.chapter ?? 0, chMeta?.title);
  const archived = !!chMeta?.archived;

  // ── 信息差对齐（PR6）：章纲顶部只读块 ────────────────────────────────
  // 卷级 info_gap_start/end（卷纲 §三）+ 卷纲 §七章节规划行按章号对齐的本章 info_gap。
  // 增强展示：卷未配/接口失败一律静默置 null（不渲染），不打扰章纲主流程。
  const [infoGap, setInfoGap] = useState<{
    volStart: string;
    volEnd: string;
    chapterGap: string;
  } | null>(null);
  useEffect(() => {
    let cancelled = false;
    const m = chapterRef.match(/^vol-(\d+)-ch-(\d+)$/);
    if (!m) {
      setInfoGap(null);
      return;
    }
    const volRef = `vol-${parseInt(m[1], 10)}`;
    const chNo = parseInt(m[2], 10);
    api
      .get(`/novels/${projectId}/volumes/${volRef}`)
      .then((d: unknown) => {
        if (cancelled) return;
        const v = d as VolumeDetail;
        const plan = (v.chapter_plans ?? []).find((p) => p.chapter_no === chNo);
        const volStart = (v.info_gap_start ?? "").trim();
        const volEnd = (v.info_gap_end ?? "").trim();
        const chapterGap = (plan?.info_gap ?? "").trim();
        setInfoGap(
          volStart || volEnd || chapterGap
            ? { volStart, volEnd, chapterGap }
            : null,
        );
      })
      .catch(() => {
        if (!cancelled) setInfoGap(null);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, chapterRef]);

  // ── 三页签：点章强制落「章纲」（设计稿行为） ─────────────────────────
  const [chTab, setChTab] = useState<"og" | "prompt" | "prose">("og");
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

  const saveOg = useCallback(async (): Promise<boolean> => {
    if (ogLoadingRef.current) return false;
    const issues = ogFormIssues(ogForm);
    if (issues.length > 0) {
      toast.error(issues[0]);
      return false;
    }
    setOgSaving(true);
    try {
      await outline.saveChapter(
        chapterRef,
        ogToPartial(ogForm, outline.chaptersMap.get(chapterRef)),
      );
      ogSnapRef.current = JSON.stringify(ogForm);
      return true;
    } catch {
      toast.error("章纲保存失败，请重试");
      return false;
    } finally {
      setOgSaving(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [outline.saveChapter, outline.chaptersMap, chapterRef, ogForm]);

  // 3s 静默后台保存（不改 status；设计稿之外的应用侧扩展，已登记 ADJUSTMENTS）
  const ogKey = JSON.stringify(ogForm);
  useEffect(() => {
    if (ogLoadingRef.current) return;
    if (ogKey === ogSnapRef.current) return;
    // 校验不过时静默跳过（不打扰），待用户补齐后下一次输入触发重试
    if (ogFormIssues(ogForm).length > 0) return;
    const t = setTimeout(() => {
      outline
        .saveChapter(chapterRef, ogToPartial(ogForm, outline.chaptersMap.get(chapterRef)))
        .then(() => {
          ogSnapRef.current = ogKey;
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
      [ogForm.task, ogForm.summary, ogForm.mood, ogForm.rstate, ogForm.rstrat, ogForm.changes, ogForm.ladder, ogForm.wt].some(
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
    if (ok) toast.success(`《${label}》已归档 · 只读`);
  }, [archived, wordCount, projectId, label, store]);

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
    onRailDataRef.current({
      wordCount,
      targetWords,
      setTargetWords,
      archived,
      bookWords,
      unarchive: unarchiveRef.current,
    });
    return () => onRailDataRef.current(null);
  }, [wordCount, targetWords, setTargetWords, archived, bookWords]);

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
      <div className="editor-toolbar">
        <span className="ch-name serif">{label}</span>
        {archived && <span className="arch-tag">已归档</span>}
        <span className="grow" />
        <span className="prose-ctrls" hidden={chTab !== "prose"}>
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
          {isPro && (
            <button className="btn btn-primary btn-sm" onClick={onAiWrite}>
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2l2.4 6.2L21 9l-5 4.4 1.6 6.6L12 16.6 6.4 20 8 13.4 3 9l6.6-.8z" />
              </svg>
              AI 生成正文
            </button>
          )}
        </span>
      </div>

      <div className="ch-tabs" role="tablist" aria-label="章节对象">
        {(
          [
            ["og", "章纲", ogCnt],
            // 提示词子 label PRO-only：免费态隐藏（workbench-3-label spec）
            ...(isPro ? ([["prompt", "提示词", promptCnt]] as const) : []),
            ["prose", "正文", proseCnt],
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
      />

      <ArchiveModal
        open={showArchive}
        onClose={() => setShowArchive(false)}
        onConfirm={() => void handleArchive()}
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
          infoGap={infoGap}
          onPatch={(patch) => setOgForm((f) => ({ ...f, ...patch }))}
          gaps={gaps}
          confirmed={confirmed}
          saving={ogLoading || ogSaving}
          onSaveDraft={() => void handleSaveDraft()}
          onConfirm={() => void handleConfirm()}
          onGoWrite={() => void handleGoWrite()}
          canAiDraft={isPro}
          aiDrafting={aiDrafting}
          onAiDraft={() => void handleAiDraft()}
        />
      )}

      {chTab === "prompt" && (
        <PromptPane
          projectId={projectId}
          chapterRef={chapterRef}
          title={label}
          hasPrompts={hasPrompts}
        />
      )}

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
