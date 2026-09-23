// 提示词管理（整章单卡，ai-prompt-crafting）：每章一张卡，承载该章唯一的
// 整章写作提示词 —— 查看分段渲染 / 编辑保存 / 「AI 润色」（素材包 → 大模型
// 润色 → 校验落库）。分段提示词列表与「生成段落提示词」按钮已随分段链路退役。
// PR 5 轻重皮：design 类与图标注册表（pm-* 壳沿用）。
import { useCallback, useEffect, useMemo, useState } from "react";
import { Ico, P } from "@/components/icons";
import { api, request } from "@/lib/api";
import { toast } from "@/lib/toast";
import { getToken } from "@/lib/auth";
import { getApiBaseUrl } from "@/lib/env";
import { polishWritePrompt } from "@/lib/ai";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface VolumeInfo {
  name: string;
  volNum: number;
  chapters: { ref: string; title: string }[];
}

/** 章卡状态：none = 无存量；saved = 存量整章提示词；polished/modified = 本会话润色/编辑过 */
type ChapterStatus = "none" | "saved" | "polished" | "modified";

interface ChapterPromptInfo {
  chapterRef: string;
  chapterTitle: string;
  hasStored: boolean;
  status: ChapterStatus;
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface PromptManagementPageProps {
  projectId: string;
  /** 传入时 overview 只渲染该章的卡片（工作台「提示词」子 label 按当前章过滤，011） */
  chapterRef?: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Fetch raw text prompt content from the API (PlainTextResponse).
 * seg 固定 "write"：整章单卡退役了分段 seg-N（后端其余 seg 404）。
 */
async function fetchPromptText(
  projectId: string,
  chapterRef: string,
): Promise<string> {
  const token = getToken();
  const res = await fetch(
    `${getApiBaseUrl()}/api/novels/${projectId}/chapters/${chapterRef}/prompts/write`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  if (!res.ok) {
    // 404＝确无存量（空态引导）；其余（5xx/网络）由调用方走失败态（c-silent-data-guards）
    const errText = await res.text().catch(() => res.statusText);
    const err = new Error(errText || "获取提示词失败") as Error & { status?: number };
    err.status = res.status;
    throw err;
  }
  return res.text();
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function PromptManagementPage({
  projectId,
  chapterRef,
}: PromptManagementPageProps) {
  // ── Internal view state ────────────────────────────────────────────
  const [view, setView] = useState<"overview" | "viewer" | "editor">(
    "overview",
  );

  // ── Overview state ─────────────────────────────────────────────────
  const [volumes, setVolumes] = useState<VolumeInfo[]>([]);
  const [chapterPrompts, setChapterPrompts] = useState<
    Record<string, ChapterPromptInfo>
  >({});
  const [overviewLoading, setOverviewLoading] = useState(true);
  // 加载失败≠「没有卷章/没有提示词」：显式失败态＋重试（c-silent-data-guards）
  const [volumesError, setVolumesError] = useState(false);
  const [promptsError, setPromptsError] = useState(false);
  const [reloadTick, setReloadTick] = useState(0);
  const reload = useCallback(() => setReloadTick((t) => t + 1), []);
  // 未配 AI Key（prompts 端点 503）：就地提示 + 去配置，不再整页跳 /config
  const [aiUnavailable, setAiUnavailable] = useState(false);
  const [expandedChapters, setExpandedChapters] = useState<Set<string>>(
    new Set(),
  );

  // 当前可见章节：传入 chapterRef 时只保留该章（工作台子 label 按当前章过滤）
  const visibleChapters = useMemo(
    () =>
      chapterRef
        ? volumes.flatMap((v) => v.chapters).filter((ch) => ch.ref === chapterRef)
        : volumes.flatMap((v) => v.chapters),
    [volumes, chapterRef],
  );

  // 传入 chapterRef 时自动展开该章，直达提示词卡
  useEffect(() => {
    if (chapterRef) setExpandedChapters(new Set([chapterRef]));
  }, [chapterRef]);

  // ── Viewer / editor state ──────────────────────────────────────────
  const [viewerChapterRef, setViewerChapterRef] = useState("");
  const [viewerContent, setViewerContent] = useState("");
  const [viewerLoading, setViewerLoading] = useState(false);
  const [viewerError, setViewerError] = useState(false);
  const [polishing, setPolishing] = useState(false);
  const [polishError, setPolishError] = useState<string | null>(null);

  // ── Editor state ───────────────────────────────────────────────────
  const [editorContent, setEditorContent] = useState("");
  const [saving, setSaving] = useState(false);

  // =====================================================================
  // Data loading
  // =====================================================================

  // Load volumes & chapters
  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;

    async function load() {
      setOverviewLoading(true);
      setVolumesError(false);
      try {
        // change 006：GET /volumes 返回 DB 全量树（卷含 ref + chapters 元数据），
        // 卷章一次到位，无需逐卷二次请求。
        const vols: any[] = await api.get(`/novels/${projectId}/volumes`);
        const result: VolumeInfo[] = vols.map((v) => {
          const volNum =
            parseInt((v.ref || "").replace("vol-", ""), 10) || 0;
          const chapters = (v.chapters || []).map((ch: any) => ({
            ref: ch.ref,
            title: ch.title || `ch-${ch.chapter}`,
          }));
          return { name: v.ref, volNum, chapters };
        });
        if (!cancelled) setVolumes(result);
      } catch {
        // 失败要可见：静默呈现为「没有卷章」会诱导作者以为书空了
        if (!cancelled) setVolumesError(true);
      } finally {
        if (!cancelled) setOverviewLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [projectId, reloadTick]);

  // Fetch stored-prompt existence（批量端点一次取全书，替代逐章串行 N+1）
  useEffect(() => {
    if (volumes.length === 0) return;
    let cancelled = false;

    async function loadAllPrompts() {
      setPromptsError(false);
      setAiUnavailable(false);
      try {
        const res = (await request(`/novels/${projectId}/prompt-summary`, { soft503: true })) as {
          chapters: { ref: string; has_stored: boolean }[];
        };
        const stored = new Set(res.chapters.filter((c: { has_stored: boolean }) => c.has_stored).map((c: { ref: string }) => c.ref));
        const newMap: Record<string, ChapterPromptInfo> = {};
        for (const ch of visibleChapters) {
          const hasStored = stored.has(ch.ref);
          newMap[ch.ref] = {
            chapterRef: ch.ref,
            chapterTitle: ch.title,
            hasStored,
            status: hasStored ? "saved" : "none",
          };
        }
        if (!cancelled) setChapterPrompts(newMap);
      } catch (e: any) {
        if (cancelled) return;
        // 503 = 会员但未配 AI Key：就地提示（沿用原口径）
        if (e?.status === 503) {
          setAiUnavailable(true);
          return;
        }
        setPromptsError(true);
      }
    }

    loadAllPrompts();
    return () => {
      cancelled = true;
    };
  }, [visibleChapters, projectId, reloadTick]);

  // =====================================================================
  // Actions
  // =====================================================================

  const openViewer = useCallback(
    async (chRef: string) => {
      setView("viewer");
      setViewerChapterRef(chRef);
      setViewerLoading(true);
      setPolishError(null);
      setViewerError(false);
      setViewerContent("");
      try {
        const text = await fetchPromptText(projectId, chRef);
        setViewerContent(text);
      } catch (e: any) {
        // 404＝确无存量 → 空态引导（润色或生成时会落库）；其余失败≠「没有」，要能重试
        if (e?.status === 404) {
          setViewerContent("");
        } else {
          setViewerError(true);
        }
      } finally {
        setViewerLoading(false);
      }
    },
    [projectId],
  );

  const handlePolish = useCallback(async () => {
    if (polishing || !viewerChapterRef) return;
    setPolishing(true);
    setPolishError(null);
    try {
      const text = await polishWritePrompt(projectId, viewerChapterRef);
      setViewerContent(text);
      setEditorContent(text);
      setChapterPrompts((prev) => {
        const ch = prev[viewerChapterRef];
        if (!ch) return prev;
        return {
          ...prev,
          [viewerChapterRef]: { ...ch, hasStored: true, status: "polished" },
        };
      });
      toast.success("AI 润色完成 · 已保存");
    } catch (e: any) {
      // 502（润色未过校验/模型出错）不动既有行 → 就地提示可重试
      setPolishError(e?.message || "润色失败，请重试");
    } finally {
      setPolishing(false);
    }
  }, [projectId, viewerChapterRef, polishing]);

  const handleEdit = useCallback(() => {
    setEditorContent(viewerContent);
    setView("editor");
  }, [viewerContent]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      await api.put(
        `/novels/${projectId}/chapters/${viewerChapterRef}/prompts/write`,
        { content: editorContent },
      );
      setViewerContent(editorContent);
      setChapterPrompts((prev) => {
        const ch = prev[viewerChapterRef];
        if (!ch) return prev;
        return {
          ...prev,
          [viewerChapterRef]: { ...ch, hasStored: true, status: "modified" },
        };
      });
      toast.success("保存成功");
      setView("viewer");
    } catch (e: any) {
      toast.error(e.message || "保存失败");
    } finally {
      setSaving(false);
    }
  }, [projectId, viewerChapterRef, editorContent]);

  const handleCancelEdit = useCallback(() => {
    setView("viewer");
  }, []);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(viewerContent);
      toast.success("已复制到剪贴板");
    } catch {
      toast.error("复制失败");
    }
  }, [viewerContent]);

