// 退化数据/非 Error 拒绝分支补测（c-character-library）：未命名/空人设/未知来源等兜底。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const api = vi.hoisted(() => ({
  listLibrary: vi.fn(),
  createLibraryCard: vi.fn(),
  updateLibraryCard: vi.fn(),
  deleteLibraryCard: vi.fn(),
  importCardFromBook: vi.fn(),
  syncCardFromBook: vi.fn(),
  applyCardToBook: vi.fn(),
  randomLibraryName: vi.fn(),
  listNovelOptions: vi.fn(),
  fetchLibraryAvatar: vi.fn(),
  clearLibraryAvatarCache: vi.fn(),
}));

vi.mock("@/lib/libraryApi", async (orig) => {
  const actual = await orig<typeof import("@/lib/libraryApi")>();
  return { ...actual, ...api };
});

import CharacterLibraryPage from "@/components/library/CharacterLibraryPage";
import CardEditorModal from "@/components/library/CardEditorModal";
import UseInNovelModal from "@/components/library/UseInNovelModal";
import ImportFromLibraryModal from "@/components/library/ImportFromLibraryModal";
import CollectToLibrary from "@/components/library/CollectToLibrary";
import LibraryAvatar from "@/components/library/LibraryAvatar";
import { toast } from "@/lib/toast";
import { queryClient } from "@/lib/queryClient";

vi.spyOn(toast, "error").mockReturnValue(0);
vi.spyOn(toast, "success").mockReturnValue(0);
vi.spyOn(toast, "info").mockReturnValue(0);

