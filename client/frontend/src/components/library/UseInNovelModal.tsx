// 用到新书（c-character-library）：选目标书（现存书单选）＋换名换龄开关。
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "@/lib/toast";
import Modal from "@/components/design/Modal";
import { applyCardToBook, type ApplyResult, type LibraryCard } from "@/lib/libraryApi";
import { queryKeys } from "@/lib/queryKeys";

import { listNovelOptions, type NovelOption } from "@/lib/libraryApi";

export default function UseInNovelModal({
  card,
  onClose,
  onDone,
}: {
  card: LibraryCard | null;
  onClose: () => void;
  onDone?: (result: ApplyResult) => void;
}) {
  const qc = useQueryClient();
  const { data: novels } = useQuery({ queryKey: queryKeys.novels, queryFn: listNovelOptions, enabled: !!card });
  const [target, setTarget] = useState<string>("");
  const [rename, setRename] = useState(true);
  const [busy, setBusy] = useState(false);

  const list = novels || [];
  const effectiveTarget = target || (list[0]?.id ?? "");

  const submit = async () => {
    // 提交钮在无目标书/无卡时为 disabled——这里两者必存在（按钮态保证）
    setBusy(true);
    try {
      const result = await applyCardToBook(card!.id, effectiveTarget, rename);
      await qc.invalidateQueries({ queryKey: queryKeys.novels });
      const notes = [
        `已把「${card!.name}」用到《${list.find((n) => n.id === effectiveTarget)!.name}》`,
        result.renamed ? `改名「${result.name}」` : "",
        result.demoted ? "书里已有主角，这张落为配角" : "",
      ].filter(Boolean);
      toast.success(notes.join("——"));
      onDone?.(result);
      onClose();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "用到新书失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={!!card}
      onClose={onClose}
      title={card ? `把「${card.name}」用到新书` : "用到新书"}
      width={480}
      locked={busy}
      footer={
        <>
          <button className="btn btn-secondary" onClick={onClose} disabled={busy}>
            取消
          </button>
          <button
            className="btn btn-primary"
            onClick={() => void submit()}
            disabled={busy || !effectiveTarget}
            data-testid="lib-use-submit"
          >
            {busy ? "正在放进去…" : "用到这本书"}
          </button>
        </>
      }
    >
      <p className="alt" style={{ marginTop: 0 }}>
        设定照库里的原卡复制一份；换完名字和年龄，细节你再手动调。
      </p>
      <div className="field">
        <label>放进哪本书</label>
        {list.length === 0 ? (
          <div className="alt">书架还没有书——先去新建一本，再回来取用。</div>
        ) : (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {list.map((n) => (
              <button
                key={n.id}
                type="button"
                className={"btn btn-sm " + (effectiveTarget === n.id ? "btn-primary" : "btn-secondary")}
                onClick={() => setTarget(n.id)}
              >
                《{n.name}》
              </button>
            ))}
          </div>
        )}
      </div>
      <label style={{ display: "flex", gap: 8, marginTop: 12, fontSize: 13 }}>
        <input type="checkbox" checked={rename} onChange={(e) => setRename(e.target.checked)} />
        <span>
          换个新名字和年龄
          <span className="alt" style={{ display: "block", marginTop: 2 }}>
            库里的原卡不动；性格、说话方式、背景都照旧
          </span>
        </span>
      </label>
    </Modal>
  );
}
