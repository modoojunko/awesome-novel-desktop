// 角色库交互分支补测（c-character-library）：编辑器全部输入面/页键盘与动作/空态出口。
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
import LibraryAvatar from "@/components/library/LibraryAvatar";
import { toast } from "@/lib/toast";
import { queryClient } from "@/lib/queryClient";

vi.spyOn(toast, "error").mockReturnValue(0);
vi.spyOn(toast, "success").mockReturnValue(0);
vi.spyOn(toast, "info").mockReturnValue(0);

function card(over: Record<string, unknown> = {}) {
  return {
    id: "c1",
    name: "秦重霄",
    aliases: ["大当家"],
    role: "反派",
    genre: "武侠",
    kind: "敌人",
    persona: "黑风寨大当家",
    dossier: { gender: "男", age: "42", speech: "骂人" },
    cog: { b1: "暴躁" },
    src: { kind: "book", novel_name: "剑照山河", ref: "n1", character_id: "ch1" },
    avatar: { has: false, url: "", thumb_url: "" },
    rev: 1,
    updated_at: "",
    ...over,
  };
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
  api.listLibrary.mockResolvedValue({ count: 1, items: [card()] });
  api.listNovelOptions.mockResolvedValue([{ id: "n1", name: "剑照山河" }]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("CardEditorModal 全输入面", () => {
  it("名字/定位/小类/人设/别名/性别/年龄 全改并保存；删除失败与同步失败提示", async () => {
    api.updateLibraryCard.mockResolvedValue(card());
    api.deleteLibraryCard.mockRejectedValue(new Error("删不掉"));
    api.syncCardFromBook.mockRejectedValue(new Error("同步不了"));
    wrap(<CardEditorModal open card={card() as never} onClose={vi.fn()} />);
    fireEvent.change(screen.getByPlaceholderText("角色叫什么"), { target: { value: "新名" } });
    fireEvent.click(screen.getByText("主角"));
    fireEvent.click(screen.getByText("挚友"));
    fireEvent.change(screen.getByPlaceholderText("每章都会带上这张卡的这句"), { target: { value: "新的人设" } });
    fireEvent.change(screen.getByPlaceholderText("顿号隔开，可留空"), { target: { value: "甲、乙" } });
    fireEvent.change(screen.getByLabelText("性别"), { target: { value: "女" } });
    fireEvent.change(screen.getByRole("textbox", { name: "年龄" }), { target: { value: "77" } });
    fireEvent.click(screen.getByTestId("lib-save"));
    await waitFor(() => expect(api.updateLibraryCard).toHaveBeenCalled());
    const sent = api.updateLibraryCard.mock.calls[0][1];
    expect(sent.name).toBe("新名");
    expect(sent.role).toBe("主角");
    expect(sent.kind).toBe("挚友");
    expect(sent.persona).toBe("新的人设");
    expect(sent.aliases).toEqual(["甲", "乙"]);
    expect(sent.dossier.gender).toBe("女");
    expect(sent.dossier.age).toBe("77");
    // 同步失败
    fireEvent.click(screen.getByText(/同步最新设定/));
    await waitFor(() => expect(api.syncCardFromBook).toHaveBeenCalled());
    // 删除失败（两段确认 → 确认后 API 抛错）
    fireEvent.click(screen.getByTestId("lib-delete"));
    fireEvent.click(screen.getByText("确认删除"));
    await waitFor(() => expect(api.deleteLibraryCard).toHaveBeenCalled());
  });
});

describe("CharacterLibraryPage 键盘与动作", () => {
  it("卡片键盘 Enter/Space 进编辑、行键盘 Enter、动作按钮、rail 全部复位、视图回切", async () => {
    wrap(<CharacterLibraryPage />);
    const cards = await screen.findAllByTestId("lib-card");
    fireEvent.keyDown(cards[0], { key: "Enter" });
    await waitFor(() => expect(screen.getByTestId("lib-save")).toBeInTheDocument());
    fireEvent.click(within(screen.getAllByRole("dialog").at(-1)!).getByText("取消"));
    await waitFor(() => expect(screen.queryByTestId("lib-save")).not.toBeInTheDocument());
    fireEvent.keyDown(screen.getAllByTestId("lib-card")[0], { key: " " });
    await waitFor(() => expect(screen.getByTestId("lib-save")).toBeInTheDocument());
    fireEvent.click(within(screen.getAllByRole("dialog").at(-1)!).getByText("取消"));
    // 点击卡本体（open edit 分支）
    fireEvent.click(screen.getAllByTestId("lib-card")[0]);
    await waitFor(() => expect(screen.getByTestId("lib-save")).toBeInTheDocument());
    fireEvent.click(within(screen.getAllByRole("dialog").at(-1)!).getByText("取消"));
    // rail 选出后点「全部」复位
    fireEvent.click(within(screen.getByTestId("lib-rail-role")).getByText("反派"));
    await waitFor(() =>
      expect(
        within(screen.getByTestId("lib-rail-role")).getByText("全部").className.includes("on"),
      ).toBe(false),
    );
    fireEvent.click(within(screen.getByTestId("lib-rail-role")).getByText("全部"));
    // 列表视图：行的编辑钮/用到新书钮、键盘 Enter、回切卡片
    fireEvent.click(within(screen.getByTestId("lib-viewseg")).getByText("列表"));
    const row = (await screen.findAllByTestId("lib-row"))[0];
    fireEvent.keyDown(row, { key: "Enter" });
    await waitFor(() => expect(screen.getByTestId("lib-save")).toBeInTheDocument());
    fireEvent.click(within(screen.getAllByRole("dialog").at(-1)!).getByText("取消"));
    fireEvent.click(within(screen.getAllByTestId("lib-row")[0]).getByText("编辑"));
    await waitFor(() => expect(screen.getByTestId("lib-save")).toBeInTheDocument());
    fireEvent.click(within(screen.getAllByRole("dialog").at(-1)!).getByText("取消"));
    fireEvent.click(within(screen.getAllByTestId("lib-row")[0]).getByText("用到新书"));
    await waitFor(() => expect(screen.getByText("放进哪本书")).toBeInTheDocument());
    fireEvent.click(within(screen.getAllByRole("dialog").at(-1)!).getByText("取消"));
    // 视图回切（卡片钮）
    fireEvent.click(within(screen.getByTestId("lib-viewseg")).getByText("卡片"));
    await waitFor(() => expect(screen.getAllByTestId("lib-card").length).toBeGreaterThan(0));
  });

  it("卡上两个动作钮的 stopPropagation 分支", async () => {
    wrap(<CharacterLibraryPage />);
    await screen.findAllByTestId("lib-card");
    fireEvent.click(within(screen.getAllByTestId("lib-card")[0]).getByText("编辑"));
    await waitFor(() => expect(screen.getByTestId("lib-save")).toBeInTheDocument());
    fireEvent.click(within(screen.getAllByRole("dialog").at(-1)!).getByText("取消"));
    fireEvent.click(within(screen.getAllByTestId("lib-card")[0]).getByText("用到新书"));
    await waitFor(() => expect(screen.getByText("放进哪本书")).toBeInTheDocument());
  });

  it("空库两钮：去拆书收角色与新建角色", async () => {
    api.listLibrary.mockResolvedValue({ count: 0, items: [] });
    wrap(<CharacterLibraryPage />);
    await waitFor(() => expect(screen.getByText("去拆书收角色")).toBeInTheDocument());
    fireEvent.click(screen.getByText("去拆书收角色"));
    // 空态区里的「新建角色」钮（页头同名，取最后一个）
    const news = screen.getAllByText("新建角色");
    fireEvent.click(news[news.length - 1]);
    await waitFor(() => expect(screen.getAllByTestId("lib-save").length).toBeGreaterThan(0));
  });

  it("localStorage 读取抛错时视图兜底为卡片", async () => {
    const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("storage 挂了");
    });
    wrap(<CharacterLibraryPage />);
    await waitFor(() => expect(screen.getAllByTestId("lib-card").length).toBeGreaterThan(0));
    spy.mockRestore();
  });
});

describe("LibraryAvatar 尺寸档", () => {
  it("sm/lg 类名渲染", () => {
    api.fetchLibraryAvatar.mockResolvedValue("blob:x");
    wrap(
      <>
        <LibraryAvatar card={{ id: "a", name: "甲", avatar: { has: false, url: "", thumb_url: "" } }} size="sm" />
        <LibraryAvatar card={{ id: "b", name: "乙", avatar: { has: false, url: "", thumb_url: "" } }} size="lg" />
      </>,
    );
    expect(document.querySelectorAll(".lib-ava.sm").length).toBe(1);
    expect(document.querySelectorAll(".lib-ava.lg").length).toBe(1);
  });
});
