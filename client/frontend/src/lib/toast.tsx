import { useEffect, useState } from "react";
import { Ico, P } from "@/components/icons";

type ToastType = "error" | "success" | "info";

interface ToastAction {
  label: string;
  onClick: () => void;
}

interface Toast {
  id: number;
  message: string;
  type: ToastType;
  action?: ToastAction;
}

let _toasts: Toast[] = [];
let _nextId = 1;
const _listeners = new Set<(toasts: Toast[]) => void>();
/** 全站基线：默认 3 秒自动消失（c-toast-dismiss；原 4 秒，2026-10-07 拍板） */
const AUTO_DISMISS_MS = 3000;

function notify() {
  for (const fn of _listeners) fn([..._toasts]);
}

function addToast(type: ToastType, msg: string, opts?: { action?: ToastAction }): number {
  const id = _nextId++;
  _toasts.push({ id, message: msg, type, action: opts?.action });
  notify();
  setTimeout(() => {
    _toasts = _toasts.filter((t) => t.id !== id);
    notify();
  }, AUTO_DISMISS_MS);
  return id;
}

export const toast = {
  error(msg: string, opts?: { action?: ToastAction }) {
    return addToast("error", msg, opts);
  },
  success(msg: string, opts?: { action?: ToastAction }) {
    return addToast("success", msg, opts);
  },
  info(msg: string, opts?: { action?: ToastAction }) {
    return addToast("info", msg, opts);
  },
  /** 主动收掉一条（「编辑即收」等提前收口语义） */
  dismiss(id: number) {
    _toasts = _toasts.filter((t) => t.id !== id);
    notify();
  },
};

export function useToasts() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  useEffect(() => {
    _listeners.add(setToasts);
    return () => { _listeners.delete(setToasts); };
  }, []);
  return toasts;
}

/** 设计系统 toast（list.html .toast-wrap/.toast）：底部居中深底胶囊。 */
export function Toaster() {
  const toasts = useToasts();
  if (toasts.length === 0) return null;

  return (
    <div className="toast-wrap" role="status" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={"toast" + (t.type === "error" ? " err" : "")}>
          {t.type === "success" ? (
            <Ico d={P.check} sw={2.2} />
          ) : t.type === "error" ? (
            <Ico d={P.close} sw={2.2} />
          ) : (
            <Ico d={P.other} sw={2.2} />
          )}
          <span>{t.message}</span>
          {t.action && (
            <button
              onClick={t.action.onClick}
              style={{ color: "inherit", fontWeight: 500, textDecoration: "underline", textUnderlineOffset: 2 }}
            >
              {t.action.label}
            </button>
          )}
          <button
            aria-label="关闭"
            onClick={() => toast.dismiss(t.id)}
            style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", width: 18, height: 18, marginLeft: 2, padding: 0, border: 0, background: "none", color: "inherit", opacity: 0.7, flex: "none", cursor: "pointer" }}
          >
            <Ico d={P.close} sw={2.2} />
          </button>
        </div>
      ))}
    </div>
  );
}
