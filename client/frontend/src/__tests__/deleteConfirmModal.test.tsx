// 删除确认弹窗（书架删书门禁）契约（c-del-confirm-space-tolerant）：
//   空白容错比对——半角/全角空格、首尾空白不拦（全角括号字形留白视觉似空格，
//   手敲极易带入），内容不符恒禁用＋Enter 无效；
//   原文「复制」钮——clipboard 写入＋「已复制」就地反馈、失败回退 execCommand、
//   再失败 toast err＋「重试」出口；确认/取消路径。
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import DeleteConfirmModal from "@/components/novel/DeleteConfirmModal";
import { toast } from "@/lib/toast";

vi.mock("@/lib/toast", () => ({ toast: { success: vi.fn(), info: vi.fn(), error: vi.fn() } }));

const LONG = "soushu2025.com@【恐怖】《13路末班车》【作者：老八零】[搜书吧]";
const onConfirm = vi.fn();
const onCancel = vi.fn();

const renderModal = () =>
  render(<DeleteConfirmModal title="小说" confirmText={LONG} onConfirm={onConfirm} onCancel={onCancel} />);

const confirmBtn = () => screen.getByRole("button", { name: "确认删除" }) as HTMLButtonElement;
const typeInput = (text: string) =>
  fireEvent.change(screen.getByRole("textbox"), { target: { value: text } });

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.useRealTimers();
  Reflect.deleteProperty(navigator, "clipboard");
  Reflect.deleteProperty(document, "execCommand");
});

describe("删除确认门禁（空白容错比对）", () => {
  it("精确原文点亮确认删除", () => {
    renderModal();
    expect(confirmBtn().disabled).toBe(true);
    typeInput(LONG);
    expect(confirmBtn().disabled).toBe(false);
  });

  it("视觉空隙处带半角空格仍点亮（2026-10-16 用户实报形态）", () => {
    renderModal();
    typeInput("soushu2025.com@ 【恐怖】《13路末班车》【作者：老八零】 [搜书吧]");
    expect(confirmBtn().disabled).toBe(false);
  });

  it("全角空格／首尾空白／连续空白均点亮", () => {
    renderModal();
    typeInput(`　${LONG.replace("【恐怖】", "【恐怖　】")}　`);
    expect(confirmBtn().disabled).toBe(false);
    typeInput(`  ${LONG}  `);
    expect(confirmBtn().disabled).toBe(false);
  });

  it("内容不符（缺字/错字）保持禁用，Enter 不触发", () => {
    renderModal();
    typeInput(LONG.slice(0, -1));
    expect(confirmBtn().disabled).toBe(true);
    typeInput(LONG.replace("末班车", "末班东"));
    expect(confirmBtn().disabled).toBe(true);
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter" });
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("输入可用时 Enter 触发确认", () => {
    renderModal();
    typeInput(`${LONG} `);
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter" });
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});

describe("复制书名", () => {
  it("点复制写入剪贴板＋就地「已复制」反馈，不动输入框、不放行门禁", async () => {
    vi.useFakeTimers();
    const writeText = vi.fn(async () => {});
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    renderModal();
    typeInput("还没输");
    fireEvent.click(screen.getByRole("button", { name: "复制书名" }));
    await act(async () => {});
    expect(writeText).toHaveBeenCalledWith(LONG);
    expect(screen.getByRole("button", { name: "复制书名" }).textContent).toBe("已复制");
    expect((screen.getByRole("textbox") as HTMLInputElement).value).toBe("还没输");
    expect(confirmBtn().disabled).toBe(true);
    act(() => {
      vi.advanceTimersByTime(1500);
    });
    expect(screen.getByRole("button", { name: "复制书名" }).textContent).toBe("复制");
  });

  it("clipboard 缺位回退 execCommand 成功", async () => {
    const exec = vi.fn(() => true);
    Object.defineProperty(document, "execCommand", { value: exec, configurable: true });
    renderModal();
    fireEvent.click(screen.getByRole("button", { name: "复制书名" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "复制书名" }).textContent).toBe("已复制"));
    expect(exec).toHaveBeenCalledWith("copy");
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("两路全失败弹 err＋「重试」出口，重试再次尝试", async () => {
    renderModal();
    fireEvent.click(screen.getByRole("button", { name: "复制书名" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
    const [msg, opts] = (toast.error as ReturnType<typeof vi.fn>).mock.calls[0] as [
      string,
      { action: { label: string; onClick: () => void } },
    ];
    expect(msg).toContain("复制失败");
    expect(opts.action.label).toBe("重试");
    // 重试仍失败不再叠加新出口（同一 toast 链路只留一次调用断言口径：出口可重复点击）
    opts.action.onClick();
    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(2));
  });
});

describe("取消与关闭", () => {
  it("取消回调触发且零副作用", () => {
    renderModal();
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
