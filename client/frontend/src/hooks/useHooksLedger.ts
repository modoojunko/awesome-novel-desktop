// 伏笔台账取数（c-og-hooks-projection 自 HooksPane 抽出共享）：
// /novels/{id}/hooks（真表投影，含废弃条——可见性过滤归各消费方）
// ＋卷章树（DB 章 id ↔ 章号/标题解析）。HooksPane 与章纲页两格投影共用。
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

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

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const d = (await api.get(`/novels/${projectId}/hooks`)) as {
          data?: { items?: HookRow[] };
          items?: HookRow[];
          count?: number;
        };
        // 端点外层 {ok, data:{count, items}}；容错 items 直挂在顶层
        const items = d.data?.items ?? d.items ?? [];
        if (!cancelled) setHooks(items);
      } catch {
        if (!cancelled) setError("伏笔台账加载失败");
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
        if (!cancelled) setChapters(flat);
      } catch {
        /* 树加载失败只影响章号解析，不阻断台账 */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  return { hooks, chapters, error };
}
