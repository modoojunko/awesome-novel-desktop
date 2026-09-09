import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import AiSink from "@/components/novel/settings/AiSink";

// AI 结果区（genre-signup-redesign tasks 3.3 / D3）
describe("AiSink 结果区", () => {
  it("渲染操作名标签 + 内容", () => {
    render(
      <AiSink label="AI 体检 · 六段逐项">
        <span>缺失：本来的生活</span>
      </AiSink>,
    );
    expect(screen.getByText("AI 体检 · 六段逐项")).toBeTruthy();
    expect(screen.getByText("缺失：本来的生活")).toBeTruthy();
  });

  it("不传 onAdopt/onRetry 时不渲染操作按钮", () => {
    const { container } = render(<AiSink label="AI 体检">内容</AiSink>);
    expect(container.querySelector(".ans-act")).toBeNull();
  });

  it("采纳/重试按钮触发回调，采纳文案可定制", () => {
    const onAdopt = vi.fn();
    const onRetry = vi.fn();
    render(
      <AiSink label="补全缺失" adoptText="采纳 · 追加到简介" onAdopt={onAdopt} onRetry={onRetry}>
        候选
      </AiSink>,
    );
    fireEvent.click(screen.getByRole("button", { name: "采纳 · 追加到简介" }));
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(onAdopt).toHaveBeenCalledTimes(1);
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("容器类名为 .ai-sink（TintPanel 只读底，样式侧保证非 --surface）", () => {
    const { container } = render(<AiSink label="润色">对照</AiSink>);
    expect(container.querySelector(".ai-sink")).toBeTruthy();
    expect(container.querySelector(".aiz-head")).toBeTruthy();
  });
});
