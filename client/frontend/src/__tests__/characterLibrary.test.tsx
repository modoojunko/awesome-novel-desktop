// 角色库组件测试（c-character-library）：库页筛选/搜索/双视图/空态、编辑弹窗 CRUD/同步/AI、
// 选书弹窗、书内导入弹窗、收录钮、头像兜底。
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

const toastSuccess = vi.spyOn(toast, "success").mockReturnValue(0);
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

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

import { queryClient } from "@/lib/queryClient";

beforeEach(() => {
  localStorage.clear(); // 视图偏好跨测试污染（视图切换测试会写 charlib.view）
  queryClient.clear(); // CollectToLibrary 走应用级单例缓存：跨测试清干净
  api.listLibrary.mockResolvedValue({
    count: 2,
    items: [card(), card({ id: "c2", name: "苏晚晴", role: "配角", kind: "挚友", src: { kind: "manual", novel_name: "", ref: "", character_id: "" }, dossier: { gender: "女", age: "17" } })],
  });
  api.listNovelOptions.mockResolvedValue([{ id: "n1", name: "剑照山河" }]);
});

describe("CharacterLibraryPage", () => {
  it("渲染统计/卡/筛选计数；搜索命中与隐藏字段回落", async () => {
    wrap(<CharacterLibraryPage />);
    await waitFor(() => expect(screen.getAllByTestId("lib-card")).toHaveLength(2));
    expect(screen.getByTestId("lib-stats").textContent).toContain("2");
    // 搜索命中语言特征
    fireEvent.change(screen.getByTestId("lib-search"), { target: { value: "娘亲" } });
    await waitFor(() => expect(screen.getAllByTestId("lib-card")).toHaveLength(1));
    expect(screen.getAllByText("娘亲").length).toBeGreaterThan(0);
    // 搜索命中隐藏字段（认知）→ 卡底「命中：」行
    fireEvent.change(screen.getByTestId("lib-search"), { target: { value: "暴躁" } });
    await waitFor(() => expect(screen.getAllByText(/命中：/).length).toBeGreaterThan(0));
    // 清空
    fireEvent.change(screen.getByTestId("lib-search"), { target: { value: "" } });
    await waitFor(() => expect(screen.getAllByTestId("lib-card")).toHaveLength(2));
  });

  it("左侧四组筛选（定位/来源/小类）与清空出口", async () => {
    wrap(<CharacterLibraryPage />);
    await waitFor(() => expect(screen.getAllByTestId("lib-card")).toHaveLength(2));
    fireEvent.click(within(screen.getByTestId("lib-rail-src")).getByText("手建"));
    await waitFor(() => expect(screen.getAllByTestId("lib-card")).toHaveLength(1));
    fireEvent.click(within(screen.getByTestId("lib-rail-role")).getByText("配角"));
    await waitFor(() => expect(screen.getAllByTestId("lib-card")).toHaveLength(1));
    fireEvent.click(within(screen.getByTestId("lib-rail-kind")).getByText("敌人"));
    await waitFor(() => expect(screen.getByText("没有符合筛选的角色")).toBeInTheDocument());
    fireEvent.click(screen.getByText("清空筛选"));
    await waitFor(() => expect(screen.getAllByTestId("lib-card")).toHaveLength(2));
  });

  it("视图切换存 localStorage；空库双入口；排序", async () => {
    wrap(<CharacterLibraryPage />);
    await waitFor(() => expect(screen.getAllByTestId("lib-card")).toHaveLength(2));
    fireEvent.click(within(screen.getByTestId("lib-viewseg")).getByText("列表"));
    await waitFor(() => expect(screen.getAllByTestId("lib-row")).toHaveLength(2));
    expect(localStorage.getItem("charlib.view")).toBe("list");
    fireEvent.change(screen.getByTestId("lib-sort"), { target: { value: "name" } });
    expect(screen.getAllByTestId("lib-row")).toHaveLength(2);
    cleanup();
    api.listLibrary.mockResolvedValue({ count: 0, items: [] });
    wrap(<CharacterLibraryPage />);
    await waitFor(() => expect(screen.getByText("柜子还空着")).toBeInTheDocument());
    expect(screen.getByText("去拆书收角色")).toBeInTheDocument();
  });

  it("加载失败显示重试并恢复", async () => {
    api.listLibrary.mockRejectedValueOnce(new Error("网络炸了"));
    wrap(<CharacterLibraryPage />);
    await waitFor(() => expect(screen.getByText("加载失败")).toBeInTheDocument());
    api.listLibrary.mockResolvedValue({ count: 0, items: [] });
    fireEvent.click(screen.getByText("重试"));
    await waitFor(() => expect(screen.queryByText("加载失败")).not.toBeInTheDocument());
  });

  it("新建按钮打开编辑弹窗；用到新书打开选书弹窗", async () => {
    wrap(<CharacterLibraryPage />);
    await waitFor(() => expect(screen.getAllByTestId("lib-card")).toHaveLength(2));
    fireEvent.click(screen.getByTestId("lib-new"));
    // 页头按钮与弹窗标题同名——弹窗以「取消」钮为开面判据
    await waitFor(() => expect(screen.getByTestId("lib-save")).toBeInTheDocument());
    fireEvent.click(screen.getByText("取消"));
    await waitFor(() => expect(screen.queryByTestId("lib-save")).not.toBeInTheDocument());
    // 卡上动作（hover 面的两个钮都在 DOM 内）
    fireEvent.click(screen.getAllByText("用到新书")[0]);
    await waitFor(() => expect(screen.getByText("放进哪本书")).toBeInTheDocument());
  });
});

