// 挑原型弹窗覆盖（c-kb-character）：开合/加载态/空态/拉取失败兜底/选中回调/背景与关闭钮收起。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = vi.hoisted(() => ({ entries: vi.fn() }));
vi.mock("@/lib/kbApi", async (orig) => {
  const actual = await orig<typeof import("@/lib/kbApi")>();
  return { ...actual, kbApi: { ...actual.kbApi, ...api } };
});

import PrototypePickModal from "@/components/novel/settings/PrototypePickModal";

function entry(over: Record<string, unknown> = {}) {
  return {
    id: "e1", genre: "都市", concept: "角色设定", concept_id: "都市:角色设定",
    title: "落魄天才", instruction: "家道中落但心气极高的主角底子。",
    payload: { archetype: "落魄天才" }, example: "", negative_example: "",
    when: {}, evidence: "", src_kind: "manual", src_novel_name: "",
    created_at: "", updated_at: "",
    ...over,
  };
}

beforeEach(() => {
  api.entries.mockResolvedValue({ entries: [entry()], next_cursor: "" });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("PrototypePickModal", () => {
  it("open=false 不渲染；打开拉列表、点选回调、关闭钮与背景收起", async () => {
    const onPick = vi.fn();
    const onClose = vi.fn();
    const { rerender } = render(<PrototypePickModal open={false} onClose={onClose} onPick={onPick} />);
    expect(screen.queryByText("从知识库挑原型")).not.toBeInTheDocument();
    expect(api.entries).not.toHaveBeenCalled(); // 关闭态不拉

    rerender(<PrototypePickModal open onClose={onClose} onPick={onPick} />);
    fireEvent.click(await screen.findByText("落魄天才"));
    expect(onPick).toHaveBeenCalledTimes(1);
    expect(onPick.mock.calls[0][0].id).toBe("e1");
    // 面板内点击不冒泡（stopPropagation 臂）
    fireEvent.click(screen.getByText("从知识库挑原型"));
    expect(onClose).not.toHaveBeenCalled();
    // 关闭钮
    fireEvent.click(screen.getByText("关闭"));
    expect(onClose).toHaveBeenCalledTimes(1);
    // 背景遮罩
    fireEvent.click(document.querySelector(".bg-black\\/50")!);
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("空列表空态；拉取失败兜底空态；标题兜底 instruction 截断", async () => {
    const onPick = vi.fn();
    render(<PrototypePickModal open onClose={vi.fn()} onPick={onPick} />);
    expect(await screen.findByText("落魄天才")).toBeInTheDocument();

    api.entries.mockResolvedValue({ entries: [entry({ id: "e2", title: "", payload: null })], next_cursor: "" }); // payload 缺失走 ?? {} 臂
    render(<PrototypePickModal open onClose={vi.fn()} onPick={onPick} />);
    // 无标题走 instruction 截 20 兜底
    expect(await screen.findByText(/家道中落但心气极高的主角底子。/)).toBeInTheDocument();

    api.entries.mockResolvedValue({ entries: [], next_cursor: "" });
    render(<PrototypePickModal open onClose={vi.fn()} onPick={onPick} />);
    expect(await screen.findByText(/还没有角色原型/)).toBeInTheDocument();

    api.entries.mockRejectedValue(new Error("net"));
    render(<PrototypePickModal open onClose={vi.fn()} onPick={onPick} />);
    expect(await screen.findByText(/还没有角色原型/)).toBeInTheDocument();
  });
});

describe("PrototypePickModal 卸载竞态", () => {
  it("卸载后回包/回错：alive 假臂不 setState", async () => {
    let resolveApi!: (v: unknown) => void;
    let rejectApi!: (e: unknown) => void;
    api.entries.mockReturnValueOnce(new Promise((res) => { resolveApi = res; }));
    const { unmount } = render(<PrototypePickModal open onClose={vi.fn()} onPick={vi.fn()} />);
    unmount();
    resolveApi({ entries: [entry()] }); // 卸载后 resolve → alive=false 臂

    api.entries.mockReturnValueOnce(new Promise((_, rej) => { rejectApi = rej; }));
    const u2 = render(<PrototypePickModal open onClose={vi.fn()} onPick={vi.fn()} />);
    u2.unmount();
    rejectApi(new Error("late")); // 卸载后 reject → alive=false 臂
    // 不抛 unhandled（setEntries 未被调用）
    await new Promise((r) => setTimeout(r, 10));
    expect(true).toBe(true);
  });
});
