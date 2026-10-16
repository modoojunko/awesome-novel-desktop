import { useEffect, useRef, useState } from "react";
import Modal from "@/components/design/Modal";
import { toast } from "@/lib/toast";

/** 比对口径（c-del-confirm-space-tolerant）：双方剥除全部空白后逐字相等。
 *  全角括号字形留白视觉似空格而实无，手敲极易带入空白；空白不构成书名身份差异，
 *  内容仍须逐字对上。JS \s 覆盖半角/全角空格、NBSP、\uFEFF 等现实污染源。 */
const squashWs = (s: string) => s.replace(/\s+/g, "");

interface DeleteConfirmModalProps {
  title: string;
  confirmText: string;   // 用户需要敲的字
  description?: string;  // 覆盖默认删除说明（默认面向删除小说）
  /** 书工作台内弹窗版式（book.html mcard 默认 440 flex 纵滚；书架=list.html 420） */
  wbStyle?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** 删除确认（设计 .mcard 容器语言；确认按钮 btn-danger） */
export default function DeleteConfirmModal({ title, confirmText, description, wbStyle, onConfirm, onCancel }: DeleteConfirmModalProps) {
  const [input, setInput] = useState("");
  const [copied, setCopied] = useState(false);
  const copyTimer = useRef<number | null>(null);
  const canDelete = squashWs(input) === squashWs(confirmText);

  useEffect(() => () => {
    if (copyTimer.current) window.clearTimeout(copyTimer.current);
  }, []);

  const flashCopied = () => {
    setCopied(true);
    if (copyTimer.current) window.clearTimeout(copyTimer.current);
    copyTimer.current = window.setTimeout(() => setCopied(false), 1500);
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(confirmText);
      flashCopied();
      return;
    } catch {
      // 落 execCommand 老路（宿主 clipboard 缺位/权限收紧时）
    }
    const ta = document.createElement("textarea");
    ta.value = confirmText;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch {
      ok = false;
    }
    document.body.removeChild(ta);
    if (ok) {
      flashCopied();
    } else {
      toast.error("复制失败，可手动选择上方书名复制", {
        action: { label: "重试", onClick: () => void handleCopy() },
      });
    }
  };

  return (
    <Modal
      open={true}
      onClose={onCancel}
      title={`删除${title}`}
      width={380}
      wbStyle={wbStyle}
      footer={
        <>
          <button onClick={onCancel} className="btn btn-secondary">
            取消
          </button>
          <button onClick={onConfirm} disabled={!canDelete} className="btn btn-danger">
            确认删除
          </button>
        </>
      }
    >
      <p style={{ fontSize: 13.5, color: "var(--muted)", lineHeight: 1.7, margin: "0 0 10px" }}>
        {description ?? "此操作不可撤销。所有卷、章节和设定将被永久删除。"}
      </p>
      <p style={{ fontSize: 13.5, color: "var(--muted)", lineHeight: 1.7, margin: "0 0 10px" }}>
        请输入 <b style={{ color: "var(--fg)", fontWeight: 500 }}>{confirmText}</b>{" "}
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          aria-label="复制书名"
          data-testid="del-confirm-copy"
          onClick={() => void handleCopy()}
          style={{ verticalAlign: "middle", marginLeft: 4 }}
        >
          {copied ? "已复制" : "复制"}
        </button>{" "}
        确认删除：
      </p>
      <div className="field" style={{ marginBottom: 4 }}>
        <input
          type="text"
          className="input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={confirmText}
          onKeyDown={(e) => e.key === "Enter" && canDelete && onConfirm()}
          autoFocus
          aria-label={`输入${confirmText}确认删除`}
        />
      </div>
    </Modal>
  );
}
