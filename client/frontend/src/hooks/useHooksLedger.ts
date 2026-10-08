// 伏笔台账取数（c-og-hooks-projection 自 HooksPane 抽出共享）：
// /novels/{id}/hooks（真表投影，含废弃条——可见性过滤归各消费方）
// ＋卷章树（DB 章 id ↔ 章号/标题解析）。HooksPane 与章纲页两格投影共用。
// 台账变更（hooksApi create/patch/remove/restore）广播 HOOKS_CHANGED_EVENT，
// 此处监听重取——页签「该收」泡泡与台账行免切章刷新（c-chtab-confirm-bubbles）。
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { HOOKS_CHANGED_EVENT } from "@/lib/hooksApi";

export interface HookRow {
  id: string;
  code: string;
  description: string;
  type: string;
  priority: number;
  status: string;
  introduced_chapter_id: string | null;
  planned_chapter_id: string | null;
  mentioned_chapter_id: string | null;
  resolved_chapter_id: string | null;
}

export interface ChapterLite {
  id: string;
  ref: string;
  chapter: number;
  title: string;
}

export function useHooksLedger(projectId: string): {
  hooks: HookRow[];
  chapters: ChapterLite[];
  error: string | null;
} {
  const [hooks, setHooks] = useState<HookRow[]>([]);
  const [chapters, setChapters] = useState<ChapterLite[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (cancelled: { v: boolean }) => {
      try {
        const d = (await api.get(`/novels/${projectId}/hooks`)) as {
          data?: { items?: HookRow[] };
          items?: HookRow[];
          count?: number;
        };
        // 端点外层 {ok, data:{count, items}}；容错 items 直挂在顶层
        const items = d.data?.items ?? d.items ?? [];
        if (!cancelled.v) setHooks(items);
      } catch {
        if (!cancelled.v) setError("伏笔台账加载失败");
      }
      try {
        const tree = (await api.get(`/novels/${projectId}/volumes`)) as Array<{
          name?: string;
          ref?: string;
          chapters?: Array<{ id?: string; chapter: number; ref?: string; title?: string }>;
        }>;
        const flat: ChapterLite[] = [];
        for (const v of tree) {
          for (const c of v.chapters ?? []) {
            const ref = c.ref ?? `${v.name ?? v.ref}-ch-${c.chapter}`;
            flat.push({
              id: c.id ?? ref,
              ref,
              chapter: c.chapter,
              title: c.title ?? "",
            });
          }
        }
        if (!cancelled.v) setChapters(flat);
      } catch {
        /* 树加载失败只影响章号解析，不阻断台账 */
      }
    },
    [projectId],
  );

  useEffect(() => {
    const cancelled = { v: false };
    void load(cancelled);
    return () => {
      cancelled.v = true;
    };
  }, [load]);

  // 台账变更广播 → 重取（detail.projectId 匹配才取；竞态守卫同上）
  useEffect(() => {
    const cancelled = { v: false };
    const onChanged = (e: Event) => {
      const d = (e as CustomEvent).detail as { projectId?: string };
      if (d?.projectId !== projectId) return;
      void load(cancelled);
    };
    window.addEventListener(HOOKS_CHANGED_EVENT, onChanged);
    return () => {
      window.removeEventListener(HOOKS_CHANGED_EVENT, onChanged);
      cancelled.v = true;
    };
  }, [load, projectId]);

  return { hooks, chapters, error };
}
