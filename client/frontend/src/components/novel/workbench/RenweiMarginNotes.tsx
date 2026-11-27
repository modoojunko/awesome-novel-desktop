/** 人味边注覆盖层（c-renwei-check）：右侧问题简述，段落对齐，悬停看改法。
 *
 *  布局契约（设计说明 §3.2，用户两次拍板）：
 *  - 正文**锁死**：边注是绝对定位覆盖层，不占布局流，不改变正文宽度与位置；
 *  - 边注右贴边，宽度自适应剩余空白（放不下自动换行）——不挤跑正文、不产生横向滚动；
 *  - 左侧留给朱雀批注（zhuqueMarks 段尾章由 CSS 在 margin 态左移）；
 *  - 窄栏圆点锚＝**段尾实测**（末字后缘 Range 矩形）：圆点跟文字走——短行贴末字
 *    右侧、末行写满贴列缘；不钉层缘（11-22 判例：钉层缘＝脱离段落飘到滚动条旁），
 *    也不钉列缘（11-22 二次反馈：列缘＝行的最右侧，短行时离文字太远）。量测缺席
 *    （首帧/无布局环境）回落 book.css 的列缘 min() 兜底；
 *  - 窄栏交互：整盒不吃点击（只有 8px 点/详情卡接事件），逐字编辑 MutationObserver
 *    重锚——点末字右侧仍能落光标，圆点不等 0.7s 重扫；
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
/** 窄栏圆点盒高（8px 点＋上下 5px 内衬，与 book.css narrow 规则同值）——按末行行高中点对齐用。 */
const DOT_BOX_H = 18;
/** 窄栏圆点盒宽（与 book.css narrow 规则同值）——极窄列向左收时的溢出钳制用。 */
const DOT_BOX_W = 18;
/** 圆点盒左缘相对段尾的偏移（布局 px）：3px 盒内衬 → 点与末字视觉间距 6px。 */
const DOT_GAP_TO_BOX = 3;

/** 段落末字后缘（插入位）的实测矩形；无文本或无布局环境（测试/jsdom）返回 null 走 CSS 兜底。 */
function textEndRect(p: HTMLElement): DOMRect | null {
  try {
    // 取最后一个含可见字的**正文**文本节点折叠到末尾——不用段尾整体 collapse（段尾 <br>
    // 会把插入位落到下一行行首，right 变成行左缘，圆点会跳行）；尾部空白/零宽字符同理。
    // 段内装饰/控件（朱雀判定章 .zq-mark、ProseMirror widget、contenteditable=false）
    // 的文字不是正文：不跳过会量到左边距里的「AI/疑似」章，圆点被劫持到段落开头。
    const DECO = ".zq-mark, .ProseMirror-widget, [contenteditable='false']";
    const texts: Text[] = [];
    const walk = (n: Node) => {
      for (let c = n.firstChild; c; c = c.nextSibling) {
        if (c.nodeType === Node.ELEMENT_NODE && (c as Element).matches(DECO)) continue;
        if (c.nodeType === Node.TEXT_NODE && (c.textContent ?? "").length > 0) {
          texts.push(c as Text);
        } else {
          walk(c);
        }
      }
    };
    walk(p);
    const last = [...texts].reverse().find((t) => (t.data ?? "").trim().length > 0);
    if (!last) return null;
    const trail = /[\s\u200b]+$/.exec(last.data ?? "");
    const end = last.length - (trail ? trail[0].length : 0);
    const range = p.ownerDocument.createRange();
    range.setStart(last, end); // 新建 Range 折叠在 (document,0)，起止都要落到末字后
    range.setEnd(last, end);
    const r = range.getBoundingClientRect();
    if (!r || (r.width === 0 && r.height === 0 && r.right === 0 && r.top === 0)) return null;
    return r;
  } catch {
    return null;
  }
}

