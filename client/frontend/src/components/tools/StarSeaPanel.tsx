/* 知识星图（c-kb-knowledge-v2 → c-kb-summarize 树形化）：知识树图谱——概念根星 →
   知识枝干（parent_id 层级边·实线）＋六类关联边（虚线），叶子知识挂实例群（点开卡看）。
   Three.js + 3d-force-graph 动态 import（主包零负载）；WebGL 不可用降级到提示行。 */
import { useCallback, useEffect, useRef, useState } from "react";

import { kbApi } from "@/lib/kbApi";

const CATEGORY_COLORS: Record<string, string> = {
  文风: "#7c9ef5", 文笔: "#f5b87c", 世界设定: "#9ef57c",
  角色设定: "#f57c9e", 手法: "#7cf5d0", 情节: "#c77cf5",
};
const FOLD_DEPTH = 3; // 折叠是展示策略：超过此深度的子树折叠计数，点开展全层（数据不截断）

interface TreeNode {
  id: string;
  kind: string;
  title?: string;
  concept: string;
  genre: string;
  definition?: string;
  children: TreeNode[];
}
interface TreeData {
  roots: TreeNode[];
  rel_edges: { source: string; target: string; rel_type: string }[];
}
interface StarNode {
  id: string; label: string; category: string;
  genre: string; color: string; size: number;
  folded?: number; depth: number;
  kind?: string; definition?: string;
}
interface StarLink {
  source: string; target: string; color: string; dashed?: boolean;
}

export default function StarSeaPanel({ genre }: { genre: string }) {
  const boxRef = useRef<HTMLDivElement | null>(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<StarNode | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const buildGraph = useCallback(async (): Promise<{ nodes: StarNode[]; links: StarLink[] }> => {
    const tree = (await kbApi.graphTree(genre)) as unknown as TreeData;
    const nodes: StarNode[] = [];
    const links: StarLink[] = [];
    const inGraph = new Set<string>();

    const walk = (node: TreeNode, depth: number, parentId: string | null, color: string) => {
      const kids = node.children ?? [];
      const overFold = depth >= FOLD_DEPTH && kids.length > 0 && !expanded.has(node.id);
      const label = node.kind === "root" ? `${node.genre || "通用"} · ${node.concept}` : node.title || node.id.slice(0, 8);
      nodes.push({
        id: node.id,
        label: overFold ? `${label}（＋${kids.length}）` : label,
        category: node.concept,
        genre: node.genre,
        color,
        size: node.kind === "root" ? 8 : Math.max(2, 5 - depth),
        folded: overFold ? kids.length : undefined,
        depth,
        kind: node.kind,
        definition: node.definition || "",
      });
      if (parentId) {
        links.push({ source: parentId, target: node.id, color: "#2a4a6a" });
      }
      inGraph.add(node.id);
      if (overFold) return; // 折叠：该子树不展开（展示策略，点折叠星进入 expanded 再展开）
      kids.forEach((k) => walk(k, depth + 1, node.id, color));
    };

    for (const root of tree.roots ?? []) {
      const color = CATEGORY_COLORS[root.concept] ?? "#38bdf8";
      walk(root, 0, null, color);
    }
    // 关联边（两端都在已展开节点内的才画，虚线区分层级实线）
    for (const e of tree.rel_edges ?? []) {
      if (inGraph.has(e.source) && inGraph.has(e.target)) {
        links.push({ source: e.source, target: e.target, color: "#1a3a5a", dashed: true });
      }
    }
    return { nodes, links };
  }, [genre, expanded]);

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
        const { nodes, links } = await buildGraph();
        graph = ForceGraph3D()(el)
          .backgroundColor("#020408")
          .nodeId("id")
          .nodeLabel("label")
          .nodeColor("color")
          .nodeVal("size")
          .linkColor("color")
          .linkWidth(0.5)
          .linkLineDash((l: any) => (l?.dashed ? [2, 2] : null))
          .onNodeClick((node: any) => {
            const sn = node as StarNode;
            if (sn.folded) {
              // 折叠星：展开该子树
              setExpanded((prev) => new Set(prev).add(sn.id));
              return;
            }
            if (sn.kind === "root") return;
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
      <p className="mt-2 text-center text-[10.5px] text-[var(--faint)]">
        实线＝知识层级（枝干无限嵌套，点折叠星展开）· 虚线＝整理产出的关联 · 点知识星看详情（实例在知识卡内）
      </p>
      {selected && (
        <div className="mt-3 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
          <p className="text-[14px] font-semibold text-[var(--fg)]">{selected.label}</p>
          <p className="mt-1 text-[11px] text-[var(--muted)]">
            类别 / {selected.category} · 题材 / {selected.genre}
          </p>
          {selected.definition && (
            <p className="mt-1 text-[12px] leading-relaxed text-[var(--muted)]">{selected.definition}</p>
          )}
          <p className="mt-1 text-[11px] text-[var(--faint)]">实例群在知识详情里查看（列表点开本条）。</p>
          <button onClick={() => setSelected(null)} className="mt-2 text-[11px] text-[var(--accent)] hover:underline">
            关闭
          </button>
        </div>
      )}
    </div>
  );
}
