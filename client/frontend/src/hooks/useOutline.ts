import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "@/lib/toast";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type OutlineStatus = "unfilled" | "in_progress" | "confirmed";

export interface ChapterData {
  volume: number;
  chapter: number;
  title: string;
  status: string;
  /** 拆章两格（c-chapter-plan-ai；顶层键，与 ladder_exit 同层；
   *  c-og-slim-v2：「本章行动」随该列退役） */
  challenge?: string;
  plot_stage?: string;
  /** 章内剧情（c-plot-split；顶层键，presence-gate：缺键保持原样、显式 [] 清空） */
  plot_items?: string[];
  outline?: {
    summary?: string;
    characters?: string[];
    [key: string]: unknown;
  };
  memo?: {
    payoff_plan?: {
      must_resolve?: string[];
      must_hold?: string[];
    };
    required_changes?: string[];
    prohibitions?: string[];
    downtime_functions?: string[];
    key_choices?: string[];
    [key: string]: unknown;
  };
  emotional_design?: {
    primary_mood?: string;
    [key: string]: unknown;
  };
  segments?: Array<{
    summary?: string;
    target_words?: number;
    [key: string]: unknown;
  }>;
  /** 提示词格子（ai-prompt-crafting）：场景卡 / 读者获得 / 章末落点 / 目标字数 */
  scene_cards?: Array<{
    scene_name?: string;
    goal?: string;
    obstacle?: string;
    hook?: string;
    weight?: string;
    focus?: string;
    [key: string]: unknown;
  }>;
  micro_payoffs?: Array<{
    kind?: string;
    description?: string;
    location?: string;
    [key: string]: unknown;
  }>;
  ladder_exit?: string;
  word_target?: number | null;
  prose?: string;
  word_count?: number;
  [key: string]: unknown;
}

export interface ChapterMetaEntry {
  ref: string;
  /** DB 章 id（foreshadow-settings-v2：伏笔选择器按 id 引用章；旧树缺省时不读） */
  id?: string;
  volume: number;
  chapter: number;
  title: string;
  status: string;
  word_count: number;
  /** DB-backed 全量树（change 005）缺省时降级本地推断（N1） */
  has_prose?: boolean;
  archived?: boolean;
  /** chapter-rewrite：基于旧设定（上游章被重写置位、本章保存清除） */
  stale?: boolean;
}

export interface VolumeEntry {
  ref: string;
  title: string;
  summary: string;
  chapter_count: number;
  chapters: ChapterMetaEntry[];
  /** DB-backed 全量树（change 005）缺省时降级本地推断（N1） */
  has_prose?: boolean;
  archived?: boolean;
}

interface TreeResponse {
  volumes: VolumeEntry[];
}

export interface UseOutlineReturn {
  loading: boolean;
  error: string | null;
  volumes: VolumeEntry[];
  chaptersMap: Map<string, ChapterData>;
  chapterStatuses: Map<string, OutlineStatus>;
  totalChapters: number;
  filledCount: number;
  confirmedCount: number;
  allConfirmed: boolean;
  loadChapterData(ref: string): Promise<ChapterData>;
  saveChapter(ref: string, data: Partial<ChapterData>): Promise<{ warnings?: string[] }>;
  confirmChapter(ref: string): Promise<void>;
  unconfirmChapter(ref: string): Promise<void>;
  transitionToPrompt(): Promise<void>;
  refetchTree(): Promise<void>;
}

// ---------------------------------------------------------------------------
// Status helpers
// ---------------------------------------------------------------------------

