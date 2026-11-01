// 知识库来源行覆盖（c-kb-snapshot）：未启用→启用弹窗→启用/失败；已启用→更新提示/同步/失败；
// 来源库已移除；解除绑定/失败；数据失败静默兜底。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = vi.hoisted(() => ({
  bindings: vi.fn(),
  libraries: vi.fn(),
  bind: vi.fn(),
  syncBinding: vi.fn(),
  unbind: vi.fn(),
}));

vi.mock("@/lib/kbApi", async (orig) => {
  const actual = await orig<typeof import("@/lib/kbApi")>();
  return { ...actual, kbApi: { ...actual.kbApi, ...api } };
});

const toast = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
}));
vi.mock("@/lib/toast", () => ({ toast }));

import KbSourceStrip from "@/components/novel/settings/KbSourceStrip";

function binding(over: Record<string, unknown> = {}) {
  return {
    id: "b1", novel_id: "n1", library_id: "l1", enabled: true,
    genre: "都市", concept: "文风", library_name: "文风库",
    member_count: 2, scene_count: 1, added: 0, removed: 0,
    library_missing: false, synced_at: "",
    ...over,
  };
}

const LIBS = [
  { id: "l1", genre: "都市", concept: "文风", name: "文风库", purpose: "", contract: "snapshot", enabled: true, entry_count: 6, bound_novels: 1 },
  { id: "lw", genre: "都市", concept: "世界设定", name: "世界库", purpose: "", contract: "snapshot", enabled: true, entry_count: 3, bound_novels: 0 },
  { id: "lc", genre: "都市", concept: "文笔", name: "文笔库", purpose: "", contract: "snapshot", enabled: true, entry_count: 2 },
];

beforeEach(() => {
  api.bindings.mockResolvedValue([]);
  api.libraries.mockResolvedValue(LIBS);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("KbSourceStrip 未启用", () => {
  it("开弹窗按概念过滤、启用失败 error→成功 toast＋弹窗收起＋来源行＋onChanged", async () => {
    const onChanged = vi.fn();
    render(<KbSourceStrip projectId="n1" scope="style" onChanged={onChanged} />);
    fireEvent.click(await screen.findByText("从知识库启用"));
    // 弹窗：只有文风/文笔（世界库被过滤）
    await screen.findByText("从知识库启用", { selector: "h3" });
    expect(screen.getByText("文风库")).toBeInTheDocument();
    expect(screen.queryByText("世界库")).not.toBeInTheDocument();
    expect(screen.getByText(/2 条/)).toBeInTheDocument();
    // 启用失败（弹窗保持开）
    api.bind.mockRejectedValueOnce(new Error("nope"));
    fireEvent.click(screen.getAllByText("启用", { exact: true })[0]);
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("nope"));
    // 无 message → 兜底「启用失败」
    api.bind.mockRejectedValueOnce({ message: "" });
    fireEvent.click(screen.getAllByText("启用", { exact: true })[0]);
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("启用失败"));
    expect(screen.getByText("从知识库启用", { selector: "h3" })).toBeInTheDocument();
    // 再点：启用成功 → 弹窗收起、来源行出现
    api.bind.mockResolvedValueOnce({ binding_id: "b1", member_count: 2, landed: { "style.role": 1 }, replaced_bindings: 0 });
    api.bindings.mockResolvedValueOnce([binding()]);
    fireEvent.click(screen.getAllByText("启用", { exact: true })[0]);
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("已启用，落了 2 条"));
    await waitFor(() => expect(screen.getByText(/来自「文风库」· 2 条/)).toBeInTheDocument());
    expect(onChanged).toHaveBeenCalled();
  });

  it("面板内点击不冒泡、背景点击与关闭钮收起；空库/拉库失败空态", async () => {
    render(<KbSourceStrip projectId="n1" scope="style" />);
    fireEvent.click(await screen.findByText("从知识库启用"));
    await screen.findByText("从知识库启用", { selector: "h3" });
    // 面板内点击不关（stopPropagation 臂）
    fireEvent.click(screen.getByText("文风库"));
    expect(screen.getByText("从知识库启用", { selector: "h3" })).toBeInTheDocument();
    // 背景遮罩点击关
    fireEvent.click(document.querySelector(".bg-black\\/50")!);
    await waitFor(() => expect(screen.queryByText("关闭")).not.toBeInTheDocument());
    // 重开：停用库被过滤、本书已启用徽章、在用计数臂
    api.libraries.mockResolvedValueOnce([
      ...LIBS,
      { id: "lx", genre: "都市", concept: "文笔", name: "旧文笔库", purpose: "", contract: "snapshot", enabled: false, entry_count: 9, bound_novels: 0 },
      { id: "l4", genre: "都市", concept: "文笔", name: "文笔库B", purpose: "", contract: "snapshot", enabled: true, entry_count: 1, bound_novels: 2, bound_in_book: 1 },
      { id: "l5", genre: "都市", concept: "文风", name: "文风库C", purpose: "", contract: "snapshot", enabled: true, bound_novels: 0 }, // 缺 entry_count 走 ?? 0 臂
    ]);
    fireEvent.click(screen.getByText("从知识库启用", { selector: "button" }));
    await screen.findByText("从知识库启用", { selector: "h3" });
    expect(screen.getByText("文笔库B")).toBeInTheDocument();
    expect(screen.getByText("本书已启用")).toBeInTheDocument();
    expect(screen.getByText(/2 本书在用/)).toBeInTheDocument(); // 模板串同节点，正则匹配
    expect(screen.queryByText("旧文笔库")).not.toBeInTheDocument(); // 停用被过滤
    fireEvent.click(screen.getByText("关闭"));
    await waitFor(() => expect(screen.queryByText("关闭")).not.toBeInTheDocument());
    // 空库空态（可选库全被过滤）
    api.libraries.mockResolvedValueOnce(LIBS.filter((l) => l.concept === "世界设定"));
    fireEvent.click(screen.getByText("从知识库启用", { selector: "button" }));
    expect(await screen.findByText(/还没有可启用的库/)).toBeInTheDocument();
    // 拉库失败 → 空态不炸
    api.libraries.mockRejectedValueOnce(new Error("net"));
    fireEvent.click(screen.getByText("从知识库启用", { selector: "button" }));
    expect(await screen.findByText(/还没有可启用的库/)).toBeInTheDocument();
  });

  it("bindings 接口失败静默：仍显示启用入口（不挡面板）", async () => {
    api.bindings.mockRejectedValue(new Error("network"));
    render(<KbSourceStrip projectId="n1" scope="style" />);
    expect(await screen.findByText("从知识库启用")).toBeInTheDocument();
  });
});

