// c-char-batch-import：批量导入确认链路（运行期 409 跳过 / 停批重试撤销范围累积 /
// 撤销错误保留重试入口）。handleBatchSubmit/doBatchUndo 的行为钉子——评审 P3 修复配套。
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import CharacterManager from "@/components/novel/settings/CharacterManager";

const apiGet = vi.fn();
const apiPost = vi.fn();
const apiPatch = vi.fn();
const apiDelete = vi.fn();

vi.mock("@/lib/api", () => ({
  api: {
    get: (...a: unknown[]) => apiGet(...a),
    post: (...a: unknown[]) => apiPost(...a),
    patch: (...a: unknown[]) => apiPatch(...a),
    delete: (...a: unknown[]) => apiDelete(...a),
  },
}));

function cardData(overrides: Record<string, unknown> = {}) {
  return {
    id: "c1",
    novel_id: "p1",
    seq: 1,
    code: "C-0001",
    name: "种子甲",
    aliases: [] as string[],
    role: "配角",
    persona: "",
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

function csvFile(content: string): File {
  const bytes = new TextEncoder().encode(content);
  const f = new File([bytes as unknown as BlobPart], "名单.csv", { type: "text/csv" });
  Object.defineProperty(f, "arrayBuffer", { value: async () => bytes.buffer.slice(0) });
  return f;
}

beforeEach(() => {
  vi.clearAllMocks();
  apiGet.mockImplementation((url: string) => {
    if (String(url) === "/novels/p1/characters") {
      return Promise.resolve({ data: listWith([cardData()]) });
    }
    return Promise.resolve({ data: cardData() });
  });
  apiPatch.mockResolvedValue({ data: { rev: 2 } });
});

async function openAndUpload(content: string) {
  await screen.findByText("种子甲");
  fireEvent.click(screen.getByTestId("char-batch-open"));
  const input = screen.getByTestId("char-batch-file-input");
  await waitFor(async () => {
    fireEvent.change(input, { target: { files: [csvFile(content)] } });
  });
  await waitFor(() => expect(screen.getAllByTestId("char-batch-row").length).toBeGreaterThan(0));
}

describe("CharacterManager 批量导入确认链路", () => {
  it("运行期 409：计跳过、toast 全部跳过、不出现撤销回执", async () => {
    apiPost.mockRejectedValueOnce(
      Object.assign(new Error("已有角色"), { status: 409, code: "name_taken" }),
    );
    render(<CharacterManager projectId="p1" />);
    await openAndUpload("\ufeff名字*,类型\n白芷,配角");
    fireEvent.click(screen.getByTestId("char-batch-confirm"));
    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toContain("全部跳过（1 个重名）"),
    );
    expect(screen.queryByTestId("char-batch-receipt")).toBeNull();
    expect(apiDelete).not.toHaveBeenCalled();
  });

  it("停批→重试：撤销范围累积（第一次的卡也在撤销靶子里）", async () => {
    apiPost
      .mockResolvedValueOnce({ data: cardData({ id: "n1", name: "白芷" }) })
      .mockRejectedValueOnce(Object.assign(new Error("网络抖动"), { status: 503 }))
      .mockResolvedValueOnce({ data: cardData({ id: "n2", name: "韩十三" }) });
    apiDelete.mockResolvedValue({ data: {} });
    render(<CharacterManager projectId="p1" />);
    await openAndUpload("\ufeff名字*,类型\n白芷,配角\n韩十三,配角");

    // 第一次确认：第 2 行非 409 错误 → 停批，回执＝已建 1 张，撤销还没被点
    fireEvent.click(screen.getByTestId("char-batch-confirm"));
    await waitFor(() =>
      expect(screen.getByTestId("char-batch-fail").textContent).toContain("已建 1/2"),
    );
    expect(screen.getByTestId("char-batch-receipt").textContent).toContain("本批已导入 1 张卡");
    expect(apiDelete).not.toHaveBeenCalled();

    // 重试（剩余行）：成功 → 弹层关；撤销范围＝累积 2 张（n1＋n2）
    fireEvent.click(screen.getByTestId("char-batch-confirm"));
    await waitFor(() => expect(apiPost).toHaveBeenCalledTimes(3));
    const undoBtn = await screen.findByTestId("char-batch-undo");
    fireEvent.click(undoBtn);
    await waitFor(() => expect(apiDelete).toHaveBeenCalledTimes(2));
    const deleted = apiDelete.mock.calls.map((c) => String(c[0]));
    expect(deleted).toEqual(
      expect.arrayContaining(["/novels/p1/characters/n1", "/novels/p1/characters/n2"]),
    );
  });

  it("撤销删除失败：回执保留（重试入口不清）＋报残留数；补删成功后收口", async () => {
    apiPost.mockResolvedValue({ data: cardData({ id: "n1", name: "白芷" }) });
    apiDelete
      .mockRejectedValueOnce(Object.assign(new Error("服务端炸了"), { status: 500 }))
      .mockResolvedValueOnce({ data: {} });
    render(<CharacterManager projectId="p1" />);
    await openAndUpload("\ufeff名字*,类型\n白芷,配角");
    fireEvent.click(screen.getByTestId("char-batch-confirm"));
    await waitFor(() => expect(screen.getByTestId("char-batch-receipt")).toBeTruthy());
    fireEvent.click(screen.getByTestId("char-batch-undo"));
    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toContain("还有 1 张未删干净"),
    );
    // 回执还在＝重试入口保留
    expect(screen.getByTestId("char-batch-receipt")).toBeTruthy();
    fireEvent.click(screen.getByTestId("char-batch-undo"));
    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toContain("已撤销本次导入"),
    );
    expect(screen.queryByTestId("char-batch-receipt")).toBeNull();
  });
});
