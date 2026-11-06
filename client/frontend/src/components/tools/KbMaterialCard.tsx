// 素材提示卡（c-kb-summarize）：知识视图抽屉内的素材态提示＋删除入口。
// 自包含 confirm（删除后不可恢复的口径写进弹窗文案）；busy 期间禁点。
interface Props {
  busy?: boolean;
  note?: string;
  onDelete: () => void;
}

export default function KbMaterialCard({ busy = false, note = "", onDelete }: Props) {
  return (
    <div className="mt-4 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-3" data-testid="kb-material-card">
      <p className="text-[11px] text-[var(--muted)]">
        这是素材——记录的原始写法案例，经「知识整理 → 总结知识点」提炼后成为知识点。
      </p>
      <button
        data-testid="kb-material-delete"
        disabled={busy}
        onClick={() => {
          if (window.confirm("删除这条素材？删除后不可恢复。")) {
            onDelete();
          }
        }}
        className="mt-2 rounded-lg border border-[var(--border)] px-3 py-1.5 text-[12px] text-[var(--muted)] hover:text-red-500 disabled:opacity-50"
      >
        删除素材
      </button>
      {note && <p className="mt-1 text-[11px] text-red-500">{note}</p>}
    </div>
  );
}
