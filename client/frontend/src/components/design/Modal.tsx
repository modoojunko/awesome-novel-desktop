/**
 * 设计系统弹窗（list.html 弹窗通用行为的 React 化）：
 * scrim + .modal/.mcard 进出场、Esc 关闭、Tab 焦点圈、关闭后还原焦点。
 * locked=true（提交中）时禁止关闭，与旧 CreateProjectModal 行为一致。
 */
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Ico, P } from "@/components/icons";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  /** 提交中锁定（Esc/遮罩/关闭钮全部失效） */
  locked?: boolean;
  /** mcard 宽度上限（默认 420，与原型一致） */
  width?: number;
  /** 书工作台弹窗版式（book.html：440 宽 + 纵向 flex 滚动体）。
   *  弹窗统一 portal 到 body（脱离 .wb 作用域）→ 工作台内弹窗需显式开启 */
  wbStyle?: boolean;
  /** 隐去头部 X 关闭钮（原型确认族口径：删除确认/归档本章无 X，仅取消/确认/Esc/遮罩） */
  hideClose?: boolean;
  /** 关闭后是否还原焦点（默认还原；关闭后将跳转到别处聚焦时传 false，防 200ms 还原抢走焦点） */
  restoreFocus?: boolean;
  children: ReactNode;
  /** 头部标题与关闭钮之间的扩展区（原型 mcard-head 的 text-btn 等） */
  headExtra?: ReactNode;
  /** 紧贴标题右侧的标记区（原型 ai-tag「PRO」等 margin-left:8px 形态） */
  afterTitle?: ReactNode;
  footer?: ReactNode;
}

export default function Modal({ open, onClose, title, locked, width = 420, wbStyle, hideClose, restoreFocus, children, headExtra, afterTitle, footer }: ModalProps) {
  const [shown, setShown] = useState(false); // 控制 .show 进出场
  const [render, setRender] = useState(false); // 200ms 退场后再卸载
  const lastFocus = useRef<Element | null>(null);
  const restoreRef = useRef(true);
  restoreRef.current = restoreFocus !== false;
  const rootRef = useRef<HTMLDivElement>(null);
  const labelId = useId();

  useEffect(() => {
    if (open) {
      lastFocus.current = document.activeElement;
      setRender(true);
      const raf = requestAnimationFrame(() => setShown(true));
      return () => cancelAnimationFrame(raf);
    }
    setShown(false);
    const t = setTimeout(() => {
      setRender(false);
      const el = lastFocus.current as HTMLElement | null;
      if (restoreRef.current && el && el.focus) el.focus();
    }, 200);
    return () => clearTimeout(t);
  }, [open]);

  useEffect(() => {
    if (!render) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (!locked) onClose();
        return;
      }
      if (e.key !== "Tab") return;
      const focusables = rootRef.current
        ? [...rootRef.current.querySelectorAll<HTMLElement>("button, a[href], input, select, textarea, [tabindex]:not([tabindex='-1'])")].filter(
            (el) => !(el as HTMLButtonElement).disabled && el.offsetParent !== null,
          )
        : [];
      if (!focusables.length) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [render, locked, onClose]);

  if (!render) return null;

  // 挂载到 body：弹窗是 viewport 级 fixed 遮罩（原型 mcard 挂 body 尾部），
  // 留在组件树内会被任意 transform 祖先（含 identity matrix）劫持 containing block
  return createPortal(
    <>
      <div className={"scrim" + (shown ? " show" : "")} onClick={() => !locked && onClose()} />
      <div
        ref={rootRef}
        className={"modal" + (shown ? " show" : "")}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelId}
        onClick={(e) => {
          if (e.target === e.currentTarget && !locked) onClose();
        }}
      >
        <div
          className={"mcard" + (wbStyle ? " wb-style" : "")}
          style={width !== 420 ? { width: `min(${width}px, 92vw)` } : undefined}
        >
          <div className="mcard-head">
            <span className="mh serif" id={labelId} role="heading" aria-level={2}>
              {title}
            </span>
            {afterTitle && <span style={{ marginLeft: 8 }}>{afterTitle}</span>}
            {headExtra && <span style={{ marginLeft: "auto" }}>{headExtra}</span>}
            {!hideClose && (
              <button
                className="icon-btn x"
                style={headExtra ? { marginLeft: 0 } : undefined}
                aria-label="关闭"
                onClick={() => !locked && onClose()}
                disabled={locked}
              >
                <Ico d={P.close} sw={1.8} />
              </button>
            )}
          </div>
          <div className="mcard-body">{children}</div>
          {footer && <div className="mcard-foot">{footer}</div>}
        </div>
      </div>
    </>,
    document.body,
  );
}
