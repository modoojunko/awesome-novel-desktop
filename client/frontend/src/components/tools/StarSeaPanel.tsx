/* 知识星图（c-kb-knowledge-v2）：单一大星系，节点＝概念，边＝D6 矩阵允许的概念对。
   Three.js + 3d-force-graph 动态 import（主包零负载）；WebGL 不可用降级到提示行。 */
import { useCallback, useEffect, useRef, useState } from "react";

const GENRES = ["科幻", "都市", "仙侠", "悬疑"] as const;
const CONCEPTS = ["文风", "文笔", "世界设定", "角色设定", "手法", "情节"] as const;
const CONCEPT_DESC: Record<string, string> = {
  文风: "这本书的整体声音", 文笔: "具体句子的写法",
  世界设定: "舞台、力量、势力、铁律", 角色设定: "造角色的方法",
  手法: "写每一章时的场面打法", 情节: "事件怎么推进",
};
const CATEGORY_COLORS: Record<string, string> = {
  文风: "#7c9ef5", 文笔: "#f5b87c", 世界设定: "#9ef57c",
  角色设定: "#f57c9e", 手法: "#7cf5d0", 情节: "#c77cf5",
};
const GENRE_COLORS: Record<string, string> = {
  科幻: "#38bdf8", 都市: "#fbbf24", 仙侠: "#c084fc", 悬疑: "#34d399",
};
/* D6 概念相容矩阵允许的跨概念对/方向 */
const CONCEPT_EDGES: [string, string, string][] = [
  ["手法", "文风", "applies_to"],
  ["手法", "文笔", "applies_to"],
  ["手法", "世界设定", "depends_on"],
  ["手法", "角色设定", "depends_on"],
  ["手法", "文风", "derived_from"],
  ["手法", "文笔", "contradicts"],
];

interface StarNode {
  id: string; label: string; category: string;
  genre: string; color: string; size: number;
}
interface StarLink {
  source: string; target: string; color: string;
}

export default function StarSeaPanel({ genre }: { genre: string }) {
  const boxRef = useRef<HTMLDivElement | null>(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<StarNode | null>(null);

  const buildGraph = useCallback(() => {
    const nodes: StarNode[] = [];
    const links: StarLink[] = [];
    const genres = genre && GENRES.includes(genre as (typeof GENRES)[number]) ? [genre] : [...GENRES];
    genres.forEach((g) => {
      nodes.push({ id: `root_${g}`, label: g, category: g, genre: g, color: GENRE_COLORS[g] ?? "#38bdf8", size: 8 });
    });
    genres.forEach((g) => {
      CONCEPTS.forEach((c) => {
        nodes.push({
          id: `${g}:${c}`, label: c, category: g, genre: g,
          color: CATEGORY_COLORS[c] ?? "#38bdf8", size: 5,
        });
        links.push({ source: `root_${g}`, target: `${g}:${c}`, color: "#2a4a6a" });
      });
    });
    // D6 矩阵允许的概念关系（同题材内）
    genres.forEach((g) => {
      CONCEPT_EDGES.forEach(([a, b]) => {
        links.push({ source: `${g}:${a}`, target: `${g}:${b}`, color: "#1a3a5a" });
      });
    });
    return { nodes, links };
  }, [genre]);

  useEffect(() => {
    let alive = true;
    let graph: Record<string, (...args: unknown[]) => unknown> | null = null;

    (async () => {
      try {
        const [{ default: ForceGraph3DRaw }] = await Promise.all([
          import("3d-force-graph"),
        ]);
        // 3d-force-graph 类型不友好，用宽松调用（原型→实现同口径） */
        /* eslint-disable @typescript-eslint/no-explicit-any */
        const ForceGraph3D = ForceGraph3DRaw as any;
        if (!alive || !boxRef.current) return;
        const el = boxRef.current;
        const { nodes, links } = buildGraph();
        graph = ForceGraph3D()(el)
          .backgroundColor("#020408")
          .nodeId("id")
          .nodeLabel("label")
          .nodeColor("color")
          .nodeVal("size")
          .linkColor("color")
          .linkWidth(0.5)
          .onNodeClick((node: any) => {
            const sn = node as StarNode;
            if (!sn.category || sn.id.startsWith("root_")) return;
            setSelected(sn);
          });
        graph!.graphData({ nodes, links });
      } catch {
        if (alive) setError("WebGL 不可用，星图无法渲染。可回到列表继续编辑知识。");
      }
    })();

    return () => {
      alive = false;
      if (boxRef.current) boxRef.current.innerHTML = "";
    };
  }, [buildGraph]);

  if (error) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="text-center">
          <p className="text-[13px] text-[var(--muted)]">{error}</p>
          <button
            onClick={() => setError("")}
            className="mt-3 rounded-lg border border-[var(--accent)] px-4 py-2 text-[12px] text-[var(--accent)]"
          >
            回到列表
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="relative">
      <div ref={boxRef} className="h-[560px] overflow-hidden rounded-xl border border-[var(--border)] bg-[#020408]" />
      {selected && (
        <div className="mt-3 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
          <p className="text-[14px] font-semibold text-[var(--fg)]">{selected.label}</p>
          <p className="mt-1 text-[11px] text-[var(--muted)]">
            类别 / {selected.category} · 题材 / {selected.genre}
          </p>
          {CONCEPT_DESC[selected.label] && (
            <p className="mt-1 text-[12px] text-[var(--muted)]">{CONCEPT_DESC[selected.label]}</p>
          )}
          <button onClick={() => setSelected(null)} className="mt-2 text-[11px] text-[var(--accent)] hover:underline">
            关闭
          </button>
        </div>
      )}
    </div>
  );
}
