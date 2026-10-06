/** 「角色关系」页签（workbench-relations-graph）：关系图为主表达，行清单兜底。
 *  节点=角色卡（本章变化里未登记的名字给虚线占位节点），边=单向视角关系。
 *  章打开态（chapterRef）双源：往章演变边＝dossier/preview（写章消费同源：已采纳
 *  ∧已归档∧非 stale，按 (owner,other) 后章覆盖）；本章边＝章档端点（已采纳高亮、
 *  待确认虚线，与「本章关系变化」工作流区同源同态，不要求本章已归档）。
 *  同向剧情边覆盖开书设定边。行清单只列开书设定与往章演变边，本章边由工作流区
 *  呈现（证据＋采纳/驳回）。
 *  卷选中态（volumeScope）：截至该卷末的剧情投影，只读无章高亮——剧情边＝preview
 *  截至本卷末章（已归档折叠单源）＋范围内未归档章的已采纳行并入，随时对齐本卷剧情
 *  最新的已确认关系；待确认提案不上图（c-volume-rels-live）。 */
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
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
type Polarity = "friendly" | "hostile" | "neutral";
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
  polarity: Polarity;
}
interface PaneNode extends GraphNode {
  /** 无角色卡的未登记名（虚线占位） */
  ghost?: boolean;
}

const W = 560;
const H = 380;
const CX = W / 2;
const CY = H / 2;
/** 节点圆半径：SVG 圆与边端点回缩共用同一值 */
const NODE_R = 26;
/** 箭头端与圆周的留白：箭头尖落在圆外，别藏进节点圆下 */
const ARROW_GAP = 3;

const norm = (s: string | undefined) => (s ?? "").trim();

/** 边优先级：本章采纳 > 本章待确认 > 往章演变 > 开书设定（同向高优先者胜）。 */
const KIND_PRIO: Record<EdgeKind, number> = { hit: 0, pending: 1, evo: 2, base: 3 };

/** 关系极性（敌红/友绿/中性灰）：AI 提取的 rel_type 是自由词（师徒/同僚、敌对/审查），
 *  闭合词表盖不住，按字面关键词归类；敌对优先（亦敌亦友从红）。 */
const HOSTILE_WORDS = [
  "敌", "仇", "恨", "猎杀", "追杀", "追缉", "通缉", "决裂", "背叛", "戒备", "警惕",
  "提防", "防范", "对立", "对抗", "竞争", "冲突", "审查", "审讯", "清剿", "囚", "奴", "威胁",
];
const FRIENDLY_WORDS = [
  "盟", "友", "同伴", "伙伴", "同僚", "同事", "师", "徒", "弟子", "亲", "恋", "爱", "挚",
  "知己", "至交", "结拜", "信任", "忠诚", "恩", "救", "护", "合作", "青梅", "夫妻", "兄妹", "姐弟",
];
function relPolarity(relType: string): Polarity {
  const t = relType ?? "";
  if (HOSTILE_WORDS.some((w) => t.includes(w))) return "hostile";
  if (FRIENDLY_WORDS.some((w) => t.includes(w))) return "friendly";
  return "neutral";
}

/** 节点按角色类型着色（词表 ROLES=主角/配角/反派/路人，白名单校验；未知值回落配角）。 */
function roleKey(role: string | undefined): "protagonist" | "villain" | "extra" | "support" {
  if (role === "主角") return "protagonist";
  if (role === "反派") return "villain";
  if (role === "路人") return "extra";
  return "support";
}

/** 路径端点贴圆周：端点从节点圆心沿参考点方向回缩 r+gap。起点终点同用——
 *  节点圆有透明填充档（反派红软底、路人空底），线画到圆心会从圆里透出来；
 *  回缩最多到半径连线的中点，防角色多、相邻节点间距不足时两端回缩把线吃成反向。 */
