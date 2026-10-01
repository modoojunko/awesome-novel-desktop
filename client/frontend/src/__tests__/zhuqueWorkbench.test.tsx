// 朱雀工作台三件套单测（c-zhuque-ai-detect）：
// - zhuqueMarks：Decorations 映射（非空段序、底色、行尾章、stale 变体、不进文档）
// - zhuqueHeadStrip：错误族出口（401/503→去配置、429/502→重试、400/422/404→关闭、stale）
import { describe, expect, it, vi } from "vitest";
import { Editor } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import ZhuqueHeadStrip from "@/components/novel/workbench/zhuqueHeadStrip";
import {
  ZhuqueMarks,
  applyZhuqueSegments,
  type ZhuqueSeg,
} from "@/components/novel/workbench/zhuqueMarks";

function mkEditor(content: string) {
  return new Editor({
    extensions: [ZhuqueMarks, StarterKit],
    content,
  });
}

const SEGS: ZhuqueSeg[] = [
  { paragraph_index: 0, label: 0, confidence: 0.04 },
  { paragraph_index: 1, label: 2, confidence: 0.62 },
  { paragraph_index: 2, label: 1, confidence: 0.86 },
];

describe("zhuqueMarks（Decorations 覆盖层·带化 c-zhuque-mark-band）", () => {
  it("按非空段序着色＋带尾章：人写段静默，疑似/AI 单段各自成带", () => {
    const ed = mkEditor("<p>人工段一。</p><p></p><p>疑似段二。</p><p>AI 段三。</p>");
    applyZhuqueSegments(ed, SEGS);
    const paras = ed.view.dom.querySelectorAll("p");
    expect(paras[0].classList.contains("zq-warn")).toBe(false); // 人写：静默（无底色无章）
    expect(paras[0].querySelector(".zq-mark")).toBeNull();
    expect(paras[1].classList.contains("zq-warn")).toBe(false); // 空段：跳过
    expect(paras[2].classList.contains("zq-warn")).toBe(true);
    expect(paras[3].classList.contains("zq-err")).toBe(true);
    const marks = ed.view.dom.querySelectorAll(".zq-mark");
    expect(marks.length).toBe(2); // 单段带＝带尾章；人写带零渲染
    expect(marks[0].textContent).toBe("疑似");
    expect(marks[1].textContent).toBe("AI");
    // 悬停：title 挂在着色段（判定词＋置信度），章本体不带百分数
    expect(paras[2].getAttribute("title")).toBe("疑似 62%");
    expect(paras[3].getAttribute("title")).toBe("AI 86%");
    expect(paras[0].getAttribute("title")).toBeNull();
    ed.destroy();
  });

  it("连续同判定聚合带尾单章：空段不打断聚合", () => {
    const ed = mkEditor(
      "<p>疑一。</p><p>疑二。</p><p></p><p>疑三。</p><p>疑四。</p><p>人工收尾。</p>",
    );
    applyZhuqueSegments(ed, [
      { paragraph_index: 0, label: 2, confidence: 0.6 },
      { paragraph_index: 1, label: 2, confidence: 0.6 },
      { paragraph_index: 2, label: 2, confidence: 0.6 },
      { paragraph_index: 3, label: 2, confidence: 0.6 },
      { paragraph_index: 4, label: 0, confidence: 0.1 },
    ]);
    const paras = ed.view.dom.querySelectorAll("p");
    // DOM 位与非空段序错位：paras[2] 是空段（跳过），非空段 #0-#3＝DOM 0/1/3/4（#3 是带尾）
    const nonTail = [paras[0], paras[1], paras[3]];
    for (const p of nonTail) {
      expect(p.classList.contains("zq-warn")).toBe(true);
      expect(p.querySelector(".zq-mark")).toBeNull(); // 带内非尾段无章
    }
    expect(paras[2].classList.contains("zq-warn")).toBe(false); // 空段不着色
    expect(paras[4].classList.contains("zq-warn")).toBe(true); // 带尾段有着色
    const marks = ed.view.dom.querySelectorAll(".zq-mark");
    expect(marks.length).toBe(1); // 带尾唯一章
    expect(marks[0].textContent).toBe("疑似");
    expect(paras[4].contains(marks[0])).toBe(true);
    expect(paras[5].classList.contains("zq-warn")).toBe(false); // 人写静默
    ed.destroy();
  });

  it("stale：段落无底色、带尾章灰变体、人写带零渲染", () => {
    const ed = mkEditor("<p>一。</p><p>二。</p><p>三。</p>");
    applyZhuqueSegments(ed, SEGS, true);
    expect(ed.view.dom.querySelectorAll("p.zq-warn, p.zq-err").length).toBe(0);
    const marks = ed.view.dom.querySelectorAll(".zq-mark.stale");
    expect(marks.length).toBe(2); // 疑似/AI 两带各一章（人写带静默）
    ed.destroy();
  });

  it("段数多于 segments：越界守卫不炸", () => {
    const ed = mkEditor("<p>一。</p><p>二。</p><p>三。</p><p>四。</p>");
    applyZhuqueSegments(ed, SEGS.slice(0, 1)); // 只有 1 条
    expect(ed.view.dom.querySelectorAll(".zq-mark").length).toBe(0); // 人写段静默
    ed.destroy();
  });

  it("装饰不进文档：导出/保存文本与未检测一致", () => {
    const ed = mkEditor("<p>一。</p><p>二。</p><p>三。</p>");
    const before = ed.getJSON();
    applyZhuqueSegments(ed, SEGS);
    const after = ed.getJSON();
    expect(JSON.stringify(after)).toBe(JSON.stringify(before));
    expect(ed.getText()).not.toContain("疑似");
    ed.destroy();
  });

  it("清除：segments=null 撤掉全部装饰", () => {
    const ed = mkEditor("<p>一。</p><p>二。</p><p>三。</p>");
    applyZhuqueSegments(ed, SEGS);
    applyZhuqueSegments(ed, null);
    expect(ed.view.dom.querySelectorAll(".zq-mark, p.zq-warn, p.zq-err").length).toBe(0);
    ed.destroy();
  });
});

