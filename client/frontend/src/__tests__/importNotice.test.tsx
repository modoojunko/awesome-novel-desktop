// 建书提示条（c-deconstruct-import-async 8.1）：有提示才出现，关掉即删键，失败不静默。
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const state = vi.hoisted(() => ({ get: vi.fn(), dismiss: vi.fn() }));
const toastState = vi.hoisted(() => ({ error: vi.fn(), info: vi.fn(), success: vi.fn() }));
vi.mock("@/lib/importNotice", () => ({
  getImportNotice: state.get,
  dismissImportNotice: state.dismiss,
}));
vi.mock("@/lib/toast", () => ({ toast: toastState }));

import ImportNotice from "@/components/novel/workbench/ImportNotice";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ImportNotice", () => {
  it("有提示时列出全部条目", async () => {
    state.get.mockResolvedValue({ items: ["势力 8 条超过上限 6，已截断", "关系 34 条合并为 26 条"] });
    render(<ImportNotice projectId="b1" />);
    await waitFor(() => expect(screen.getByText(/建书时的 2 条提示/)).toBeInTheDocument());
    expect(screen.getByText(/势力 8 条超过上限/)).toBeInTheDocument();
    expect(screen.getByText(/合并为 26 条/)).toBeInTheDocument();
    expect(state.get).toHaveBeenCalledWith("b1");
  });

  it("没有提示时不渲染（不占位）", async () => {
    state.get.mockResolvedValue({ items: [] });
    const { container } = render(<ImportNotice projectId="b1" />);
    await waitFor(() => expect(state.get).toHaveBeenCalled());
    expect(container.firstChild).toBeNull();
  });

  it("读失败当没有：不挡设定页", async () => {
    state.get.mockRejectedValue(new Error("boom"));
    const { container } = render(<ImportNotice projectId="b1" />);
    await waitFor(() => expect(state.get).toHaveBeenCalled());
    expect(container.firstChild).toBeNull();
  });

  it("「知道了」删除键并收起；失败 toast 不静默", async () => {
    state.get.mockResolvedValue({ items: ["提示一"] });
    state.dismiss.mockResolvedValue(undefined);
    render(<ImportNotice projectId="b1" />);
    await waitFor(() => expect(screen.getByText("知道了")).toBeInTheDocument());
    fireEvent.click(screen.getByText("知道了"));
    await waitFor(() => expect(state.dismiss).toHaveBeenCalledWith("b1"));
    await waitFor(() => expect(screen.queryByText("知道了")).not.toBeInTheDocument());

    cleanup();
    state.get.mockResolvedValue({ items: ["提示二"] });
    state.dismiss.mockRejectedValue(new Error("关闭失败"));
    render(<ImportNotice projectId="b2" />);
    await waitFor(() => expect(screen.getByText("知道了")).toBeInTheDocument());
    fireEvent.click(screen.getByText("知道了"));
    await waitFor(() => expect(toastState.error).toHaveBeenCalledWith("关闭失败"));
  });
});
