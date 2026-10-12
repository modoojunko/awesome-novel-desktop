// 写作工具下拉（c-deconstruct-book 5.1）：顶栏二级入口——任务清单 / 拆书 / 扩展位。
// 交互纪律照 AcctMenu（portal+fixed 定位、点外/Esc 收起）；z-index 压 scrim(40) 之下。
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { useDeconstructTasks } from "../../hooks/useDeconstructTasks";

/** 徽标口径＝进行中＋排队中＋已完成未取结果（评审 P1-3） */
export function useToolsBadge(): number {
  const { data } = useDeconstructTasks();
  return data?.badge ?? 0;
}

export default function ToolsMenu() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const badge = useToolsBadge();

  useLayoutEffect(() => {
    if (!open) return;
    const t = triggerRef.current;
    const p = panelRef.current;
    if (!t || !p) return;
    const r = t.getBoundingClientRect();
    p.style.top = `${r.bottom + 4}px`;
    p.style.left = `${r.left}px`;
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (!panelRef.current?.contains(t) && !triggerRef.current?.contains(t)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const go = (path: string) => {
    setOpen(false);
    navigate(path);
  };

  return (
    <>
      <button
        ref={triggerRef}
        className={"tools-trigger" + (open ? " open" : "")}
        data-od-id="tools-trigger"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        写作工具
        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <path d="M6 9l6 6 6-6" />
        </svg>
        {badge > 0 && (
          <span className="tools-badge" data-od-id="tools-badge" aria-label={`${badge} 个任务`}>
            {badge}
          </span>
        )}
      </button>
      {open &&
        createPortal(
          <div
            ref={panelRef}
            className="tools-menu"
            data-od-id="tools-menu"
            role="menu"
            aria-label="写作工具"
          >
            <button className="tm-item" role="menuitem" data-od-id="menu-tasks" onClick={() => go("/tools")}>
              <b>任务清单</b>
              <span className="tm-desc">全部写作工具任务，按类型分标</span>
              {badge > 0 && <span className="tools-badge" style={{ marginLeft: "auto" }}>{badge}</span>}
            </button>
            <button className="tm-item" role="menuitem" data-od-id="menu-deconstruct" onClick={() => go("/tools/deconstruct/new")}>
              <b>拆书</b>
              <span className="tm-desc">把一本小说拆成设定、剧情、文风与技法</span>
            </button>
            <div className="tm-note">更多写作工具陆续上线</div>
          </div>,
          document.body,
        )}
    </>
  );
}
