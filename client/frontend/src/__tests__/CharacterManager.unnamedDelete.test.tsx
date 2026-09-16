// 回归测试（09-11 bug）：未命名角色的占位名含 \u0000 前缀，删除/合并确认若用
// 原始 card.name 比对，用户永远打不出名字、按钮永远 disabled。修复后确认走
// displayName 桶底「未命名」，输入「未命名」即可删除/合并。
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { charactersApi } from "@/lib/charactersApi";
import CharacterManager from "@/components/novel/settings/CharacterManager";

vi.mock("@/lib/charactersApi", () => ({
  charactersApi: {
    list: vi.fn(),
    get: vi.fn(),
    patch: vi.fn(),
    remove: vi.fn(),
    merge: vi.fn(),
    undo: vi.fn(),
  },
}));

const UNNAMED = "\u0000abc123def456";
const card = {
  id: "c1",
  novel_id: "n1",
  seq: 1,
  code: "01",
  name: UNNAMED,
  aliases: [],
  role: "配角",
  persona: "",
  dossier: {},
  cog: {},
  rev: 1,
  created_at: null,
  updated_at: null,
  first_chapter: null,
  relations: [],
};

function mockApi() {
  vi.mocked(charactersApi.list).mockResolvedValue({
    count: 1,
    protagonist_id: null,
    gate: { ok: false, no_protagonist: true },
    confirmed: false,
    items: [{ ...card }],
  });
  vi.mocked(charactersApi.get).mockResolvedValue({ ...card, relations: [] });
  vi.mocked(charactersApi.remove).mockResolvedValue({
    receipt: "已删除《未命名》",
    undo: { op_id: "t1" },
  });
}

describe("CharacterManager 未命名角色的删除确认", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApi();
  });

  it("确认文案与输入框显示「未命名」，不漏占位名", async () => {
    const { container } = render(<CharacterManager projectId="n1" />);
    await waitFor(() => screen.getByText("删除"));
    fireEvent.click(screen.getByText("删除"));
    await screen.findByPlaceholderText("输入「未命名」以确认");
    expect(screen.getByText(/删除《未命名》/)).toBeTruthy();
    expect(container.querySelector(".char-ops-panel.danger")?.textContent).not.toContain("abc123");
  });

  it("输入「未命名」后删除按钮可用，点击调用 remove（修复前永远 disabled）", async () => {
    const { container } = render(<CharacterManager projectId="n1" />);
    await waitFor(() => screen.getByText("删除"));
    fireEvent.click(screen.getByText("删除"));
    const input = await screen.findByPlaceholderText("输入「未命名」以确认");
    fireEvent.change(input, { target: { value: "未命名" } });
    const danger = container.querySelector(
      ".char-ops-panel.danger .btn-danger",
    ) as HTMLButtonElement;
    expect(danger.disabled).toBe(false);
    fireEvent.click(danger);
    await waitFor(() =>
      expect(charactersApi.remove).toHaveBeenCalledWith("n1", "c1"),
    );
  });
});

describe("CharacterManager 未命名角色的合并确认", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(charactersApi.list).mockResolvedValue({
      count: 2,
      protagonist_id: null,
      gate: { ok: false, no_protagonist: true },
      confirmed: false,
      items: [
        { ...card },
        {
          ...card,
          id: "c2",
          seq: 2,
          code: "02",
          name: "李四",
          role: "配角",
        },
      ],
    });
    vi.mocked(charactersApi.get).mockResolvedValue({ ...card, relations: [] });
    vi.mocked(charactersApi.merge).mockResolvedValue({
      receipt: "已合并",
      undo: { op_id: "t2" },
      target: { ...card, id: "c2", name: "李四" },
    });
  });

  it("输入「未命名」后合并按钮可用，点击调用 merge", async () => {
    const { container } = render(<CharacterManager projectId="n1" />);
    await waitFor(() => screen.getByText("合并…"));
    fireEvent.click(screen.getByText("合并…"));
    const input = await screen.findByPlaceholderText("输入「未命名」以确认");
    fireEvent.change(input, { target: { value: "未命名" } });
    const select = container.querySelector(".char-ops-panel select") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "c2" } });
    const primary = container.querySelector(
      ".char-ops-panel .btn-primary",
    ) as HTMLButtonElement;
    expect(primary.disabled).toBe(false);
    fireEvent.click(primary);
    await waitFor(() =>
      expect(charactersApi.merge).toHaveBeenCalledWith("n1", "c1", "c2"),
    );
  });
});
