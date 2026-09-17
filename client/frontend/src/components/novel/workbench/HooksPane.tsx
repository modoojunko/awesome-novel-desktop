/** 「伏笔」页签（第 8 个，storyline.html hooksHTML 复刻）：
 *  章内只读台账投影——全书统一维护的伏笔按埋点章展示，本章埋下/回收的条目高亮。
 *  数据源：真表 novel_hooks（status active/resolved）＋卷章树（id→章号解析）。 */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";

interface HookRow {
  id: string;
  code: string;
  description: string;
  type: string;
  priority: number;
  status: string;
  introduced_chapter_id: string | null;
  planned_chapter_id: string | null;
  resolved_chapter_id: string | null;
}

interface ChapterLite {
  id: string;
  ref: string;
  chapter: number;
  title: string;
}

export function HooksPane({
  projectId,
  chapterRef,
}: {
  projectId: string;
  chapterRef: string;
}) {
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

  const chapterNo = useMemo(() => {
    const m = chapterRef.match(/-ch-(\d+)$/);
    return m ? Number(m[1]) : 0;
  }, [chapterRef]);

  const currentId = useMemo(() => {
    const hit = chapters.find((c) => c.chapter === chapterNo && c.ref === chapterRef);
    return hit?.id ?? chapters.find((c) => c.chapter === chapterNo)?.id ?? null;
  }, [chapters, chapterNo, chapterRef]);

  const labelOf = (id: string | null): string | null => {
    if (!id) return null;
    const hit = chapters.find((c) => c.id === id);
    return hit ? `第 ${hit.chapter} 章` : null;
  };
  const titleOf = (id: string | null): string => {
    if (!id) return "";
    return chapters.find((c) => c.id === id)?.title ?? "";
  };

  const openCount = hooks.filter((h) => h.status === "active").length;
  const plantHere = hooks.filter((h) => h.introduced_chapter_id === currentId).length;
  const resolveHere = hooks.filter((h) => h.resolved_chapter_id === currentId).length;

  if (error) return <p className="vempty">{error}</p>;

  return (
    <div className="hooks-pane" data-od-id="hooks-pane">
      <p className="seg-title">
        伏笔台账 <span className="note">全书统一维护 · 记下埋点与回收章 · 本章条目高亮</span>
      </p>
      <p className="hp-sum">
        <b>{hooks.length}</b> 条 · <b>{openCount}</b> 条悬置
        {plantHere > 0 && (
          <>
            {" "}
            · 本章埋下 <b>{plantHere}</b>
          </>
        )}
        {resolveHere > 0 && (
          <>
            {" "}
            · 本章回收 <b>{resolveHere}</b>
          </>
        )}
      </p>
      {hooks.length === 0 && (
        <p className="vempty">还没有伏笔条目。到「设定 · 伏笔」里登记第一条。</p>
      )}
      {hooks.length > 0 && (
        <div className="hp-ledger">
          {hooks.map((h) => {
            const hit =
              (currentId && h.introduced_chapter_id === currentId) ||
              (currentId && h.resolved_chapter_id === currentId);
            const state =
              h.status === "resolved"
                ? `已收 · ${labelOf(h.resolved_chapter_id) ?? "—"}`
                : h.status === "abandoned"
                  ? "已弃"
                  : "悬置";
            return (
              <div className={`hp-row${hit ? " hit" : ""}`} key={h.id}>
                <span className="hp-name">
                  <em className="hp-code">{h.code}</em>
                  {h.description}
                  <em className="hp-origin">
                    埋于 {labelOf(h.introduced_chapter_id) ?? "开书"}
                    {titleOf(h.introduced_chapter_id) ? ` · ${titleOf(h.introduced_chapter_id)}` : ""}
                  </em>
                </span>
                <span className={`hp-state${h.status === "active" ? " open" : ""}`}>
                  {state}
                </span>
              </div>
            );
          })}
        </div>
      )}
      {hooks.length > 0 && (
        <p className="foot-note">
          台账在「设定 · 伏笔」维护；归档时 AI 的伏笔登记提案在「操作」页签逐条确认。
        </p>
      )}
    </div>
  );
}
