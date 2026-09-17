/** 「角色关系」页签（workbench-relations-graph）：全书关系图。
 *  节点=角色（主角加重），边=单向视角关系（rel_type · stance，带来源章）。
 *  布局＝确定性环形（storyline.html graphLayout 同款），无随机、可截图。 */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";

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

export function RelationsGraphPane({ projectId }: { projectId: string }) {
  const [graph, setGraph] = useState<GraphData | null>(null);
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

  const pos = useMemo(
    () => (graph ? layout(graph.nodes) : new Map()),
    [graph],
  );

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
        {graph.edges.map((e, i) => {
          const a = pos.get(e.owner_id);
          const b = pos.get(e.other_id);
          if (!a || !b) return null;
          const mx = (a.x + b.x) / 2;
          const my = (a.y + b.y) / 2;
          return (
            <g key={`${e.owner_id}-${e.other_id}-${i}`}>
              <line
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke="var(--border)"
                strokeWidth={1.5}
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
        {graph.nodes.length} 个角色 · {graph.edges.length} 条关系
        {graph.edges.some((e) => e.origin_chapter) && " · 边按来源章排序见列表"}
      </p>
      {graph.edges.length > 0 && (
        <ul className="rg-list">
          {graph.edges.map((e, i) => (
            <li key={i}>
              {e.owner_name} → {e.other_name}：{e.rel_type}
              {e.stance ? ` · ${e.stance}` : ""}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
