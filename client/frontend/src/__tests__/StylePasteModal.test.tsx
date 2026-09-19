// StylePasteModal（c-style-paste-distill）——粘贴文风样本弹窗：
//   · 字数实时提示：空态默认提示 / 不足报还差多少 / 区间内可提交 / 超限劝挑代表性
//   · 区间外禁用「开始蒸馏」；区间内提交回调携带原文
//   · 关闭即清空：半截草稿不跨开合残留
//   · 超限 fast-path：原始长度超 4 倍上限时跳过精确计数（提示为超限方向）
import { beforeEach, describe, expect, it, vi } from "vitest";
import { configure, fireEvent, render, screen } from "@testing-library/react";
configure({ testIdAttribute: "data-od-id" });
import StylePasteModal from "@/components/novel/settings/StylePasteModal";

function openModal() {
  const onSubmit = vi.fn();
  const onClose = vi.fn();
  render(<StylePasteModal open onClose={onClose} onSubmit={onSubmit} />);
  return { onSubmit, onClose };
}

const type = (value: string) => fireEvent.change(screen.getByTestId("input-paste-sample"), { target: { value } });
const start = () => screen.getByTestId("btn-paste-start") as HTMLButtonElement;

beforeEach(() => {
  vi.clearAllMocks();
});

describe("字数提示与提交门", () => {
  it("空文本：默认提示，提交禁用", () => {
    openModal();
    expect(screen.getByTestId("paste-hint").textContent).toContain("需 3,000–10,000 字");
    expect(start().disabled).toBe(true);
  });

  it("不足 3,000：报还差多少字（warn），提交禁用", () => {
    openModal();
    type("雨".repeat(1000)); // 去空白后 1,000 字
    expect(screen.getByTestId("paste-hint").textContent).toContain("还差 2,000 字");
    expect(start().disabled).toBe(true);
  });

  it("区间内：提示可开始，提交回调携带原文", () => {
    const { onSubmit } = openModal();
    const sample = "他把账合上，像合上一口棺材。".repeat(240); // 3,360 字（无空白）
    type(sample);
    expect(screen.getByTestId("paste-hint").textContent).toContain("区间内");
    expect(start().disabled).toBe(false);
    fireEvent.click(start());
    expect(onSubmit).toHaveBeenCalledWith(sample);
  });

  it("超过 10,000：劝挑代表性段落，提交禁用", () => {
    openModal();
    type("字".repeat(10_001));
    expect(screen.getByTestId("paste-hint").textContent).toContain("挑最有代表性的几章");
    expect(start().disabled).toBe(true);
  });

  it("fast-path：原始长度远超上限时跳过精确计数，仍按超限禁提交", () => {
    openModal();
    type("字".repeat(40_001));
    expect(screen.getByTestId("paste-hint").textContent).toContain("挑最有代表性的几章");
    expect(start().disabled).toBe(true);
    // 计数不冒充精确值：如实标注原始长度（含空白）而非「不含空白」口径（评审 P3）
    expect(screen.getByText(/原始 40,001 字（超长，未剔除空白）/)).toBeTruthy();
  });
});

describe("关闭与取消", () => {
  it("取消触发 onClose；重开后草稿已清空（重新计数为 0）", () => {
    const onClose = vi.fn();
    const onSubmit = vi.fn();
    const view = render(<StylePasteModal open onClose={onClose} onSubmit={onSubmit} />);
    type("字".repeat(3200));
    expect(start().disabled).toBe(false);
    fireEvent.click(screen.getByTestId("btn-paste-cancel"));
    expect(onClose).toHaveBeenCalledTimes(1);
    // 父组件按 open=false→true 翻转：重开后草稿已清空
    view.rerender(<StylePasteModal open={false} onClose={onClose} onSubmit={onSubmit} />);
    view.rerender(<StylePasteModal open onClose={onClose} onSubmit={onSubmit} />);
    expect((screen.getByTestId("input-paste-sample") as HTMLTextAreaElement).value).toBe("");
    expect(start().disabled).toBe(true);
  });
});
