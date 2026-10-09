/**
 * 出场角色胶囊的身份小标＋悬停身份卡（c-og-cast-role-hover）。
 *
 * 卡摘要由 ChapterWorkspace.refreshCharacterNames 聚合（角色卡正名与每个别名各一键
 * 指向同一张卡）。身份卡＝只读信息面，portal 到 body ＋ fixed 定位——`.og-pane` 是
 * overflow-y:auto 滚动容器，卡内绝对定位浮层会被裁切（`.mp-panel` 先例）；rect 视觉值
 * 经 `htmlZoom()` 折算回布局 px（大屏 `html { zoom }` 双重放大对策，panelAnchor 同口径）。
 * 空格不出行（别名/人设/档案/首次出场各格有值才渲染）。
 */

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { htmlZoom } from "@/lib/panelAnchor";
import { DOSSIER_FIELDS } from "@/lib/characterModel";

export interface CastInfo {
  /** 角色卡正名（名单里写别名时，卡上仍显正名） */
  name: string;
  role: string;
  aliases: string[];
  persona: string;
  dossier: Record<string, string>;
  firstChapter: number | null;
}

/** role → 小标修饰词（与关系图 .rg-node.role-* 同名族）；闭集外取值不出标 */
const ROLE_MOD: Record<string, string> = {
  主角: "role-protagonist",
  配角: "role-extra",
  反派: "role-villain",
  路人: "role-ghost",
};

export function RoleTag({ role }: { role: string }) {
  const mod = ROLE_MOD[role];
  if (!mod) return null;
  return <span className={`cast-role ${mod}`}>{role}</span>;
}

const OPEN_DELAY = 150;
const CLOSE_DELAY = 150;
const CARD_W = 300;
const CARD_MAX = 360;
const CARD_MIN = 140;

/** 基础档案行：性别·年龄·种族合一行（沿角色卡 UI 六行口径）＋其余已填格逐行 */
function dossierRows(dossier: Record<string, string>): [string, string][] {
  const get = (k: string) => String(dossier[k] ?? "").trim();
  const rows: [string, string][] = [];
  const gar = [get("gender"), get("age"), get("race")].filter(Boolean).join(" · ");
  if (gar) rows.push(["性别 · 年龄 · 种族", gar]);
  for (const f of DOSSIER_FIELDS) {
    if (f.k === "gender" || f.k === "age" || f.k === "race") continue;
    const v = get(f.k);
    if (v) rows.push([f.label, v]);
  }
  return rows;
}

export function CastHover({ info, children }: { info?: CastInfo; children: ReactNode }) {
  const wrapRef = useRef<HTMLSpanElement>(null);
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ left: number; top?: number; bottom?: number; maxHeight: number } | null>(null);
  const openT = useRef<number | null>(null);
  const closeT = useRef<number | null>(null);
  const hoverId = useId();

  // 开着时随滚动/resize 重锚（.mp-panel 同款）。effect 必须挂在提前 return 之前——
  // info 在两次渲染间可能翻转（角色清单异步到货/卡被删），钩序不稳 React 直接炸。
  useEffect(() => {
    if (!open) return;
    const re = () => anchor();
    window.addEventListener("scroll", re, true);
    window.addEventListener("resize", re);
    return () => {
      window.removeEventListener("scroll", re, true);
      window.removeEventListener("resize", re);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!info) return <>{children}</>;

  // 锚定：胶囊视觉矩形 → fixed 排版值（/zoom 折算＋横向视口夹取；竖向默认下方、
  // 下方放不下且上方更宽裕则翻转向上，卡自带限高整层滚动）
  const anchor = () => {
    const el = wrapRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const z = htmlZoom();
    const gapV = 6 * z;
    const wV = CARD_W * z;
    const leftV = Math.max(8, Math.min(r.left + r.width / 2 - wV / 2, window.innerWidth - wV - 8));
    const spaceBelow = window.innerHeight - r.bottom - gapV;
    const spaceAbove = r.top - gapV;
    const flip = spaceBelow < CARD_MIN * z && spaceAbove > spaceBelow;
    const room = Math.max(CARD_MIN, Math.min(CARD_MAX, (flip ? spaceAbove : spaceBelow) / z));
    setPos({
      left: leftV / z,
      ...(flip ? { bottom: (window.innerHeight - r.top) / z + 6 } : { top: (r.bottom + gapV) / z }),
      maxHeight: room,
    });
  };

  const cancelOpen = () => {
    if (openT.current != null) {
      window.clearTimeout(openT.current);
      openT.current = null;
    }
  };
  const cancelClose = () => {
    if (closeT.current != null) {
      window.clearTimeout(closeT.current);
      closeT.current = null;
    }
  };
  const enter = () => {
    cancelClose();
    if (openT.current != null || open) return;
    openT.current = window.setTimeout(() => {
      openT.current = null;
      anchor();
      setOpen(true);
    }, OPEN_DELAY);
  };
  const leave = () => {
    cancelOpen();
    if (!open) return;
    cancelClose();
    closeT.current = window.setTimeout(() => {
      closeT.current = null;
      setOpen(false);
    }, CLOSE_DELAY);
  };

  return (
    <span
      className="cast-wrap"
      ref={wrapRef}
      onMouseEnter={enter}
      onMouseLeave={leave}
      onFocus={() => {
        anchor();
        setOpen(true);
      }}
      onBlur={() => setOpen(false)}
      onKeyDown={(e) => {
        if (e.key === "Escape") setOpen(false);
      }}
      aria-describedby={open ? hoverId : undefined}
    >
      {children}
      {open &&
        pos &&
        createPortal(
          <div
            className="cast-hover"
            role="tooltip"
            id={hoverId}
            data-testid={`cast-hover-${info.name}`}
            style={{
              position: "fixed",
              top: pos.top,
              bottom: pos.bottom,
              left: pos.left,
              width: CARD_W,
              maxHeight: pos.maxHeight,
              zIndex: 70,
            }}
            onMouseEnter={cancelClose}
            onMouseLeave={leave}
          >
            <div className="chc-name">
              {info.name} <RoleTag role={info.role} />
            </div>
            {info.aliases.length > 0 && (
              <div className="chc-alias">别名：{info.aliases.join(" · ")}</div>
            )}
            {info.persona.trim() && (
              <div className="chc-persona">
                <span className="chc-k">一句话人设</span>
                {info.persona.trim()}
              </div>
            )}
            {dossierRows(info.dossier).map(([label, value]) => (
              <div className="chc-row" key={label}>
                <span className="chc-k">{label}</span>
                {value}
              </div>
            ))}
            {info.firstChapter != null && (
              <div className="chc-foot">
                第 {String(info.firstChapter).padStart(2, "0")} 章首次出场
              </div>
            )}
          </div>,
          document.body,
        )}
    </span>
  );
}
