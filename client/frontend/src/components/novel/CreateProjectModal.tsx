import { useEffect, useReducer, useRef, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "@/lib/toast";
import Modal from "@/components/design/Modal";
import { Ico, P } from "@/components/icons";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ModalAction = { type: "SET_NAME"; value: string } | { type: "DISMISS" };

interface ModalState {
  name: string;
}

interface CreateProjectModalProps {
  open: boolean;
  onClose: () => void;
  onCreated: (novelId: string) => void;
  /** 是否有效会员（免费层或套餐过期均为 false，与后端 require_project_limit 口径一致） */
  isMember?: boolean;
  /** Current novel count, for free-limit check */
  novelCount?: number;
}

// ---------------------------------------------------------------------------
// Reducer — 极简单字段：书名。
// 2026-09-10 用户裁定：建书只问书名（「类型」不再问——类型改由「设定 · 题材」
// 的六格承载，建书时问一次等于让作者在还没想清故事时先做分类）。
// ---------------------------------------------------------------------------

const INITIAL: ModalState = {
  name: "",
};

function reducer(state: ModalState, action: ModalAction): ModalState {
  switch (action.type) {
    case "SET_NAME":
      return { ...state, name: action.value };
    case "DISMISS":
      return { ...INITIAL };
    default:
      return state;
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function CreateProjectModal({
  open,
  onClose,
  onCreated,
  isMember,
  novelCount,
}: CreateProjectModalProps) {
  const [state, dispatch] = useReducer(reducer, INITIAL);
  const [submitting, setSubmitting] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Reset on open
  useEffect(() => {
    if (open) {
      dispatch({ type: "DISMISS" });
      setSubmitting(false);
    }
  }, [open]);

  // Focus the name input when the modal opens（原型 60ms 后聚焦）
  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => inputRef.current?.focus(), 60);
    return () => clearTimeout(t);
  }, [open]);

  async function handleCreate() {
    const name = state.name.trim();
    if (!name || submitting) return;
    setSubmitting(true);
    try {
      const novel = await api.createNovel({ name, source: "manual" });
      toast.success(`已创建《${novel.name}》，正在进入这本书…`);
      onCreated(novel.id);
    } catch {
      toast.error("创建失败");
    } finally {
      setSubmitting(false);
    }
  }

  // 口径=页面级 !isMember（过期会员也拦，与后端 require_project_limit 一致）
  const freeLimitReached =
    isMember === false && novelCount !== undefined && novelCount >= 1;
  const canCreate = state.name.trim().length > 0 && !freeLimitReached && !submitting;

  return (
    <Modal
      open={open}
      onClose={onClose}
      locked={submitting}
      title="新建作品"
      footer={
        <>
          <button className="btn btn-secondary" onClick={onClose} disabled={submitting}>
            取消
          </button>
          <button className="btn btn-primary" onClick={() => void handleCreate()} disabled={!canCreate}>
            {submitting ? "创建中…" : "创建，去写简介"}
          </button>
        </>
      }
    >
      <div className="field">
        <label htmlFor="bkTitle">书名</label>
        <input
          id="bkTitle"
          ref={inputRef}
          className="input"
          placeholder="先随手起一个，之后能改"
          maxLength={30}
          value={state.name}
          onChange={(e) => dispatch({ type: "SET_NAME", value: e.target.value })}
          onKeyDown={(e) => e.key === "Enter" && void handleCreate()}
          disabled={submitting}
        />
      </div>
      <p className="hint">
        创建后<b>直接进入这本书</b>。书名先随手起一个，之后随时能改；建好后先写简介、
        再定题材——两步都能跳过，以后随时回来补。
      </p>
      {freeLimitReached && (
        <p className="hint" style={{ marginTop: 10, background: "var(--warn-soft)" }}>
          免费用户限 1 本。升级套餐可创建更多小说。
        </p>
      )}
    </Modal>
  );
}
