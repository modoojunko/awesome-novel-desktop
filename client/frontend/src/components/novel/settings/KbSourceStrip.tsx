// 知识库来源行（c-kb-snapshot 批3）：设定面板顶部一条——作家在书内启用/同步/解绑库。
// 数据失败静默不渲染（来源行是增强件，不能挡设定主面板）。
import { useCallback, useEffect, useState } from "react";
import { kbApi, type KbBinding, type KbLibrary } from "@/lib/kbApi";
import { toast } from "@/lib/toast";

export type KbStripConcept = "style" | "world";

const CONCEPTS_OF: Record<KbStripConcept, string[]> = {
  style: ["文风", "文笔"],
  world: ["世界设定"],
};

export default function KbSourceStrip({
  projectId,
  scope,
  onChanged,
}: {
  projectId: string;
  scope: KbStripConcept;
  /** 绑定变化后通知父级（重载设定内容） */
  onChanged?: () => void;
}) {
  const [binding, setBinding] = useState<KbBinding | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [libs, setLibs] = useState<KbLibrary[]>([]);
  const [busy, setBusy] = useState(false);
  const concepts = CONCEPTS_OF[scope];

  const load = useCallback(async () => {
    try {
      const rows = await kbApi.bindings(projectId);
      const mine = rows.find((r) => r.enabled && concepts.includes(r.concept));
      setBinding(mine ?? null);
    } catch {
      setBinding(null);
    }
  }, [projectId, concepts]);

  useEffect(() => {
    load();
  }, [load]);

  const openPicker = async () => {
    setPickerOpen(true);
    try {
      const all = await kbApi.libraries(undefined, projectId);
      setLibs(all.filter((l) => concepts.includes(l.concept) && l.enabled !== false));
    } catch {
      setLibs([]);
    }
  };

  const doBind = async (libraryId: string) => {
    setBusy(true);
    try {
      const r = await kbApi.bind(projectId, libraryId);
      toast.success(`已启用，落了 ${r.member_count} 条`);
      setPickerOpen(false);
      await load();
      onChanged?.();
    } catch (e: unknown) {
      toast.error((e as { message?: string }).message || "启用失败");
    } finally {
      setBusy(false);
    }
  };

  const doSync = async () => {
    /* v8 ignore start -- 防御分支：同步钮只在 binding 存在时渲染 */
    if (!binding) return;
    /* v8 ignore stop */
    setBusy(true);
    try {
      const r = await kbApi.syncBinding(binding.id);
      toast.success(`已同步 ${r.member_count} 条`);
      await load();
      onChanged?.();
    } catch (e: unknown) {
      toast.error((e as { message?: string }).message || "同步失败");
    } finally {
      setBusy(false);
    }
  };

  const doUnbind = async () => {
    /* v8 ignore start -- 防御分支：解除钮只在 binding 存在时渲染 */
    if (!binding) return;
    /* v8 ignore stop */
    setBusy(true);
    try {
      await kbApi.unbind(binding.id, projectId);
      toast.info("已解除绑定（本书已落的内容保留）");
      setBinding(null);
      onChanged?.();
    } catch (e: unknown) {
      toast.error((e as { message?: string }).message || "解除失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="mb-2 flex flex-wrap items-center gap-2 text-[12px]">
        {binding ? (
          <>
            <span className="text-[var(--muted)]">
              来自「{binding.library_name}」· {binding.member_count} 条
            </span>
            {binding.library_missing ? (
              <span className="text-[var(--faint)]">来源库已移除</span>
            ) : binding.added > 0 ? (
              <span className="text-[var(--accent)]">库有更新 {binding.added} 条</span>
            ) : null}
            {!binding.library_missing && binding.added > 0 && (
              <button
                onClick={doSync}
                disabled={busy}
                className="rounded-md border border-[var(--accent)] px-2 py-0.5 text-[11px] text-[var(--accent)] hover:bg-[var(--accent-soft)] disabled:opacity-50"
              >
                同步
              </button>
            )}
            <button
              onClick={doUnbind}
              disabled={busy}
              className="text-[11px] text-[var(--faint)] hover:text-[var(--muted)] disabled:opacity-50"
            >
              解除绑定
            </button>
          </>
        ) : (
          <button
            onClick={openPicker}
            className="text-[12px] text-[var(--accent)] hover:underline"
          >
            从知识库启用
          </button>
        )}
      </div>

      {pickerOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setPickerOpen(false)}>
          <div
            className="w-full max-w-md rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="mb-1 text-[15px] font-semibold text-[var(--fg)]">从知识库启用</h3>
            <p className="mb-3 text-[11.5px] text-[var(--muted)]">
              启用后库里适合整本书的知识会落进本面板；本书改过的内容不会被覆盖。
            </p>
            {!libs.length && <p className="py-6 text-center text-[12px] text-[var(--muted)]">还没有可启用的库——先去「写作工具 · 知识库」记几条。</p>}
            <div className="max-h-72 space-y-1.5 overflow-y-auto">
              {libs.map((l) => (
                <div key={l.id} className="flex items-center justify-between gap-2 rounded-lg border border-[var(--border)] px-3 py-2">
                  <div className="min-w-0">
                    <p className="truncate text-[13px] font-medium text-[var(--fg)]">
                      {l.name}
                      {l.bound_in_book ? <span className="ml-2 font-mono text-[9.5px] text-[var(--accent)]">本书已启用</span> : null}
                    </p>
                    <p className="mt-0.5 font-mono text-[10px] text-[var(--faint)]">
                      {l.concept} · {l.entry_count ?? 0} 条{(l.bound_novels ?? 0) > 0 ? ` · ${l.bound_novels} 本书在用` : ""}
                    </p>
                  </div>
                  <button
                    onClick={() => doBind(l.id)}
                    disabled={busy}
                    className="flex-none rounded-lg bg-[var(--accent)] px-3 py-1.5 text-[12px] font-medium text-[var(--on-accent)] hover:bg-[var(--accent-strong)] disabled:opacity-50"
                  >
                    启用
                  </button>
                </div>
              ))}
            </div>
            <div className="mt-3 flex justify-end">
              <button onClick={() => setPickerOpen(false)} className="rounded-lg border border-[var(--border)] px-4 py-1.5 text-[12px] text-[var(--muted)]">
                关闭
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
