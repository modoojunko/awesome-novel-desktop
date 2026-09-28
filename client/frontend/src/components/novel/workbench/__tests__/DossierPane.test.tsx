import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

// ---------------------------------------------------------------------------
// DossierPane（c-chapter-dossier）：四态渲染（提取中/失败/未提取/清单）、
// 批量与逐条动作、证据句展开、双指路。dossierApi 全 mock。
// ---------------------------------------------------------------------------

const apiState = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  delete: vi.fn(),
}));

vi.mock("@/lib/api", () => ({ api: apiState }));

import { DossierPane } from "../DossierPane";

function state(over: Record<string, unknown> = {}) {
  return {
    rows: [],
    progress: { pending: 0, accepted: 0, rejected: 0 },
    extraction: null,
    not_extracted: false,
    stale: false,
    archived: false,
    accepted_count: 0,
    ...over,
  };
}

const ROWS = [
  {
    id: "r1", domain: "settings", status: "pending", flags: "evidence_unverified",
    evidence: "守夜人接管了城门", decided_at: "", area: "势力", content: "守夜人接管城门",
  },
  {
    id: "r2", domain: "knowledge", status: "accepted", flags: "", evidence: "她不知道",
    decided_at: "2026-09-28T10:00:00", character: "阿蓟", fact: "林晚的身份", learned: false,
  },
];

beforeEach(() => {
  vi.clearAllMocks();
  apiState.get.mockResolvedValue(state());
});

describe("DossierPane 四态", () => {
  it("提取中：步骤条＋锁定横幅＋3s 轮询", async () => {
    apiState.get.mockResolvedValue(
      state({ extraction: { state: "extracting", domains: {}, error: "" } }),
    );
    render(<DossierPane projectId="p1" chapterRef="vol-1-ch-1" />);
    expect(await screen.findByTestId("dossier-extracting")).toBeTruthy();
    expect(screen.getByText("AI 提取")).toBeTruthy();
    await waitFor(
      () => expect(apiState.get.mock.calls.length).toBeGreaterThanOrEqual(2),
      { timeout: 4000 },
    );
  });

  it("失败：错误摘要＋重试＋首败逃生阀（confirm 后 skip）", async () => {
    apiState.get.mockResolvedValue(
      state({ extraction: { state: "failed", domains: {}, error: "parse: 不可解析" } }),
    );
    apiState.post.mockResolvedValue({ ok: true });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<DossierPane projectId="p1" chapterRef="vol-1-ch-1" />);
    expect(await screen.findByTestId("dossier-failed")).toBeTruthy();
    expect(screen.getByText(/parse: 不可解析/)).toBeTruthy();
    fireEvent.click(screen.getByTestId("dossier-skip"));
    await waitFor(() =>
      expect(apiState.post).toHaveBeenCalledWith(
        "/novels/p1/chapters/vol-1-ch-1/dossier/skip",
        {},
      ),
    );
  });

  it("未提取：横幅＋补提取入口", async () => {
    apiState.get.mockResolvedValue(
      state({ archived: true, not_extracted: true }),
    );
    render(<DossierPane projectId="p1" chapterRef="vol-1-ch-1" />);
    expect(await screen.findByTestId("dossier-not-extracted")).toBeTruthy();
    expect(screen.getByText("补提取章档")).toBeTruthy();
  });

  it("清单：批量按钮＋逐条动作＋证据展开＋标志＋预览＋双指路", async () => {
    apiState.get.mockResolvedValue(
      state({
        rows: ROWS,
        progress: { pending: 1, accepted: 1, rejected: 0 },
        archived: true,
      }),
    );
    apiState.get.mockResolvedValueOnce(
      state({
        rows: ROWS,
        progress: { pending: 1, accepted: 1, rejected: 0 },
        archived: true,
      }),
    ).mockResolvedValueOnce({
      up_to_ref: "vol-1-ch-1",
      domains: { settings: [], relations: [], items: [], knowledge: [] },
      counts: { settings: 2, relations: 1, items: 1, knowledge: 1 },
      skipped_stale_refs: [],
    });
    render(<DossierPane projectId="p1" chapterRef="vol-1-ch-1" />);
    expect(await screen.findByTestId("dossier-domain-settings")).toBeTruthy();
    expect(screen.getByTestId("dossier-accept-all").textContent).toContain("1");
    expect(screen.getByText("证据待核")).toBeTruthy();
    expect(screen.getByText(/仍不知道「林晚的身份」/)).toBeTruthy();
    expect(screen.getByText(/（阿蓟不知）/)).toBeTruthy();
    // 证据句默认收起（.open 类控制显隐，jsdom 不吃 CSS），点行展开
    const row = screen.getAllByTestId("dossier-row")[0];
    expect(row.className).not.toContain("open");
    fireEvent.click(row);
    expect(screen.getAllByTestId("dossier-row")[0].className).toContain("open");
    // 累计预览（有已采纳行时拉；先断言再交互——采纳刷新会重拉预览）
    await waitFor(() => expect(screen.getByTestId("dossier-preview")).toBeTruthy());
    expect(screen.getByText(/设定 2 条/)).toBeTruthy();
    expect(screen.getByText(/伏笔 \/ 世界要素提案在「操作」页签/)).toBeTruthy();
    // 逐条采纳
    apiState.post.mockResolvedValue({ ok: true, row: {} });
    fireEvent.click(screen.getByText("采纳"));
    await waitFor(() =>
      expect(apiState.post).toHaveBeenCalledWith(
        "/novels/p1/chapters/vol-1-ch-1/dossier/rows/r1",
        { action: "accept" },
      ),
    );
  });

  it("stale：横幅＋重新提取", async () => {
    apiState.get.mockResolvedValue(state({ stale: true, archived: true }));
    apiState.post.mockResolvedValue({ ok: true });
    render(<DossierPane projectId="p1" chapterRef="vol-1-ch-1" />);
    expect(await screen.findByTestId("dossier-stale-banner")).toBeTruthy();
    fireEvent.click(screen.getByText("重新提取"));
    await waitFor(() =>
      expect(apiState.post).toHaveBeenCalledWith(
        "/novels/p1/chapters/vol-1-ch-1/dossier/extract",
        {},
      ),
    );
  });
});
