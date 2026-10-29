// 角色库分支补测（c-character-library）：文件变更/弹窗异常路径/视图空态/手建兜底等覆盖率死角。
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

const toastError = vi.spyOn(toast, "error").mockReturnValue(0);
const toastInfo = vi.spyOn(toast, "info").mockReturnValue(0);

function card(over: Record<string, unknown> = {}) {
  return {
    id: "c1",
    name: "秦重霄",
    aliases: ["大当家"],
    role: "反派",
    genre: "武侠",
    kind: "敌人",
    persona: "黑风寨大当家，记仇",
    dossier: { gender: "男", age: "42", speech: "骂人先问候对方娘亲" },
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
  api.listNovelOptions.mockResolvedValue([{ id: "n1", name: "剑照山河" }, { id: "n2", name: "长夜灯" }]);
  api.listLibrary.mockResolvedValue({
    count: 1,
    items: [card(), card({ id: "c2", name: "老周", role: "配角", dossier: {}, cog: {}, src: { kind: "manual", novel_name: "", ref: "", character_id: "" } })],
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("CardEditorModal 字段编辑覆盖", () => {
  it("改种族/外貌/语言特征/背景/剧情定位/认知格都会进保存体", async () => {
    api.updateLibraryCard.mockResolvedValue(card());
    wrap(<CardEditorModal open card={card() as never} onClose={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("种族"), { target: { value: "妖族" } });
    fireEvent.change(screen.getByLabelText("外貌标签"), { target: { value: "刀疤" } });
    const speech = screen.getByLabelText("语言特征") as HTMLTextAreaElement;
    fireEvent.change(speech, { target: { value: "先骂后打" } });
    fireEvent.change(screen.getByLabelText("背景"), { target: { value: "马匪起家" } });
    fireEvent.change(screen.getByLabelText("剧情定位"), { target: { value: "追杀主角" } });
    // 认知格（默认已展开：有值）
    fireEvent.change(screen.getByLabelText("世界观 · 世界规则认知度"), { target: { value: "只信刀马" } });
    fireEvent.click(screen.getByTestId("lib-save"));
    await waitFor(() => expect(api.updateLibraryCard).toHaveBeenCalled());
    const sent = api.updateLibraryCard.mock.calls[0][1];
    expect(sent.dossier.race).toBe("妖族");
    expect(sent.dossier.look).toBe("刀疤");
    expect(sent.dossier.speech).toBe("先骂后打");
    expect(sent.dossier.background).toBe("马匪起家");
    expect(sent.dossier.plot).toBe("追杀主角");
    expect(sent.cog.w1).toBe("只信刀马");
  });
});

describe("CharacterLibraryPage 分支", () => {
  it("重叠多词搜索/手建兜底/列表视图空态清空", async () => {
    wrap(<CharacterLibraryPage />);
    await waitFor(() => expect(screen.getAllByTestId("lib-card")).toHaveLength(2));
    // 手建卡无来源书 → 「手建」脚注
    expect(screen.getAllByText("手建").length).toBeGreaterThanOrEqual(2);
    // 重叠词（娘 + 娘亲）→ 重叠区间跳过分支
    fireEvent.change(screen.getByTestId("lib-search"), { target: { value: "娘 娘亲" } });
    await waitFor(() => expect(screen.getAllByTestId("lib-card")).toHaveLength(1));
    // 命中隐藏字段：文字含「命中：」
    fireEvent.change(screen.getByTestId("lib-search"), { target: { value: "暴躁" } });
    await waitFor(() => expect(screen.getAllByText(/命中：/).length).toBeGreaterThan(0));
    expect(screen.getAllByText(/命中：/)[0].textContent).toContain("认知");
    // 列表视图 + 无结果 + 清空
    fireEvent.click(within(screen.getByTestId("lib-viewseg")).getByText("列表"));
    fireEvent.change(screen.getByTestId("lib-search"), { target: { value: "不存在的词" } });
    await waitFor(() => expect(screen.getByText("没有符合筛选的角色")).toBeInTheDocument());
    fireEvent.click(screen.getByText("清空筛选"));
    await waitFor(() => expect(screen.getAllByTestId("lib-row")).toHaveLength(2));
  });

  it("用到新书全流程（选另一本→提交→onDone 提示）", async () => {
    api.applyCardToBook.mockResolvedValue({ character_id: "x", name: "秦重霄", role: "配角", renamed: false, demoted: false, avatar: false });
    wrap(<CharacterLibraryPage />);
    await waitFor(() => expect(screen.getAllByTestId("lib-card")).toHaveLength(2));
    const goal = screen.getAllByTestId("lib-card").find((el) => el.textContent?.includes("秦重霄"))!;
    fireEvent.click(within(goal).getByText("用到新书"));
    await waitFor(() => expect(screen.getByText("《长夜灯》")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "《长夜灯》" })); // 切目标书分支
    fireEvent.click(screen.getByTestId("lib-use-submit"));
    await waitFor(() => expect(api.applyCardToBook).toHaveBeenCalledWith("c1", "n2", true));
    await waitFor(() => expect(toastInfo).toHaveBeenCalled());
  });

  it("错误非 Error 实例 → 兜底「加载失败」", async () => {
    api.listLibrary.mockRejectedValueOnce("炸了");
    wrap(<CharacterLibraryPage />);
    await waitFor(() => expect(screen.getAllByText("加载失败").length).toBeGreaterThan(0));
  });
});

describe("UseInNovelModal 分支", () => {
  it("换名开关可关、切书、提交失败给提示", async () => {
    api.applyCardToBook.mockRejectedValue(new Error("书被删了"));
    wrap(<UseInNovelModal card={card() as never} onClose={vi.fn()} />);
    await waitFor(() => expect(screen.getByText("《剑照山河》")).toBeInTheDocument());
    fireEvent.click(screen.getByText("《长夜灯》"));
    const rename = screen.getAllByRole("checkbox")[0] as HTMLInputElement;
    fireEvent.click(rename);
    fireEvent.click(screen.getByTestId("lib-use-submit"));
    await waitFor(() => expect(api.applyCardToBook).toHaveBeenCalledWith("c1", "n2", false));
    await waitFor(() => expect(toastError).toHaveBeenCalled());
  });
});

describe("ImportFromLibraryModal 分支", () => {
  it("空库提示、换名开关、提交失败", async () => {
    api.listLibrary.mockResolvedValue({ count: 0, items: [] });
    wrap(<ImportFromLibraryModal open novelId="n1" onClose={vi.fn()} />);
    await waitFor(() => expect(screen.getByText(/角色库还是空的/)).toBeInTheDocument());
    cleanup();
    queryClient.clear();
    api.listLibrary.mockResolvedValue({ count: 1, items: [card()] });
    api.applyCardToBook.mockRejectedValue(new Error("导入炸了"));
    wrap(<ImportFromLibraryModal open novelId="n1" onClose={vi.fn()} />);
    await waitFor(() => expect(screen.getByText("秦重霄")).toBeInTheDocument());
    fireEvent.click(screen.getByText("秦重霄"));
    const rename = screen.getAllByRole("checkbox")[0] as HTMLInputElement;
    fireEvent.click(rename); // 关掉换名
    fireEvent.click(screen.getByTestId("lib-import-submit"));
    await waitFor(() => expect(api.applyCardToBook).toHaveBeenCalledWith("c1", "n1", false));
    await waitFor(() => expect(toastError).toHaveBeenCalled());
  });
});

describe("CollectToLibrary 失败分支", () => {
  it("同步失败提示", async () => {
    api.listLibrary.mockResolvedValue({ count: 1, items: [card()] });
    api.syncCardFromBook.mockRejectedValue(new Error("同步炸了"));
    wrap(<CollectToLibrary novelId="n1" characterId="ch1" characterName="秦重霄" />);
    await waitFor(() => expect(screen.getByText("同步到角色库")).toBeInTheDocument());
    fireEvent.click(screen.getByText("同步到角色库"));
    await waitFor(() => expect(toastError).toHaveBeenCalled());
  });
});

describe("LibraryAvatar 加载失败兜底", () => {
  it("fetch 失败回落姓字块", async () => {
    api.fetchLibraryAvatar.mockRejectedValue(new Error("403"));
    wrap(<LibraryAvatar card={{ id: "c1", name: "沈青崖", avatar: { has: true, url: "u", thumb_url: "t" } }} />);
    await waitFor(() => expect(screen.getByText("沈")).toBeInTheDocument());
    expect(document.querySelector("img")).toBeNull();
  });
});
