// 起草角色采纳 rev 记账回归：逐格以服务端返回 rev 记账；
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

const DRAFT = {
  role: "配角",
  name: "",
  aliases: [] as string[],
  persona: "",
  cells: [
    { path: "cog.w5", value: "甲" },
    { path: "cog.p3", value: "乙" },
    { path: "cog.p4", value: "丙" },
  ],
  skipped: [] as { key: string; why: string }[],
  prompt: "【本次提示词】",
  sources: ["简介"],
};

beforeEach(() => {
  vi.clearAllMocks();
  apiGet.mockImplementation((url: string) => {
    if (String(url) === "/novels/p1/characters") {
      return Promise.resolve({ data: listWith([cardData()]) });
    }
    return Promise.resolve({ data: cardData() });
  });
  apiPost.mockImplementation((url: string, body?: unknown) => {
    if (String(url).includes("/draft-all")) {
      if ((body as { preview?: boolean } | undefined)?.preview) {
        return Promise.resolve({ data: { prompt: "【本次提示词】", sources: ["简介"], role: "配角" } });
      }
      return Promise.resolve({ data: DRAFT });
    }
    return Promise.resolve({ data: cardData() });
  });
  apiPatch.mockResolvedValue({ data: { rev: 2 } });
});

async function openDraftAllResult(ref: React.RefObject<CharacterSaveHandle | null>) {
  render(<CharacterManager ref={ref} projectId="p1" introReady />);
  await screen.findByText(/一句话人设/);
  await act(async () => {});
  await act(async () => {
    await ref.current?.runAi?.("draftAll");
  });
  await screen.findByTestId("char-ai-prompt-edit");
  fireEvent.click(screen.getByRole("button", { name: "生成" }));
  await screen.findByText("AI 拟稿 · 起草角色（采纳才写入）");
}

describe("起草角色采纳 rev 记账", () => {
  it("出稿→采纳：逐格 PATCH 以服务端返回 rev 记账（不本地 +1）", async () => {
    apiPatch
      .mockResolvedValueOnce({ data: { rev: 10 } })
      .mockResolvedValueOnce({ data: { rev: 20 } })
      .mockResolvedValueOnce({ data: { rev: 30 } });
    const ref = createRef<CharacterSaveHandle>();
    await openDraftAllResult(ref);
    fireEvent.click(screen.getByRole("button", { name: "采纳 · 写入" }));
    await waitFor(() => expect(apiPatch).toHaveBeenCalledTimes(3));
    const revs = apiPatch.mock.calls.map((c) => (c[1] as { base_rev: number }).base_rev);
    // 服务端回 10/20/30 → 下一格 base_rev 跟着走（旧实现会发 1/2/3）
    expect(revs).toEqual([1, 10, 20]);
  });

  it("单格 409：重同步 rev 后跳过该格继续，不再整批中止", async () => {
    apiPatch
      .mockRejectedValueOnce(Object.assign(new Error("rev_conflict"), { status: 409, rev: 9 }))
      .mockResolvedValueOnce({ data: { rev: 10 } })
      .mockResolvedValueOnce({ data: { rev: 11 } });
    const ref = createRef<CharacterSaveHandle>();
    await openDraftAllResult(ref);
    fireEvent.click(screen.getByRole("button", { name: "采纳 · 写入" }));
    await waitFor(() => expect(apiPatch).toHaveBeenCalledTimes(3));
    const revs = apiPatch.mock.calls.map((c) => (c[1] as { base_rev: number }).base_rev);
    expect(revs).toEqual([1, 9, 10]);
    const paths = apiPatch.mock.calls.map((c) => (c[1] as { path: string }).path);
    expect(paths).toEqual(["cog.w5", "cog.p3", "cog.p4"]);
    // 采纳完成后弹窗收起
    expect(screen.queryByText("AI 拟稿 · 起草角色（采纳才写入）")).toBeNull();
  });

  it("非 409 错误仍整批抛出并提示重试", async () => {
    apiPatch.mockRejectedValueOnce(new Error("网络断开"));
    const ref = createRef<CharacterSaveHandle>();
    await openDraftAllResult(ref);
    fireEvent.click(screen.getByRole("button", { name: "采纳 · 写入" }));
    await waitFor(() => expect(apiPatch).toHaveBeenCalledTimes(1));
    // 只尝试了第一格（错误抛出中止），弹窗未收起可重试
    expect(apiPatch).toHaveBeenCalledTimes(1);
    expect(screen.getByText("AI 拟稿 · 起草角色（采纳才写入）")).toBeTruthy();
  });
});
