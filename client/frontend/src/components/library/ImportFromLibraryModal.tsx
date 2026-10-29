// 书内「从角色库导入」（c-character-library）：列库内角色逐张选（v1 逐张），
// 换名换龄开关默认勾选；导入＝复制落卡（服务端 apply-to-book 同语义）。
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "@/lib/toast";
import { useQuery } from "@tanstack/react-query";
import { listNovelOptions } from "@/lib/libraryApi";
import Modal from "@/components/design/Modal";
import LibraryAvatar from "@/components/library/LibraryAvatar";
import { useCharacterLibrary } from "@/hooks/useCharacterLibrary";
import { applyCardToBook, type ApplyResult } from "@/lib/libraryApi";
import { queryKeys } from "@/lib/queryKeys";

interface ImportProps {
  open: boolean;
  novelId: string;
  novelName?: string;
  onClose: () => void;
  onDone?: (result: ApplyResult) => void;
}

/** 开面才挂 hooks（列表/书名的取数只在弹窗打开时发生；关闭即整树卸载，同 BatchAddModal 口径） */
export default function ImportFromLibraryModal({ open, ...props }: ImportProps) {
  if (!open) return null;
  return <ImportFromLibraryModalInner {...props} />;
}

function ImportFromLibraryModalInner({
  novelId,
  novelName = "",
  onClose,
  onDone,
}: Omit<ImportProps, "open">) {
  const qc = useQueryClient();
  const { data: novels } = useQuery({
    queryKey: queryKeys.novels,
    queryFn: listNovelOptions,
    enabled: !novelName,
  });
  const resolvedName = novelName || (novels || []).find((n) => n.id === novelId)?.name || "本书";
  const { data } = useCharacterLibrary(true);
  const [picked, setPicked] = useState<string>("");
  const [rename, setRename] = useState(true);
  const [busy, setBusy] = useState(false);
  const items = data?.items || [];
  const card = items.find((c) => c.id === picked) || null;

  const submit = async () => {
    // 提交钮在未选中卡时为 disabled——这里 card 必存在（非空断言由按钮态保证）
    setBusy(true);
    try {
      const result = await applyCardToBook(card!.id, novelId, rename);
      await qc.invalidateQueries({ queryKey: queryKeys.characterLibrary });
      await qc.invalidateQueries({ queryKey: queryKeys.novels });
      toast.success(
        `已把「${card!.name}」导入《${resolvedName}》` +
          (result.renamed ? `——落卡为「${result.name}」` : "") +
          (result.demoted ? "（书里已有主角，这张落为配角）" : ""),
      );
      onDone?.(result);
      onClose();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "导入失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      title="从角色库导入"
      width={560}
      locked={busy}
      headExtra={<span style={{ fontSize: 12, color: "var(--muted)" }}>《{resolvedName}》</span>}
      footer={
        <>
          <button className="btn btn-secondary" onClick={onClose} disabled={busy}>
            取消
          </button>
          <button
            className="btn btn-primary"
            onClick={() => void submit()}
            disabled={busy || !card}
            data-testid="lib-import-submit"
          >
            {busy ? "正在导入…" : "导入到本书"}
          </button>
        </>
      }
    >
      <p className="alt" style={{ marginTop: 0 }}>
        挑一个库里收着的角色放进这本书——设定照原卡复制一份，之后在书里怎么改都不影响库里的。
      </p>
      {items.length === 0 ? (
        <div className="alt">角色库还是空的——去「写作工具 → 角色库」先收几个角色。</div>
      ) : (
        <div
          style={{
            maxHeight: "40vh",
            overflowY: "auto",
            border: "1px solid var(--border)",
            borderRadius: 10,
          }}
        >
          {items.map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => setPicked(c.id)}
              style={{
                display: "flex",
                width: "100%",
                gap: 10,
                alignItems: "flex-start",
                padding: "10px 12px",
                border: "none",
                borderBottom: "1px solid var(--border)",
                background: picked === c.id ? "var(--accent-soft)" : "transparent",
                textAlign: "left",
                cursor: "pointer",
                font: "inherit",
              }}
            >
              <LibraryAvatar card={c} size="sm" />
              <span style={{ minWidth: 0, flex: 1 }}>
                <b style={{ fontFamily: "var(--font-display)", fontSize: 13.5 }}>{c.name || "未命名"}</b>{" "}
                <span style={{ fontSize: 11, color: "var(--muted)" }}>
                  {c.role}
                  {c.kind ? ` · ${c.kind}` : ""}
                </span>
                <span style={{ display: "block", fontSize: 12, color: "var(--muted)", marginTop: 2 }}>
                  {c.persona}——语言特征：{c.dossier?.speech || "未填"}
                </span>
              </span>
            </button>
          ))}
        </div>
      )}
      <label style={{ display: "flex", gap: 8, marginTop: 12, fontSize: 13 }}>
        <input type="checkbox" checked={rename} onChange={(e) => setRename(e.target.checked)} />
        <span>
          导入时换个新名字和年龄
          <span className="alt" style={{ display: "block", marginTop: 2 }}>
            避免和上一本的角色撞名字；导完可以在角色页里接着改
          </span>
        </span>
      </label>
    </Modal>
  );
}
