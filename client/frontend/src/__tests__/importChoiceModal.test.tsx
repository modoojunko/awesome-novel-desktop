// 题材知识导入二选一弹窗（c-kb-book-scope 弹窗二选一）契约：
//   两个选项文案 · 选导入跑 SSE 进度（逐概念组 → 落基线 → 完成）· 中途失败可重试 ·
//   选「我自己设定」落 declined 并关闭 · 导入中关闭＝abort。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";

const api = vi.hoisted(() => ({
  bookScopeImportStream: vi.fn(),
  bookScopeDecline: vi.fn(),
}));

vi.mock("@/lib/kbApi", async (orig) => {
  const actual = await orig<typeof import("@/lib/kbApi")>();
  return { ...actual, kbApi: { ...actual.kbApi, ...api } };
});

import ImportChoiceModal from "@/components/novel/settings/ImportChoiceModal";

type Cb = (ev: Record<string, unknown>) => void;

function mount(over: Record<string, unknown> = {}) {
  const props = {
    projectId: "n1",
    open: true,
    newCount: 3,
    genreLabel: "玄幻",
    onClose: vi.fn(),
    onImported: vi.fn(),
    onDeclined: vi.fn(),
    ...over,
  };
  render(<ImportChoiceModal {...props} />);
  return props;
}

/** 点「从知识库导入」并取出 SSE 回调，供用例按需推事件。 */
function startImport(): Cb {
  fireEvent.click(screen.getByTestId("kb-import-from-kb"));
  const cb = api.bookScopeImportStream.mock.calls.at(-1)?.[1] as Cb;
  expect(cb).toBeTypeOf("function");
  return cb;
}

beforeEach(() => {
  api.bookScopeImportStream.mockReset();
  api.bookScopeImportStream.mockImplementation(() => ({ abort: vi.fn() }));
  api.bookScopeDecline.mockReset();
  api.bookScopeDecline.mockResolvedValue({ declined: true });
});

afterEach(() => {
  cleanup();
});

describe("ImportChoiceModal", () => {
  it("二选一：两个选项＋条数文案", () => {
    mount();
    expect(screen.getByText(/知识库里已经有「玄幻」题材的默认设定（3 条/)).toBeTruthy();
    expect(screen.getByTestId("kb-import-from-kb").textContent).toContain("从知识库导入默认设定");
    expect(screen.getByTestId("kb-import-manual").textContent).toContain("我自己一项项设定");
  });

  it("选导入：逐概念组进度 → 落基线 → 完成回调", () => {
    const props = mount();
    const cb = startImport();
    expect(screen.getByTestId("kb-import-progress")).toBeTruthy();
    expect(screen.getByTestId("kb-import-phase").textContent).toContain("正在读取知识库");

    act(() => cb({ type: "phase", phase: "copy", total: 3 }));
    act(() => cb({ type: "phase", phase: "copy", concept: "手法", done: 2, total: 3 }));
    expect(screen.getByTestId("kb-import-phase").textContent).toContain("手法");
    expect(screen.getByTestId("kb-import-phase").textContent).toContain("2/3");
    expect(screen.getByTestId("kb-import-progress-bar").getAttribute("aria-valuenow")).toBe("59");

    act(() => cb({ type: "phase", phase: "baseline" }));
    expect(screen.getByTestId("kb-import-phase").textContent).toContain("基线设定");
    expect(screen.getByTestId("kb-import-progress-bar").getAttribute("aria-valuenow")).toBe("92");

    act(() => cb({ type: "done", imported: 3, skipped: 0 }));
    expect(screen.getByTestId("kb-import-phase").textContent).toContain("已导入 3 条知识");
    expect(screen.getByTestId("kb-import-progress-bar").getAttribute("aria-valuenow")).toBe("100");
    expect(props.onImported).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId("kb-import-close"));
    expect(props.onClose).toHaveBeenCalledTimes(1);
  });

  it("流内失败：显示错误并可重试；无 message 走兜底文案", () => {
    const props = mount();
    const cb = startImport();
    act(() => cb({ type: "error", message: "数据库忙" }));
    expect(screen.getByTestId("kb-import-error").textContent).toContain("数据库忙");

    fireEvent.click(screen.getByTestId("kb-import-retry"));
    expect(api.bookScopeImportStream).toHaveBeenCalledTimes(2);
    expect(screen.getByTestId("kb-import-progress")).toBeTruthy();

    // 无 message：兜底「导入失败，请重试」；错误态脚部「知道了」关闭
    const cb2 = api.bookScopeImportStream.mock.calls.at(-1)?.[1] as Cb;
    act(() => cb2({ type: "error" }));
    expect(screen.getByTestId("kb-import-error").textContent).toContain("导入失败，请重试");
    fireEvent.click(screen.getByTestId("kb-import-close"));
    expect(props.onClose).toHaveBeenCalledTimes(1);
  });

  it("无题材名用「本题材」；选项卡是唯一出口（脚部不重复）", async () => {
    const props = mount({ genreLabel: undefined });
    expect(screen.getByText(/知识库里已经有「本题材」题材的默认设定/)).toBeTruthy();
    // 二选一阶段没有脚部重复按钮：只有两张选项卡
    expect(screen.getAllByText("我自己一项项设定")).toHaveLength(1);

    fireEvent.click(screen.getByTestId("kb-import-manual"));
    expect(api.bookScopeDecline).toHaveBeenCalledWith("n1", true);
    await act(async () => {});
    expect(props.onDeclined).toHaveBeenCalledTimes(1);
    expect(props.onClose).toHaveBeenCalledTimes(1);
  });

  it("事件缺字段：total/done/imported 缺省不崩", () => {
    mount();
    const cb = startImport();
    act(() => cb({ type: "phase", phase: "copy", concept: "文风" }));
    // 无 total：仍按「读取中」文案（不显示 0/0 假进度）
    expect(screen.getByTestId("kb-import-phase").textContent).toContain("正在读取知识库");
    // 未知 phase：忽略（不崩）
    act(() => cb({ type: "phase", phase: "other" }));
    expect(screen.getByTestId("kb-import-progress")).toBeTruthy();
    act(() => cb({ type: "done" }));
    expect(screen.getByTestId("kb-import-phase").textContent).toContain("已导入 0 条知识");
  });

  it("选「我自己设定」：落 declined＋关闭＋回调", async () => {
    const props = mount();
    fireEvent.click(screen.getByTestId("kb-import-manual"));
    expect(api.bookScopeDecline).toHaveBeenCalledWith("n1", true);
    // await 微任务后回调落地
    await act(async () => {});
    expect(props.onDeclined).toHaveBeenCalledTimes(1);
    expect(props.onClose).toHaveBeenCalledTimes(1);
  });

  it("导入中关闭＝abort 在途流", () => {
    const abort = vi.fn();
    api.bookScopeImportStream.mockImplementation(() => ({ abort }));
    const props = mount();
    startImport();
    fireEvent.click(screen.getByText("取消"));
    expect(abort).toHaveBeenCalledTimes(1);
    expect(props.onClose).toHaveBeenCalledTimes(1);
  });
});
