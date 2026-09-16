/** 「设定」页签：本章变化（可编辑）＋截至本章（投影，只读）。
 *  数据源：本章出场引用行的 state_change（archive-reconcile 落点）＋
 *  出场角色的关系（origin_chapter 标注）。设定类变化（lore-apply）走世界
 *  设定投影，由「世界设定」投影接口提供；本期先呈现角色/关系两类。 */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";

interface CastRow {
  character_name: string;
  character_id: string | null;
  state_change: string;
}

interface RelationRow {
  owner_id: string;
  other_id: string;
  rel_type: string;
  stance: string;
  note: string;
  origin_chapter_id: string | null;
}

interface ChapterLite {
  id: string;
  ref: string;
  chapter: number;
}

export function SettingsChangelogPane({
  projectId,
  chapterRef,
}: {
  projectId: string;
  chapterRef: string;
}) {
  const [cast, setCast] = useState<CastRow[]>([]);
  const [relations, setRelations] = useState<RelationRow[]>([]);
  const [chapters, setChapters] = useState<ChapterLite[]>([]);
  const [nameById, setNameById] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const ch = (await api.get(
          `/novels/${projectId}/chapters/${chapterRef}`,
        )) as {
          outline?: { characters?: Array<{ name?: string; state_change?: string }> };
        };
        const rows: CastRow[] = (ch.outline?.characters ?? []).map((c) => ({
          character_name: c?.name ?? "",
          character_id: null,
          state_change: c?.state_change ?? "",
        }));
        setCast(rows);
        if (!cancelled) setError(null);
      } catch {
        if (!cancelled) setError("本章数据加载失败");
      }
    })();
    return () => {
      cancelled = true;
    };
    // outlineCharacters 只作首帧兜底，避免轮询重置
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, chapterRef]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const chars = (await api.get(`/novels/${projectId}/characters`)) as Array<{
          id: string;
          name: string;
        }>;
        const map: Record<string, string> = {};
        for (const c of chars) map[c.id] = c.name;
        if (!cancelled) setNameById(map);
      } catch {
        /* 名字解析失败不阻断 */
      }
      try {
        const rels = (await api.get(`/novels/${projectId}/characters/relations`)) as
          | RelationRow[]
          | { relations?: RelationRow[] };
        const list = Array.isArray(rels) ? rels : (rels.relations ?? []);
        if (!cancelled) setRelations(list);
      } catch {
        if (!cancelled) setRelations([]);
      }
      try {
        const tree = (await api.get(`/novels/${projectId}/volumes`)) as Array<{
          id: string;
          ref?: string;
          name?: string;
          chapters?: Array<{ id?: string; chapter: number; ref?: string }>;
        }>;
        const flat: ChapterLite[] = [];
        for (const v of tree) {
          for (const c of v.chapters ?? []) {
            const ref = c.ref ?? `${v.name ?? v.ref}-ch-${c.chapter}`;
            const cid = c.id ?? ref;
            flat.push({ id: cid, ref, chapter: c.chapter });
          }
        }
        if (!cancelled) setChapters(flat);
      } catch {
        /* 树加载失败不阻断 */
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

  const chapterId = useMemo(() => {
    // 与后端一致：本章 id 由章节列表按 ref 反查（chapters/{ref} 响应里未带 id 时）
    const hit = chapters.find((c) => {
      const m = chapterRef.match(/^(vol-\d+)-/);
      return m && c.chapter === chapterNo;
    });
    return hit?.id ?? null;
  }, [chapters, chapterRef, chapterNo]);

  const originName = (id: string | null): string | null => {
    if (!id) return null;
    const hit = chapters.find((c) => c.id === id);
    return hit ? `第 ${hit.chapter} 章` : null;
  };

  // 截至本章：来源章号 ≤ 本章的关系（投影语义；本/更早章均显示）
  const relsUntil = useMemo(
    () =>
      relations.filter((r) => {
        const ch = chapters.find((c) => c.id === r.origin_chapter_id);
        return !ch || ch.chapter <= chapterNo;
      }),
    [relations, chapters, chapterNo],
  );

  const hasChanges = cast.some((c) => c.state_change) || relsUntil.length > 0;

  if (error) return <p className="vempty">{error}</p>;

  return (
    <div className="settings-changelog" data-od-id="settings-changelog">
      <p className="seg-title">本章变化</p>
      {cast.length === 0 && <p className="vempty">本章还没有出场角色。</p>}
      {cast.map((c) => (
        <div className="change-row" key={c.character_name + c.character_id}>
          <span className="who">{c.character_name}</span>
          <span className="what">
            {c.state_change || "（暂无状态变化）"}
          </span>
        </div>
      ))}

      <p className="seg-title">截至本章的关系变化</p>
      {relsUntil.length === 0 && (
        <p className="vempty">还没有随章节积累的关系变化。</p>
      )}
      {relsUntil.map((r, i) => (
        <div className="change-row" key={`${r.owner_id}-${r.other_id}-${i}`}>
          <span className="who">
            {nameById[r.owner_id] ?? r.owner_id} ↔ {nameById[r.other_id] ?? r.other_id}
          </span>
          <span className="what">
            {r.rel_type}
            {r.stance ? ` · ${r.stance}` : ""}
            {r.note ? `（${r.note}）` : ""}
          </span>
          <span className="origin">{originName(r.origin_chapter_id) ?? "开书"}</span>
        </div>
      ))}

      <p className="foot-note">
        以上内容会作为本章及之后章节的写作参考；世界设定的变化请见「世界设定」投影。
      </p>
    </div>
  );
}
