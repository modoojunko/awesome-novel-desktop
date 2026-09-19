/** 「角色关系」页签（workbench-relations-graph）：全书关系图。
 *  节点=角色（主角加重），边=单向视角关系（rel_type · stance，带来源章）。
 *  布局＝确定性环形（storyline.html graphLayout 同款），无随机、可截图。
 *  volumeScope（卷选中态）：截至该卷末的关系投影——来源卷号 > 该卷的边不显示，
 *  只读无章高亮（c-volume-view-storyline）。 */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { chapterNoOf, parseChapterRef } from "@/lib/chapterRef";

interface GraphNode {
  id: string;
  name: string;
  role: string;
}
interface GraphEdge {
  owner_id: string;
  other_id: string;
  owner_name: string;
  other_name: string;
  rel_type: string;
  stance: string;
  origin_chapter: string;
}
interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

const W = 560;
const H = 380;
const CX = W / 2;
const CY = H / 2;

/** 确定性环形布局：节点沿圆周均布（顺序=id 排序，稳定可复现）。 */
function layout(nodes: GraphNode[]): Map<string, { x: number; y: number }> {
  const pos = new Map<string, { x: number; y: number }>();
  const n = nodes.length;
  const R = Math.min(W, H) / 2 - 70;
  nodes.forEach((nd, i) => {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / Math.max(1, n);
    pos.set(nd.id, {
      x: CX + R * Math.cos(a),
      y: CY + R * Math.sin(a),
    });
  });
  return pos;
}

export function RelationsGraphPane({
  projectId,
  chapterRef,
  volumeScope,
}: {
  projectId: string;
  /** 当前章 ref：本章新建/变化的关系在图上高亮（storyline rels 页签口径） */
  chapterRef?: string;
  /** 卷选中态：截至该卷末的关系投影（来源卷号 > 该卷的边不显示） */
  volumeScope?: number;
}) {
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [chapters, setChapters] = useState<
    Array<{ ref: string; chapter: number; title: string; stale?: boolean }>
  >([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const data = (await api.get(`/novels/${projectId}/characters/graph`)) as {
          ok: boolean;
          data: GraphData;
        };
        if (alive) {
          setGraph(data.data);
          setError(null);
        }
      } catch {
        if (alive) setError("关系图加载失败");
      }
    })();
    return () => {
      alive = false;
    };
  }, [projectId]);

  // 来源章题名与「基于旧设定」角标（投影用；失败静默，不阻断图）
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const tree = (await api.get(`/novels/${projectId}/volumes`)) as Array<{
          name?: string;
          ref?: string;
          chapters?: Array<{ ref?: string; chapter: number; title?: string; stale?: boolean }>;
        }>;
        const flat: Array<{ ref: string; chapter: number; title: string; stale?: boolean }> = [];
        for (const v of tree ?? []) {
          for (const c of v.chapters ?? []) {
            flat.push({
              ref: c.ref ?? `${v.name ?? v.ref}-ch-${c.chapter}`,
              chapter: c.chapter,
              title: c.title ?? "",
              stale: c.stale,
            });
          }
        }
        if (alive) setChapters(flat);
      } catch {
        /* 题名失败不阻断 */
      }
    })();
    return () => {
      alive = false;
    };
  }, [projectId]);

  const pos = useMemo(
    () => (graph ? layout(graph.nodes) : new Map()),
    [graph],
  );

  // 卷域投影：来源卷号 > 该卷的边不显示（开书设定无来源章，始终可见）
  const visibleEdges = useMemo(() => {
    if (!graph) return [];
    if (volumeScope == null) return graph.edges;
    return graph.edges.filter((e) => {
      const p = parseChapterRef(e.origin_chapter || "");
      return p == null || p.vol <= volumeScope;
    });
  }, [graph, volumeScope]);

  if (error) return <p className="vempty">{error}</p>;
  if (!graph) return <p className="vempty">加载中……</p>;
  if (graph.nodes.length === 0)
    return <p className="vempty">还没有角色卡。到「设定 · 角色」里建卡后，这里会画出关系图。</p>;

  return (
    <div className="relations-graph" data-od-id="relations-graph">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label="全书角色关系图"
        style={{ width: "100%", height: "auto" }}
      >
        {/* 边：视角单向，画带箭头直线；标签取中点 */}
        {visibleEdges.map((e, i) => {
          const a = pos.get(e.owner_id);
          const b = pos.get(e.other_id);
          if (!a || !b) return null;
          const mx = (a.x + b.x) / 2;
          const my = (a.y + b.y) / 2;
          const hit = !!chapterRef && e.origin_chapter === chapterRef;
          return (
            <g key={`${e.owner_id}-${e.other_id}-${i}`}>
              <line
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke={hit ? "var(--accent)" : "var(--border)"}
                strokeWidth={hit ? 2.5 : 1.5}
                data-hit={hit ? "1" : undefined}
              />
              <text x={mx} y={my - 4} textAnchor="middle" className="rg-edge-label">
                {e.rel_type}
                {e.stance ? ` · ${e.stance}` : ""}
              </text>
            </g>
          );
        })}
        {/* 节点 */}
        {graph.nodes.map((nd) => {
          const p = pos.get(nd.id);
          if (!p) return null;
          return (
            <g key={nd.id} transform={`translate(${p.x}, ${p.y})`}>
              <circle r={26} fill="var(--surface)" stroke="var(--border)" strokeWidth={1.5} />
              <text textAnchor="middle" dy="4" className="rg-name">
                {nd.name}
              </text>
            </g>
          );
        })}
      </svg>
      <p className="rg-legend">
        {graph.nodes.length} 个角色 · {visibleEdges.length} 条关系
        {volumeScope != null && ` · 截至第 ${volumeScope} 卷末（只读投影）`}
        {chapterRef && " · 本章新建或变化的关系在图上高亮"}
      </p>
      {visibleEdges.length > 0 && (
        <ul className="rg-list">
          {visibleEdges.map((e, i) => {
            const hit = !!chapterRef && e.origin_chapter === chapterRef;
            const origin = chapters.find((c) => c.ref === e.origin_chapter);
            const state = !e.origin_chapter
              ? "开书设定"
              : origin?.stale
                ? "基于旧设定"
                : "随剧情演变";
            const originLabel = !e.origin_chapter
              ? "开书设定 · 全书统一"
              : `第 ${origin?.chapter ?? chapterNoOf(e.origin_chapter)} 章${origin?.title ? ` · ${origin.title}` : ""}`;
            return (
              <li key={i} className={hit ? "hit" : undefined} data-testid="rg-row">
                {e.owner_name} → {e.other_name}：{e.rel_type}
                {e.stance ? ` · ${e.stance}` : ""}
                <em className="rg-origin">
                  {originLabel}
                  {hit ? " · 本章" : ""}
                </em>
                <span className="rg-state">{state}</span>
              </li>
            );
          })}
        </ul>
      )}
      {graph.nodes.filter((nd) => !graph.edges.some(
        (e) => e.owner_id === nd.id || e.other_id === nd.id,
      )).length > 0 && (
        <p className="rg-iso">
          还没连线：
          {graph.nodes
            .filter((nd) => !graph.edges.some((e) => e.owner_id === nd.id || e.other_id === nd.id))
            .map((nd) => nd.name)
            .join(" · ")}
        </p>
      )}
    </div>
  );
}