/** 退化卡：未命名/空人设/未知来源/无别名无认知/路人定位 */
function degenerate(over: Record<string, unknown> = {}) {
  return {
    id: "dg1",
    name: "",
    role: "路人",
    genre: "",
    kind: "",
    persona: "",
    src: { kind: "unknown", novel_name: "", ref: "", character_id: "" },
    avatar: { has: false, url: "", thumb_url: "" },
    rev: 1,
    updated_at: "",
    ...over,
  } as never;
}

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  queryClient.clear();
  api.listLibrary.mockResolvedValue({ count: 1, items: [degenerate()] });
  api.listNovelOptions.mockResolvedValue([{ id: "n1", name: "剑照山河" }]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("退化卡渲染（页/行/编辑器兜底）", () => {
  it("未命名/空人设/未知来源/路人定位 全部走兜底文案；键位非 Enter 不触发", async () => {
    wrap(<CharacterLibraryPage />);
    const cards = await screen.findAllByTestId("lib-card");
    expect(screen.getAllByText("未命名").length).toBeGreaterThan(0);
    expect(screen.getAllByText("还没写一句话人设").length).toBeGreaterThan(0);
    expect(screen.getAllByText("手建").length).toBeGreaterThanOrEqual(1); // 未知来源 → 手建
    fireEvent.keyDown(cards[0], { key: "a" }); // 非 Enter/Space 分支
    expect(screen.queryByTestId("lib-save")).not.toBeInTheDocument();
    // 行视图兜底 + 行键盘/点击
    fireEvent.click(within(screen.getByTestId("lib-viewseg")).getByText("列表"));
    const rows = await screen.findAllByTestId("lib-row");
    expect(screen.getAllByText("未命名").length).toBeGreaterThan(0);
    fireEvent.keyDown(rows[0], { key: "a" }); // 行：非 Enter 分支
    fireEvent.keyDown(rows[0], { key: "Enter" });
    await waitFor(() => expect(screen.getByTestId("lib-save")).toBeInTheDocument());
    fireEvent.click(within(screen.getAllByRole("dialog").at(-1)!).getByText("取消"));
    fireEvent.click(screen.getAllByTestId("lib-row")[0]);
    await waitFor(() => expect(screen.getByTestId("lib-save")).toBeInTheDocument());
  });

  it("退化卡隐藏词搜索（无 dossier/cog 键时兜底）与空认知格", async () => {
    api.listLibrary.mockResolvedValue({
      count: 1,
      items: [degenerate({ name: "甲", src: { kind: "unknown", novel_name: "剑照山河", ref: "", character_id: "" } })],
    });
    wrap(<CharacterLibraryPage />);
    await waitFor(() => expect(screen.getAllByTestId("lib-card").length).toBeGreaterThan(0));
    fireEvent.change(screen.getByTestId("lib-search"), { target: { value: "剑照" } });
    await waitFor(() => expect(screen.getAllByText(/命中：/).length).toBeGreaterThan(0));
    cleanup();
    queryClient.clear();
    api.updateLibraryCard.mockResolvedValue(degenerate());
    wrap(<CardEditorModal open card={degenerate({ cog: { w1: "" } })} onClose={vi.fn()} />);
    // 空认知格：filledCog 过滤右臂（v || "" 的空值）
    expect(screen.getByText(/认知内核/)).toBeInTheDocument();
  });

  it("保留字高亮有中段缺口（start > cursor 分支）", async () => {
    api.listLibrary.mockResolvedValue({
      count: 1,
      items: [degenerate({ name: "秦重霄", aliases: ["霄爷"] })],
    });
    wrap(<CharacterLibraryPage />);
    await waitFor(() => expect(screen.getAllByTestId("lib-card").length).toBeGreaterThan(0));
    fireEvent.change(screen.getByTestId("lib-search"), { target: { value: "秦 霄" } });
    await waitFor(() => expect(document.querySelectorAll("mark").length).toBeGreaterThan(1));
  });

  it("题材筛选（有题材时选项出现、点选后过滤、点全部复位）", async () => {
    api.listLibrary.mockResolvedValue({
      count: 2,
      items: [
        degenerate({ id: "a", name: "甲", genre: "武侠" }),
        degenerate({ id: "b", name: "乙", genre: "都市" }),
      ],
    });
    wrap(<CharacterLibraryPage />);
    await waitFor(() => expect(screen.getAllByTestId("lib-card").length).toBe(2));
    fireEvent.click(within(screen.getByTestId("lib-rail-genre")).getByText("武侠"));
    await waitFor(() => expect(screen.getAllByTestId("lib-card").length).toBe(1));
    fireEvent.click(within(screen.getByTestId("lib-rail-genre")).getByText("全部"));
    await waitFor(() => expect(screen.getAllByTestId("lib-card").length).toBe(2));
  });
});

describe("编辑器退化卡 fromCard 兜底", () => {
  it("缺别名/小类/认知的卡打开不炸，保存体字段齐全", async () => {
    api.updateLibraryCard.mockResolvedValue(degenerate());
    wrap(<CardEditorModal open card={degenerate({ kind: "" })} onClose={vi.fn()} />);
    fireEvent.change(screen.getByPlaceholderText("角色叫什么"), { target: { value: "甲" } });
    fireEvent.click(screen.getByTestId("lib-save"));
    await waitFor(() => expect(api.updateLibraryCard).toHaveBeenCalled());
    const sent = api.updateLibraryCard.mock.calls[0][1];
    expect(sent.aliases).toEqual([]);
    expect(sent.cog).toEqual({});
  });
});

describe("非 Error 拒绝对话兜底文案", () => {
  it("编辑弹窗：随机/保存/删除/同步 字符串拒绝", async () => {
    api.randomLibraryName.mockRejectedValue("炸1");
    api.updateLibraryCard.mockRejectedValue("炸2");
    api.deleteLibraryCard.mockRejectedValue("炸3");
    api.syncCardFromBook.mockRejectedValue("炸4");
    wrap(<CardEditorModal open card={degenerate({ src: { kind: "book", novel_name: "书", ref: "n1", character_id: "ch1" } })} onClose={vi.fn()} />);
    fireEvent.click(screen.getByTestId("lib-ai-random"));
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    fireEvent.change(screen.getByPlaceholderText("角色叫什么"), { target: { value: "甲" } });
    fireEvent.click(screen.getByTestId("lib-save"));
    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByText(/同步最新设定/));
    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(3));
    fireEvent.click(screen.getByTestId("lib-delete"));
    fireEvent.click(screen.getByText("确认删除"));
    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(4));
  });

  it("选书/导入/收录：字符串拒绝", async () => {
    api.applyCardToBook.mockRejectedValue("炸");
    wrap(<UseInNovelModal card={degenerate()} onClose={vi.fn()} />);
    await waitFor(() =>
      expect(screen.getByTestId("lib-use-submit")).not.toBeDisabled(),
    );
    fireEvent.click(screen.getByTestId("lib-use-submit"));
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    cleanup();
    queryClient.clear();
    api.listLibrary.mockResolvedValue({ count: 1, items: [degenerate()] });
    wrap(<ImportFromLibraryModal open novelId="n1" onClose={vi.fn()} />);
    const dlg = () => within(screen.getAllByRole("dialog").at(-1)!);
    await waitFor(() => expect(dlg().getByRole("button", { name: /未命名/ })).toBeInTheDocument());
    fireEvent.click(dlg().getByRole("button", { name: /未命名/ }));
    await waitFor(() => expect(screen.getByTestId("lib-import-submit")).not.toBeDisabled());
    fireEvent.click(screen.getByTestId("lib-import-submit"));
    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(2));
    cleanup();
    queryClient.clear();
    api.importCardFromBook.mockRejectedValue("炸");
    wrap(<CollectToLibrary novelId="n1" characterId="ch1" characterName="甲" />);
    await waitFor(() => expect(screen.getByText("收入角色库")).toBeInTheDocument());
    fireEvent.click(screen.getByText("收入角色库"));
    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(3));
  });

  it("收录返回 created=false（已存在）走另一条文案", async () => {
    api.importCardFromBook.mockResolvedValue({ created: false, card: degenerate() });
    api.listLibrary.mockResolvedValue({ count: 0, items: [] });
    wrap(<CollectToLibrary novelId="n1" characterId="ch1" characterName="甲" />);
    await waitFor(() => expect(screen.getByText("收入角色库")).toBeInTheDocument());
    fireEvent.click(screen.getByText("收入角色库"));
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
  });

  it("导入结果 demoted=true 文案分支", async () => {
    api.applyCardToBook.mockResolvedValue({ character_id: "x", name: "甲", role: "配角", renamed: false, demoted: true, avatar: false });
    wrap(<ImportFromLibraryModal open novelId="n1" onClose={vi.fn()} />);
    const dlg2 = () => within(screen.getAllByRole("dialog").at(-1)!);
    await waitFor(() => expect(dlg2().getByRole("button", { name: /未命名/ })).toBeInTheDocument());
    fireEvent.click(dlg2().getByRole("button", { name: /未命名/ }));
    await waitFor(() => expect(screen.getByTestId("lib-import-submit")).not.toBeDisabled());
    fireEvent.click(screen.getByTestId("lib-import-submit"));
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
  });
});

describe("头像卸载竞态与 className", () => {
  it("请求未回即卸载不 setState；className 拼接", async () => {
    let resolvePromise: (v: string) => void = () => {};
    api.fetchLibraryAvatar.mockReturnValue(new Promise((res) => (resolvePromise = res)));
    const { unmount, container } = wrap(
      <LibraryAvatar card={{ id: "c1", name: "", avatar: { has: true, url: "u", thumb_url: "t" } }} className="extra" />,
    );
    expect(container.querySelector(".lib-ava.extra")).toBeTruthy();
    unmount();
    resolvePromise("blob:x");
    await Promise.resolve();
    // 无异常即通过（alive=false 分支已走）
  });

  it("卸载后加载失败不 setState", async () => {
    let rejectPromise: (e: Error) => void = () => {};
    api.fetchLibraryAvatar.mockReturnValue(new Promise((_res, rej) => (rejectPromise = rej)));
    const { unmount } = wrap(
      <LibraryAvatar card={{ id: "c2", name: "乙", avatar: { has: true, url: "u", thumb_url: "t" } }} />,
    );
    unmount();
    rejectPromise(new Error("late"));
    await Promise.resolve();
  });
});
