// 采纳 rev 记账回归（fix/char-adopt-rev 评审补测）：逐格以服务端返回 rev 记账；
// 单格 409 重同步后跳过续走，不再整批静默失败。
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createRef } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import CharacterManager, {
  type CharacterSaveHandle,
} from "@/components/novel/settings/CharacterManager";

const apiGet = vi.fn();
const apiPost = vi.fn();
const apiPatch = vi.fn();

vi.mock("@/lib/api", () => ({
  api: {
    get: (...a: unknown[]) => apiGet(...a),
    post: (...a: unknown[]) => apiPost(...a),
    patch: (...a: unknown[]) => apiPatch(...a),
    delete: vi.fn(),
  },
}));

function cardData(overrides: Record<string, unknown> = {}) {
  return {
    id: "c1",
    novel_id: "p1",
    seq: 1,
    code: "02",
    name: "邵青梧",
    aliases: [],
    role: "配角",
    persona: "把林野从新人带出来的上司",
    dossier: {},
    cog: {},
    rev: 1,
    created_at: null,
    updated_at: null,
    relations: [],
    ...overrides,
  };
}

function listWith(items: Record<string, unknown>[]) {
  return {
    count: items.length,
    protagonist_id: null,
    gate: { ok: false, no_protagonist: true },
    confirmed: false,
    items,
  };
}

function streamReceivedRefUnknown() {
  return "n/a";
}
const DRAFT_COG = {
  targets: "认知",
  cells: [
    { path: "cog.w5", value: "甲" },
    { path: "cog.p3", value: "乙" },
    { path: "cog.p4", value: "丙" },
  ],
  skipped: [] as { key: string; why: string }[],
  act: "insert",
};

beforeEach(() => {
  vi.clearAllMocks();
  apiGet.mockImplementation((url: string) => {
    if (String(url) === "/novels/p1/characters") {
      return Promise.resolve({ data: listWith([cardData()]) });
    }
    return Promise.resolve({ data: cardData() });
  });
  apiPost.mockResolvedValue({ data: cardData() });
  apiPatch.mockResolvedValue({ data: { rev: 2 } });
});

async function openCogSink(ref: React.RefObject<CharacterSaveHandle | null>) {
  render(<CharacterManager ref={ref} projectId="p1" introReady />);
  // 等卡片视图就绪（列表项会先行出现，card 未载时 runAi 会静默空跑）
  await screen.findByText(/一句话人设/);
  // 排空挂载期 loadCard 的尾巴（其 setSink(null) 会清掉刚出的稿）
  await act(async () => {});
  await act(async () => {
    await ref.current?.runAi?.("cog");
  });
  await screen.findByText("AI 生成 · 采纳才写入（只补空格）");
}

describe("角色卡 AI 采纳 rev 记账", () => {
  it("认知出稿→采纳：逐格 PATCH 以服务端返回 rev 记账（不本地 +1）", async () => {
    apiPost.mockResolvedValue({ data: DRAFT_COG });
    apiPatch
      .mockResolvedValueOnce({ data: { rev: 10 } })
      .mockResolvedValueOnce({ data: { rev: 20 } })
      .mockResolvedValueOnce({ data: { rev: 30 } });
    const ref = createRef<CharacterSaveHandle>();
    await openCogSink(ref);
    fireEvent.click(screen.getByRole("button", { name: "采纳 · 写入" }));
    await waitFor(() => expect(apiPatch).toHaveBeenCalledTimes(3));
    const revs = apiPatch.mock.calls.map((c) => (c[1] as { base_rev: number }).base_rev);
    // 服务端回 10/20/30 → 下一格 base_rev 跟着走（旧实现会发 1/2/3）
    expect(revs).toEqual([1, 10, 20]);
  });

  it("单格 409：重同步 rev 后跳过该格继续，不再整批中止", async () => {
    apiPost.mockResolvedValue({ data: DRAFT_COG });
    apiPatch
      .mockRejectedValueOnce(Object.assign(new Error("rev_conflict"), { status: 409, rev: 9 }))
      .mockResolvedValueOnce({ data: { rev: 10 } })
      .mockResolvedValueOnce({ data: { rev: 11 } });
    const ref = createRef<CharacterSaveHandle>();
    await openCogSink(ref);
    fireEvent.click(screen.getByRole("button", { name: "采纳 · 写入" }));
    await waitFor(() => expect(apiPatch).toHaveBeenCalledTimes(3));
    const revs = apiPatch.mock.calls.map((c) => (c[1] as { base_rev: number }).base_rev);
    expect(revs).toEqual([1, 9, 10]);
    const paths = apiPatch.mock.calls.map((c) => (c[1] as { path: string }).path);
    expect(paths).toEqual(["cog.w5", "cog.p3", "cog.p4"]);
    // 采纳完成后 sink 收起
    expect(screen.queryByText("AI 生成 · 采纳才写入（只补空格）")).toBeNull();
  });

  it("非 409 错误仍整批抛出并提示重试", async () => {
    apiPost.mockResolvedValue({ data: DRAFT_COG });
    apiPatch.mockRejectedValueOnce(new Error("网络断开"));
    const ref = createRef<CharacterSaveHandle>();
    await openCogSink(ref);
    fireEvent.click(screen.getByRole("button", { name: "采纳 · 写入" }));
    await waitFor(() => expect(apiPatch).toHaveBeenCalledTimes(1));
    // 只尝试了第一格（错误抛出中止），sink 未收起可重试
    expect(apiPatch).toHaveBeenCalledTimes(1);
    expect(screen.getByText("AI 生成 · 采纳才写入（只补空格）")).toBeTruthy();
  });
});
