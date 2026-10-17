import { useRef, useState, useCallback } from "react";
import { Ico, P } from "@/components/icons";
import { downloadTemplate } from "@/lib/api";
import { toast } from "@/lib/toast";

interface ImportUploadZoneProps {
  /** Called when user selects a file (via click or drop) */
  onFileSelected: (file: File) => void;
  /** Called when user cancels / goes back */
  onCancel: () => void;
}

export default function ImportUploadZone({
  onFileSelected,
  onCancel,
}: ImportUploadZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const handleFile = useCallback(
    (file: File) => {
      if (!file) return;
      const validTypes = [".md", ".txt", ".docx"];
      const ext = "." + file.name.split(".").pop()?.toLowerCase();
      if (!validTypes.includes(ext)) {
        toast.error(`不支持 ${ext} 格式，请选择 .md / .txt / .docx`);
        return;
      }
      // 文案承诺「≤10MB」必须真校验（spec-review #1）：超大文件解析会卡死
      if (file.size > 10 * 1024 * 1024) {
        toast.error("文件超过 10MB 上限，请拆分后分批导入");
        return;
      }
      onFileSelected(file);
    },
    [onFileSelected],
  );

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) handleFile(file);
      // Reset so the same file can be re-selected
      e.target.value = "";
    },
    [handleFile],
  );

  // ---- Drag / drop ----

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragging(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setDragging(false);
      const file = e.dataTransfer.files?.[0];
      if (file) handleFile(file);
    },
    [handleFile],
  );

  // ---- Template download ----

  const handleDownloadTemplate = useCallback(
    async (e: React.MouseEvent) => {
      e.preventDefault();
      try {
        const content = await downloadTemplate();
        const blob = new Blob([content], { type: "text/markdown" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "import-template.md";
        a.click();
        URL.revokeObjectURL(url);
      } catch {
        toast.error("模板下载失败");
      }
    },
    [],
  );

  // ---- Render ----

  return (
    <div className="space-y-4">
      <button className="btn btn-ghost btn-xs -ml-2" onClick={onCancel}>
        ← 返回选择
      </button>

      <h3 className="font-bold text-lg">导入已有稿子</h3>
      <p className="text-sm leading-relaxed" style={{ color: "var(--muted)" }}>
        支持 .txt、.md、.docx 格式，单文件不超过 10MB。
      </p>

      {/* Upload zone */}
      <div
        className="border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-colors"
        style={{
          borderColor: dragging ? "var(--accent)" : "var(--border)",
          background: dragging
            ? "var(--accent-5)"
            : undefined,
        }}
        onClick={() => inputRef.current?.click()}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter") inputRef.current?.click();
        }}
      >
        <div className="mb-3">
          <Ico
            d={P.upload}
            size={40}
            style={{ color: dragging ? "var(--accent)" : "var(--muted)" }}
          />
        </div>
        <p className="text-sm" style={{ color: "var(--muted)" }}>
          {dragging ? "松开鼠标以选择此文件" : "拖拽文件到此处，或点击选择文件"}
        </p>
        <p className="text-xs mt-1" style={{ color: "var(--muted)" }}>
          .md / .txt / .docx
        </p>
        <input
          ref={inputRef}
          type="file"
          accept=".md,.txt,.docx"
          className="hidden"
          onChange={handleInputChange}
        />
      </div>

      <div className="text-center">
        <a href="#" className="lnk text-xs" onClick={handleDownloadTemplate}>
          下载模板参考 →
        </a>
      </div>
    </div>
  );
}