  const handleBackToOverview = useCallback(() => {
    setView("overview");
  }, []);

  const toggleChapter = useCallback((ref: string) => {
    setExpandedChapters((prev) => {
      const next = new Set(prev);
      if (next.has(ref)) next.delete(ref);
      else next.add(ref);
      return next;
    });
  }, []);

  // =====================================================================
  // Parse prompt content into sections
  // =====================================================================

  const parsedSections = useMemo(() => {
    if (!viewerContent) return [];

    const lines = viewerContent.split("\n");
    const sections: { heading: string; body: string[] }[] = [];
    let currentHeading = "";
    let currentBody: string[] = [];

    for (const line of lines) {
      const headingMatch = line.match(/^#{1,3}\s+(.+)/);
      if (headingMatch) {
        if (currentHeading || currentBody.length > 0) {
          sections.push({ heading: currentHeading, body: currentBody });
        }
        currentHeading = headingMatch[1].trim();
        currentBody = [];
      } else if (line.trim() === "" && currentBody.length === 0) {
        // skip leading blank lines
      } else {
        currentBody.push(line);
      }
    }
    sections.push({ heading: currentHeading, body: currentBody });

    // If no markdown headings found, split by double newlines
    if (
      sections.length === 1 &&
      !sections[0].heading &&
      sections[0].body.length > 0
    ) {
      const paras = viewerContent.split(/\n\n+/);
      return paras.map((p) => ({
        heading: "",
        body: p.split("\n"),
      }));
    }

    return sections;
  }, [viewerContent]);

  // =====================================================================
  // Render: Overview
  // =====================================================================

  const renderOverview = () => {
    if (overviewLoading) {
      return (
        <div className="pm-loading">
          <Ico d={P.spinner} className="spin" size={18} style={{ color: "var(--accent)" }} />
        </div>
      );
    }

    // 卷章骨架/提示词清单加载失败：显式失败态＋重试，不冒充「没有卷章」（c-silent-data-guards）
    if (volumesError || promptsError) {
      return (
        <div className="pm-empty" data-testid="pm-load-error">
          <Ico d={P.doc} size={28} style={{ color: "var(--muted)" }} />
          <div className="pm-empty-text">
            <p>提示词清单没加载出来</p>
            <p className="sub">
              {volumesError
                ? "章节列表没读到，为避免误显为「没有章节」，请重新加载。"
                : "各章提示词状态没读到，请重新加载。"}
            </p>
          </div>
          <button className="btn btn-primary btn-sm" onClick={reload}>
            重新加载
          </button>
        </div>
      );
    }

    // 未配 AI Key：提示词读写全链路不可用 → 就地引导配置（不整页跳转）
    if (aiUnavailable) {
      return (
        <div className="pm-empty">
          <Ico d={P.lock} size={28} style={{ color: "var(--muted)" }} />
          <div className="pm-empty-text">
            <p>尚未配置模型 API Key</p>
            <p className="sub">
              提示词的润色与查看需要 AI 能力，请先配置 API Key 后再使用。
            </p>
          </div>
          <a href="#/config" className="btn btn-primary btn-sm">
            去配置
          </a>
        </div>
      );
    }

    const allChapters = visibleChapters;

    if (allChapters.length === 0) {
      return (
        <div className="pm-empty">
          <Ico d={P.doc} size={28} style={{ color: "var(--muted)" }} />
          <p className="pm-empty-text">
            {volumes.length > 0
              ? "未找到当前章节的提示词"
              : '暂无章节，请先在"正文"中创建章节'}
          </p>
        </div>
      );
    }

    return (
      <div>
        <h2 className="serif pm-h2">提示词管理</h2>

        {allChapters.map((ch) => {
          const info = chapterPrompts[ch.ref];
          const status = info?.status || "none";

          const statusBadge =
            status === "polished" ? (
              <span className="badge ok">
                <Ico d={P.spark} size={10} />
                已润色
              </span>
            ) : status === "modified" ? (
              <span className="badge warn">
                <Ico d={P.dot} fill size={10} />
                已修改
              </span>
            ) : status === "saved" ? (
              <span className="badge ok">
                <Ico d={P.check} sw={2.6} size={10} />
                已保存
              </span>
            ) : (
              <span className="badge empty">未生成</span>
            );

          const isExpanded = expandedChapters.has(ch.ref);

          return (
            <div key={ch.ref} className="pm-card">
              {/* Chapter header */}
              <button onClick={() => toggleChapter(ch.ref)} className="pm-head">
                <Ico
                  d={isExpanded ? P.chevronDown : P.chevronRight}
                  sw={1.8}
                  size={14}
                  style={{ color: "var(--muted)", flex: "none" }}
                />
                <span className="pm-title">{ch.title}</span>
                {statusBadge}
              </button>

              {/* Expanded content：整章单卡 */}
              {isExpanded && (
                <div className="pm-body">
                  <div
                    className="pm-row"
                    data-testid="pm-write-row"
                    onClick={() => void openViewer(ch.ref)}
                  >
                    <span className="idx">W.</span>
                    <span
                      style={{
                        flex: 1,
                        minWidth: 0,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      整章写作提示词
                    </span>
                    <Ico d={P.eye} size={14} style={{ color: "var(--muted)" }} />
                  </div>
                  <p className="pm-none">
                    每章一条整章提示词 ·「AI 生成正文」弹窗内可先润色再生成
                  </p>
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  };

  // =====================================================================
  // Render: Viewer
  // =====================================================================

  const renderViewer = () => {
    return (
      <div>
        {/* Action bar */}
        <div className="pm-bar">
          <button onClick={handleBackToOverview} className="btn btn-ghost btn-sm">
            <Ico d={P.back} sw={1.8} size={13} />
            返回
          </button>
          <span className="grow" />
          <span className="cnt">整章写作提示词</span>
          <span className="tsep" />
          <button
            onClick={() => void handlePolish()}
            disabled={polishing}
            className="btn btn-secondary btn-sm"
            data-testid="pm-polish"
          >
            {polishing ? (
              <Ico d={P.spinner} className="spin" size={12} />
            ) : (
              <Ico d={P.spark} size={12} />
            )}
            {polishing ? "润色中…" : "AI 润色"}
          </button>
          <button onClick={handleCopy} className="btn btn-secondary btn-sm">
            <Ico d={P.copy} size={13} />
            复制全文
          </button>
          <button onClick={handleEdit} className="btn btn-primary btn-sm">
            <Ico d={P.pencil} size={13} />
            编辑
          </button>
        </div>

        {/* 润色失败：就地重试（后端失败不清空既有行） */}
        {polishError && (
          <p style={{ margin: "0 0 10px", fontSize: 12.5, color: "var(--err)" }}>
            {polishError} ·{" "}
            <button
              className="btn btn-ghost btn-sm"
              disabled={polishing}
              onClick={() => void handlePolish()}
            >
              重试润色
            </button>
          </p>
        )}

        {/* Content area */}
        {viewerLoading ? (
          <div className="pm-loading">
            <Ico d={P.spinner} className="spin" size={18} style={{ color: "var(--accent)" }} />
          </div>
        ) : viewerError ? (
          <div className="pm-empty" data-testid="pm-write-error">
            <Ico d={P.doc} size={28} style={{ color: "var(--muted)" }} />
            <div className="pm-empty-text">
              <p>提示词没读出来</p>
              <p className="sub">读取失败与「还没有提示词」是两回事——请重试后再看。</p>
            </div>
            <button
              className="btn btn-primary btn-sm"
              onClick={() => void openViewer(viewerChapterRef)}
            >
              重新加载
            </button>
          </div>
        ) : viewerContent ? (
          <div data-testid="pm-write-view">
            {parsedSections.map((section, i) => (
              <div key={i} className="pm-sec" style={{ marginBottom: 10 }}>
                {section.heading && <h3>{section.heading}</h3>}
                <pre>{section.body.join("\n")}</pre>
              </div>
            ))}
          </div>
        ) : (
          <div className="pm-empty" data-testid="pm-write-empty">
            <Ico d={P.doc} size={28} style={{ color: "var(--muted)" }} />
            <div className="pm-empty-text">
              <p>本章还没有整章提示词</p>
              <p className="sub">
                点「AI 润色」由设定 + 章纲生成润色稿；或在「AI 生成正文」弹窗中直接组装。
              </p>
            </div>
          </div>
        )}
      </div>
    );
  };

  // =====================================================================
  // Render: Editor
  // =====================================================================

  const renderEditor = () => {
    return (
      <div>
        {/* Action bar */}
        <div className="pm-bar">
          <span className="pm-bar-title">整章写作提示词 · 编辑</span>
          <span className="grow" />
          <button onClick={handleCancelEdit} disabled={saving} className="btn btn-secondary btn-sm">
            <Ico d={P.close} size={13} />
            取消
          </button>
          <button
            onClick={() => void handleSave()}
            disabled={saving}
            className="btn btn-primary btn-sm"
            data-testid="pm-save"
          >
            {saving ? (
              <Ico d={P.spinner} className="spin" size={12} />
            ) : (
              <Ico d={P.check} size={13} />
            )}
            {saving ? "保存中…" : "保存"}
          </button>
        </div>

        {/* Textarea */}
        <textarea
          className="ai-prompt"
          style={{ height: "calc(100vh - 16rem)", minHeight: 400 }}
          value={editorContent}
          onChange={(e) => setEditorContent(e.target.value)}
          data-testid="pm-editor"
        />
      </div>
    );
  };

  // =====================================================================
  // Main render
  // =====================================================================

  return (
    <div className="prompt-mgmt">
      {view === "overview" && renderOverview()}
      {view === "viewer" && renderViewer()}
      {view === "editor" && renderEditor()}
    </div>
  );
}
