// 知识视图「关联知识」段测试（c-kb-relations-view）：active 过滤/按类句式/点跳/这条不对/merged/空态。
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
    { id: "rel-2", rel_type: "depends_on", status: "active", direction: "in",
      other_id: "w2", other_title: "世界观铁律", confidence: 0.7, note: "", evidence: "" },
    { id: "rel-3", rel_type: "derived_from", status: "pending", direction: "out",
      other_id: "w3", other_title: "待确认条目", confidence: 0.6, note: "", evidence: "" },
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
  it("只显示 active（pending 过滤）且按类定制句式", async () => {
    render(<KbEntryRelations entryId="e1" />);
    await waitFor(() => expect(screen.getByText(/适用于 短句文风/)).toBeTruthy());
    // 入向 depends_on：「对端 依赖本知识」
    expect(screen.getByText(/世界观铁律 依赖本知识/)).toBeTruthy();
    // pending 行不出现
    expect(screen.queryByText(/待确认条目/)).toBeNull();
    expect(screen.queryByText(/待确认/)).toBeNull();
    expect(screen.getAllByText("这条不对").length).toBe(2);
    // 取数带 status=active
    await waitFor(() => expect(api.entryRelations).toHaveBeenCalledWith("e1", { status: "active" }));
  });

  it("出向六类句式逐类正确", async () => {
    api.entryRelations.mockResolvedValue({
      relations: [
        { id: "r1", rel_type: "applies_to", status: "active", direction: "out", other_id: "o1", other_title: "甲", confidence: 1, note: "", evidence: "" },
        { id: "r2", rel_type: "derived_from", status: "active", direction: "out", other_id: "o2", other_title: "乙", confidence: 1, note: "", evidence: "" },
        { id: "r3", rel_type: "instance_of", status: "active", direction: "out", other_id: "o3", other_title: "丙", confidence: 1, note: "", evidence: "" },
        { id: "r4", rel_type: "depends_on", status: "active", direction: "out", other_id: "o4", other_title: "丁", confidence: 1, note: "", evidence: "" },
        { id: "r5", rel_type: "contradicts", status: "active", direction: "out", other_id: "o5", other_title: "戊", confidence: 1, note: "", evidence: "" },
        { id: "r6", rel_type: "refines", status: "active", direction: "out", other_id: "o6", other_title: "己", confidence: 1, note: "", evidence: "" },
      ],
      merged_into: null,
    });
    render(<KbEntryRelations entryId="e1" />);
    await waitFor(() => expect(screen.getByText(/适用于 甲/)).toBeTruthy());
    expect(screen.getByText(/源自 乙/)).toBeTruthy();
    expect(screen.getByText(/属于 丙/)).toBeTruthy();
    expect(screen.getByText(/依赖 丁/)).toBeTruthy();
    expect(screen.getByText(/与 戊 相冲/)).toBeTruthy();
    expect(screen.getByText(/细化 己/)).toBeTruthy();
  });

  it("点跳回调带对端 id；不传回调保持纯文本", async () => {
    const onOpen = vi.fn();
    render(<KbEntryRelations entryId="e1" onOpenKnowledge={onOpen} />);
    await waitFor(() => expect(screen.getByText(/适用于 短句文风/)).toBeTruthy());
    fireEvent.click(screen.getByText(/适用于 短句文风/));
    expect(onOpen).toHaveBeenCalledWith("w1");
    cleanup();
    render(<KbEntryRelations entryId="e1" />);
    await waitFor(() => expect(screen.getByText(/适用于 短句文风/)).toBeTruthy());
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