describe("CardEditorModal", () => {
  it("新建：空名拦截、AI 随机只填名字年龄、保存后关闭", async () => {
    api.randomLibraryName.mockResolvedValue({ name: "霍青山", age: 30, source: "local" });
    api.createLibraryCard.mockResolvedValue(card());
    const onClose = vi.fn();
    wrap(<CardEditorModal open card={null} onClose={onClose} />);
    fireEvent.click(screen.getByTestId("lib-save"));
    await waitFor(() => expect(toast.success).toBeDefined);
    // 空名 → 不调用 API
    expect(api.createLibraryCard).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("lib-ai-random"));
    await waitFor(() => expect((screen.getByPlaceholderText("角色叫什么") as HTMLInputElement).value).toBe("霍青山"));
    fireEvent.change(screen.getByTestId("lib-genre"), { target: { value: "都市" } });
    fireEvent.click(screen.getByTestId("lib-save"));
    await waitFor(() => expect(api.createLibraryCard).toHaveBeenCalled());
    const sent = api.createLibraryCard.mock.calls[0][0];
    expect(sent.name).toBe("霍青山");
    expect(sent.dossier.age).toBe("30");
    expect(onClose).toHaveBeenCalled();
  });

  it("编辑：保存、删除两段确认、书源卡同步", async () => {
    const c = card();
    api.updateLibraryCard.mockResolvedValue(c);
    api.deleteLibraryCard.mockResolvedValue({ deleted: "c1" });
    api.syncCardFromBook.mockResolvedValue({ ...c, persona: "同步后的人设" });
    const onClose = vi.fn();
    wrap(<CardEditorModal open card={c as never} onClose={onClose} />);
    // 同步
    fireEvent.click(screen.getByText(/同步最新设定/));
    await waitFor(() => expect(api.syncCardFromBook).toHaveBeenCalledWith("c1"));
    // 保存
    fireEvent.click(screen.getByTestId("lib-save"));
    await waitFor(() => expect(api.updateLibraryCard).toHaveBeenCalled());
    // 删除两段确认
    fireEvent.click(screen.getByTestId("lib-delete"));
    expect(screen.getByText(/只删库里的这张卡/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("取消"));
    fireEvent.click(screen.getByTestId("lib-delete"));
    fireEvent.click(screen.getByText("确认删除"));
    await waitFor(() => expect(api.deleteLibraryCard).toHaveBeenCalledWith("c1"));
  });

  it("AI 随机失败给可读提示；保存失败提示", async () => {
    api.randomLibraryName.mockRejectedValue(new Error("模型不可用"));
    api.updateLibraryCard.mockRejectedValue(new Error("写库失败"));
    wrap(<CardEditorModal open card={card() as never} onClose={vi.fn()} />);
    fireEvent.click(screen.getByTestId("lib-ai-random"));
    await waitFor(() => expect(toastError).toHaveBeenCalled());
    fireEvent.click(screen.getByTestId("lib-save"));
    await waitFor(() => expect(toastError).toHaveBeenCalledTimes(2));
  });
});

