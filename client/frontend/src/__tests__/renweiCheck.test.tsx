/** 人味检测（c-renwei-check）：报告弹窗四拍／边注覆盖层的交互钉。
 *
 *  纯本地：检测端点被 mock；本文件只钉 UI 契约——
 *  说明页先讲清流程（不直接出结果）、结果页字段齐全、短章「打不了分」、
 *  边注悬停详情与「标为已改/跳过」动作、以及「去AI味」入口的退役缺席。
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockCheck = vi.fn();
vi.mock("@/lib/renwei", () => ({
  renweiCheck: (...args: unknown[]) => mockCheck(...args),
}));

// 大屏 zoom（large-screen.css）：边注 top 必须按 html 缩放折算回布局 px。
const mockHtmlZoom = vi.hoisted(() => ({ value: 1 }));
vi.mock("@/lib/panelAnchor", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/panelAnchor")>();
  return { ...actual, htmlZoom: () => mockHtmlZoom.value };
});

import RenweiCheckModal from "@/components/novel/workbench/RenweiCheckModal";
import RenweiMarginNotes from "@/components/novel/workbench/RenweiMarginNotes";
import type { RenweiFinding, RenweiReport } from "@/lib/renwei";

function report(over: Partial<RenweiReport> = {}): RenweiReport {
  return {
    ok: true,
    chars: 1600,
    paras: 20,
    score: { rate: 53.9, band: "偏机器", cls: "warn" },
    priorities: [{ k: "句号 / 千字", w: 3, z: 10.6, fix: "句号→逗号连缀并句" }],
    metrics: [
      { k: "句号 / 千字", v: "67.3", t: "≤ 24", h: "9.1 ~ 14.7", w: 3, ok: false },
      { k: "感官覆盖类数", v: "3 类", t: "≥ 4 类", h: "4 ~ 5 类", w: 0, ok: false },
    ],
    findings: [
      {
        rule_id: "dash",
        rule: "破折号",
        sev: "err",
        para: 1,
        before: "他按住她的手",
        hit: "——",
        after: "掌心一片凉。",
        why: "破折号是典型的机器味。",
        fix: "改逗号或句号断开。",
      },
    ],
    short_chapter: false,
    mtld_unconverged: false,
    ...over,
  };
}

describe("RenweiCheckModal（人味检测四拍）", () => {
  beforeEach(() => mockCheck.mockReset());

  const base = {
    open: true,
    projectId: "p1",
    chapterRef: "vol-1-ch-1",
    onClose: vi.fn(),
    onMarkToBody: vi.fn(),
    onClear: vi.fn(),
  };

  it("首开是说明页＋流程图，不自动检测", () => {
    render(<RenweiCheckModal {...base} />);
    expect(screen.getByText("这是做什么的")).toBeTruthy();
    // 流程图四步
    for (const t of ["验", "查", "改", "再验"]) expect(screen.getByText(t)).toBeTruthy();
    expect(screen.getByText(/改到你觉得可以为止/)).toBeTruthy();
    expect(screen.getByTestId("renwei-start")).toBeTruthy();
    expect(mockCheck).not.toHaveBeenCalled();
  });

  it("点「了解了，开始检测」→ 运行 → 结果页（人味率＋优先级＋定位清单＋对照表）", async () => {
    mockCheck.mockResolvedValue(report());
    render(<RenweiCheckModal {...base} />);
    fireEvent.click(screen.getByTestId("renwei-start"));
    await waitFor(() => expect(screen.getByTestId("rw-score")).toBeTruthy());
    expect(mockCheck).toHaveBeenCalledWith("p1", "vol-1-ch-1");
    expect(screen.getByText("53.9")).toBeTruthy();
    expect(screen.getByText("偏机器")).toBeTruthy();
    expect(screen.getByTestId("rw-priorities")).toBeTruthy();
    expect(screen.getByText("破折号")).toBeTruthy();
    expect(screen.getByText("段 2")).toBeTruthy(); // para 0-based 1 → 展示 2
    expect(screen.getByText("真人常见范围")).toBeTruthy();
    expect(screen.getByText("分量")).toBeTruthy();
  });

  it("短章：不给人味率（打不了分）但仍出定位清单", async () => {
    mockCheck.mockResolvedValue(
      report({ chars: 600, score: null, priorities: [], short_chapter: true }),
    );
    render(<RenweiCheckModal {...base} />);
    fireEvent.click(screen.getByTestId("renwei-start"));
    await waitFor(() => expect(screen.getByTestId("rw-score")).toBeTruthy());
    expect(screen.getByText("打不了分")).toBeTruthy();
    expect(screen.getByText(/先写完再打一次分/)).toBeTruthy();
    expect(screen.queryByTestId("rw-priorities")).toBeNull();
  });

  it("零发现：好稿形态文案；标记按钮禁用", async () => {
    mockCheck.mockResolvedValue(
      report({ findings: [], score: { rate: 81.6, band: "很像人", cls: "ok" } }),
    );
    render(<RenweiCheckModal {...base} />);
    fireEvent.click(screen.getByTestId("renwei-start"));
    await waitFor(() => expect(screen.getByText(/没有发现明显问题/)).toBeTruthy());
    expect(screen.getByText(/不代表朱雀也放行/)).toBeTruthy();
    expect((screen.getByTestId("renwei-mark") as HTMLButtonElement).disabled).toBe(true);
  });

  it("清除标注：结果页脚部可撤（清空正文标记并关窗）", async () => {
    const onClear = vi.fn();
    const onClose = vi.fn();
    mockCheck.mockResolvedValue(report());
    render(<RenweiCheckModal {...base} onClear={onClear} onClose={onClose} />);
    fireEvent.click(screen.getByTestId("renwei-start"));
    await waitFor(() => expect(screen.getByTestId("renwei-clear")).toBeTruthy());
    fireEvent.click(screen.getByTestId("renwei-clear"));
    expect(onClear).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("标记到正文：把报告交回父层（结果不自动上屏）", async () => {
    const onMarkToBody = vi.fn();
    mockCheck.mockResolvedValue(report());
    render(<RenweiCheckModal {...base} onMarkToBody={onMarkToBody} />);
    fireEvent.click(screen.getByTestId("renwei-start"));
    await waitFor(() => expect(screen.getByTestId("renwei-mark")).toBeTruthy());
    fireEvent.click(screen.getByTestId("renwei-mark"));
    expect(onMarkToBody).toHaveBeenCalledTimes(1);
    expect(onMarkToBody.mock.calls[0][0].findings.length).toBe(1);
  });

});

describe("RenweiMarginNotes（左右分边注）", () => {
  // 断言失败也收回原型桩：否则 430/520 的假 Range 会漏给后续用例
  afterEach(() => {
    vi.restoreAllMocks();
    mockHtmlZoom.value = 1;
  });

  const findings: RenweiFinding[] = [
    { rule_id: "dash", rule: "破折号", sev: "err", para: 1, before: "", hit: "——", after: "", why: "机器味", fix: "改逗号。" },
    { rule_id: "run_len", rule: "句长趋同连串", sev: "warn", para: 3, before: "", hit: "x", after: "", why: "太齐", fix: "拆一句。" },
  ];

  function makeEditor() {
    const wrap = document.createElement("div");
    wrap.className = "editor-wrap";
    const editor = document.createElement("div");
    editor.className = "editor";
    // 4 个非空段
    for (const t of ["第一段", "第二段", "第三段", "第四段"]) {
      const p = document.createElement("p");
      p.textContent = t;
      editor.appendChild(p);
    }
    wrap.appendChild(editor);
    document.body.appendChild(wrap);
    return editor;
  }

  it("按段渲染边注（一票否决/提示）且已处理段不渲染", () => {
    const editor = makeEditor();
    render(
      <RenweiMarginNotes editorEl={editor} findings={findings} settled={{}} onDone={vi.fn()} onSkip={vi.fn()} />,
    );
    expect(screen.getByTestId("rw-note-1")).toBeTruthy();
    expect(screen.getByTestId("rw-note-3")).toBeTruthy();
    expect(screen.getByText(/一票否决 · 破折号/)).toBeTruthy();
    expect(screen.getByText(/提示 · 句长趋同连串/)).toBeTruthy();
    document.body.removeChild(editor.parentElement as HTMLElement);
  });

  it("标为已改/跳过回调到父层（精准消卡由父层记录 settled）", () => {
    const editor = makeEditor();
    const onDone = vi.fn();
    const onSkip = vi.fn();
    render(
      <RenweiMarginNotes editorEl={editor} findings={findings} settled={{}} onDone={onDone} onSkip={onSkip} />,
    );
    fireEvent.click(screen.getByTestId("rw-done-1"));
    expect(onDone).toHaveBeenCalledWith(1);
    fireEvent.click(screen.getAllByText("跳过")[0]);
    expect(onSkip).toHaveBeenCalledWith(1);
    document.body.removeChild(editor.parentElement as HTMLElement);
  });

  it("大屏 zoom：边注 top/left 都按实测折算（贴正文右缘，不随段落下移越漂越远）", () => {
    const editor = makeEditor();
    const paraTops = [100, 500, 900, 1300];
    [...editor.querySelectorAll("p")].forEach((p, i) => {
      (p as HTMLElement).dataset.paraTop = String(paraTops[i]);
    });
    editor.dataset.bodyRight = "625"; // 正文栏右缘（视觉 px）
    const rect = (el: Element) => {
      const h = el as HTMLElement;
      const top = Number(h.dataset.paraTop ?? 0);
      // 边注层给一个 1200 的视觉宽（布局 960），其余元素用正文右缘
      const isLayer = h.classList.contains("rw-marginlayer");
      const right = isLayer ? 1200 : Number(h.dataset.bodyRight ?? 0);
      const width = isLayer ? 1200 : right;
      return { top, bottom: top, left: 0, right, width, height: 0, x: 0, y: 0 } as DOMRect;
    };
    const spy = vi
      .spyOn(Element.prototype, "getBoundingClientRect")
      .mockImplementation(function (this: Element) {
        return rect(this);
      });
    mockHtmlZoom.value = 1.25;
    render(
      <RenweiMarginNotes editorEl={editor} findings={findings} settled={{}} onDone={vi.fn()} onSkip={vi.fn()} />,
    );
    // 视觉 500 → 布局 400；视觉 1300 → 布局 1040（不是原值直接铺上去）
    expect(screen.getByTestId("rw-note-1").style.top).toBe("400px");
    expect(screen.getByTestId("rw-note-3").style.top).toBe("1040px");
    // 横向：正文右缘 625 视觉 → 500 布局 px ＋ 16px 间距（窗口再宽也不飘到最右）
    const layer = document.querySelector(".rw-marginlayer") as HTMLElement;
    expect(layer.style.getPropertyValue("--rw-notes-left")).toBe("516px");
    // 右侧留白 960−516＝444 ≥ 264+8：详情卡朝右展开，不压正文
    expect(layer.classList.contains("rw-notes-dtl-right")).toBe(true);
    spy.mockRestore();
    mockHtmlZoom.value = 1;
    document.body.removeChild(editor.parentElement as HTMLElement);
  });

  it("窄栏放不下最小边注列：收成段侧圆点兜底（不裁字/不压正文），详情卡不朝右", () => {
    const editor = makeEditor();
    editor.dataset.bodyRight = "625";
    const rect = (el: Element) => {
      const h = el as HTMLElement;
      const isLayer = h.classList.contains("rw-marginlayer");
      const right = isLayer ? 700 : Number(h.dataset.bodyRight ?? 0);
      const width = isLayer ? 700 : right;
      return { top: 0, bottom: 0, left: 0, right, width, height: 0, x: 0, y: 0 } as DOMRect;
    };
    const spy = vi
      .spyOn(Element.prototype, "getBoundingClientRect")
      .mockImplementation(function (this: Element) {
        return rect(this);
      });
    mockHtmlZoom.value = 1;
    render(
      <RenweiMarginNotes editorEl={editor} findings={findings} settled={{}} onDone={vi.fn()} onSkip={vi.fn()} />,
    );
    // 右侧只剩 700 − (625＋16)＝59px，小于最小列宽 120＋间距 16
    const layer = document.querySelector(".rw-marginlayer") as HTMLElement;
    expect(layer.classList.contains("rw-notes-narrow")).toBe(true);
    expect(layer.classList.contains("rw-notes-dtl-right")).toBe(false);
    spy.mockRestore();
    mockHtmlZoom.value = 1;
    document.body.removeChild(editor.parentElement as HTMLElement);
  });

  /** 层/正文的矩形桩：层宽 layerW，正文右缘 bodyRight（布局 px 由 zoom 折算） */
  function stubLayout(bodyRight: number, layerW: number, zoom = 1) {
    mockHtmlZoom.value = zoom;
    return vi
      .spyOn(Element.prototype, "getBoundingClientRect")
      .mockImplementation(function (this: Element) {
        const h = this as HTMLElement;
        const isLayer = h.classList.contains("rw-marginlayer");
        const right = isLayer ? layerW : bodyRight;
        const width = isLayer ? layerW : right;
        return { top: 0, bottom: 0, left: 0, right, width, height: 0, x: 0, y: 0 } as DOMRect;
      });
  }

  /** 段尾插入位桩（test-setup 默认给全零矩形，这里按用例覆写） */
  function stubTextEnd(rect: Partial<DOMRect> = {}) {
    return vi.spyOn(Range.prototype, "getBoundingClientRect").mockReturnValue({
      left: 0,
      right: 0,
      top: 0,
      bottom: 0,
      width: 0,
      height: 0,
      x: 0,
      y: 0,
      ...rect,
    } as DOMRect);
  }

  it("窄栏圆点锚＝段尾实测：left/top 跟末字后缘走，不钉列缘/层缘（11-22 判例）", () => {
    const editor = makeEditor();
    stubLayout(625, 700);
    // 段尾插入位（末字后缘）视觉 right=430 / top=520 / 行盒高 34（zoom=1）
    stubTextEnd({ left: 430, right: 430, top: 520, bottom: 554, height: 34, x: 430, y: 520 });
    render(
      <RenweiMarginNotes editorEl={editor} findings={findings} settled={{}} onDone={vi.fn()} onSkip={vi.fn()} />,
    );
    const layer = document.querySelector(".rw-marginlayer") as HTMLElement;
    expect(layer.classList.contains("rw-notes-narrow")).toBe(true);
    // left ＝ 430（末字后缘）＋ 3（盒内衬）→ 点与末字视觉间距 6px
    expect((screen.getByTestId("rw-note-1") as HTMLElement).style.left).toBe("433px");
    // top ＝ 520 ＋ (34−18)/2 → 圆点盒按末行行高中点对齐
    expect((screen.getByTestId("rw-note-1") as HTMLElement).style.top).toBe("528px");
    document.body.removeChild(editor.parentElement as HTMLElement);
  });

  it("大屏 zoom：圆点锚 left/top 同样折算回布局 px（1.25 倍下 433/528 → 347/421）", () => {
    const editor = makeEditor();
    stubLayout(625, 700, 1.25);
    stubTextEnd({ left: 430, right: 430, top: 520, bottom: 554, height: 34, x: 430, y: 520 });
    render(
      <RenweiMarginNotes editorEl={editor} findings={findings} settled={{}} onDone={vi.fn()} onSkip={vi.fn()} />,
    );
    const note = screen.getByTestId("rw-note-1") as HTMLElement;
    // 层 700/1.25=560、正文右缘 625/1.25=500 → 仍是窄栏
    expect((document.querySelector(".rw-marginlayer") as HTMLElement).classList.contains("rw-notes-narrow")).toBe(true);
    expect(note.style.left).toBe("347px"); // 430/1.25 ＋ 3
    expect(note.style.top).toBe("421px"); // 520/1.25 ＋ (34/1.25−18)/2 ＝ 420.6
    document.body.removeChild(editor.parentElement as HTMLElement);
  });

  it("极窄列：内联锚也钳在覆盖层内（盒宽 18＋2px 内缩）", () => {
    const editor = makeEditor();
    stubLayout(625, 700);
    // 段尾贴到层右缘：left 本应 703，钳到 700−18−2＝680
    stubTextEnd({ left: 700, right: 700, top: 520, bottom: 554, height: 34, x: 700, y: 520 });
    render(
      <RenweiMarginNotes editorEl={editor} findings={findings} settled={{}} onDone={vi.fn()} onSkip={vi.fn()} />,
    );
    expect((screen.getByTestId("rw-note-1") as HTMLElement).style.left).toBe("680px");
    document.body.removeChild(editor.parentElement as HTMLElement);
  });

  it("宽栏文字列：即使量到段尾也不写内联 left（仍走 --rw-notes-left）", () => {
    const editor = makeEditor();
    stubLayout(900, 1200); // 1200 − (900＋16) = 284 ≥ 136 → 宽栏
    stubTextEnd({ left: 430, right: 430, top: 520, bottom: 554, height: 34, x: 430, y: 520 });
    render(
      <RenweiMarginNotes editorEl={editor} findings={findings} settled={{}} onDone={vi.fn()} onSkip={vi.fn()} />,
    );
    const layer = document.querySelector(".rw-marginlayer") as HTMLElement;
    expect(layer.classList.contains("rw-notes-narrow")).toBe(false);
    const note = screen.getByTestId("rw-note-1") as HTMLElement;
    expect(note.style.left).toBe("");
    expect(note.style.top).toBe("0px");
    document.body.removeChild(editor.parentElement as HTMLElement);
  });

  it("窄→宽切换：上一档的段尾锚不跟进文字列（stale dots 由 narrow 门挡住）", async () => {
    const editor = makeEditor();
    stubLayout(625, 700);
    stubTextEnd({ left: 430, right: 430, top: 520, bottom: 554, height: 34, x: 430, y: 520 });
    render(
      <RenweiMarginNotes editorEl={editor} findings={findings} settled={{}} onDone={vi.fn()} onSkip={vi.fn()} />,
    );
    const layer = document.querySelector(".rw-marginlayer") as HTMLElement;
    const note = screen.getByTestId("rw-note-1") as HTMLElement;
    expect(note.style.left).toBe("433px");
    // 窗口拉宽：ResizeObserver 之外的 resize 监听经 rAF 重算 → 宽栏
    stubLayout(900, 1200);
    window.dispatchEvent(new Event("resize"));
    await waitFor(() => expect(layer.classList.contains("rw-notes-narrow")).toBe(false));
    // dots 仍是上一档的 433，但窄栏门必须把它挡在文字列之外
    expect(note.style.left).toBe("");
    document.body.removeChild(editor.parentElement as HTMLElement);
  });

  it("量测缺席（Range 矩形全零）：窄栏圆点不给内联 left，回落 CSS 列缘兜底", () => {
    const editor = makeEditor();
    stubLayout(625, 700);
    stubTextEnd(); // 全零 → textEndRect 返回 null
    render(
      <RenweiMarginNotes editorEl={editor} findings={findings} settled={{}} onDone={vi.fn()} onSkip={vi.fn()} />,
    );
    const layer = document.querySelector(".rw-marginlayer") as HTMLElement;
    expect(layer.classList.contains("rw-notes-narrow")).toBe(true);
    // 不给内联 left → book.css 窄栏 min(--rw-notes-left, 100%−20px) 兜底
    expect((screen.getByTestId("rw-note-1") as HTMLElement).style.left).toBe("");
    document.body.removeChild(editor.parentElement as HTMLElement);
  });

  it("段尾带空格/零宽：插入位跳过尾部空白（落回末字后，不折到下一行）", () => {
    const editor = makeEditor();
    const ps = editor.querySelectorAll("p");
    ps[1].textContent = "第二段  \u200b"; // 尾部 2 空格＋零宽
    stubLayout(625, 700);
    stubTextEnd({ left: 200, right: 200, top: 520, bottom: 554, height: 34, x: 200, y: 520 });
    const setStart = vi.spyOn(Range.prototype, "setStart");
    render(
      <RenweiMarginNotes editorEl={editor} findings={findings} settled={{}} onDone={vi.fn()} onSkip={vi.fn()} />,
    );
    const call = setStart.mock.calls.find((c) => (c[0] as Text).data === "第二段  \u200b");
    expect(call?.[1]).toBe(3); // 「第二段」3 字后＝末字后；不取 6（含空白）
    document.body.removeChild(editor.parentElement as HTMLElement);
  });

  it("窄栏兜底 CSS：列缘 min() ＋ 只有 8px 圆点吃事件（防 right:2px 回潮/点击抢光标）", () => {
    const css = readFileSync(path.resolve(process.cwd(), "src/design/book.css"), "utf8");
    const flat = (re: RegExp) => (re.exec(css)?.[1] ?? "").replace(/\s+/g, " ");
    const box = flat(/\.rw-marginlayer\.rw-notes-narrow \.rw-mnote\s*\{([^}]*)\}/);
    expect(box).toContain("left: min(var(--rw-notes-left), calc(100% - 20px));");
    expect(box).toContain("pointer-events: none;");
    expect(box).not.toContain("right: 2px");
    expect(flat(/\.rw-marginlayer\.rw-notes-narrow \.rw-mnote \.nt \.dot\s*\{([^}]*)\}/)).toContain(
      "pointer-events: auto;",
    );
    expect(flat(/\.rw-marginlayer\.rw-notes-narrow \.rw-mnote \.dtl\s*\{([^}]*)\}/)).toContain(
      "pointer-events: auto;",
    );
  });

  it("已处理的段不再渲染边注", () => {
    const editor = makeEditor();
    render(
      <RenweiMarginNotes
        editorEl={editor}
        findings={findings}
        settled={{ 1: "done" }}
        onDone={vi.fn()}
        onSkip={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("rw-note-1")).toBeNull();
    expect(screen.getByTestId("rw-note-3")).toBeTruthy();
    document.body.removeChild(editor.parentElement as HTMLElement);
  });
});
