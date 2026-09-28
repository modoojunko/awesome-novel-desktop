// 去AI味/扩写对比预览（产品扩展——原型将两能力标「规划中」，无弹窗设计稿；
// 按 book.html 弹窗语言轻重皮：mcard + 双栏 serif 对比 + 设计按钮）。
import { useEffect } from "react";
import Modal from "@/components/design/Modal";

interface ContrastPreviewModalProps {
  open: boolean;
  onClose: () => void;
  mode: "polish" | "expand" | "compress";
  originalText: string;
  modifiedText: string | null;
  loading: boolean;
  error: string | null;
  onAccept: () => void;
  onReject: () => void;
  onRetry: () => void;
}

const paneStyle: React.CSSProperties = {
  flex: 1,
  padding: "14px 16px",
  border: "1px solid var(--border)",
  borderRadius: 10,
  background: "var(--surface)",
  minHeight: 200,
  maxHeight: "52vh",
  overflowY: "auto",
  fontSize: 14,
  lineHeight: 1.9,
  whiteSpace: "pre-wrap",
  fontFamily: "var(--font-display)",
};

const labelStyle: React.CSSProperties = {
  display: "block",
  fontFamily: "var(--font-mono)",
  fontSize: 11,
  letterSpacing: "0.08em",
  color: "var(--muted)",
  marginBottom: 8,
};

export default function ContrastPreviewModal({
  open,
  onClose,
  mode,
  originalText,
  modifiedText,
  loading,
  error,
  onAccept,
  onReject,
  onRetry,
}: ContrastPreviewModalProps) {
  const actionLabel =
    mode === "polish" ? "去AI味后" : mode === "expand" ? "扩写后" : "压缩后";
  const canAccept = !loading && !error && modifiedText !== null;

  // Enter 接受（Esc 由 Modal 统一处理）；焦点在按钮上时让按钮自身的 Enter 生效
  useEffect(() => {
    if (!open || !canAccept) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Enter") return;
      if (document.activeElement instanceof HTMLButtonElement) return;
      e.preventDefault();
      onAccept();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, canAccept, onAccept]);

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={mode === "polish" ? "去AI味" : mode === "expand" ? "场景扩写" : "压缩啰嗦段落"}
      wbStyle
      width={680}
      footer={
        <>
          <button className="btn btn-secondary" onClick={onReject} disabled={loading}>
            拒绝
          </button>
          <button className="btn btn-secondary" onClick={onRetry} disabled={loading}>
            换一个
          </button>
          <button className="btn btn-primary" onClick={onAccept} disabled={!canAccept}>
            接受
          </button>
        </>
      }
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 16,
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
          <span style={labelStyle}>原文</span>
          <div style={paneStyle}>
            {originalText || <span style={{ color: "var(--muted)" }}>无内容</span>}
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
          <span style={{ ...labelStyle, color: "var(--accent)" }}>{actionLabel}</span>
          <div style={{ ...paneStyle, borderLeft: "3px solid var(--accent)" }}>
            {loading ? (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  color: "var(--muted)",
                }}
              >
                <span
                  style={{
                    width: 6,
                    height: 6,
                    borderRadius: "50%",
                    background: "var(--accent)",
                    animation: "pulse 1s ease-in-out infinite",
                    flex: "none",
                  }}
                />
                生成中…
              </div>
            ) : error ? (
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ color: "var(--err)" }}>{error}</span>
                <button className="btn btn-ghost btn-sm" onClick={onRetry}>
                  重试
                </button>
              </div>
            ) : modifiedText ? (
              modifiedText
            ) : (
              <span style={{ color: "var(--muted)" }}>待生成</span>
            )}
          </div>
        </div>
      </div>
      <p style={{ margin: "10px 0 0", fontSize: 12.5, color: "var(--muted)" }}>
        接受后将替换原文选区；「换一个」按同一提示词重新生成。
      </p>
    </Modal>
  );
}