describe("UseInNovelModal", () => {
  it("列出书、默认换名、提交后回调", async () => {
    api.applyCardToBook.mockResolvedValue({ character_id: "x", name: "霍青山", role: "配角", renamed: true, demoted: true, avatar: true });
    const onClose = vi.fn();
    const onDone = vi.fn();
    wrap(<UseInNovelModal card={card() as never} onClose={onClose} onDone={onDone} />);
    await waitFor(() => expect(screen.getByText("《剑照山河》")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("lib-use-submit"));
    await waitFor(() => expect(api.applyCardToBook).toHaveBeenCalledWith("c1", "n1", true));
    expect(onDone).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it("书架空时提示先去建书", async () => {
    api.listNovelOptions.mockResolvedValue([]);
    wrap(<UseInNovelModal card={card() as never} onClose={vi.fn()} />);
    await waitFor(() => expect(screen.getByText(/书架还没有书/)).toBeInTheDocument());
  });
});

describe("ImportFromLibraryModal", () => {
  it("逐张选择导入（v1 单张），默认换名", async () => {
    api.applyCardToBook.mockResolvedValue({ character_id: "x", name: "新名字", role: "配角", renamed: true, demoted: false, avatar: false });
    const onDone = vi.fn();
    wrap(<ImportFromLibraryModal open novelId="n1" novelName="剑照山河" onClose={vi.fn()} onDone={onDone} />);
    await waitFor(() => expect(screen.getByText("秦重霄")).toBeInTheDocument());
    fireEvent.click(screen.getByText("秦重霄"));
    fireEvent.click(screen.getByTestId("lib-import-submit"));
    await waitFor(() => expect(api.applyCardToBook).toHaveBeenCalledWith("c1", "n1", true));
    expect(onDone).toHaveBeenCalled();
  });
});

describe("CollectToLibrary", () => {
  it("未收录→收入；已收录→同步", async () => {
    api.importCardFromBook.mockResolvedValue({ created: true, card: card() });
    api.syncCardFromBook.mockResolvedValue(card());
    api.listLibrary.mockResolvedValue({ count: 0, items: [] });
    wrap(<CollectToLibrary novelId="n1" characterId="ch1" characterName="秦重霄" />);
    await waitFor(() => expect(screen.getByText("收入角色库")).toBeInTheDocument());
    fireEvent.click(screen.getByText("收入角色库"));
    await waitFor(() => expect(api.importCardFromBook).toHaveBeenCalledWith("n1", "ch1", false));
    cleanup();
    queryClient.clear();
    api.listLibrary.mockResolvedValue({ count: 1, items: [card()] });
    wrap(<CollectToLibrary novelId="n1" characterId="ch1" characterName="秦重霄" />);
    await waitFor(() => expect(screen.getByText("同步到角色库")).toBeInTheDocument());
    fireEvent.click(screen.getByText("同步到角色库"));
    await waitFor(() => expect(api.syncCardFromBook).toHaveBeenCalledWith("c1"));
  });
});

describe("LibraryAvatar", () => {
  it("无图回落姓字块；有图加载后出 img", async () => {
    wrap(<LibraryAvatar card={{ id: "c1", name: "沈青崖", avatar: { has: false, url: "", thumb_url: "" } }} />);
    expect(screen.getByText("沈")).toBeInTheDocument();
    api.fetchLibraryAvatar.mockResolvedValue("blob:mock");
    wrap(<LibraryAvatar card={{ id: "c1", name: "沈青崖", avatar: { has: true, url: "u", thumb_url: "t" } }} />);
    await waitFor(() => expect(document.querySelector("img")).toBeTruthy());
  });
});

describe("题材选择器（c-library-genre-align）", () => {
  it("选项来自开书题材目录：未分题材＋目录大类", async () => {
    wrap(<CardEditorModal open card={null} onClose={vi.fn()} />);
    const sel = screen.getByTestId("lib-genre") as HTMLSelectElement;
    const texts = Array.from(sel.options).map((o) => o.textContent);
    expect(texts[0]).toBe("未分题材");
    expect(texts).toContain("都市");
    expect(texts).toContain("玄幻");
    expect(texts).toContain("悬疑");
  });
});
