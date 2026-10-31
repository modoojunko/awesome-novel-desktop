// 知识库页覆盖（c-knowledge-base）：题材栏折叠/概念页签/手录全分支/详情抽屉/加载更多。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = vi.hoisted(() => ({
  genres: vi.fn(),
  entries: vi.fn(),
  libraries: vi.fn(),
  createEntry: vi.fn(),
}));

vi.mock("@/lib/kbApi", async (orig) => {
  const actual = await orig<typeof import("@/lib/kbApi")>();
  // kbApi 是对象导出：mock 要替换对象内方法，不是模块顶层
  return { ...actual, kbApi: { ...actual.kbApi, ...api } };
});

import KnowledgeBasePage from "@/pages/KnowledgeBasePage";

function entry(over: Record<string, unknown> = {}) {
  return {
    id: "aaaaaaaa-0000-0000-0000-000000000001",
    genre: "都市",
    concept: "手法",
    concept_id: "都市:手法",
    title: "先果后因",
    instruction: "先给果再补因。",
    payload: {},
    example: "他倒在血泊里，三分钟前剑才出鞘。",
    negative_example: "别按时间顺序平铺。",
    when: {},
    evidence: "第3章 引文",
    src_kind: "manual",
    src_novel_name: "",
    created_at: "",
    updated_at: "",
    ...over,
  };
}

const SEVEN_GENRES = [
  { name: "都市", count: 3 },
  { name: "仙侠/修真", count: 2 },
  { name: "玄幻", count: 1 },
  { name: "悬疑", count: 1 },
  { name: "科幻", count: 1 },
  { name: "末世/废土", count: 1 },
  { name: "谍战", count: 1 },
  { name: "游戏文", count: 0 },
  { name: "美食", count: 0 },
];

