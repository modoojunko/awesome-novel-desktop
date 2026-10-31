// 知识库全局图（c-kb-organize 批7）：Obsidian 式 2D 力导图——聚合（题材×概念格）
// ＋格子下钻＋面包屑返回＋悬停邻域高亮。force-graph 动态 import（主包零负载）。
// 关系边（条目—条目）随 AI 整理二阶段；本视图边=层级边。
import { useCallback, useEffect, useRef, useState } from "react";
import { kbApi } from "@/lib/kbApi";
import {
  adjacencyOf,
  cellLabel,
  genreLabel,
  toAggregateGraph,
  toCellGraph,
  tokenColors,
  type GraphLink,
  type GraphNode,
} from "@/lib/kbGraph";

interface Drill {
  genre: string;
  concept: string;
}

interface GraphFactory {
  (elem: HTMLElement): GraphInstance;
}

interface GraphInstance {
  graphData: (d: unknown) => GraphInstance;
  nodeColor: (fn: (n: object) => string) => GraphInstance;
  nodeLabel: (fn: (n: object) => string) => GraphInstance;
  nodeVal: (fn: (n: object) => number) => GraphInstance;
  linkColor: (fn: (l: object) => string) => GraphInstance;
  linkWidth: (fn: (l: object) => number) => GraphInstance;
  nodeId: (fn: (n: object) => string) => GraphInstance;
  nodeCanvasObject: (fn: (n: object, ctx: CanvasRenderingContext2D, scale: number) => void) => GraphInstance;
  onNodeHover: (fn: (n: object | null) => void) => GraphInstance;
  onNodeClick: (fn: (n: object) => void) => GraphInstance;
  d3Force: (name: string, force: unknown) => GraphInstance;
  width: (n: number) => GraphInstance;
  height: (n: number) => GraphInstance;
  cooldownTicks?: number;
}

