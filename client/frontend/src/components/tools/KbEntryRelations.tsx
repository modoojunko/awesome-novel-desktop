// 条目详情关系段（c-kb-organize 批D）：该条目的生效/待确认关系＋「这条不对」反馈
// ＋merged 追溯入口。数据 /entries/{id}/relations。
import { useCallback, useEffect, useState } from "react";
import { kbApi } from "@/lib/kbApi";

interface RelRow {
  id: string;
  rel_type: string;
  status: string;
  direction: string;
  other_id: string;
  other_title: string;
  confidence: number;
  note: string;
  evidence: string;
}

export default function KbEntryRelations({ entryId }: { entryId: string }) {
  const [rows, setRows] = useState<RelRow[] | null>(null);
  const [mergedInto, setMergedInto] = useState<{ surviving_id: string; title: string } | null>(null);
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    try {
      const r = await kbApi.organize.entryRelations(entryId);
      setRows(r.relations);
      setMergedInto(r.merged_into);
    } catch {
      setRows([]);
    }
  }, [entryId]);

  useEffect(() => {
    void load();
  }, [load]);

  const feedback = async (relId: string) => {
    try {
      const r = await kbApi.organize.relationFeedback(relId);
      setNotice(r.message);
    } catch (e: unknown) {
      setNotice((e as { message?: string }).message || "反馈失败");
    }
  };

  if (rows === null) return null;
  if (rows.length === 0 && !mergedInto) return null;

  return (
    <div className="mt-3 border-t border-[var(--border)] pt-3" data-testid="kb-entry-relations">
      <p className="font-mono text-[10px] tracking-[0.14em] text-[var(--muted)]">知识关系（AI 整理产出）</p>
      {mergedInto && (
        <p className="mt-1 text-[12px] text-amber-500">
          这条知识已合并进「{mergedInto.title}」。
        </p>
      )}
      <ul className="mt-1 space-y-1">
        {rows.map((r) => (
          <li key={r.id} className="rounded-md border border-[var(--border)] px-2 py-1.5 text-[12px]">
            <span className="font-medium">{r.rel_type}</span>
            ：{r.direction === "out" ? r.other_title : `← ${r.other_title}`}
            {r.status === "pending" && <span className="ml-1 text-amber-500">（待确认）</span>}
            {r.note && <span className="text-[var(--muted)]">· {r.note}</span>}
            <button
              onClick={() => void feedback(r.id)}
              className="ml-2 text-[11px] text-[var(--muted)] underline"
            >
              这条不对
            </button>
          </li>
        ))}
      </ul>
      {notice && <p className="mt-1 text-[11px] text-[var(--accent)]">{notice}</p>}
    </div>
  );
}
