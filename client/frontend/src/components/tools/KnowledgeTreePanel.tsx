import { useCallback, useEffect, useMemo, useState } from "react";
import { kbApi, type KbInstanceRow } from "@/lib/kbApi";

/** 树视图数据节点（graphTree 形状）。 */
interface TreeNode {
  id: string;
  kind: string;
  title: string;
  concept: string;
  genre: string;
  definition?: string;
  children: TreeNode[];
}

/** 知识树视图（原型定稿 2026-11-08）：树只管结构——实例不树上展开，
 *  点叶子知识点开右侧抽屉看实例列表，抽屉里点行开实例详情（onSelectInstance）。 */
export default function KnowledgeTreePanel({
  genre,
  onSelectInstance,
}: {
  genre: string;
  onSelectInstance?: (row: KbInstanceRow) => void;
}) {
  const [roots, setRoots] = useState<TreeNode[]>([]);
  const [rows, setRows] = useState<KbInstanceRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [treeReady, setTreeReady] = useState<boolean | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [drawerNode, setDrawerNode] = useState<TreeNode | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    void (async () => {
      try {
        const [tree, flat] = await Promise.all([
          kbApi.graphTree(genre),
          kbApi.instancesFlat(genre ? { genre } : {}),
        ]);
        if (!alive) return;
        setRoots(tree.roots as unknown as TreeNode[]);
        setTreeReady(tree.tree?.ready ?? null);
        setRows(flat.rows.filter((x): x is KbInstanceRow => x.row_kind === "instance"));
        // 默认展开到第二层（根＋枝干可见，叶子收起）
        const init = new Set<string>();
        for (const r of tree.roots as unknown as TreeNode[]) {
          init.add(r.id);
          for (const c of r.children ?? []) init.add(c.id);
        }
        setExpanded(init);
      } catch {
        if (alive) { setRoots([]); setRows([]); }
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [genre]);

  const byKnowledge = useMemo(() => {
    const m = new Map<string, KbInstanceRow[]>();
    for (const r of rows) {
      const list = m.get(r.knowledge_id) ?? [];
      list.push(r);
      m.set(r.knowledge_id, list);
    }
    return m;
  }, [rows]);

  const toggle = useCallback((id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }, []);

  const openDrawer = useCallback((node: TreeNode, chain: TreeNode[]) => {
    setDrawerNode({ ...node, children: [], definition: chain.length > 1 ? node.definition : node.definition });
    setDrawerChain(chain);
  }, []);
  const [drawerChain, setDrawerChain] = useState<TreeNode[]>([]);

  const renderNode = (node: TreeNode, depth: number, chain: TreeNode[]) => {
    const insts = byKnowledge.get(node.id) ?? [];
    const kids = node.children ?? [];
    const isOpen = expanded.has(node.id);
    const hasKids = kids.length > 0;
    const nextChain = [...chain, node];
    return (
      <div key={node.id} data-testid="kb-tree-node" style={{ paddingLeft: depth === 0 ? 0 : 14 }}>
        <div
          className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 hover:bg-[var(--accent-soft)]"
          onClick={() => {
            if (hasKids) { toggle(node.id); return; }
            if (insts.length > 0) openDrawer(node, nextChain);
          }}
        >
          <span className="w-3 text-[10px] text-[var(--muted)]">{hasKids ? (isOpen ? "▾" : "▸") : ""}</span>
          <span className={`text-[13.5px] ${node.kind === "root" ? "font-semibold text-[var(--fg)]" : depth <= 2 ? "font-medium text-[var(--fg)]" : "text-[var(--fg)]"}`}>{node.title}</span>
          {insts.length > 0 && (
            <span data-testid="kb-tree-count" className="rounded-full bg-[var(--accent-soft)] px-1.5 text-[10px] text-[var(--accent)]">{insts.length}</span>
          )}
          {node.definition && depth >= 2 && (
            <span className="truncate text-[11px] text-[var(--muted)]">{node.definition.slice(0, 30)}</span>
          )}
        </div>
        {isOpen && hasKids && (
          <div className="ml-4 border-l border-[var(--border)] pl-2.5">
            {kids.map((k) => renderNode(k, depth + 1, nextChain))}
          </div>
        )}
      </div>
    );
  };

  const drawerInsts = drawerNode ? (byKnowledge.get(drawerNode.id) ?? []) : [];
  const chainText = drawerChain.length > 1
    ? drawerChain.map((c) => c.title).join(" ← ")
    : "写作知识";

  if (loading) {
    return <div data-testid="kb-tree-panel" className="p-6 text-[12px] text-[var(--muted)]">树装载中…</div>;
  }
  if (!roots.length) {
    // c-kb-tree-cdn：树未同步 ≠ 没有知识点——口径分开说，别误导用户去收录
    if (treeReady === false) {
      return (
        <div data-testid="kb-tree-panel" data-tree-ready="false" className="p-6 text-[12px] text-[var(--muted)]">
          知识树还没从 CDN 同步下来——联网重启应用后会自动同步；同步前「知识提炼」「知识总结」暂不可用。
        </div>
      );
    }
    return <div data-testid="kb-tree-panel" className="p-6 text-[12px] text-[var(--muted)]">这个题材还没有知识点——收录拆书或点「知识提炼」会长出来。</div>;
  }
  return (
    <>
      <div data-testid="kb-tree-panel" className="mx-auto max-w-4xl px-6 py-4">
        {treeReady === false && (
          <p data-testid="kb-tree-degraded" className="mb-2 text-[11px] text-[var(--muted)]">
            知识树未同步：现有知识点按默认顺序展示；联网重启后恢复层次与「知识提炼」。
          </p>
        )}
        {roots.map((r) => renderNode(r, 0, []))}
      </div>
      {drawerNode && (
        <div className="fixed inset-0 z-[55] flex justify-end bg-black/25" onClick={() => setDrawerNode(null)} data-testid="kb-tree-drawer">
          <div className="flex h-full w-[480px] max-w-[92vw] flex-col border-l border-[var(--border)] bg-[var(--surface)] shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="border-b border-[var(--border)] px-5 pb-3 pt-4">
              <p className="text-[11px] text-[var(--muted)]">{chainText}</p>
              <div className="mt-1 flex items-center justify-between">
                <h2 className="font-[var(--font-display)] text-xl font-semibold text-[var(--fg)]">
                  {drawerNode.title}
                  {drawerInsts.length > 0 && (
                    <span className="ml-2 rounded-full bg-[var(--accent-soft)] px-2 py-0.5 align-middle text-[11px] text-[var(--accent)]">{drawerInsts.length}</span>
                  )}
                </h2>
                <button onClick={() => setDrawerNode(null)} className="text-[var(--faint)] hover:text-[var(--fg)]">✕</button>
              </div>
              {drawerNode.definition && (
                <p className="mt-1.5 text-[12px] text-[var(--muted)]">{drawerNode.definition}</p>
              )}
            </div>
            <div className="flex-1 overflow-y-auto px-3 pb-5">
              {drawerInsts.map((row) => (
                <div
                  key={row.id}
                  data-testid="kb-tree-instance"
                  className="cursor-pointer rounded-lg px-2 py-3 hover:bg-[var(--fg-soft)]"
                  style={{ borderBottom: "1px solid var(--border)" }}
                  onClick={() => onSelectInstance?.(row)}
                >
                  <div className="text-[13.5px] text-[var(--fg)]">
                    {row.text}
                    {row.quote && <span className="text-[var(--muted)]"> ——{row.quote.slice(0, 40)}</span>}
                  </div>
                  <div className="mt-1 text-[11px] text-[var(--faint)]">
                    源自：{row.source_novel}{row.source_chapter ? ` · ${row.source_chapter}` : ""}
                  </div>
                </div>
              ))}
              {drawerInsts.length === 0 && (
                <p className="px-2 py-4 text-center text-[12px] text-[var(--muted)]">这个知识点下还没有实例。</p>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
