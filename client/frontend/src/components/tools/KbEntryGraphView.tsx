// 条目图视图本体（c-kb-organize 批D；KbEntryGraph.tsx 为薄壳 re-export）：题材内 active 条目为节点、生效关系为边（六类分色）。
// 点边出说明＋证据浮层；cap 截断提示。数据 /graph/entries（≤500 边按置信降序）。
// 结构与 KbGraph 同构（graphReady 门控＋独立 paint effect——测试 mock 命中口径一致）。
import { useCallback, useEffect, useRef, useState } from "react";
import { kbApi, type KbGraphEntryEdge, type KbGraphEntryNode } from "@/lib/kbApi";
import {
  initEntryGraph,
  type EntryGraphInstance,
} from "@/lib/kbEntryGraph";

const REL_COLOR: Record<string, string> = {
  refines: "#7c9ef5",
  contradicts: "#f57c7c",
  depends_on: "#f5b87c",
  instance_of: "#9ef57c",
  derived_from: "#c77cf5",
  applies_to: "#7cf5d0",
};

const CONCEPT_COLOR: Record<string, string> = {
  文风: "#7c9ef5", 文笔: "#f5b87c", 世界设定: "#9ef57c",
  角色设定: "#f57c9e", 手法: "#7cf5d0", 情节: "#c77cf5",
};

interface EdgeInfo extends KbGraphEntryEdge {
  from_title: string;
  to_title: string;
}


export default function KbEntryGraphView({ genre }: { genre: string }) {
  const boxRef = useRef<HTMLDivElement | null>(null);
  const graphRef = useRef<EntryGraphInstance | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [graphReady, setGraphReady] = useState(false);
  const [truncated, setTruncated] = useState(0);
  const [edgeInfo, setEdgeInfo] = useState<EdgeInfo | null>(null);
  const [edgeList, setEdgeList] = useState<KbGraphEntryEdge[]>([]);
  const [graphData, setGraphData] = useState<{ nodes: object[]; links: object[] } | null>(null);
  // 点击浮层用 ref：force-graph 回调注册一次，state 闭包会过期
  const titleRef = useRef<Map<string, string>>(new Map());

  // 数据加载与图装配解耦：加载 effect 不经动态 import（测试可直接 mock 命中）
  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      setError("");
      try {
        const data = await kbApi.organize.graphEntries(genre);
        if (!alive) return;
        titleRef.current = new Map(data.nodes.map((n: KbGraphEntryNode) => [n.id, n.title]));
        setTruncated(data.edge_truncated);
        setEdgeList(data.edges);
        const nodes = data.nodes.map((n) => ({
          id: n.id, label: n.title || "未命名", val: 6,
          color: CONCEPT_COLOR[n.concept] || "#7c9ef5",
        }));
        const links = data.edges.map((e) => ({
          source: e.from_id, target: e.to_id,
          color: REL_COLOR[e.rel_type] || "#999", width: 1.5,
          ...e,
        }));
        setGraphData({ nodes, links });
      } catch (e: unknown) {
        if (alive) setError((e as { message?: string }).message || "条目图加载失败");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [genre]);

  // 挂图（一次）——动态 import 下沉 kb/organize 同款 lib（jsdom 挂起段 lib 侧 v8 ignore）
  useEffect(() => {
    let alive = true;
    (async () => {
      if (!boxRef.current) return;
      const graph = await initEntryGraph(boxRef.current, {
        onEdgeClick: setEdgeInfo,
        titleOf: (id: string) => titleRef.current.get(id) || "",
      });
      /* v8 ignore next */
      if (!alive) return;
      /* v8 ignore next */
      graphRef.current = graph;
      /* v8 ignore next */
      graph.graphData({ nodes: [], links: [] });
      /* v8 ignore next */
      setGraphReady(true);
    })();
    return () => {
      alive = false;
      graphRef.current = null;
    };
  }, []);

  // 图就绪＋数据就绪 → 喂图（顺序无关：两边各自就绪即喂；jsdom 下 graphReady 不置位＝真机段）
  useEffect(() => {
    if (!graphReady || !graphData) return;
    graphRef.current?.graphData(graphData);
    setTimeout(() => graphRef.current?.zoomToFit(400, 60), 300);
  }, [graphReady, graphData]);

  return (
    <div>
      {error && <p className="text-[12px] text-red-500">{error}</p>}
      {loading && <p className="text-[12px] text-[var(--muted)]">条目图加载中…</p>}
      <div ref={boxRef} data-testid="kb-entry-graph" className="h-[480px] w-full rounded-lg border border-[var(--border)] bg-[var(--surface)]" />
      {truncated > 0 && (
        <p className="mt-1 text-[11px] text-amber-500">
          关系较多，仅显示置信最高的部分（另有 {truncated} 条未画出）。
        </p>
      )}
      <div className="mt-3 space-y-1">
        <p className="font-mono text-[10px] tracking-[0.14em] text-[var(--muted)]">关系清单（点图上的边可看详情）</p>
        {edgeList.length === 0 && !loading && (
          <p className="text-[12px] text-[var(--muted)]">还没有生效关系——去「知识整理」跑一次。</p>
        )}
        {edgeList.slice(0, 20).map((e) => (
          <button
            key={`${e.from_id}-${e.to_id}-${e.rel_type}`}
            onClick={() => setEdgeInfo({
              ...e,
              from_title: titleRef.current.get(e.from_id) || e.from_id,
              to_title: titleRef.current.get(e.to_id) || e.to_id,
            })}
            className="block w-full rounded-md border border-[var(--border)] px-3 py-1.5 text-left text-[12px] hover:bg-[var(--accent-soft)]"
          >
            <span className="font-medium">{e.rel_type}</span>
            ：{titleRef.current.get(e.from_id) || e.from_id} → {titleRef.current.get(e.to_id) || e.to_id}
            <span className="ml-1 text-[var(--muted)]">（置信 {Math.round(e.confidence * 100)}%）</span>
          </button>
        ))}
      </div>
      {edgeInfo && (
        <div className="mt-2 rounded-lg border border-[var(--border)] px-3 py-2 text-[12px]" data-testid="edge-info">
          <p className="font-medium">
            {edgeInfo.rel_type}：{edgeInfo.from_title} → {edgeInfo.to_title}
          </p>
          {edgeInfo.note && <p className="text-[var(--muted)]">{edgeInfo.note}</p>}
          {edgeInfo.evidence && <p className="text-[var(--muted)]">证据：{edgeInfo.evidence}</p>}
          <button onClick={() => setEdgeInfo(null)} className="mt-1 text-[11px] text-[var(--muted)] underline">收起</button>
        </div>
      )}
    </div>
  );
}
