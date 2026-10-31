// 全局图数据整形（c-kb-organize 批7）：聚合/下钻 → force-graph 节点边＋token 实色解析。
// 颜色走 design token 计算值（canvas 不认 var(--x)；内联 oklch 被 check-inline-colors 闸拦截），
// 取不到（jsdom/旧内核兜底）时回落冷灰阶 hex。

export interface KbAggNode {
  id: string;
  kind: "genre" | "cell";
  genre: string;
  concept: string;
  count: number;
}

export interface KbCellNode {
  id: string;
  kind: "entry";
  genre: string;
  concept: string;
  title: string;
  scope: string;
}

export interface GraphNode {
  id: string;
  label: string;
  kind: "genre" | "cell" | "entry";
  genre: string;
  concept: string;
  count: number;
  /** 力导模型体积（genre 恒大、cell 随条目数、entry 恒小） */
  val: number;
  scope: string;
}

export interface GraphLink {
  source: string;
  target: string;
}

const GENERAL_LABEL = "跨题材通用";

export function genreLabel(genre: string): string {
  return genre || GENERAL_LABEL;
}

export function cellLabel(genre: string, concept: string): string {
  return `${genreLabel(genre)} · ${concept}`;
}

/** 聚合视图：题材节点＋格子节点＋题材—格子层级边。 */
export function toAggregateGraph(
  nodes: KbAggNode[],
  links: { source: string; target: string }[],
): { nodes: GraphNode[]; links: GraphLink[] } {
  const out: GraphNode[] = nodes.map((n) => ({
    id: n.id,
    label: n.kind === "genre" ? `${genreLabel(n.genre)} ${n.count}` : `${n.concept} ${n.count}`,
    kind: n.kind,
    genre: n.genre,
    concept: n.concept,
    count: n.count,
    val: n.kind === "genre" ? 7 : 2 + Math.min(n.count, 10),
    scope: "base",
  }));
  return { nodes: out, links: links.map((l) => ({ ...l })) };
}

/** 下钻视图：格子中心节点＋条目节点＋星形边（邻域高亮=中心＋被点格子）。 */
export function toCellGraph(
  genre: string,
  concept: string,
  entries: KbCellNode[],
): { nodes: GraphNode[]; links: GraphLink[] } {
  const cellId = `cell:${genre || "_general"}:${concept}`;
  const nodes: GraphNode[] = [
    {
      id: cellId,
      label: `${concept} ${entries.length}`,
      kind: "cell",
      genre,
      concept,
      count: entries.length,
      val: 7,
      scope: "base",
    },
  ];
  const links: GraphLink[] = [];
  for (const e of entries) {
    nodes.push({
      id: e.id,
      label: e.title || e.concept,
      kind: "entry",
      genre: e.genre,
      concept: e.concept,
      count: 0,
      val: 2,
      scope: e.scope,
    });
    links.push({ source: cellId, target: e.id });
  }
  return { nodes, links };
}

export interface TokenColors {
  accent: string;
  fg: string;
  muted: string;
  line: string;
}

/** design token → canvas 实色（旧内核/jsdom 取不到时回落冷灰阶）。 */
export function tokenColors(): TokenColors {
  const fallback: TokenColors = { accent: "#4a7c7c", fg: "#2a2f33", muted: "#8a9199", line: "#d8dcdf" };
  try {
    const cs = getComputedStyle(document.documentElement);
    const pick = (name: string, fb: string): string => {
      const v = cs.getPropertyValue(name)?.trim();
      return v ? v : fb;
    };
    return {
      accent: pick("--accent", fallback.accent),
      fg: pick("--fg", fallback.fg),
      muted: pick("--muted", fallback.muted),
      line: pick("--border", fallback.line),
    };
  } catch {
    return fallback;
  }
}

/** 邻域表：id → 相邻 id 集合（悬停高亮用）。 */
export function adjacencyOf(links: GraphLink[]): Map<string, Set<string>> {
  const adj = new Map<string, Set<string>>();
  for (const l of links) {
    if (!adj.has(l.source)) adj.set(l.source, new Set());
    if (!adj.has(l.target)) adj.set(l.target, new Set());
    adj.get(l.source)!.add(l.target);
    adj.get(l.target)!.add(l.source);
  }
  return adj;
}
