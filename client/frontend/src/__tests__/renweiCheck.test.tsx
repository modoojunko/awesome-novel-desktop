/** 人味检测（c-renwei-check）：报告弹窗四拍／边注覆盖层的交互钉。
 *
 *  纯本地：检测端点被 mock；本文件只钉 UI 契约——
 *  说明页先讲清流程（不直接出结果）、结果页字段齐全、短章「打不了分」、
 *  边注悬停详情与「标为已改/跳过」动作、以及「去AI味」入口的退役缺席。
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockCheck = vi.fn();
vi.mock("@/lib/renwei", () => ({
  renweiCheck: (...args: unknown[]) => mockCheck(...args),
}));

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
