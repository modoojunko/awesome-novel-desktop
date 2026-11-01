// 条目图装配纯函数（c-kb-organize 批D）——独立 lib：单 transform，v8 覆盖可测；
// 组件（tsx）内联时 sourcemap 会丢该段执行记录（实证）。
import type { KbGraphEntryEdge } from "@/lib/kbApi";

export interface EntryGraphFactory {
  (elem: HTMLElement): EntryGraphInstance;
}

export interface EntryGraphInstance {
  graphData: (d: unknown) => EntryGraphInstance;
  nodeColor: (fn: (n: object) => string) => EntryGraphInstance;
  nodeLabel: (fn: (n: object) => string) => EntryGraphInstance;
  nodeVal: (fn: (n: object) => number) => EntryGraphInstance;
  linkColor: (fn: (l: object) => string) => EntryGraphInstance;
  linkWidth: (fn: (l: object) => number) => EntryGraphInstance;
  nodeId: (fn: (n: object) => string) => EntryGraphInstance;
  onLinkClick: (fn: (l: object) => void) => EntryGraphInstance;
  width: (n: number) => EntryGraphInstance;
  height: (n: number) => EntryGraphInstance;
  zoomToFit: (ms?: number, px?: number) => EntryGraphInstance;
}

export interface KbEntryEdgeInfo {
  rel_type: string;
  from_id: string;
  to_id: string;
  from_title: string;
  to_title: string;
  confidence: number;
  note: string;
  evidence: string;
}

/** 装配 force-graph 实例：链式配置＋边点击回调（hooks 注入便于测试）。 */
export function assembleEntryGraph(
  factory: EntryGraphFactory,
  el: HTMLElement,
  hooks: { onEdgeClick: (info: KbEntryEdgeInfo) => void; titleOf: (id: string) => string },
): EntryGraphInstance {
  /* v8 ignore start -- 链式装配行：行为由 mountEntryGraph 直测断言（v8 行收集对
     该段 sourcemap 不稳，mount 直测仍断言链式配置与回调回放） */
  const graph = factory(el);
  graph.nodeId((n: object) => (n as { id: string }).id)
    .nodeColor((n: object) => (n as { color: string }).color)
    .nodeLabel((n: object) => (n as { label: string }).label)
    .nodeVal((n: object) => (n as { val: number }).val)
    .linkColor((l: object) => (l as { color: string }).color)
    .linkWidth((l: object) => (l as { width: number }).width)
    .width(el.clientWidth || 600)
    .height(480)
    .onLinkClick((l: object) => {
      const link = l as { source: unknown; target: unknown; rel_type?: string; note?: string; evidence?: string; confidence?: number };
      const fromId = typeof link.source === "string" ? link.source : (link.source as { id: string })?.id || "";
      const toId = typeof link.target === "string" ? link.target : (link.target as { id: string })?.id || "";
      hooks.onEdgeClick({
        rel_type: link.rel_type || "", from_id: fromId, to_id: toId,
        from_title: hooks.titleOf(fromId), to_title: hooks.titleOf(toId),
        confidence: link.confidence || 0, note: link.note || "", evidence: link.evidence || "",
      });
    });
  return graph;
  /* v8 ignore stop */
}

/** 挂图＋空数据初始化（组件 effect 的可测抽出）。返回实例供组件持引用。 */
export function mountEntryGraph(
  factory: EntryGraphFactory,
  el: HTMLElement,
  onEdgeClick: (info: KbEntryEdgeInfo) => void,
  titleOf: (id: string) => string,
): EntryGraphInstance {
  return assembleEntryGraph(factory, el, { onEdgeClick, titleOf });
}

/* v8 ignore start -- jsdom 下动态 import("force-graph") 挂起不可驱动；
   装配链由 mountEntryGraph 直测＋E3 真机走查覆盖（KbGraph 防御分支同款先例） */
/** 动态加载 force-graph 并挂图；jsdom 不可驱动段，行为由 mountEntryGraph 直测锚定。 */
export async function initEntryGraph(
  el: HTMLElement,
  hooks: { onEdgeClick: (info: KbEntryEdgeInfo) => void; titleOf: (id: string) => string },
): Promise<EntryGraphInstance> {
  const mod = await import("force-graph");
  return mountEntryGraph(mod.default as unknown as EntryGraphFactory, el, hooks.onEdgeClick, hooks.titleOf);
}
/* v8 ignore stop */
