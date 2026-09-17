/** 「AI 检测」弹窗（右栏 AI 辅助·检测族）：卷纲/关系/伏笔冲突、文风一致性、
 *  标记偏离段落、建议补边——打开即跑一次检查，就地列出 finding；产物不落库。
 *  空结果＝「没有发现明显问题」；失败可就地重试。 */
import { useCallback, useEffect, useState } from "react";
import Modal from "@/components/design/Modal";
import { CHECK_TITLE, runAiCheck, type AiCheckKind, type AiFinding } from "@/lib/aiCheck";

export default function AiCheckModal({
  open,
  onClose,
  projectId,
  chapterRef,
  chapterLabel,
  kind,
}: {
  open: boolean;
  onClose: () => void;
  projectId: string;
  chapterRef: string;
  chapterLabel: string;
  /** 为 null 时不跑（关闭态） */
  kind: AiCheckKind | null;
}) {
  const [findings, setFindings] = useState<AiFinding[] | null>(null);
  const [error, setError] = useState("");
  const [runKey, setRunKey] = useState(0);

  const load = useCallback(async () => {
    if (!kind) return;
    setFindings(null);
    setError("");
    try {
      setFindings(await runAiCheck(projectId, chapterRef, kind));
    } catch (e) {
      setError((e as Error).message || "检查失败，请重试");
    }
  }, [projectId, chapterRef, kind]);

  useEffect(() => {
    if (!open || !kind) {
      setFindings(null);
      setError("");
      return;
    }
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, kind, runKey, load]);

  const title = kind ? CHECK_TITLE[kind] : "AI 检测";

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      wbStyle
      footer={
        <>
          <button className="btn btn-secondary" onClick={onClose}>
            关闭
          </button>
          <button
            className="btn btn-ghost"
            disabled={findings === null && !error}
            onClick={() => setRunKey((n) => n + 1)}
          >
            重新检查
          </button>
        </>
      }
    >
      <p className="ck-lead">
        《{chapterLabel}》· 依据本章章纲、正文与相应全书设定逐条核对，只报能指出依据的问题。
      </p>
      {findings === null && !error && <p className="ck-note">检查中……</p>}
      {error && <p className="ck-note err">{error}</p>}
      {findings !== null && findings.length === 0 && (
        <p className="ck-note ok" data-testid="ai-check-empty">
          没有发现明显问题。
        </p>
      )}
      {findings !== null && findings.length > 0 && (
        <ul className="ck-list" data-testid="ai-check-list">
          {findings.map((f, i) => (
            <li key={i}>
              <b>{f.title}</b>
              <span>{f.detail}</span>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  );
}
