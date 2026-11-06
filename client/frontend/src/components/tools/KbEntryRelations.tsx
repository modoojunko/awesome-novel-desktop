// 知识视图「关联知识」段（c-kb-relations-view，源自 c-kb-organize 批D 关系段）：
// 只读展示该知识的生效关系（AI 整理产出，存量行未经逐条采纳——提示语不说「你采纳的」），
// 对端知识可点跳；「这条不对」反馈保留。数据 /entries/{id}/relations?status=active。
import { useCallback, useEffect, useState } from "react";
import { kbApi } from "@/lib/kbApi";
import { relPhrase } from "@/lib/kbRelations";

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

interface Props {
  entryId: string;
  /** 传入时对端知识名可点跳（切 selected）；不传保持纯文本（向后兼容）。 */
  onOpenKnowledge?: (knowledgeId: string) => void;
}

export default function KbEntryRelations({ entryId, onOpenKnowledge }: Props) {
  const [rows, setRows] = useState<RelRow[] | null>(null);
  const [mergedInto, setMergedInto] = useState<{ surviving_id: string; title: string } | null>(null);
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    try {
      const r = await kbApi.organize.entryRelations(entryId, { status: "active" });
      // 防御过滤：服务端已只回 active，这里兜底锁「只读段不出现待确认/淘汰行」的口径
      setRows(r.relations.filter((x) => x.status === "active"));
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
      <p className="font-mono text-[10px] tracking-[0.14em] text-[var(--muted)]">关联知识 · 来自知识整理</p>
      {mergedInto && (
        <p className="mt-1 text-[12px] text-amber-500">
          这条知识已合并进「{mergedInto.title}」。
        </p>
      )}
      <ul className="mt-1 space-y-1">
        {rows.map((r) => (
          <li key={r.id} className="rounded-md border border-[var(--border)] px-2 py-1.5 text-[12px]">
            {onOpenKnowledge ? (
              <button
                onClick={() => onOpenKnowledge(r.other_id)}
                className="underline underline-offset-2 hover:text-[var(--accent)]"
              >
                {relPhrase(r.rel_type, r.direction === "out" ? "out" : "in", r.other_title)}
              </button>
            ) : (
              relPhrase(r.rel_type, r.direction === "out" ? "out" : "in", r.other_title)
            )}
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