describe("KbSourceStrip 已启用", () => {
  it("库有更新→同步成功/失败；解除绑定成功/失败", async () => {
    api.bindings.mockResolvedValue([binding({ added: 1 })]);
    const onChanged = vi.fn();
    render(<KbSourceStrip projectId="n1" scope="style" onChanged={onChanged} />);
    expect(await screen.findByText("库有更新 1 条")).toBeInTheDocument();
    // 同步成功
    api.syncBinding.mockResolvedValueOnce({ member_count: 3, landed: {} });
    api.bindings.mockResolvedValueOnce([binding({ added: 0, member_count: 3 })]);
    fireEvent.click(screen.getByText("同步"));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("已同步 3 条"));
    await waitFor(() => expect(screen.queryByText("同步")).not.toBeInTheDocument());
    // 解除绑定成功
    api.unbind.mockResolvedValueOnce({ unbound: "b1" });
    fireEvent.click(screen.getByText("解除绑定"));
    await waitFor(() => expect(toast.info).toHaveBeenCalledWith("已解除绑定（本书已落的内容保留）"));
    expect(onChanged).toHaveBeenCalled();
    await waitFor(() => expect(screen.getByText("从知识库启用")).toBeInTheDocument());

    // 同步失败与解绑失败臂
    api.bindings.mockResolvedValue([binding({ added: 1 })]);
    render(<KbSourceStrip projectId="n3" scope="style" />);
    await screen.findByText("库有更新 1 条");
    api.syncBinding.mockRejectedValueOnce(new Error("sync boom"));
    fireEvent.click(screen.getByText("同步"));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("sync boom"));
    // 无 message 错误 → 兜底文案（|| 右臂）
    api.syncBinding.mockRejectedValueOnce({ message: "" });
    fireEvent.click(screen.getByText("同步"));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("同步失败"));
    api.unbind.mockRejectedValueOnce(new Error("unbind boom"));
    fireEvent.click(screen.getByText("解除绑定"));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("unbind boom"));
    api.unbind.mockRejectedValueOnce({ message: "" });
    fireEvent.click(screen.getByText("解除绑定"));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("解除失败"));
  });

  it("来源库已移除：不显示同步钮，仅可解除", async () => {
    api.bindings.mockResolvedValue([binding({ library_missing: true })]);
    render(<KbSourceStrip projectId="n1" scope="style" />);
    expect(await screen.findByText("来源库已移除")).toBeInTheDocument();
    expect(screen.queryByText("同步")).not.toBeInTheDocument();
  });
});
