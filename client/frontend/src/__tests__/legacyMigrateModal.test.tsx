import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import LegacyMigrateModal from "@/components/LegacyMigrateModal";
import type { LegacyCandidate, QuarantinedLibrary } from "@/hooks/useLegacyDb";

/** 清理清单 UI 与只读隔离件清单（c-db-per-version，UP-12 前端半）。
 *
 * 覆盖：单候选「一次确认」自动预演；结果页清理入口的**两态**（全部成功才出现）；
 * 待删清单渲染与两段确认；不可读隔离件的只读清单。 */

const getMock = vi.fn();
const postMock = vi.fn();
vi.mock("@/lib/api", () => ({
  api: {
    get: (...a: unknown[]) => getMock(...a),
    post: (...a: unknown[]) => postMock(...a),
  },
}));
vi.mock("@/lib/toast", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warn: vi.fn() },
}));

const cand = (over: Partial<LegacyCandidate> = {}): LegacyCandidate => ({
  filename: "novel-v1.db",
  version: null,
  kind: "legacy",
  legacy_generation: 1,
  size_bytes: 2048,
  mtime: 1758500000,
  book_count: 2,
  unreadable: false,
  recommended: true,
  stamp: "s",
  suppressed: false,
  ...over,
});

const quarantined: QuarantinedLibrary[] = [
  { filename: "novel-v0.25.db.corrupt-20260922-1", size_bytes: 4096, mtime: 1758500000 },
];

const PREVIEW_OK = { code: 0, data: { v: 1, book_count_source: 2, tables_skipped: [] } };
const DONE_OK = {
  code: 0,
  data: {
    state: "done",
    report: {
      status: "ok",
      book_count_source: 2,
      book_count_migrated: 2,
      book_count_target_after: 2,
      fk_violations: [],
    },
  },
};

function routeApi(status: unknown = DONE_OK) {
  getMock.mockImplementation((url: string) => {
    if (url.includes("/status")) return Promise.resolve(status);
    if (url.includes("/retention")) {
      return Promise.resolve({
        code: 0,
        data: {
          keep: 2,
          items: [
            { filename: "novel-v0.20.db", book_count: 1, size_bytes: 20480, mtime: 1758400000 },
            { filename: "novel-v0.19.db", book_count: 3, size_bytes: 30720, mtime: 1758300000 },
          ],
        },
      });
    }
    return Promise.resolve({ code: 0, data: {} });
  });
  postMock.mockImplementation((url: string) => {
    if (url.includes("/preview")) return Promise.resolve(PREVIEW_OK);
    if (url.includes("/start")) return Promise.resolve({ code: 0, data: { state: "running" } });
    if (url.includes("/cleanup")) {
      return Promise.resolve({ code: 0, data: { deleted: ["novel-v0.20.db", "novel-v0.19.db"], refused: [] } });
    }
    return Promise.resolve({ code: 0, data: {} });
  });
}

async function renderToResult(report: Record<string, unknown>) {
  routeApi({ code: 0, data: { state: "done", report } });
  const onDone = vi.fn();
  render(
    <LegacyMigrateModal open candidates={[cand()]} quarantined={quarantined}
                        onClose={vi.fn()} onDone={onDone} />,
  );
  // 单候选＝一次确认：打开即预演（无需点「下一步」）
  const confirm = await screen.findByRole("button", { name: "把上一版的作品带过来" });
  fireEvent.click(confirm);                     // 第二次点击：启动搬运
  await screen.findByText(/已带回 \d+ 本书/, {}, { timeout: 5000 });
  return onDone;
}

describe("带回向导：清理清单与只读隔离件", () => {
  beforeEach(() => {
    getMock.mockReset();
    postMock.mockReset();
  });

  it("单候选打开即预演（一次确认路径）", async () => {
    routeApi();
    render(<LegacyMigrateModal open candidates={[cand()]} onClose={vi.fn()} onDone={vi.fn()} />);
    // 自动预演后直接停在预览步：主按钮可见，且未点过「下一步」
    expect(await screen.findByRole("button", { name: "把上一版的作品带过来" })).toBeTruthy();
    await waitFor(() =>
      expect(postMock.mock.calls.some((c) => String(c[0]).includes("/preview"))).toBe(true),
    );
    expect(screen.queryByRole("button", { name: "下一步" })).toBeNull();
  });

  it("只读隔离件清单在发现步列出（不提供带回动作；多候选不走自动预演）", async () => {
    routeApi();
    render(
      <LegacyMigrateModal
        open
        candidates={[cand(), cand({ filename: "novel-v0.24.db", kind: "semver", version: "0.24",
                                    legacy_generation: null, book_count: 5 })]}
        quarantined={quarantined}
        onClose={vi.fn()}
        onDone={vi.fn()}
      />,
    );
    // 多候选：停在发现步（需手点「下一步」），隔离件以只读清单呈现
    expect(await screen.findByText("下一步")).toBeTruthy();
    expect(screen.getByText(/另有 1 份旧文件读不出来/)).toBeTruthy();
    expect(screen.getByText(/4 KB/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /带回.*读不出来|恢复.*读不出来/ })).toBeNull();
  });

  it("全部成功：结果页出现清理入口 → 清单 → 两段确认 → 调 cleanup", async () => {
    await renderToResult({
      status: "ok", book_count_source: 2, book_count_migrated: 2,
      book_count_target_after: 2, fk_violations: [],
    });
    const entry = await screen.findByRole("button", { name: /清理旧文件/ });
    fireEvent.click(entry);
    expect(await screen.findByText("1 本")).toBeTruthy();       // 后端给的书数
    expect(screen.getByText("3 本")).toBeTruthy();
    expect(screen.getByText(/删除不可撤销，已带回的内容不受影响/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "删除这些旧文件" }));
    const finalBtn = screen.getByRole("button", { name: /确认删除/ });
    fireEvent.click(finalBtn);
    await waitFor(() => {
      const call = postMock.mock.calls.find((c) => String(c[0]).includes("/cleanup"));
      expect(call).toBeTruthy();
      expect((call![1] as { filenames: string[] }).filenames).toEqual([
        "novel-v0.20.db", "novel-v0.19.db",
      ]);
    });
  });

  it("部分失败（有书没带回）：结果页不出现清理入口", async () => {
    await renderToResult({
      status: "ok", book_count_source: 5, book_count_migrated: 2,
      book_count_target_after: 2, fk_violations: [],
    });
    expect(screen.queryByRole("button", { name: /清理旧文件/ })).toBeNull();
  });

  it("有 FK 违规（部分失败）：结果页不出现清理入口", async () => {
    await renderToResult({
      status: "ok", book_count_source: 2, book_count_migrated: 2,
      book_count_source_after: 2, fk_violations: [{ table: "chapters" }],
    });
    expect(screen.queryByRole("button", { name: /清理旧文件/ })).toBeNull();
  });
});
