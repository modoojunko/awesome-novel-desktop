import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { ReconcilePane } from "@/components/novel/workbench/ReconcilePane";

// ---------------------------------------------------------------------------
// archive-reconcile 前端：各归各的页签（kinds 过滤）、已决折叠、免费档不渲染。
// ---------------------------------------------------------------------------

const apiState = vi.hoisted(() => ({
  fetchReconcile: vi.fn(),
  acceptReconcile: vi.fn(),
  rejectReconcile: vi.fn(),
  retryReconcile: vi.fn(),
}));
vi.mock("@/lib/reconcileApi", () => ({
  KIND_LABEL: {
    set_changes: "设定变化",
    relations: "角色关系",
    hooks: "伏笔登记",
    lore: "世界要素",
    char_states: "角色状态变化",
  },
  fetchReconcile: apiState.fetchReconcile,
  acceptReconcile: apiState.acceptReconcile,
  rejectReconcile: apiState.rejectReconcile,
  retryReconcile: apiState.retryReconcile,
}));

const ROWS = {
  rows: [
    {
      id: "r1",
      chapter_id: "c1",
      kind: "lore",
      status: "pending",
      payload: { items: [{ key: "静默带", value: "无人区", set: "extra" }] },
      error: "",
      created_at: "",
      decided_at: "",
    },
    {
      id: "r2",
      chapter_id: "c1",
      kind: "hooks",
      status: "failed",
      payload: { planted: [{ description: "旧失败行" }] },
      error: "parse: 模型输出不是可解析的 JSON（```json {\"planted\": [...]",
      created_at: "",
      decided_at: "",
    },
    {
      id: "r3",
      chapter_id: "c1",
      kind: "hooks",
      status: "accepted",
      payload: { planted: [{ description: "渡口的雾" }] },
      error: "",
      created_at: "",
      decided_at: "",
    },
    {
      id: "r4",
      chapter_id: "c1",
      kind: "relations",
      status: "pending",
      payload: { items: [{ owner: "林晚", other: "老聋" }] },
      error: "",
      created_at: "",
      decided_at: "",
    },
  ],
  progress: { pending: 2, failed: 1, accepted: 1, rejected: 0 },
};

beforeEach(() => {
  apiState.fetchReconcile.mockReset().mockResolvedValue(ROWS);
  apiState.acceptReconcile.mockReset().mockResolvedValue(undefined);
  apiState.rejectReconcile.mockReset().mockResolvedValue(undefined);
  apiState.retryReconcile.mockReset().mockResolvedValue(undefined);
});

function renderPane(props: Partial<Parameters<typeof ReconcilePane>[0]> = {}) {
  return render(
    <ReconcilePane
      projectId="p1"
      chapterRef="vol-1-ch-1"
      archived
      kinds={["lore"]}
      {...props}
    />,
  );
}

describe("ReconcilePane（收尾提案·各归各的页签）", () => {
  it("未归档不渲染收尾区：无占位、不拉取（归档 AI 全家免费后档位不再拦截）", () => {
    const { container } = renderPane({ archived: false });
    expect(container.textContent).toBe("");
    expect(apiState.fetchReconcile).not.toHaveBeenCalled();
  });

  it("未归档不渲染", () => {
    const { container } = renderPane({ archived: false });
    expect(container.textContent).toBe("");
    expect(apiState.fetchReconcile).not.toHaveBeenCalled();
  });

  it("kinds 过滤：设定页签只显世界要素，计数按本类聚合", async () => {
    renderPane({ kinds: ["lore"] });
    await waitFor(() => expect(apiState.fetchReconcile).toHaveBeenCalled());
    const lead = document.querySelector(".reconcile-lead")?.textContent ?? "";
    expect(lead).toContain("归档收尾 · 世界要素提案");
    expect(lead).toContain("待确认 1");
    expect(lead).not.toContain("失败 1"); // hooks 的失败不计入
    expect(screen.getByText(/静默带：无人区/)).toBeTruthy();
    // 他类行不出现
    expect(screen.queryByText(/旧失败行/)).toBeNull();
    expect(screen.queryByText(/林晚↔老聋/)).toBeNull();
  });

  it("伏笔页签：待确认＋失败在列，已决默认折叠只显计数", async () => {
    renderPane({ kinds: ["hooks"] });
    await waitFor(() => expect(apiState.fetchReconcile).toHaveBeenCalled());
    const lead = document.querySelector(".reconcile-lead")?.textContent ?? "";
    expect(lead).toContain("归档收尾 · 伏笔登记提案");
    expect(lead).toContain("失败 1");
    expect(lead).toContain("已处理 1");
    // 失败行错误单行省略（title 悬停看全文）
    const err = screen.getByText(/parse: 模型输出不是可解析的 JSON/);
    expect(err.className).toBe("rc-error");
    // 已决行在折叠区内
    const details = document.querySelector("details.rc-decided") as HTMLDetailsElement;
    expect(details).toBeTruthy();
    expect(details.open).toBe(false);
    expect(within(details).getByText(/埋下：渡口的雾/)).toBeTruthy();
    expect(screen.queryByText("已处理 1 条（点开留痕）")).toBeTruthy();
  });

  it("采纳/驳回/重试分别走对应 API 并触发刷新", async () => {
    renderPane({ kinds: ["hooks", "lore"] });
    await waitFor(() => expect(apiState.fetchReconcile).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole("button", { name: "采纳" }));
    await waitFor(() =>
      expect(apiState.acceptReconcile).toHaveBeenCalledWith("p1", "vol-1-ch-1", "r1"),
    );

    fireEvent.click(screen.getByRole("button", { name: "驳回" }));
    await waitFor(() =>
      expect(apiState.rejectReconcile).toHaveBeenCalledWith("p1", "vol-1-ch-1", "r1"),
    );

    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    await waitFor(() =>
      expect(apiState.retryReconcile).toHaveBeenCalledWith("p1", "vol-1-ch-1", "r2"),
    );

    await waitFor(() =>
      expect(apiState.fetchReconcile.mock.calls.length).toBeGreaterThanOrEqual(4),
    );
  });

  it("拉取失败就地提示可重试（不抛到全局）", async () => {
    apiState.fetchReconcile.mockRejectedValue(new Error("boom"));
    renderPane();
    await screen.findByText(/收尾进度获取失败/);
  });
});
