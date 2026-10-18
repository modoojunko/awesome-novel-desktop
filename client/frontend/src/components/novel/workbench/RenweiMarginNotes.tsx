/** 人味边注覆盖层（c-renwei-check）：右侧问题简述，段落对齐，悬停看改法。
 *
 *  布局契约（设计说明 §3.2，用户两次拍板）：
 *  - 正文**锁死**：边注是绝对定位覆盖层，不占布局流，不改变正文宽度与位置；
 *  - 边注右贴边，宽度自适应剩余空白（放不下自动换行）——不挤跑正文、不产生横向滚动；
 *  - 左侧留给朱雀批注（zhuqueMarks 段尾章由 CSS 在 margin 态左移）；
 *  - 只指路不代笔：动作只有「标为已改（本地重扫）」「跳过」。
 */
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { htmlZoom } from "@/lib/panelAnchor";
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

/** 边注列与正文右缘的间距（布局 px，设计说明 §3.2：≥12px）。 */
const NOTE_GAP = 16;
/** 边注列最小宽度（布局 px，与 book.css 的 clamp 下限同值）。 */
const NOTE_MIN_W = 120;
/** 悬停详情卡宽度（布局 px，与 book.css .rw-mnote .dtl 同值）。 */
const DETAIL_W = 264;

export default function RenweiMarginNotes({ editorEl, findings, settled, onDone, onSkip }: Props) {
  const layerRef = useRef<HTMLDivElement>(null);
  const [tops, setTops] = useState<Record<number, number>>({});

  const groups = useMemo(
    () => groupByPara(findings).filter((g) => !settled[g.para]),
    [findings, settled],
  );

  const measure = () => {
    if (!editorEl || !layerRef.current) return;
    const layer = layerRef.current;
    const layerRect = layer.getBoundingClientRect();
    const paras = [...editorEl.querySelectorAll("p")].filter(
      (p) => (p.textContent ?? "").trim().length > 0,
    );
    // 层是 .editor-wrap 内的覆盖层：位置按段落/正文与层的相对量算，滚动时重算（rAF 节流）。
    // 大屏 large-screen.css 给 html 设 zoom（≥2000px 起，4K 封顶 1.75），
    // getBoundingClientRect 已是放大后的**视觉值**——直接当 CSS 值会被再放大一次：
    // 纵向越往下的段落漂得越多（2560 屏 1.28 倍时 500px 处漂 ~140px）。
    // 与 panelAnchor / CastHover 同口径：一律 /zoom 折算回布局 px。
    const zoom = htmlZoom();
    const next: Record<number, number> = {};
    paras.forEach((p, i) => {
      next[i] = Math.round((p.getBoundingClientRect().top - layerRect.top) / zoom);
    });
    setTops(next);
    // 横向自适应（窗口再宽也不飘到最右）：边注列左缘＝正文栏实测右缘＋固定间距，
    // 列宽由 CSS 吃掉右侧剩余空白（clamp 到 224 上限）。rail/字体档变化由下面的
    // ResizeObserver 兜底重算。
    const bodyRight = (editorEl.getBoundingClientRect().right - layerRect.left) / zoom;
    const notesLeft = bodyRight + NOTE_GAP;
    const roomRight = layerRect.width / zoom - notesLeft;
    layer.style.setProperty("--rw-notes-left", `${Math.round(notesLeft)}px`);
    // 窄栏兜底（设计说明 §8 的最小窗宽/胶囊形态未拍板）：右侧放不下最小边注列时
    // 收成段侧圆点（不裁字、不压正文），悬停仍出详情卡。
    layer.classList.toggle("rw-notes-narrow", roomRight < NOTE_MIN_W + NOTE_GAP);
    // 悬停详情卡默认自右向左展开（会压到正文最右一点）；右侧留白放得下就改成
    // 自左向右，完全不压正文。留白不够的窄窗口仍走原方向。
    layer.classList.toggle("rw-notes-dtl-right", roomRight >= DETAIL_W + 8);
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

  // 栏宽/字体档变化（不改窗口尺寸）也要重新锚定；scroll/resize 之外的最后一道兜底。
  // 正文自身宽 680 不变、只是位置随栏宽移动时，单观察正文不会触发——外层栏也要观察。
  useEffect(() => {
    if (!editorEl || typeof ResizeObserver === "undefined") return;
    let raf = 0;
    const ro = new ResizeObserver(() => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(measure);
    });
    ro.observe(editorEl);
    const wrap = editorEl.closest(".editor-wrap");
    if (wrap) ro.observe(wrap);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
    // measure 只读 editorEl/layerRef（均稳定），无需随 findings 重挂观察器
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editorEl]);

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
