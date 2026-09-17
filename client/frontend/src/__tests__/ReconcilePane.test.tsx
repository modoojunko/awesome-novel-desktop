import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ReconcilePane } from "@/components/novel/workbench/ReconcilePane";

// ---------------------------------------------------------------------------
// archive-reconcile 前端：收尾进度聚合、逐条采纳/驳回/重试、免费档占位。
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
      kind: "relations",
      status: "failed",
      payload: { items: [] },
      error: "写回失败：boom",
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
  ],
  progress: { pending: 1, failed: 1, accepted: 1, rejected: 0 },
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
      isPro
      {...props}
    />,
  );
}

describe("ReconcilePane（归档收尾区）", () => {
  it("免费档占位：不拉取收尾数据", () => {
    renderPane({ isPro: false });
    expect(screen.getByText(/PRO 可用/)).toBeTruthy();
    expect(apiState.fetchReconcile).not.toHaveBeenCalled();
  });

  it("未归档不渲染", () => {
    const { container } = renderPane({ archived: false });
    expect(container.textContent).toBe("");
    expect(apiState.fetchReconcile).not.toHaveBeenCalled();
  });

  it("进度聚合＋行摘要（世界要素/伏笔埋下可读）", async () => {
    renderPane();
    await waitFor(() => expect(apiState.fetchReconcile).toHaveBeenCalled());
    const lead = document.querySelector(".reconcile-lead")?.textContent ?? "";
    expect(lead).toContain("待确认 1");
    expect(lead).toContain("失败 1");
    expect(lead).toContain("已处理 1");
    // 摘要：lore 条目 key：value；hooks planted「埋下：…」
    expect(screen.getByText(/静默带：无人区/)).toBeTruthy();
    expect(screen.getByText(/埋下：渡口的雾/)).toBeTruthy();
    // 类别标签
    expect(screen.getByText("世界要素")).toBeTruthy();
    expect(screen.getByText("伏笔登记")).toBeTruthy();
    // 失败行错误可见
    expect(screen.getByText(/写回失败：boom/)).toBeTruthy();
  });

  it("采纳/驳回/重试分别走对应 API 并触发刷新", async () => {
    renderPane();
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

    // 每次动作后刷新（挂载 1 次 + 三个动作各 1 次）
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