function rimPoint(
  cx: number, cy: number, refx: number, refy: number, gap = 0, r = NODE_R,
): { x: number; y: number } {
  const dx = cx - refx;
  const dy = cy - refy;
  const len = Math.hypot(dx, dy) || 1;
  const t = Math.min((r + gap) / len, 0.5);
  return { x: cx - dx * t, y: cy - dy * t };
}

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
      polarity: relPolarity(r.rel_type || ""),
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
      polarity: relPolarity(e.rel_type || ""),
    });
  }
  return { nodes, edges: [...edges.values()] };
}

type ChapterMeta = Array<{
  ref: string;
  chapter: number;
  title: string;
  stale?: boolean;
  archived?: boolean;
}>;

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
  /** 卷树是否已就位（卷态投影要等它圈定本卷末章与未归档章清单） */
  const [chaptersReady, setChaptersReady] = useState(false);
  const [dossier, setDossier] = useState<Array<EvoRelation & { kind: EdgeKind }>>([]);
  /** 剧情边数据已就位的域键（章 ref / `vol:{N}`；null＝首次加载中；""＝无域）。
   *  行动作触发的重拉不改它 → 沿用旧渲染，不闪「加载中」。 */
  const [loadedForRef, setLoadedForRef] = useState<string | null>(
    chapterRef || volumeScope != null ? null : "",
  );
  const [dossierTick, setDossierTick] = useState(0);
  const [error, setError] = useState<string | null>(null);
  /** 当前投影域键：章态＝章 ref，卷态＝`vol:{N}`，书态＝""（实际不出现） */
  const scopeKey = chapterRef ?? (volumeScope != null ? `vol:${volumeScope}` : "");

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

  // 来源章题名、「基于旧设定」角标与卷态投影材料（未归档章清单；失败静默，不阻断图）
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const tree = (await api.get(`/novels/${projectId}/volumes`)) as Array<{
          name?: string;
          ref?: string;
          chapters?: Array<{
            ref?: string;
            chapter: number;
            title?: string;
            stale?: boolean;
            archived?: boolean;
          }>;
        }>;
        const flat: ChapterMeta = [];
        for (const v of tree ?? []) {
          for (const c of v.chapters ?? []) {
            flat.push({
              ref: c.ref ?? `${v.name ?? v.ref}-ch-${c.chapter}`,
              chapter: c.chapter,
              title: c.title ?? "",
              stale: c.stale,
              archived: c.archived,
            });
          }
        }
        if (alive) setChapters(flat);
      } catch {
        /* 题名失败不阻断 */
      } finally {
        if (alive) setChaptersReady(true);
      }
    })();
    return () => {
      alive = false;
    };
  }, [projectId]);

  // 章打开态：往章演变边走 preview（写章消费单源：已归档口径）＋本章边走章档端点
  // （已采纳＝hit、待确认＝虚线提案，与下方工作流区同源同态，不要求本章已归档）；
  // 行动作后事件重拉。
  // 卷选中态（c-volume-rels-live）：截至本卷末章的 preview 折叠行＋范围内未归档章的
  // 已采纳行并入（归档后回草稿窗口不丢已确认关系，随时对齐本卷最新）；preview 行在
  // 前＝回草稿旧章的重写窗口里，后归档章的更晚剧情事实胜出（mergeGraph 同向先到先得）。
  useEffect(() => {
    if (!chapterRef && volumeScope == null) {
      setDossier([]);
      setLoadedForRef("");
      return;
    }
    // 卷态等卷树就绪（本卷末章 ref 与未归档章清单取自它）
    if (!chapterRef && !chaptersReady) return;
    let alive = true;
    (async () => {
      try {
        if (chapterRef) {
          const [pv, cur] = await Promise.all([
            dossierApi.preview(projectId, chapterRef),
            dossierApi.get(projectId, chapterRef),
          ]);
          if (!alive) return;
          // 往章已采纳（preview 已按 (owner,other) 后章覆盖；本章行由章档端点承载，跳过防重）
          const evolved = ((pv.domains?.relations ?? []) as Array<Record<string, string>>)
            .filter((r) => r.ref !== chapterRef)
            .map((r) => ({
              owner: r.owner ?? "",
              other: r.other ?? "",
              rel_type: r.rel_type ?? "",
              change_note: r.change_note ?? "",
              ref: r.ref ?? "",
              kind: "evo" as const,
            }));
          // 本章边：已采纳（高亮实线）＋待确认（虚线提案），章级口径与工作流区一致
          const mine = (cur.rows ?? [])
            .filter((r) => r.domain === "relations" && r.status !== "rejected")
            .map((r) => ({
              owner: r.owner ?? "",
              other: r.other ?? "",
              rel_type: r.rel_type ?? "",
              change_note: r.change_note ?? "",
              ref: chapterRef,
              kind: (r.status === "accepted" ? "hit" : "pending") as EdgeKind,
            }));
          setDossier([...evolved, ...mine]);
        } else {
          const scope = volumeScope as number;
          const inScope = chapters.filter((c) => {
            const p = parseChapterRef(c.ref);
            return p != null && p.vol <= scope;
          });
          const parts: Array<EvoRelation & { kind: EdgeKind }> = [];
          // 已归档部分：截至本卷末章的折叠单源（本卷零章则跳过）
          const volLast = inScope
            .filter((c) => parseChapterRef(c.ref)?.vol === scope)
            .pop();
          if (volLast) {
            const pv = await dossierApi.preview(projectId, volLast.ref);
            if (!alive) return;
            for (const r of (pv.domains?.relations ?? []) as Array<Record<string, string>>) {
              parts.push({
                owner: r.owner ?? "",
                other: r.other ?? "",
                rel_type: r.rel_type ?? "",
                change_note: r.change_note ?? "",
                ref: r.ref ?? "",
                kind: "evo",
              });
            }
          }
          // 未归档章（归档后回草稿窗口）：已采纳行并入；待确认提案不上图
          const openRefs = inScope.filter((c) => !c.archived).map((c) => c.ref);
          const opens = await Promise.all(
            openRefs.map(async (ref) => {
              try {
                return { ref, st: await dossierApi.get(projectId, ref) };
              } catch {
                return null; // 单章失败跳过，不阻断投影
              }
            }),
          );
          if (!alive) return;
          for (const o of opens) {
            if (!o) continue;
            for (const r of o.st.rows ?? []) {
              if (r.domain !== "relations" || r.status !== "accepted") continue;
              parts.push({
                owner: r.owner ?? "",
                other: r.other ?? "",
                rel_type: r.rel_type ?? "",
                change_note: r.change_note ?? "",
                ref: o.ref,
                kind: "evo",
              });
            }
          }
          setDossier(parts);
        }
      } catch {
        /* 静默：图退回开书设定边，不阻断 */
      } finally {
        if (alive) setLoadedForRef(scopeKey);
      }
    })();
    return () => {
      alive = false;
    };
  }, [projectId, chapterRef, volumeScope, chapters, chaptersReady, dossierTick, scopeKey]);

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
  const evoCnt = visibleEdges.filter((e) => e.kind === "evo" || e.kind === "hit").length;

  // 画布缩放/平移（viewBox 视窗法）：默认全图适配＝刚好区域内看完；滚轮以光标为锚
  // 缩放、拖拽平移、右下角按钮；放大上限 4×（w≥W/4），缩到全图即自动复位对齐
  const vpRef = useRef<HTMLDivElement | null>(null);
  const [view, setView] = useState({ x: 0, y: 0, w: W, h: H });
  const [dragging, setDragging] = useState(false);
  const uid = useId();
  const dragRef = useRef<{ px: number; py: number } | null>(null);
  const clampView = useCallback((v: { x: number; y: number; w: number; h: number }) => {
    const w = Math.min(W, Math.max(W / 4, v.w));
    const h = (w * H) / W;
    if (w >= W - 0.5) return { x: 0, y: 0, w: W, h: H };
    const cx = Math.min(1.2 * W, Math.max(-0.2 * W, v.x + w / 2)) - w / 2;
    const cy = Math.min(1.2 * H, Math.max(-0.2 * H, v.y + h / 2)) - h / 2;
    return { x: cx, y: cy, w, h };
  }, []);
  const zoomAt = useCallback(
    (factor: number, clientX?: number, clientY?: number) => {
      setView((v) => {
        const rect = vpRef.current?.getBoundingClientRect();
        const anchored = rect != null && rect.width > 0 && rect.height > 0 && clientX != null && clientY != null;
        const ax = anchored ? Math.min(1, Math.max(0, (clientX - rect.left) / rect.width)) : 0.5;
        const ay = anchored ? Math.min(1, Math.max(0, (clientY - rect.top) / rect.height)) : 0.5;
        const w = Math.min(W, Math.max(W / 4, v.w * factor));
        const k = w / v.w;
        const nh = v.h * k;
        const px = v.x + ax * v.w;
        const py = v.y + ay * v.h;
        return clampView({ x: px - ax * w, y: py - ay * nh, w, h: nh });
      });
    },
    [clampView],
  );
  useEffect(() => {
    const el = vpRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      zoomAt(e.deltaY > 0 ? 1.15 : 1 / 1.15, e.clientX, e.clientY);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [zoomAt]);
  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    // 缩放按钮必须能点：pointerdown 一旦被容器 setPointerCapture，pointerup 会重定向
    // 到容器，click 目标变成公共祖先（容器），按钮 onClick 永远不触发（真机实锤）。
    // 交互控件上不开启拖拽。
    if ((e.target as HTMLElement).closest(".rg-zoombar")) return;
    dragRef.current = { px: e.clientX, py: e.clientY };
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {
      /* jsdom 无 pointer capture */
    }
    setDragging(true);
  };
  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const d = dragRef.current;
    const rect = vpRef.current?.getBoundingClientRect();
    if (!d || !rect || rect.width <= 0) return;
    setView((v) =>
      clampView({
        x: v.x - ((e.clientX - d.px) * v.w) / rect.width,
        y: v.y - ((e.clientY - d.py) * v.h) / rect.height,
        w: v.w,
        h: v.h,
      }),
    );
    dragRef.current = { px: e.clientX, py: e.clientY };
  };
  const endDrag = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragRef.current) return;
    dragRef.current = null;
    setDragging(false);
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      /* jsdom */
    }
  };

  if (error) return <p className="vempty">{error}</p>;
  if (!graph || (scopeKey && loadedForRef !== scopeKey))
    return <p className="vempty">加载中……</p>;
  if (merged.nodes.length === 0)
    return <p className="vempty">还没有角色卡。到「设定 · 角色」里建卡后，这里会画出关系图。</p>;

  return (
    <div className="relations-graph" data-od-id="relations-graph">
      <div
        ref={vpRef}
        className={`rg-viewport${dragging ? " dragging" : ""}`}
        role="group"
        aria-label="关系图画布（滚轮缩放，拖拽平移）"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
      >
      <svg
        viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`}
        role="img"
        aria-label={
          chapterRef
            ? "角色关系图（含截至本章剧情演变）"
            : volumeScope != null
              ? `角色关系图（截至第 ${volumeScope} 卷末剧情投影）`
              : "全书角色关系图"
        }
        preserveAspectRatio="xMidYMid meet"
      >
        <defs>
          {(["neutral", "friendly", "hostile"] as const).map((po) => (
            <marker
              key={po}
              id={`rgar-${uid}-${po}`}
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="5.5"
              markerHeight="5.5"
              orient="auto-start-reverse"
              markerUnits="strokeWidth"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" className={`rg-arrow ${po}`} />
            </marker>
          ))}
        </defs>
        {/* 边：视角单向，箭头指向被视角方；色＝关系极性（敌红/友绿/中性灰），
            线宽/虚实/透明度＝状态（开书设定淡、往章演变中、本章加重、待确认虚线）。
            同一对节点的双向边各画一侧弓形（左法线），避免直线重叠 */}
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
            const start = rimPoint(a.x, a.y, cx, cy);
            const end = rimPoint(b.x, b.y, cx, cy, ARROW_GAP);
            d = `M ${start.x} ${start.y} Q ${cx} ${cy} ${end.x} ${end.y}`;
            lx = 0.25 * a.x + 0.5 * cx + 0.25 * b.x;
            ly = 0.25 * a.y + 0.5 * cy + 0.25 * b.y;
          } else {
            const start = rimPoint(a.x, a.y, b.x, b.y);
            const end = rimPoint(b.x, b.y, a.x, a.y, ARROW_GAP);
            d = `M ${start.x} ${start.y} L ${end.x} ${end.y}`;
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
            <g key={e.key} className={`rg-edge ${e.kind} p-${e.polarity}${hit ? " hit" : ""}`}>
              <title>{tip}</title>
              <path
                d={d}
                fill="none"
                className="rg-line"
                markerEnd={`url(#rgar-${uid}-${e.polarity})`}
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
              className={nd.ghost ? "rg-node ghost" : `rg-node role-${roleKey(nd.role)}`}
            >
              <circle r={NODE_R} />
              <text textAnchor="middle" dy="4" className="rg-name">
                {nd.name}
              </text>
            </g>
          );
        })}
      </svg>
        <div className="rg-zoombar">
          <button type="button" className="rg-zbtn" data-testid="rg-zoom-in" title="放大" aria-label="放大" onClick={() => zoomAt(1 / 1.25)}>＋</button>
          <button type="button" className="rg-zbtn" data-testid="rg-zoom-out" title="缩小" aria-label="缩小" onClick={() => zoomAt(1.25)}>−</button>
          <button type="button" className="rg-zbtn" data-testid="rg-zoom-reset" title="复位为整图" aria-label="复位为整图" onClick={() => setView({ x: 0, y: 0, w: W, h: H })}>复位</button>
        </div>
      </div>
      <p className="rg-legend">
        {merged.nodes.length} 个角色 · {visibleEdges.length} 条关系
        {chapterRef && dossier.length > 0 &&
          `（剧情演变 ${dossier.length - pendingCnt} · 待确认 ${pendingCnt}）`}
        {volumeScope != null && evoCnt > 0 && `（含剧情演变 ${evoCnt} 条）`}
        {volumeScope != null && ` · 截至第 ${volumeScope} 卷末（只读投影）`}
        {chapterRef && " · 本章采纳边高亮，虚线为待确认提案"}
        {" · 滚轮缩放，拖拽平移"}
        <span className="rg-key"><i className="rg-swatch friendly" />友好</span>
        <span className="rg-key"><i className="rg-swatch hostile" />敌对</span>
        <span className="rg-key"><i className="rg-swatch neutral" />中性</span>
        <span className="rg-key"><i className="rg-dot protagonist" />主角</span>
        <span className="rg-key"><i className="rg-dot villain" />反派</span>
        <span className="rg-key"><i className="rg-dot support" />配角</span>
        <span className="rg-key"><i className="rg-dot extra" />路人</span>
      </p>
      {listEdges.length > 0 && (
        <ul className="rg-list">
          {listEdges.map((e) => {
            // 收尾提案物化进设定的本章新边：清单里沿 #405 口径高亮＋「· 本章」标注
            const hitBase = e.kind === "base" && !!chapterRef && e.origin === chapterRef;
            const note =
              e.note && (
                <em className="rg-note">
                  （{e.note.length > 60 ? `${e.note.slice(0, 60)}…` : e.note}）
                </em>
              );
            return (
              <li key={e.key} className={hitBase ? "hit" : undefined} data-testid="rg-row">
                <i className={`rg-swatch ${e.polarity}`} />
                {e.aName} → {e.bName}：{e.relType}
                {e.stance ? ` · ${e.stance}` : ""}
                {note}
                <em className="rg-origin">
                  {originLabel(e, chapters)}
                  {hitBase ? " · 本章" : ""}
                </em>
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
