/** 「提示词精修」弹窗（补全负向约束 / 精简提示词）：提案制——
 *  打开即按模式跑一次修订，结果只读展示；「采纳并保存」走既有提示词保存链写回，
 *  「放弃」不改动任何已存的提示词。 */
import { useCallback, useEffect, useState } from "react";
import Modal from "@/components/design/Modal";
import {
  REFINE_TITLE,
  refinePrompt,
  saveWritePrompt,
  type RefineMode,
} from "@/lib/aiCheck";
import { toast } from "@/lib/toast";

export default function RefinePromptModal({
  open,
  onClose,
  projectId,
  chapterRef,
  chapterLabel,
  mode,
  onAdopted,
}: {
  open: boolean;
  onClose: () => void;
  projectId: string;
  chapterRef: string;
  chapterLabel: string;
  mode: RefineMode | null;
  /** 采纳保存成功后通知（提示词页签据此刷新） */
  onAdopted?: () => void;
}) {
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    if (!mode) return;
    setLoading(true);
    setText("");
    setError("");
    try {
      setText(await refinePrompt(projectId, chapterRef, mode));
    } catch (e) {
      setError((e as Error).message || "修订失败，请重试");
    } finally {
      setLoading(false);
    }
  }, [projectId, chapterRef, mode]);

  useEffect(() => {
    if (!open || !mode) {
      setText("");
      setError("");
      return;
    }
    void load();
  }, [open, mode, load]);

  const handleAdopt = useCallback(async () => {
    setSaving(true);
    try {
      await saveWritePrompt(projectId, chapterRef, text);
      toast.success("已采纳并保存为本章提示词");
      onAdopted?.();
      onClose();
    } catch (e) {
      toast.error((e as Error).message || "保存失败，请重试");
    } finally {
      setSaving(false);
    }
  }, [projectId, chapterRef, text, onAdopted, onClose]);

  const title = mode ? REFINE_TITLE[mode] : "提示词精修";

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      wbStyle
      footer={
        <>
          <button className="btn btn-secondary" onClick={onClose}>
            放弃
          </button>
          <button
            className="btn btn-primary"
            data-testid="refine-adopt"
            disabled={loading || saving || !text}
            onClick={() => void handleAdopt()}
          >
            {saving ? "保存中…" : "采纳并保存"}
          </button>
        </>
      }
    >
      <p className="ck-lead">
        《{chapterLabel}》· 采纳后覆盖本章提示词（可随时在提示词页签里再改）。
      </p>
      {loading && <p className="ck-note">修订中……</p>}
      {error && <p className="ck-note err">{error}</p>}
      {!loading && !error && (
        <pre className="ck-pre" data-testid="refine-preview">
          {text}
        </pre>
      )}
    </Modal>
  );
}