beforeEach(() => {
  api.genres.mockResolvedValue(SEVEN_GENRES);
  api.libraries.mockResolvedValue([
    { id: "l1", genre: "都市", concept: "手法", name: "手法库", purpose: "", contract: "live", enabled: true },
    { id: "l2", genre: "都市", concept: "文风", name: "文风库", purpose: "", contract: "snapshot", enabled: true },
    { id: "l3", genre: "", concept: "文笔", name: "文笔库", purpose: "", contract: "snapshot", enabled: true },
  ]);
  api.entries.mockResolvedValue({ entries: [entry()], next_cursor: "" });
  api.createEntry.mockResolvedValue(entry());
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("KnowledgeBasePage 题材栏与列表", () => {
  it("题材>5 折叠/展开、库分组标题、加载更多追加、详情抽屉开关", async () => {
    // 分页链先于挂载：首屏带 cursor 出「加载更多」，第二页收口。
    // 第二页条目三无（无标题/无指令/无例证）：标题与预览双兜底臂＋抽屉空字段臂
    api.entries
      .mockResolvedValueOnce({ entries: [entry()], next_cursor: "cur2" })
      .mockResolvedValueOnce({
        entries: [entry({ id: "bbbbbbbb-0000-0000-0000-000000000002", title: "", instruction: "", example: "", negative_example: "", evidence: "" })],
        next_cursor: "",
      });
    const { container } = render(<KnowledgeBasePage />);
    // 首屏：visibleGenres 截 5（末世/废土 藏起），0 计数题材只露前两个
    await screen.findByText("更多题材 (2)");
    expect(screen.getByText("都市")).toBeInTheDocument();
    expect(screen.queryByText("末世/废土")).not.toBeInTheDocument();
    expect(screen.getByText("游戏文")).toBeInTheDocument();
    // 库分组：都市×2 ＋ 跨题材通用×1（genre 空串走兜底名）
    await screen.findByText("都市 · 2 个库");
    expect(screen.getByText("跨题材通用 · 1 个库")).toBeInTheDocument();
    // 展开全部题材 → 收起臂（展开后按钮仍要在，收得回去）
    fireEvent.click(screen.getByText("更多题材 (2)"));
    expect(screen.getByText("收起")).toBeInTheDocument();
    expect(screen.getByText("末世/废土")).toBeInTheDocument();
    fireEvent.click(screen.getByText("收起"));
    expect(await screen.findByText("更多题材 (2)")).toBeInTheDocument();
    expect(screen.queryByText("末世/废土")).not.toBeInTheDocument();
    // 列表分页：第二页空标题走 instruction 截断兜底，无 cursor 后按钮消失
    fireEvent.click(await screen.findByText("加载更多"));
    await waitFor(() => expect(api.entries).toHaveBeenCalledTimes(2));
    expect(api.entries.mock.calls[1][0].cursor).toBe("cur2");
    await screen.findByText("2 条");
    // 三无条目详情：无指令/正例/反例/证据（假臂），标题兜底空
    fireEvent.click(screen.getAllByText(/bbbbbbbb/)[0]); // 列表头（抽屉头同文案）
    await screen.findByText("✕"); // 抽屉已开
    expect(screen.queryByText("指令")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("✕"));
    expect(screen.queryByText("加载更多")).not.toBeInTheDocument();
    // 详情抽屉：全字段 + ✕ 关
    fireEvent.click(screen.getByText("先果后因"));
    expect(screen.getByText("正例")).toBeInTheDocument();
    expect(screen.getByText("反例")).toBeInTheDocument();
    expect(screen.getByText("证据")).toBeInTheDocument();
    fireEvent.click(screen.getByText("✕"));
    await waitFor(() => expect(screen.queryByText("正例")).not.toBeInTheDocument());
    // 背景遮罩点击关抽屉
    fireEvent.click(screen.getByText("先果后因"));
    await screen.findByText("正例");
    fireEvent.click(container.querySelector(".bg-black\\/50")!);
    await waitFor(() => expect(screen.queryByText("正例")).not.toBeInTheDocument());
  });

  it("概念页签切换带 concept 参数、题材切换带 genre、搜索带 q、情节页签禁用", async () => {
    render(<KnowledgeBasePage />);
    await screen.findByText("先果后因");
    // 初始 libraries 不带 genre（undefined 臂）
    expect(api.libraries).toHaveBeenCalledWith(undefined);
    // 概念页签 → 手法
    fireEvent.click(screen.getByTitle("写每一章时的场面打法"));
    await waitFor(() => expect(api.entries.mock.calls.at(-1)![0].concept).toBe("手法"));
    // 概念页签回「全部」→ 参数缺席（undefined）
    fireEvent.click(screen.getAllByText("全部")[1]);
    await waitFor(() => expect(api.entries.mock.calls.at(-1)![0].concept).toBeUndefined());
    // 题材切换：libraries 收到 genre（truthy 臂）
    fireEvent.click(screen.getByText("都市"));
    await waitFor(() => expect(api.libraries).toHaveBeenCalledWith("都市"));
    // 搜索
    fireEvent.change(screen.getByPlaceholderText("搜名字、内容、来源书名"), { target: { value: "打斗" } });
    await waitFor(() => expect(api.entries.mock.calls.at(-1)![0].q).toBe("打斗"));
    // 情节页签禁用不可点
    expect(screen.getByText(/情节/)).toBeDisabled();
    // 侧栏「全部」复位＋0 计数题材两态点击（折叠 slice(0,2) 臂 / 展开 map 臂）
    fireEvent.click(screen.getAllByText("全部")[0]);
    await waitFor(() => expect(api.libraries).toHaveBeenCalledWith(undefined));
    fireEvent.click(screen.getByText("游戏文"));
    await waitFor(() => expect(api.libraries).toHaveBeenCalledWith("游戏文"));
    fireEvent.click(screen.getByText("更多题材 (2)"));
    fireEvent.click(screen.getByText("美食"));
    await waitFor(() => expect(api.libraries).toHaveBeenCalledWith("美食"));
  });

  it("genres 接口失败静默（catch 臂），列表照常", async () => {
    api.genres.mockRejectedValue(new Error("network"));
    render(<KnowledgeBasePage />);
    await screen.findByText("先果后因");
    await waitFor(() => expect(api.genres).toHaveBeenCalled());
  });
});

describe("KnowledgeBasePage 手录表单", () => {
  async function openManual() {
    api.entries.mockResolvedValue({ entries: [], next_cursor: "" });
    render(<KnowledgeBasePage />);
    fireEvent.click(await screen.findByText("记一条"));
    await screen.findByText("题材 *");
  }

  it("空文本/未选题材校验、保存成功三连刷新、取消", async () => {
    await openManual();
    fireEvent.click(screen.getByText("保存"));
    expect(screen.getByText("先写一条")).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("你想记什么写法？贴上来"), { target: { value: "打斗先给果。" } });
    fireEvent.click(screen.getByText("保存"));
    expect(screen.getByText("选一个题材")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "都市" } });
    // 保存成功后的题材计数刷新失败走静默 catch 臂
    api.genres.mockRejectedValueOnce(new Error("net"));
    fireEvent.click(screen.getByText("保存"));
    await waitFor(() =>
      expect(api.createEntry).toHaveBeenCalledWith({ genre: "都市", concept: "", instruction: "打斗先给果。" }),
    );
    await waitFor(() => expect(screen.queryByText("题材 *")).not.toBeInTheDocument()); // 成功关弹窗
    await waitFor(() => expect(api.libraries).toHaveBeenCalledTimes(2)); // 条目＋库重载
    // 取消臂
    fireEvent.click(await screen.findByText("记一条"));
    fireEvent.click(screen.getByText("取消"));
    await waitFor(() => expect(screen.queryByText("题材 *")).not.toBeInTheDocument());
  });

  it("保存失败两分支：后端 422 的 message / 无 message 兜底", async () => {
    await openManual();
    fireEvent.change(screen.getByPlaceholderText("你想记什么写法？贴上来"), { target: { value: "打斗先给果。" } });
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "都市" } });
    // ① ApiError.message＝后端第一条闸门错误
    api.createEntry.mockRejectedValueOnce(new Error("指令不能为空"));
    fireEvent.click(screen.getByText("保存"));
    await screen.findByText("指令不能为空");
    // ② message 空 → 兜底
    api.createEntry.mockRejectedValueOnce({ message: "" });
    fireEvent.click(screen.getByText("保存"));
    await screen.findByText("保存失败");
  });
});
