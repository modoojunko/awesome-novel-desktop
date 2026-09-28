/** 「角色关系」页签（workbench-relations-graph）：关系图为主表达，行清单兜底。
 *  节点=角色卡（本章变化里未登记的名字给虚线占位节点），边=单向视角关系。
 *  章打开态（chapterRef）：并入「截至本章」剧情关系（dossier/preview 单源＝写章
 *  消费同源：已采纳∧已归档∧非 stale，按 (owner,other) 后章覆盖）——本章采纳边
 *  高亮、待确认边虚线；同向剧情边覆盖开书设定边。行清单只列开书设定与往章演变
 *  边，本章边由「本章关系变化」工作流区呈现（证据＋采纳/驳回）。
 *  卷选中态（volumeScope）：截至该卷末的关系投影，只读无章高亮、不并入剧情边
 *  （c-volume-view-storyline）。 */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { chapterNoOf, parseChapterRef } from "@/lib/chapterRef";
import { DOSSIER_CHANGED_EVENT, dossierApi } from "@/lib/dossierApi";

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

/** 剧情关系条目（preview 折叠行 / 本章待确认行同形）。 */
interface EvoRelation {
  owner: string;
  other: string;
  rel_type: string;
  change_note: string;
  ref: string;
}
type EdgeKind = "base" | "evo" | "hit" | "pending";
interface MergedEdge {
  key: string;
  aId: string;
  bId: string;
  aName: string;
  bName: string;
  relType: string;
  stance: string;
  note: string;
  origin: string;
  kind: EdgeKind;
}
interface PaneNode extends GraphNode {
  /** 无角色卡的未登记名（虚线占位） */
  ghost?: boolean;
}

const W = 560;
const H = 380;
const CX = W / 2;
const CY = H / 2;

const norm = (s: string | undefined) => (s ?? "").trim();

/** 边优先级：本章采纳 > 本章待确认 > 往章演变 > 开书设定（同向高优先者胜）。 */
const KIND_PRIO: Record<EdgeKind, number> = { hit: 0, pending: 1, evo: 2, base: 3 };

/** 确定性环形布局：节点沿圆周均布（顺序=id 排序，稳定可复现）。 */
function layout(nodes: PaneNode[]): Map<string, { x: number; y: number }> {
  const pos = new Map<string, { x: number; y: number }>();
  const sorted = [...nodes].sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  const n = sorted.length;
  const R = Math.min(W, H) / 2 - 70;
  sorted.forEach((nd, i) => {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / Math.max(1, n);
    pos.set(nd.id, {
      x: CX + R * Math.cos(a),
      y: CY + R * Math.sin(a),
    });
  });
  return pos;
}

/** 合并：开书设定边＋剧情关系边（同向覆盖），未登记名补占位节点。 */
function mergeGraph(
  graph: GraphData,
  dossier: Array<EvoRelation & { kind: EdgeKind }>,
): { nodes: PaneNode[]; edges: MergedEdge[] } {
  const nodes: PaneNode[] = graph.nodes.map((nd) => ({ ...nd }));
  const byName = new Map<string, PaneNode>();
  for (const nd of nodes) byName.set(norm(nd.name), nd);
  const ensure = (name: string): PaneNode | null => {
    const k = norm(name);
    if (!k) return null;
    const known = byName.get(k);
    if (known) return known;
    const ghost: PaneNode = { id: `ghost:${k}`, name: k, role: "", ghost: true };
    byName.set(k, ghost);
    nodes.push(ghost);
    return ghost;
  };

  const edges = new Map<string, MergedEdge>();
  for (const r of dossier) {
    const a = ensure(r.owner);
    const b = ensure(r.other);
    if (!a || !b || a.id === b.id) continue;
    const key = `${norm(r.owner)}→${norm(r.other)}`;
    const prev = edges.get(key);
    if (prev && KIND_PRIO[prev.kind] <= KIND_PRIO[r.kind]) continue;
    edges.set(key, {
      key,
      aId: a.id,
      bId: b.id,
      aName: a.name,
      bName: b.name,
      relType: r.rel_type || "关系",
      stance: "",
      note: r.change_note || "",
      origin: r.ref,
      kind: r.kind,
    });
  }
  for (const e of graph.edges) {
    const key = `${norm(e.owner_name)}→${norm(e.other_name)}`;
    if (edges.has(key)) continue; // 同向剧情边已覆盖开书设定
    edges.set(key, {
      key,
      aId: e.owner_id,
      bId: e.other_id,
      aName: e.owner_name,
      bName: e.other_name,
      relType: e.rel_type,
      stance: e.stance,
      note: "",
      origin: e.origin_chapter,
      kind: "base",
    });
  }
  return { nodes, edges: [...edges.values()] };
}