export default function KbGraph() {
  const boxRef = useRef<HTMLDivElement | null>(null);
  const graphRef = useRef<GraphInstance | null>(null);
  const [drill, setDrill] = useState<Drill | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [graphReady, setGraphReady] = useState(false);
  // 点击守卫用 ref：force-graph 回调注册一次，state 闭包会过期
  const drillRef = useRef<Drill | null>(null);
  useEffect(() => {
    drillRef.current = drill;
  }, [drill]);
  // 邻域与配色挂在 ref（force-graph 回调每次帧读，避免重建图）
  const adjRef = useRef<Map<string, Set<string>>>(new Map());
  const hoverRef = useRef<string | null>(null);
  const colorsRef = useRef(tokenColors());

  const paint = useCallback(async () => {
    /* v8 ignore start -- 防御分支：paint 只在挂载期 effect 里调度，容器恒在 */
    if (!boxRef.current) return;
    /* v8 ignore stop */
    setLoading(true);
    setError("");
    try {
      if (!drill) {
        const agg = await kbApi.graphAggregate();
        const { nodes, links } = toAggregateGraph(agg.nodes, agg.links);
        adjRef.current = adjacencyOf(links);
        applyData({ nodes, links });
      } else {
        const cell = await kbApi.graphCell(drill.genre, drill.concept);
        const { nodes, links } = toCellGraph(drill.genre, drill.concept, cell.nodes);
        adjRef.current = adjacencyOf(links);
        applyData({ nodes, links });
      }
    } catch (e: unknown) {
      setError((e as { message?: string }).message || "图谱加载失败");
    } finally {
      setLoading(false);
    }

    function applyData(d: { nodes: GraphNode[]; links: GraphLink[] }) {
      /* v8 ignore start -- 防御分支：paint 被 graphReady 门控，建图后才会装载 */
      const g = graphRef.current;
      if (g) g.graphData(d);
      /* v8 ignore stop */
    }
  }, [drill]);

  // 挂图（一次）＋数据装载
  useEffect(() => {
    let alive = true;
    let graph: GraphInstance | null = null;
    (async () => {
      const mod = await import("force-graph");
      /* v8 ignore start -- 防御分支：unmount 竞态（import resolve 前卸载）在
         卸载竞态用例覆盖；container 恒存，el 与 boxRef 二次判定同源 */
      if (!alive || !boxRef.current) return;
      /* v8 ignore stop */
      const el = boxRef.current;
      const colors = tokenColors();
      colorsRef.current = colors;
      const hoverBg = "rgba(0,0,0,0.06)";
      const factory = mod.default as unknown as GraphFactory;
      graph = factory(el)
        .width(el.clientWidth || 800)
        .height(el.clientHeight || 480)
        .nodeId((n: object) => (n as { id: string }).id)
        .nodeVal((n: object) => (n as { val: number }).val)
        .nodeLabel((n: object) => (n as { label: string }).label)
        .nodeColor((n: object) => {
          const node = n as { id: string; kind: string; scope: string };
          if (hoverRef.current) {
            const adj = adjRef.current.get(hoverRef.current);
            const near = hoverRef.current === node.id || !!adj?.has(node.id);
            if (!near) return hoverBg;
          }
          if (node.kind === "genre") return colors.fg;
          if (node.kind === "entry") return node.scope === "scene" ? colors.muted : colors.accent;
          return colors.accent;
        })
        .linkColor(() => colors.line)
        .linkWidth(() => 1)
        .onNodeHover((n: object | null) => {
          hoverRef.current = n ? (n as { id: string }).id : null;
        })
        .onNodeClick((n: object) => {
          const node = n as { kind: string; genre: string; concept: string };
          if (node.kind === "cell" && !drillRef.current) {
            setDrill({ genre: node.genre, concept: node.concept });
          }
        })
        .nodeCanvasObject((node: object, ctx: CanvasRenderingContext2D, scale: number) => {
          // 恒显标签（屏幕恒定：字号随缩放折算）
          const n = node as { label: string; x?: number; y?: number; val: number };
          if (n.x === undefined || n.y === undefined) return;
          const size = 11 / scale;
          const bold = n.val >= 7;
          ctx.font = `${bold ? 600 : 400} ${size}px sans-serif`;
          ctx.fillStyle = colorsRef.current.fg;
          ctx.textAlign = "center";
          ctx.textBaseline = "top";
          ctx.fillText(n.label, n.x, n.y + (n.val >= 7 ? 8 : 5));
        });
      graphRef.current = graph;
      setGraphReady(true);
    })();
    return () => {
      alive = false;
      graphRef.current = null;
      /* v8 ignore start -- 防御分支：boxRef 只在组件卸载时仍指向容器 */
      if (boxRef.current) boxRef.current.innerHTML = "";
      /* v8 ignore stop */
    };
    // 仅挂载一次；数据装载走 paint effect
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (graphReady) void paint();
  }, [paint, graphReady]);

  return (
    <div>
      {/* 面包屑 */}
      <div className="mb-2 flex items-center gap-1.5 text-[12px] text-[var(--muted)]">
        <button
          onClick={() => setDrill(null)}
          className={`hover:underline ${drill ? "" : "font-medium text-[var(--accent)]"}`}
        >
          {genreLabel(drill?.genre ?? "")}
        </button>
        {drill && (
          <>
            <span className="text-[var(--faint)]">/</span>
            <span className="font-medium text-[var(--fg)]">{drill.concept}</span>
          </>
        )}
        <span className="ml-auto text-[11px] text-[var(--faint)]">
          {drill ? cellLabel(drill.genre, drill.concept) : "点格子下钻"}
        </span>
      </div>
      {error && <p className="py-8 text-center text-[13px] text-[var(--muted)]">{error}</p>}
      {loading && !error && <p className="py-8 text-center text-[13px] text-[var(--muted)]">图谱生成中…</p>}
      <div ref={boxRef} className="h-[480px] overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface)]" />
      <p className="mt-2 text-[11px] leading-relaxed text-[var(--faint)]">
        节点大小＝条目数；实色＝基线、灰＝场景条目（逐章挑）。条目之间的关联边等 AI 整理上线后长出来。
      </p>
    </div>
  );
}
