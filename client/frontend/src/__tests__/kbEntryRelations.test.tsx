// 条目关系段测试（c-kb-organize 批D）：清单渲染/merged 追溯/这条不对反馈/空态隐藏。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = vi.hoisted(() => ({
  entryRelations: vi.fn(),
  relationFeedback: vi.fn(),
}));

vi.mock("@/lib/kbApi", async (orig) => {
  const actual = await orig<typeof import("@/lib/kbApi")>();
  return { ...actual, kbApi: { ...actual.kbApi, organize: api } };
});

import KbEntryRelations from "@/components/tools/KbEntryRelations";

const RELS = {
  relations: [
    { id: "rel-1", rel_type: "applies_to", status: "active", direction: "out",
      other_id: "w1", other_title: "短句文风", confidence: 0.9, note: "打斗适用", evidence: "第3章" },
    { id: "rel-2", rel_type: "depends_on", status: "pending", direction: "in",
      other_id: "w2", other_title: "世界观铁律", confidence: 0.7, note: "", evidence: "" },
  ],
  merged_into: null,
};

beforeEach(() => {
  api.entryRelations.mockResolvedValue(RELS);
  api.relationFeedback.mockResolvedValue({ message: "已记录，下次整理会降低同类候选权重" });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("KbEntryRelations", () => {
  it("清单渲染（含待确认标记）", async () => {
    render(<KbEntryRelations entryId="e1" />);
    await waitFor(() => expect(screen.getByText(/短句文风/)).toBeTruthy());
    expect(screen.getByText(/世界观铁律/)).toBeTruthy();
    expect(screen.getByText(/待确认/)).toBeTruthy();
    expect(screen.getAllByText("这条不对").length).toBe(2);
  });

  it("这条不对调反馈并提示", async () => {
    render(<KbEntryRelations entryId="e1" />);
    await waitFor(() => expect(screen.getAllByText("这条不对")[0]).toBeTruthy());
    fireEvent.click(screen.getAllByText("这条不对")[0]);
    await waitFor(() => expect(api.relationFeedback).toHaveBeenCalledWith("rel-1"));
    await waitFor(() => expect(screen.getByText(/降低同类候选权重/)).toBeTruthy());
  });

  it("这条不对反馈失败的缺省右臂", async () => {
    api.relationFeedback.mockRejectedValue(new Error("反馈失败"));
    render(<KbEntryRelations entryId="e1" />);
    await waitFor(() => expect(screen.getAllByText("这条不对")[0]).toBeTruthy());
    fireEvent.click(screen.getAllByText("这条不对")[0]);
    await waitFor(() => expect(screen.getByText(/反馈失败/)).toBeTruthy());
    // 非 Error 缺省臂
    api.relationFeedback.mockRejectedValue("raw");
    fireEvent.click(screen.getAllByText("这条不对")[0]);
    await waitFor(() => expect(screen.getByText(/反馈失败/)).toBeTruthy());
  });

  it("merged 追溯显示", async () => {
    api.entryRelations.mockResolvedValue({
      relations: [],
      merged_into: { surviving_id: "keep-1", title: "保留版" },
    });
    render(<KbEntryRelations entryId="merged-1" />);
    await waitFor(() => expect(screen.getByText(/已合并进「保留版」/)).toBeTruthy());
  });

  it("加载失败兜底（rows=[]）与反馈失败提示", async () => {
    api.entryRelations.mockRejectedValue(new Error("x"));
    api.relationFeedback.mockRejectedValue(new Error("反馈失败"));
    render(<KbEntryRelations entryId="e1" />);
    await waitFor(() => expect(api.entryRelations).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByTestId("kb-entry-relations")).toBeNull());
    // 再走反馈失败臂
    api.entryRelations.mockResolvedValue(RELS);
    render(<KbEntryRelations entryId="e1" />);
    await waitFor(() => expect(screen.getAllByText("这条不对").length).toBeGreaterThanOrEqual(1));
    fireEvent.click(screen.getAllByText("这条不对")[0]);
    await waitFor(() => expect(screen.getByText(/反馈失败/)).toBeTruthy());
  });

  it("空关系且未合并不渲染", async () => {
    api.entryRelations.mockResolvedValue({ relations: [], merged_into: null });
    render(<KbEntryRelations entryId="e1" />);
    await waitFor(() => expect(api.entryRelations).toHaveBeenCalled());
    expect(screen.queryByTestId("kb-entry-relations")).toBeNull();
  });
});