type ChapterMeta = Array<{ ref: string; chapter: number; title: string; stale?: boolean }>;

function originLabel(e: MergedEdge, chapters: ChapterMeta): string {
  if (e.kind === "pending") return "本章";
  if (!e.origin) return "开书设定 · 全书统一";
  const origin = chapters.find((c) => c.ref === e.origin);
  return `第 ${origin?.chapter ?? chapterNoOf(e.origin)} 章${origin?.title ? ` · ${origin.title}` : ""}`;
}

function stateLabel(e: MergedEdge, chapters: ChapterMeta): string {
  if (e.kind === "pending") return "待确认";
  if (e.kind !== "base") return "随剧情演变";
  if (!e.origin) return "开书设定";
  const origin = chapters.find((c) => c.ref === e.origin);
  return origin?.stale ? "基于旧设定" : "随剧情演变";
}

export function RelationsGraphPane({
  projectId,
  chapterRef,
  volumeScope,
}: {
  projectId: string;
  /** 当前章 ref：并入截至本章剧情关系，本章边高亮、待确认虚线 */
  chapterRef?: string;
  /** 卷选中态：截至该卷末的关系投影（来源卷号 > 该卷的边不显示） */
  volumeScope?: number;
}) {
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [chapters, setChapters] = useState<ChapterMeta>([]);
  const [dossier, setDossier] = useState<Array<EvoRelation & { kind: EdgeKind }>>([]);
  const [dossierSettled, setDossierSettled] = useState(!chapterRef);
  const [dossierTick, setDossierTick] = useState(0);
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
        const flat: ChapterMeta = [];
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

  // 章打开态：截至本章剧情关系（preview 单源）＋本章待确认行；行动作后事件重拉
  useEffect(() => {
    if (!chapterRef) {
      setDossier([]);
      setDossierSettled(true);
      return;
    }
    let alive = true;
    setDossierSettled(false);
    (async () => {
      try {
        const [pv, cur] = await Promise.all([
          dossierApi.preview(projectId, chapterRef),
          dossierApi.get(projectId, chapterRef),
        ]);
        if (!alive) return;
        const accepted = ((pv.domains?.relations ?? []) as Array<Record<string, string>>).map(
          (r) => ({
            owner: r.owner ?? "",
            other: r.other ?? "",
            rel_type: r.rel_type ?? "",
            change_note: r.change_note ?? "",
            ref: r.ref ?? "",
            kind: (r.ref === chapterRef ? "hit" : "evo") as EdgeKind,
          }),
        );
        const pending = (cur.rows ?? [])
          .filter((r) => r.domain === "relations" && r.status === "pending")
          .map((r) => ({
            owner: r.owner ?? "",
            other: r.other ?? "",
            rel_type: r.rel_type ?? "",
            change_note: r.change_note ?? "",
            ref: chapterRef,
            kind: "pending" as const,
          }));
        setDossier([...accepted, ...pending]);
      } catch {
        /* 静默：图退回开书设定边，不阻断 */
      } finally {
        if (alive) setDossierSettled(true);
      }
    })();
    return () => {
      alive = false;
    };
  }, [projectId, chapterRef, dossierTick]);

  // 本章变化行被采纳/驳回/删除后刷新图上的剧情边
  useEffect(() => {
    if (!chapterRef) return;
    const h = () => setDossierTick((t) => t + 1);
    window.addEventListener(DOSSIER_CHANGED_EVENT, h);
    return () => window.removeEventListener(DOSSIER_CHANGED_EVENT, h);
  }, [chapterRef]);

  const merged = useMemo(
    () => (graph ? mergeGraph(graph, dossier) : { nodes: [], edges: [] }),
    [graph, dossier],
  );
  const pos = useMemo(() => layout(merged.nodes), [merged.nodes]);

  // 卷域投影：来源卷号 > 该卷的边不显示（开书设定与剧情边同规则）
  const visibleEdges = useMemo(() => {
    if (volumeScope == null) return merged.edges;
    return merged.edges.filter((e) => {
      const p = parseChapterRef(e.origin || "");
      return e.kind === "pending" || p == null || p.vol <= volumeScope;
    });
  }, [merged.edges, volumeScope]);

  // 行清单兜底：开书设定＋往章演变；本章边（含待确认）由工作流区呈现
  const listEdges = useMemo(
    () => visibleEdges.filter((e) => e.kind === "base" || e.kind === "evo"),
    [visibleEdges],
  );
  const isolated = merged.nodes.filter(
    (nd) => !visibleEdges.some((e) => e.aId === nd.id || e.bId === nd.id),
  );
  const pendingCnt = visibleEdges.filter((e) => e.kind === "pending").length;

  if (error) return <p className="vempty">{error}</p>;
  if (!graph || (chapterRef && !dossierSettled)) return <p className="vempty">加载中……</p>;
  if (merged.nodes.length === 0)
    return <p className="vempty">还没有角色卡。到「设定 · 角色」里建卡后，这里会画出关系图。</p>;

  return (
    <div className="relations-graph" data-od-id="relations-graph">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={chapterRef ? "角色关系图（含截至本章剧情演变）" : "全书角色关系图"}
        style={{ width: "100%", height: "auto" }}
      >
        {/* 边：视角单向；本章采纳实线加重、待确认虚线、往章演变中间色；悬浮看全句。
            同一对节点的双向边各画一侧弓形（确定性：a.id<b.id 偏左侧），避免直线重叠 */}
        {visibleEdges.map((e) => {
          const a = pos.get(e.aId);
          const b = pos.get(e.bId);
          if (!a || !b) return null;
          const reverse = visibleEdges.some(
            (o) => o.aId === e.bId && o.bId === e.aId,
          );
          const mx = (a.x + b.x) / 2;
          const my = (a.y + b.y) / 2;
          let lx = mx;
          let ly = my - 4;
          let d: string;
          if (reverse) {
            // 左法线偏移：反向边的方向向量相反 → 左法线也相反，两条弧自然分居两侧
            const dx = b.x - a.x;
            const dy = b.y - a.y;
            const cx = mx - dy * 0.14;
            const cy = my + dx * 0.14;
            d = `M ${a.x} ${a.y} Q ${cx} ${cy} ${b.x} ${b.y}`;
            lx = 0.25 * a.x + 0.5 * cx + 0.25 * b.x;
            ly = 0.25 * a.y + 0.5 * cy + 0.25 * b.y;
          } else {
            d = `M ${a.x} ${a.y} L ${b.x} ${b.y}`;
          }
          const tip =
            e.kind === "pending"
              ? `${e.aName} → ${e.bName}：${e.relType}（待确认 · ${e.note}）`
              : `${e.aName} → ${e.bName}：${e.relType}${e.stance ? ` · ${e.stance}` : ""}${
                  e.note ? `（${e.note}）` : ""
                }（${originLabel(e, chapters)} · ${stateLabel(e, chapters)}）`;
          // 本章边：剧情采纳边，或来源章=本章的设定边（收尾提案物化进设定的新边）；待确认提案不算
          const hit =
            e.kind === "hit" || (e.kind === "base" && !!chapterRef && e.origin === chapterRef);
          return (
            <g key={e.key} className={`rg-edge ${e.kind}${hit ? " hit" : ""}`}>
              <title>{tip}</title>
              <path
                d={d}
                fill="none"
                className="rg-line"
                data-hit={hit ? "1" : undefined}
              />
              <text x={lx} y={ly} textAnchor="middle" className="rg-edge-label">
                {e.kind === "pending"
                  ? `${e.relType} · 待确认`
                  : `${e.relType}${e.stance ? ` · ${e.stance}` : ""}`}
              </text>
            </g>
          );
        })}
        {/* 节点：角色卡实线圈，未登记名虚线圈 */}
        {merged.nodes.map((nd) => {
          const p = pos.get(nd.id);
          if (!p) return null;
          return (
            <g
              key={nd.id}
              transform={`translate(${p.x}, ${p.y})`}
              className={nd.ghost ? "rg-node ghost" : "rg-node"}
            >
              <circle r={26} />
              <text textAnchor="middle" dy="4" className="rg-name">
                {nd.name}
              </text>
            </g>
          );
        })}
      </svg>
      <p className="rg-legend">
        {merged.nodes.length} 个角色 · {visibleEdges.length} 条关系
        {chapterRef && dossier.length > 0 &&
          `（剧情演变 ${dossier.length - pendingCnt} · 待确认 ${pendingCnt}）`}
        {volumeScope != null && ` · 截至第 ${volumeScope} 卷末（只读投影）`}
        {chapterRef && " · 本章采纳边高亮，虚线为待确认提案"}
      </p>
      {listEdges.length > 0 && (
        <ul className="rg-list">
          {listEdges.map((e) => {
            const note =
              e.note && (
                <em className="rg-note">
                  （{e.note.length > 60 ? `${e.note.slice(0, 60)}…` : e.note}）
                </em>
              );
            return (
              <li key={e.key} data-testid="rg-row">
                {e.aName} → {e.bName}：{e.relType}
                {e.stance ? ` · ${e.stance}` : ""}
                {note}
                <em className="rg-origin">{originLabel(e, chapters)}</em>
                <span className="rg-state">{stateLabel(e, chapters)}</span>
              </li>
            );
          })}
        </ul>
      )}
      {isolated.length > 0 && (
        <p className="rg-iso">还没连线：{isolated.map((nd) => nd.name).join(" · ")}</p>
      )}
    </div>
  );
}
