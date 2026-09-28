/** 本章变化分区（c-chapter-dossier IA 对齐）：设定页签＝设定/物品/认知（按子领域分组），
 *  关系页签＝关系；待确认/批量/删除/恢复/证据展开/stale/提取中提示。dossierApi 全 mock。 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const apiState = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn() }));
vi.mock("@/lib/api", () => ({ api: apiState }));

import {
  RelationChangesSection,
  SettingChangesSection,
} from "../ChangesSections";

function state(over: Record<string, unknown> = {}) {
  return {
    rows: [], progress: { pending: 0, accepted: 0, rejected: 0 },
    extraction: null, not_extracted: false, stale: false,
    archived: false, accepted_count: 0, ...over,
  };
}

const ROWS = [
  { id: "s1", domain: "settings", status: "pending", flags: "", evidence: "守夜人接管了城门", decided_at: "", area: "势力", content: "守夜人接管城门" },
  { id: "s2", domain: "settings", status: "pending", flags: "", evidence: "封航令下", decided_at: "", area: "舞台", content: "渡口夜里封航" },
  { id: "i1", domain: "items", status: "accepted", flags: "", evidence: "她把旧刀塞给他", decided_at: "", name: "旧刀", change_type: "易主", holder: "阿蓟" },
  { id: "k1", domain: "knowledge", status: "pending", flags: "", evidence: "她不知道", decided_at: "", character: "阿蓟", fact: "林野的身份", learned: false },
  { id: "r1", domain: "relations", status: "pending", flags: "", evidence: "背靠背", decided_at: "", owner: "林野", other: "阿蓟", rel_type: "盟友", change_note: "并肩" },
];

beforeEach(() => {
  vi.clearAllMocks();
  apiState.get.mockResolvedValue(state());
});

describe("SettingChangesSection（设定页签区块）", () => {
  it("三域分组：设定按子领域＋物品＋认知；关系行不进设定区块", async () => {
    apiState.get.mockResolvedValue(state({
      rows: ROWS, progress: { pending: 4, accepted: 1, rejected: 0 }, archived: true,
    }));
    render(<SettingChangesSection projectId="p1" chapterRef="vol-1-ch-1" />);
    expect(await screen.findByTestId("setting-changes-section")).toBeTruthy();
    // 设定按子领域分组（两个组各自可见）
    expect(screen.getByText("势力")).toBeTruthy();
    expect(screen.getByText("舞台")).toBeTruthy();
    expect(screen.getByText(/守夜人接管城门/)).toBeTruthy();
    expect(screen.getByText("物品")).toBeTruthy();
    expect(screen.getByText(/旧刀：易主，现在在 阿蓟 手中/)).toBeTruthy();
    expect(screen.getByText(/仍不知道「林野的身份」/)).toBeTruthy();
    // 关系行不在设定区块
    expect(screen.queryByText(/林野 → 阿蓟/)).toBeNull();
    expect(screen.getByTestId("changes-accept-all").textContent).toContain("3"); // s1+s2+k1（关系行不在设定区块）
  });

  it("证据句点行展开（.open 类）＋逐条采纳走 rowAction", async () => {
    apiState.get.mockResolvedValue(state({
      rows: [ROWS[0]], progress: { pending: 1, accepted: 0, rejected: 0 },
    }));
    apiState.post.mockResolvedValue({ ok: true, row: {} });
    render(<SettingChangesSection projectId="p1" chapterRef="vol-1-ch-1" />);
    const row = await screen.findByTestId("change-row");
    expect(row.className).not.toContain("open");
    fireEvent.click(row.querySelector("div")!); // onClick 在内容首行
    expect(screen.getByTestId("change-row").className).toContain("open");
    fireEvent.click(screen.getByText("采纳"));
    await waitFor(() =>
      expect(apiState.post).toHaveBeenCalledWith(
        "/novels/p1/chapters/vol-1-ch-1/dossier/rows/s1",
        { action: "accept" },
      ),
    );
  });

  it("已采纳行可删（confirm）；已驳回可恢复", async () => {
    apiState.get.mockResolvedValue(state({
      rows: [ROWS[2], { ...ROWS[0], id: "s0", status: "rejected" }],
      progress: { pending: 0, accepted: 1, rejected: 1 },
    }));
    apiState.delete.mockResolvedValue({ ok: true });
    apiState.post.mockResolvedValue({ ok: true, row: {} });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<SettingChangesSection projectId="p1" chapterRef="vol-1-ch-1" />);
    await screen.findByText("已采纳");
    fireEvent.click(screen.getByText("删除"));
    await waitFor(() =>
      expect(apiState.delete).toHaveBeenCalledWith(
        "/novels/p1/chapters/vol-1-ch-1/dossier/rows/i1",
      ),
    );
    fireEvent.click(screen.getByText("恢复待确认"));
    await waitFor(() =>
      expect(apiState.post).toHaveBeenCalledWith(
        "/novels/p1/chapters/vol-1-ch-1/dossier/rows/s0",
        { action: "restore" },
      ),
    );
  });

  it("提取中：提示行＋3s 轮询；stale：横幅＋重新提取；空且非提取中：整块不渲染", async () => {
    const { unmount } = render(<SettingChangesSection projectId="p1" chapterRef="vol-1-ch-1" />);
    await waitFor(() => expect(apiState.get).toHaveBeenCalled());
    // 空态：不渲染区块
    await waitFor(() => expect(screen.queryByTestId("setting-changes-section")).toBeNull());
    unmount();

    apiState.get.mockResolvedValue(state({ extraction: { state: "extracting", domains: {}, error: "" } }));
    render(<SettingChangesSection projectId="p1" chapterRef="vol-1-ch-1" />);
    expect(await screen.findByTestId("changes-extracting")).toBeTruthy();
    await waitFor(() => expect(apiState.get.mock.calls.length).toBeGreaterThanOrEqual(2), { timeout: 4000 });
  });

  it("stale 横幅＋重新提取；批量全部采纳", async () => {
    apiState.get.mockResolvedValue(state({
      rows: [ROWS[0], ROWS[4]], progress: { pending: 2, accepted: 0, rejected: 0 }, stale: true,
    }));
    apiState.post.mockResolvedValue({ ok: true, updated: 2 });
    render(<SettingChangesSection projectId="p1" chapterRef="vol-1-ch-1" />);
    expect(await screen.findByTestId("changes-stale-banner")).toBeTruthy();
    fireEvent.click(screen.getByText("重新提取"));
    await waitFor(() =>
      expect(apiState.post).toHaveBeenCalledWith(
        "/novels/p1/chapters/vol-1-ch-1/dossier/extract",
        {},
      ),
    );
    fireEvent.click(screen.getByTestId("changes-accept-all"));
    // 批量限定本分区三域：不传域＝后端全章批量，会把关系行一并采纳（跨域误采纳）
    await waitFor(() =>
      expect(apiState.post).toHaveBeenCalledWith(
        "/novels/p1/chapters/vol-1-ch-1/dossier/rows",
        { action: "accept", domain: "settings" },
      ),
    );
    expect(apiState.post).toHaveBeenCalledWith(
      "/novels/p1/chapters/vol-1-ch-1/dossier/rows",
      { action: "accept", domain: "items" },
    );
    expect(apiState.post).toHaveBeenCalledWith(
      "/novels/p1/chapters/vol-1-ch-1/dossier/rows",
      { action: "accept", domain: "knowledge" },
    );
    expect(apiState.post).not.toHaveBeenCalledWith(
      "/novels/p1/chapters/vol-1-ch-1/dossier/rows",
      { action: "accept" },
    );
  });
});

describe("RelationChangesSection（角色关系页签区块）", () => {
  it("只渲染关系行＋本域全采纳；设定/物品/认知不进", async () => {
    apiState.get.mockResolvedValue(state({
      rows: ROWS, progress: { pending: 4, accepted: 1, rejected: 0 },
    }));
    apiState.post.mockResolvedValue({ ok: true, updated: 1 });
    render(<RelationChangesSection projectId="p1" chapterRef="vol-1-ch-1" />);
    expect(await screen.findByTestId("relation-changes-section")).toBeTruthy();
    expect(screen.getByText(/林野 → 阿蓟：盟友（并肩）/)).toBeTruthy();
    expect(screen.queryByText("物品")).toBeNull();
    fireEvent.click(screen.getByText("本域全采纳（1）"));
    await waitFor(() =>
      expect(apiState.post).toHaveBeenCalledWith(
        "/novels/p1/chapters/vol-1-ch-1/dossier/rows",
        { action: "accept", domain: "relations" },
      ),
    );
  });

  it("空且非提取中：不渲染", async () => {
    render(<RelationChangesSection projectId="p1" chapterRef="vol-1-ch-1" />);
    await waitFor(() => expect(apiState.get).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByTestId("relation-changes-section")).toBeNull());
  });
});
