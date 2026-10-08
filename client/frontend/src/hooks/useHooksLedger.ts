// 伏笔台账取数（c-og-hooks-projection 自 HooksPane 抽出共享）：
// /novels/{id}/hooks（真表投影，含废弃条——可见性过滤归各消费方）
// ＋卷章树（DB 章 id ↔ 章号/标题解析）。HooksPane 与章纲页两格投影共用。
// 台账变更（hooksApi create/patch/remove/restore）广播 HOOKS_CHANGED_EVENT，
// 此处监听重取——页签「该收」泡泡与台账行免切章刷新（c-chtab-confirm-bubbles）。
import { useCallback, useEffect, useRef, useState } from "react";
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
  // 取数时序令牌：每次 load 领号，落库前校验仍是最新号——并发两次 load
  // （事件连发、挂载取数与事件取数撞车）旧响应后到不得覆盖新态；
  // 卸载时 +1 作废在途响应。
  const seqRef = useRef(0);

  const load = useCallback(async () => {
    const seq = ++seqRef.current;
    try {
      const d = (await api.get(`/novels/${projectId}/hooks`)) as {
        data?: { items?: HookRow[] };
        items?: HookRow[];
        count?: number;
      };
      // 端点外层 {ok, data:{count, items}}；容错 items 直挂在顶层
      const items = d.data?.items ?? d.items ?? [];
      if (seq === seqRef.current) setHooks(items);
    } catch {
      if (seq === seqRef.current) setError("伏笔台账加载失败");
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
      if (seq === seqRef.current) setChapters(flat);
    } catch {
      /* 树加载失败只影响章号解析，不阻断台账 */
    }
  }, [projectId]);

  // 挂载取数＋台账变更广播（hooksApi create/patch/remove/restore）→ 重取
  // （detail.projectId 匹配才取）；卸载作废在途响应。
  useEffect(() => {
    void load();
    const onChanged = (e: Event) => {
      const d = (e as CustomEvent).detail as { projectId?: string };
      if (d?.projectId !== projectId) return;
      void load();
    };
    window.addEventListener(HOOKS_CHANGED_EVENT, onChanged);
    return () => {
      window.removeEventListener(HOOKS_CHANGED_EVENT, onChanged);
      seqRef.current += 1;
    };
  }, [load, projectId]);

  return { hooks, chapters, error };
}