function deriveOutlineStatus(
  meta: ChapterMetaEntry,
  chapterData?: ChapterData,
): OutlineStatus {
  // 归档章视为已确认（c-og-badge-archived-confirm）：后端 status 单列生命周期
  // outline→draft→confirmed→archived，归档收口覆写 confirmed（archive/dossier.py），
  // 确认事实由归档态蕴含——c-og-confirm-gates 落地「归档双硬门」后字面为真。
  // 展示层投影的共同上游：写作徽标 / 树 dot / 删除盘点 chips 三面共用本函数。
  // 判据须在 chapterData 判定之前（真归档章 chapterData 带 outline.summary、
  // chapterDetail 甚至无 outline 字段——放后面会回落 in_progress/unfilled）；
  // 只认 meta.status 单一事实源，不读 outline_status（同源派生列、口径不同源）。
  if (meta.status === "confirmed" || meta.status === "archived")
    return "confirmed";
  if (chapterData) {
    const hasContent = !!chapterData.outline?.summary;
    return hasContent ? "in_progress" : "unfilled";
  }
  // Infer from tree-level status — if it's not 'outline', someone has been working on it
  return meta.status !== "outline" ? "in_progress" : "unfilled";
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useOutline(projectId: string): UseOutlineReturn {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [volumes, setVolumes] = useState<VolumeEntry[]>([]);
  const [chaptersMap, setChaptersMap] = useState<Map<string, ChapterData>>(
    () => new Map(),
  );
  const [chapterStatuses, setChapterStatuses] = useState<
    Map<string, OutlineStatus>
  >(() => new Map());

  // Ref to avoid stale closures in async callbacks
  const chaptersMapRef = useRef(chaptersMap);
  chaptersMapRef.current = chaptersMap;

  // -----------------------------------------------------------------------
  // Build chapter statuses from tree metadata + loaded chapter data
  // -----------------------------------------------------------------------

  const buildStatuses = useCallback(
    (vols: VolumeEntry[], chMap: Map<string, ChapterData>) => {
      const statuses = new Map<string, OutlineStatus>();
      for (const vol of vols) {
        for (const ch of vol.chapters) {
          statuses.set(ch.ref, deriveOutlineStatus(ch, chMap.get(ch.ref)));
        }
      }
      return statuses;
    },
    [],
  );

  // -----------------------------------------------------------------------
  // Refresh tree from server
  // -----------------------------------------------------------------------

  const refetchTree = useCallback(async () => {
    if (!projectId) return; // 项目缺失（如书被删除后残留的标签页）：不发空 id 请求，避免 404 循环
    setLoading(true);
    setError(null);
    try {
      const res: TreeResponse = await api.get(
        `/novels/${projectId}/tree`,
      );
      const vols = res.volumes || [];
      setVolumes(vols);
      const statuses = buildStatuses(vols, chaptersMapRef.current);
      setChapterStatuses(statuses);
    } catch (e: any) {
      setError(e.message || "加载章纲树失败");
    } finally {
      setLoading(false);
    }
  }, [projectId, buildStatuses]);

  useEffect(() => {
    refetchTree();
  }, [refetchTree]);

  // -----------------------------------------------------------------------
  // Load a single chapter's full data
  // -----------------------------------------------------------------------

  const loadChapterData = useCallback(
    async (ref: string): Promise<ChapterData> => {
      const data: ChapterData = await api.get(
        `/novels/${projectId}/chapters/${ref}`,
      );

      setChaptersMap((prev) => {
        const next = new Map(prev);
        next.set(ref, data);
        return next;
      });

      // Recalculate status for this chapter only
      setChapterStatuses((prev) => {
        const next = new Map(prev);
        for (const vol of volumes) {
          for (const ch of vol.chapters) {
            if (ch.ref === ref) {
              next.set(ref, deriveOutlineStatus(ch, data));
              break;
            }
          }
        }
        return next;
      });

      return data;
    },
    [projectId, volumes],
  );

  // -----------------------------------------------------------------------
  // Save (partial) chapter data
  // -----------------------------------------------------------------------

  const saveChapter = useCallback(
    async (ref: string, data: Partial<ChapterData>) => {
      const existing = chaptersMapRef.current.get(ref);
      // Merge incoming partial data with known data
      const merged: ChapterData = { ...existing, ...data } as ChapterData;

      const res = (await api.put(`/novels/${projectId}/chapters/${ref}`, merged)) as {
        warnings?: string[];
      };

      setChaptersMap((prev) => {
        const next = new Map(prev);
        next.set(ref, merged);
        return next;
      });

      // Recalculate status
      setChapterStatuses((prev) => {
        const next = new Map(prev);
        for (const vol of volumes) {
          for (const ch of vol.chapters) {
            if (ch.ref === ref) {
              next.set(ref, deriveOutlineStatus(ch, merged));
              break;
            }
          }
        }
        return next;
      });

      // 出场角色未命中告警（character-settings-v2）由调用方上屏
      return { warnings: res?.warnings };
    },
    [projectId, volumes],
  );

  // -----------------------------------------------------------------------
  // Confirm a single chapter
  // -----------------------------------------------------------------------

  const confirmChapter = useCallback(
    async (ref: string) => {
      try {
        await api.post(`/novels/${projectId}/chapters/${ref}/confirm`);
      } catch (e: any) {
        // 后端 400 detail 含具体缺失项（如"章纲确认失败，请先填写：核心任务、段落规划"）
        toast.error(e?.message || "确认失败，请检查章节内容是否完整");
        return;
      }

      // Optimistically update local state
      const updatedVolumes = volumes.map((v) => ({
        ...v,
        chapters: v.chapters.map((c) =>
          c.ref === ref ? { ...c, status: "confirmed" as const } : c,
        ),
      }));
      setVolumes(updatedVolumes);

      setChapterStatuses((prev) => {
        const next = new Map(prev);
        next.set(ref, "confirmed");
        return next;
      });
    },
    [projectId, volumes],
  );

  // -----------------------------------------------------------------------
  // Unconfirm a single chapter（c-og-draft-no-autconfirm）：确认态退回草稿
  // -----------------------------------------------------------------------

  const unconfirmChapter = useCallback(
    async (ref: string) => {
      try {
        await api.post(`/novels/${projectId}/chapters/${ref}/unconfirm`);
      } catch (e: any) {
        toast.error(e?.message || "撤回确认失败，请重试");
        return;
      }

      // Optimistically update local state（与 confirmChapter 对称）
      const updatedVolumes = volumes.map((v) => ({
        ...v,
        chapters: v.chapters.map((c) =>
          c.ref === ref ? { ...c, status: "draft" as const } : c,
        ),
      }));
      setVolumes(updatedVolumes);

      setChapterStatuses((prev) => {
        const next = new Map(prev);
        // 确认过的章必填已齐（gate）→ 撤回后派生态＝已填未确认
        next.set(ref, "in_progress");
        return next;
      });
    },
    [projectId, volumes],
  );

  // -----------------------------------------------------------------------
  // Transition workflow to prompt phase
  // -----------------------------------------------------------------------

  const transitionToPrompt = useCallback(async () => {
    try {
      await api.post(`/novels/${projectId}/workflow/transition`, {
        target: "prompt",
      });
    } catch {
      toast.error("确认全部章纲失败，请检查是否还有未完成的章节");
    }
  }, [projectId]);

  // -----------------------------------------------------------------------
  // Computed aggregate values
  // -----------------------------------------------------------------------

  const computed = useMemo(() => {
    let total = 0;
    let filled = 0;
    let confirmed = 0;

    for (const vol of volumes) {
      for (const ch of vol.chapters) {
        total++;
        const status = chapterStatuses.get(ch.ref) || "unfilled";
        if (status === "in_progress" || status === "confirmed") filled++;
        if (status === "confirmed") {
          confirmed++;
        }
      }
    }

    return {
      totalChapters: total,
      filledCount: filled,
      confirmedCount: confirmed,
      allConfirmed: total > 0 && confirmed === total,
    };
  }, [volumes, chapterStatuses, chaptersMap]);

  return {
    loading,
    error,
    volumes,
    chaptersMap,
    chapterStatuses,
    ...computed,
    loadChapterData,
    saveChapter,
    confirmChapter,
    unconfirmChapter,
    transitionToPrompt,
    refetchTree,
  };
}