export default function RenweiMarginNotes({ editorEl, findings, settled, onDone, onSkip }: Props) {
  const layerRef = useRef<HTMLDivElement>(null);
  const [tops, setTops] = useState<Record<number, number>>({});
  // 窄栏圆点锚（段尾实测，布局 px，相对层）；量测缺席的组走 CSS 列缘兜底
  const [dots, setDots] = useState<Record<number, { top: number; left: number }>>({});
  // 窄栏态镜像（与层上的 rw-notes-narrow class 同源同步）：渲染期决定圆点用内联段尾锚
  const [narrow, setNarrow] = useState(false);

  const groups = useMemo(
    () => groupByPara(findings).filter((g) => !settled[g.para]),
    [findings, settled],
  );
  // RO 观察器长命（deps 只挂 editorEl），闭包里的 measure 会 stale——
  // groups 随 findings 换代，圆点锚按旧组重算会互相覆盖；统一走 ref 取当轮值。
  const groupsRef = useRef(groups);
  groupsRef.current = groups;

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
    const layerW = layerRect.width / zoom;
    const bodyRight = (editorEl.getBoundingClientRect().right - layerRect.left) / zoom;
    const notesLeft = bodyRight + NOTE_GAP;
    const roomRight = layerW - notesLeft;
    layer.style.setProperty("--rw-notes-left", `${Math.round(notesLeft)}px`);
    // 窄栏兜底（设计说明 §8 的最小窗宽/胶囊形态未拍板）：右侧放不下最小边注列时
    // 收成段侧圆点（不裁字、不压正文），悬停仍出详情卡。
    const isNarrow = roomRight < NOTE_MIN_W + NOTE_GAP;
    layer.classList.toggle("rw-notes-narrow", isNarrow);
    setNarrow(isNarrow);
    // 窄栏圆点锚＝段尾实测：圆点跟段落文字走（11-22 两次反馈判例，见文件头契约）。
    // 短行贴在末字右侧；末行写满时插位 x＝列缘，圆点贴列缘外侧——都是文字的真实位置。
    // 只在窄栏算（宽栏不渲染内联锚，白跑 Range 没必要）；极窄列再向左钳住盒宽，
    // 保证内联锚也满足「不溢出覆盖层」（CSS min() 只管量测缺席那一档）。
    if (isNarrow) {
      const maxLeft = Math.round(layerW - DOT_BOX_W - 2);
      const dotNext: Record<number, { top: number; left: number }> = {};
      groupsRef.current.forEach((g) => {
        const p = paras[g.para];
        if (!p) return;
        const r = textEndRect(p);
        if (!r) return;
        // collapsed Range 的 height：Chromium 给字形盒高，WebKit 可能给 0——0 时按段落
        // 行高补足，否则圆点会按「高 0」居中、偏上半个盒高（桌面端是 WebView2，
        // 这里只是防未来/测试浏览器退化）。
        const win = p.ownerDocument.defaultView;
        const lineH =
          r.height / zoom ||
          (win ? parseFloat(win.getComputedStyle(p).lineHeight) || 0 : 0);
        dotNext[g.para] = {
          top: Math.round((r.top - layerRect.top) / zoom + (lineH - DOT_BOX_H) / 2),
          left: Math.min(
            Math.round((r.right - layerRect.left) / zoom) + DOT_GAP_TO_BOX,
            maxLeft,
          ),
        };
      });
      setDots(dotNext);
    }
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
    const schedule = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(measure);
    };
    const ro = new ResizeObserver(schedule);
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

  // 逐字输入/删改不改变尺寸，RO 抓不到；圆点 x 依赖末行内容，不重算会停在
  // 旧文字末尾直到 0.7s 重扫回来（期间可能压在刚打的字上）。rAF 合并防抖。
  // 单独一条 effect：不依赖 ResizeObserver 是否存在（jsdom/旧环境也能装）。
  useEffect(() => {
    if (!editorEl || typeof MutationObserver === "undefined") return;
    let raf = 0;
    const mo = new MutationObserver(() => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(measure);
    });
    mo.observe(editorEl, { subtree: true, characterData: true, childList: true });
    return () => {
      cancelAnimationFrame(raf);
      mo.disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editorEl]);

  return (
    <div className="rw-marginlayer" ref={layerRef} aria-label="人味检测边注">
      {groups.map((g) => {
        // 窄栏圆点：内联段尾锚（跟随文字末字）；量测缺席→只给 top，left 落到
        // book.css 的 min() 列缘兜底。宽栏文字列：left 由 --rw-notes-left 驱动。
        const dot = narrow ? dots[g.para] : undefined;
        return (
          <div
            key={g.para}
            className={`rw-mnote ${g.sev}`}
            data-testid={`rw-note-${g.para}`}
            style={dot ? { top: dot.top, left: dot.left } : { top: tops[g.para] ?? 0 }}
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
        );
      })}
    </div>
  );
}
