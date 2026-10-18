/** 人味边注覆盖层（c-renwei-check）：右侧问题简述，段落对齐，悬停看改法。
 *
 *  布局契约（设计说明 §3.2，用户两次拍板）：
 *  - 正文**锁死**：边注是绝对定位覆盖层，不占布局流，不改变正文宽度与位置；
 *  - 边注右贴边，宽度自适应剩余空白（放不下自动换行）——不挤跑正文、不产生横向滚动；
 *  - 左侧留给朱雀批注（zhuqueMarks 段尾章由 CSS 在 margin 态左移）；
 *  - 只指路不代笔：动作只有「标为已改（本地重扫）」「跳过」。
 */
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { RenweiFinding } from "@/lib/renwei";

interface Props {
  /** 编辑正文宿主（.editor 元素）；段落位置按它测量 */
  editorEl: HTMLElement | null;
  findings: RenweiFinding[];
  /** 已处理段落（0-based）——不再渲染边注（消卡后） */
  settled: Record<number, "done" | "skip">;
  onDone: (para: number) => void;
  onSkip: (para: number) => void;
}

interface ParaGroup {
  para: number;
  sev: "err" | "warn";
  names: string;
  items: RenweiFinding[];
}

function groupByPara(findings: RenweiFinding[]): ParaGroup[] {
  const by = new Map<number, RenweiFinding[]>();
  findings.forEach((f) => {
    const list = by.get(f.para) ?? [];
    list.push(f);
    by.set(f.para, list);
  });
  return [...by.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([para, items]) => ({
      para,
      sev: items.some((f) => f.sev === "err") ? "err" : "warn",
      names: items.map((f) => f.rule).join(" · "),
      items,
    }));
}

export default function RenweiMarginNotes({ editorEl, findings, settled, onDone, onSkip }: Props) {
  const layerRef = useRef<HTMLDivElement>(null);
  const [tops, setTops] = useState<Record<number, number>>({});

  const groups = useMemo(
    () => groupByPara(findings).filter((g) => !settled[g.para]),
    [findings, settled],
  );

  const measure = () => {
    if (!editorEl || !layerRef.current) return;
    const paras = [...editorEl.querySelectorAll("p")].filter(
      (p) => (p.textContent ?? "").trim().length > 0,
    );
    // 层是 .editor-wrap 内不随内容滚动的覆盖层：位置按视口相对量算，
    // 滚动时重算（rAF 节流）——段落与边注始终对齐，且不参与布局。
    const base = layerRef.current.getBoundingClientRect().top;
    const next: Record<number, number> = {};
    paras.forEach((p, i) => {
      next[i] = Math.round(p.getBoundingClientRect().top - base);
    });
    setTops(next);
  };

  useLayoutEffect(measure, [editorEl, findings, settled]);

  useEffect(() => {
    const wrap = editorEl?.closest(".editor-wrap");
    let raf = 0;
    const onScrollOrResize = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(measure);
    };
    window.addEventListener("resize", onScrollOrResize);
    wrap?.addEventListener("scroll", onScrollOrResize, { passive: true });
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", onScrollOrResize);
      wrap?.removeEventListener("scroll", onScrollOrResize);
    };
  });

  return (
    <div className="rw-marginlayer" ref={layerRef} aria-label="人味检测边注">
      {groups.map((g) => (
        <div
          key={g.para}
          className={`rw-mnote ${g.sev}`}
          data-testid={`rw-note-${g.para}`}
          style={{ top: tops[g.para] ?? 0 }}
        >
          <span className="nt">
            <span className={`dot ${g.sev}`} />
            {g.sev === "err" ? "一票否决" : "提示"} · {g.names}
            {g.items.length > 1 ? ` ×${g.items.length}` : ""}
          </span>
          <div className="dtl">
            {g.items.map((f, i) => (
              <div className="d-r" key={`${f.rule_id}-${i}`}>
                <b>{f.rule}</b>
                {f.why} <b>改法　</b>
                {f.fix}
              </div>
            ))}
            <div className="d-acts">
              <button
                className="btn btn-secondary btn-sm"
                data-testid={`rw-done-${g.para}`}
                onClick={() => onDone(g.para)}
              >
                标为已改（本地重扫）
              </button>
              <button className="btn btn-ghost btn-sm" onClick={() => onSkip(g.para)}>
                跳过
              </button>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
