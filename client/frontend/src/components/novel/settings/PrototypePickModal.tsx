// 挑原型弹窗（c-kb-character）：列知识库「角色设定」条目，选中回传给建卡预填。
import { useEffect, useState } from "react";
import { kbApi, type KbEntry } from "@/lib/kbApi";

export default function PrototypePickModal({
  open,
  onClose,
  onPick,
}: {
  open: boolean;
  onClose: () => void;
  /** 选中一条原型（调用方负责建卡＋计数回写） */
  onPick: (entry: KbEntry) => void;
}) {
  const [entries, setEntries] = useState<KbEntry[] | null>(null);

  useEffect(() => {
    if (!open) return;
    let alive = true;
    kbApi
      .entries({ concept: "角色设定" })
      .then((r) => {
        if (alive) setEntries(r.entries);
      })
      .catch(() => {
        if (alive) setEntries([]);
      });
    return () => {
      alive = false;
    };
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="flex max-h-[70vh] w-full max-w-md flex-col rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-[15px] font-semibold text-[var(--fg)]">从知识库挑原型</h3>
        <p className="mt-1 text-[11.5px] text-[var(--muted)]">
          选一个原型，档案格和认知格会逐格复制进新卡，名字你自己起。
        </p>
        <div className="mt-3 min-h-0 flex-1 space-y-1.5 overflow-y-auto">
          {entries === null && <p className="py-6 text-center text-[12px] text-[var(--muted)]">加载中…</p>}
          {entries !== null && !entries.length && (
            <p className="py-6 text-center text-[12px] text-[var(--muted)]">
              还没有角色原型——去「写作工具 · 知识库」记一条「角色设定」，或从拆书收进来。
            </p>
          )}
          {entries !== null &&
            entries.map((e) => {
              const p = (e.payload ?? {}) as Record<string, unknown>;
              return (
                <button
                  key={e.id}
                  onClick={() => onPick(e)}
                  className="block w-full rounded-lg border border-[var(--border)] px-3 py-2 text-left hover:bg-[var(--fg-soft)]"
                >
                  <span className="block text-[13px] font-medium text-[var(--fg)]">
                    {e.title || String(p.archetype || e.instruction.slice(0, 20))}
                  </span>
                  <span className="mt-0.5 block truncate text-[11.5px] text-[var(--muted)]">
                    {e.instruction.slice(0, 60)}
                  </span>
                </button>
              );
            })}
        </div>
        <div className="mt-3 flex justify-end">
          <button onClick={onClose} className="rounded-lg border border-[var(--border)] px-4 py-1.5 text-[12px] text-[var(--muted)]">
            关闭
          </button>
        </div>
      </div>
    </div>
  );
}
