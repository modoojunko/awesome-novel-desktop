// 库卡头像生成（c-library-avatar-gen）：新建先落卡再生成/已有卡重生成/无权限/出错。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const api = vi.hoisted(() => ({
  createLibraryCard: vi.fn(),
  updateLibraryCard: vi.fn(),
  generateLibraryAvatar: vi.fn(),
  deleteLibraryCard: vi.fn(),
  syncCardFromBook: vi.fn(),
  randomLibraryName: vi.fn(),
  clearLibraryAvatarCache: vi.fn(),
  fetchLibraryAvatar: vi.fn(),
}));
const toastState = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
const feature = vi.hoisted(() => ({ allowed: true }));

vi.mock("@/lib/libraryApi", async (orig) => {
  const actual = await orig<typeof import("@/lib/libraryApi")>();
  return { ...actual, ...api };
});
vi.mock("@/lib/toast", () => ({ toast: toastState }));
vi.mock("@/hooks/useTier", () => ({
  useFeature: () => feature.allowed,
}));

import CardEditorModal from "@/components/library/CardEditorModal";
import type { LibraryCard } from "@/lib/libraryApi";

function card(over: Partial<LibraryCard> = {}): LibraryCard {
  return {
    id: "c1",
    name: "秦重霄",
    aliases: [],
    role: "反派",
    genre: "武侠",
    kind: "敌人",
    persona: "暴躁记仇",
    dossier: { gender: "男", age: "42", look: "络腮胡" },
    cog: {},
    src: { kind: "book", novel_name: "剑照山河", ref: "n1", character_id: "ch1" },
    avatar: { has: false, url: "", thumb_url: "" },
    rev: 1,
    updated_at: "",
    ...over,
  };
}

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  feature.allowed = true;
  api.fetchLibraryAvatar.mockResolvedValue("");
  toastState.success.mockClear();
  toastState.error.mockClear();
  toastState.info.mockClear();
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("库卡头像生成", () => {
  it("已有卡：点生成 → 调生成接口 → 缓存清空＋toast", async () => {
    api.generateLibraryAvatar.mockResolvedValue({
      card_id: "c1",
      avatar: { has: true, url: "u", thumb_url: "t" },
      rev: 2,
    });
    wrap(<CardEditorModal open card={card()} onClose={vi.fn()} />);
    fireEvent.click(screen.getByTestId("lib-gen-avatar"));
    await waitFor(() => expect(api.generateLibraryAvatar).toHaveBeenCalledWith("c1"));
    expect(api.clearLibraryAvatarCache).toHaveBeenCalledWith("c1");
    expect(toastState.success).toHaveBeenCalled();
  });

  it("新建卡：先按表单落卡再生成；落卡后转为编辑态（出现删除）", async () => {
    api.createLibraryCard.mockResolvedValue(card({ id: "new1", name: "新角色", avatar: { has: false, url: "", thumb_url: "" } }));
    api.generateLibraryAvatar.mockResolvedValue({
      card_id: "new1",
      avatar: { has: true, url: "u", thumb_url: "t" },
      rev: 2,
    });
    wrap(<CardEditorModal open card={null} onClose={vi.fn()} />);
    fireEvent.change(screen.getByPlaceholderText("角色叫什么"), { target: { value: "新角色" } });
    fireEvent.click(screen.getByTestId("lib-gen-avatar"));
    await waitFor(() => expect(api.createLibraryCard).toHaveBeenCalled());
    expect(api.createLibraryCard.mock.calls[0][0].name).toBe("新角色");
    await waitFor(() => expect(api.generateLibraryAvatar).toHaveBeenCalledWith("new1"));
    // 删除按钮出现＝已转为编辑态
    expect(screen.getByTestId("lib-delete")).toBeInTheDocument();
    // 再保存走更新（不是重复创建）
    api.updateLibraryCard.mockResolvedValue(card({ id: "new1" }));
    fireEvent.click(screen.getByTestId("lib-save"));
    await waitFor(() => expect(api.updateLibraryCard).toHaveBeenCalledWith("new1", expect.anything()));
    expect(api.createLibraryCard).toHaveBeenCalledTimes(1);
  });

  it("新建且没名字：提示起名，不落卡不生成", async () => {
    wrap(<CardEditorModal open card={null} onClose={vi.fn()} />);
    fireEvent.click(screen.getByTestId("lib-gen-avatar"));
    await waitFor(() => expect(toastState.error).toHaveBeenCalledWith("先给角色起个名字"));
    expect(api.createLibraryCard).not.toHaveBeenCalled();
    expect(api.generateLibraryAvatar).not.toHaveBeenCalled();
  });

  it("无 PRO：提示能力门，不调接口", async () => {
    feature.allowed = false;
    wrap(<CardEditorModal open card={card()} onClose={vi.fn()} />);
    fireEvent.click(screen.getByTestId("lib-gen-avatar"));
    await waitFor(() => expect(toastState.info).toHaveBeenCalled());
    expect(api.generateLibraryAvatar).not.toHaveBeenCalled();
  });

  it("生成失败：错误可读提示，不崩", async () => {
    api.generateLibraryAvatar.mockRejectedValue(new Error("图像生成失败：供应商没有返回图片"));
    wrap(<CardEditorModal open card={card()} onClose={vi.fn()} />);
    fireEvent.click(screen.getByTestId("lib-gen-avatar"));
    await waitFor(() =>
      expect(toastState.error).toHaveBeenCalledWith("图像生成失败：供应商没有返回图片"),
    );
  });
});

describe("头像生成 · 非 Error 拒绝", () => {
  it("字符串拒绝走兜底文案", async () => {
    api.generateLibraryAvatar.mockRejectedValue("炸");
    wrap(<CardEditorModal open card={card()} onClose={vi.fn()} />);
    fireEvent.click(screen.getByTestId("lib-gen-avatar"));
    await waitFor(() => expect(toastState.error).toHaveBeenCalledWith("头像生成失败"));
  });
});
