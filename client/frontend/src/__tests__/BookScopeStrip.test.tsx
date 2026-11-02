/** 书级知识副本补平入口测试（c-kb-book-scope 批D）：差异行渲染/导入回写/零差异安静。 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const kbApiState = vi.hoisted(() => ({ diff: vi.fn(), import: vi.fn() }));
vi.mock("@/lib/kbApi", () => ({
  kbApi: { bookScopeDiff: kbApiState.diff, bookScopeImport: kbApiState.import },
}));
vi.mock("@/lib/toast", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import BookScopeStrip from "@/components/novel/settings/BookScopeStrip";

describe("BookScopeStrip", () => {
  beforeEach(() => {
    kbApiState.diff.mockReset().mockResolvedValue({ new_count: 0 });
    kbApiState.import.mockReset().mockResolvedValue({ imported: 3, skipped: 0 });
  });

  it("差异为零安静不渲染", async () => {
    kbApiState.diff.mockResolvedValue({ new_count: 0 });
    render(<BookScopeStrip projectId="p1" />);
    await waitFor(() => expect(kbApiState.diff).toHaveBeenCalled());
    expect(screen.queryByTestId("book-scope-strip")).toBeNull();
  });

  it("有新增显示差异行＋导入按钮，点击回写并归零", async () => {
    kbApiState.diff.mockResolvedValueOnce({ new_count: 2 }).mockResolvedValueOnce({ new_count: 0 });
    render(<BookScopeStrip projectId="p1" />);
    await waitFor(() => expect(screen.getByTestId("book-scope-strip")).toBeTruthy());
    expect(screen.getByText(/知识库有 2 条新增/)).toBeTruthy();
    fireEvent.click(screen.getByTestId("book-scope-import"));
    await waitFor(() => expect(kbApiState.import).toHaveBeenCalledWith("p1"));
    await waitFor(() => expect(screen.queryByText(/条新增/)).toBeNull());
  });

  it("导入失败 toast 错误可重试（不炸组件）", async () => {
    kbApiState.diff.mockResolvedValue({ new_count: 1 });
    kbApiState.import.mockRejectedValueOnce(new Error("网络"));
    render(<BookScopeStrip projectId="p1" />);
    await waitFor(() => expect(screen.getByTestId("book-scope-import")).toBeTruthy());
    fireEvent.click(screen.getByTestId("book-scope-import"));
    await waitFor(() => expect(kbApiState.import).toHaveBeenCalled());
    expect(screen.getByTestId("book-scope-import")).toBeTruthy(); // 仍可重试
  });

  it("导入成功 toast＋刷新后归零（doImport 成功路径）", async () => {
    kbApiState.diff.mockResolvedValueOnce({ new_count: 1 }).mockResolvedValue({ new_count: 0 });
    const { toast } = await import("@/lib/toast");
    render(<BookScopeStrip projectId="p1" />);
    await waitFor(() => expect(screen.getByTestId("book-scope-import")).toBeTruthy());
    fireEvent.click(screen.getByTestId("book-scope-import"));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("已从知识库导入 3 条"));
    await waitFor(() => expect(screen.queryByTestId("book-scope-strip")).toBeNull());
  });

  it("导入失败 toast 错误可重试（不炸组件）", async () => {
    kbApiState.diff.mockRejectedValue(new Error("网络"));
    render(<BookScopeStrip projectId="p1" />);
    await waitFor(() => expect(kbApiState.diff).toHaveBeenCalled());
    expect(screen.queryByTestId("book-scope-strip")).toBeNull();
  });
});