describe("zhuqueHeadStrip（错误族出口）", () => {
  const rerun = vi.fn();
  const clear = vi.fn();

  it("结果态：三占比＋免责小字＋清除/重检", () => {
    const st = {
      status: "ok" as const,
      stale: false,
      proseHash: "h",
      result: {
        ok: true as const,
        prose_hash: "h",
        summary: { human_ratio: 0.71, suspect_ratio: 0.24, ai_ratio: 0.05, softmax_confidence: 0.18 },
        segments: [],
        usage_tokens: 1,
      },
    };
    render(<ZhuqueHeadStrip state={st} onRerun={rerun} onClear={clear} />);
    const strip = document.querySelector('[data-od-id="zhuque-head-strip"]')!;
    expect(strip.textContent).toContain("人工 71%");
    expect(strip.textContent).toContain("疑似 AI 24%");
    expect(strip.textContent).toContain("概率参考 · 非平台判定");
    fireEvent.click(screen.getByTestId("zq-clear"));
    expect(clear).toHaveBeenCalledOnce();
  });

  it("401/503→去配置；429/502→重试；422/404→关闭（不给必败重试）", () => {
    const mk = (status: number, reason?: string) => ({
      status: "error" as const,
      stale: false,
      error: { status, reason, message: "可读原因" },
    });
    const { rerender, unmount } = render(
      <ZhuqueHeadStrip state={mk(401, "zhuque_auth")} onRerun={rerun} onClear={clear} />,
    );
    expect(screen.getByText("去配置")).toBeInTheDocument();
    expect(screen.queryByText("重试")).toBeNull(); // Key 侧问题重试必败，不给「重试」
    rerender(<ZhuqueHeadStrip state={mk(503, "zhuque_not_configured")} onRerun={rerun} onClear={clear} />);
    expect(screen.getByText("去配置")).toBeInTheDocument();
    rerender(<ZhuqueHeadStrip state={mk(429, "zhuque_quota")} onRerun={rerun} onClear={clear} />);
    expect(screen.getByText("重试")).toBeInTheDocument();
    expect(screen.queryByText("去配置")).toBeNull();
    rerender(<ZhuqueHeadStrip state={mk(422, "prose_too_long")} onRerun={rerun} onClear={clear} />);
    expect(screen.getByText("关闭")).toBeInTheDocument();
    expect(screen.queryByText("重试")).toBeNull();
    rerender(<ZhuqueHeadStrip state={mk(404)} onRerun={rerun} onClear={clear} />);
    expect(screen.getByText("关闭")).toBeInTheDocument();
    unmount();
  });

  it("stale：置灰＋提示重检，重检入口替代清除对", () => {
    const st = {
      status: "ok" as const,
      stale: true,
      proseHash: "h",
      result: {
        ok: true as const,
        prose_hash: "h",
        summary: { human_ratio: 0.5, suspect_ratio: 0.3, ai_ratio: 0.2, softmax_confidence: 0.2 },
        segments: [],
        usage_tokens: 1,
      },
    };
    render(<ZhuqueHeadStrip state={st} onRerun={rerun} onClear={clear} />);
    expect(screen.getByText("正文已修改，结果可能过期")).toBeInTheDocument();
    expect(screen.getByTestId("zhuque-restale")).toBeInTheDocument();
    expect(screen.queryByTestId("zq-clear")).toBeNull();
  });

  it("检测中：转圈占位", () => {
    render(<ZhuqueHeadStrip state={{ status: "running", stale: false }} onRerun={rerun} onClear={clear} />);
    expect(screen.getByText("检测中…")).toBeInTheDocument();
    cleanup();
  });
});
