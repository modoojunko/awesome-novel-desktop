// deconstructApi 真实现全分支（c-deconstruct-book）：fetch 打桩。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.stubGlobal("fetch", state.fetch);

import {
  cancelDeconstructTask,
  createDeconstructTask,
  exportTaskProducts,
  fetchModelOptions,
  getDeconstructTask,
  importBookFromTask,
  listDeconstructTasks,
  probeModel,
  retryUploadDeconstructTask,
} from "@/lib/deconstructApi";

function jsonResponse(status: number, body: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

beforeEach(() => state.fetch.mockReset());
afterEach(() => vi.restoreAllMocks());

describe("deconstructApi", () => {
  it("listDeconstructTasks 走 request JSON", async () => {
    state.fetch.mockResolvedValue(jsonResponse(200, { tasks: [], heartbeat: { running: 0, queued: 0 }, badge: 0 }));
    expect((await listDeconstructTasks()).badge).toBe(0);
    expect(String(state.fetch.mock.calls[0][0])).toContain("/api/deconstruct/tasks");
  });

  it("getDeconstructTask 401 → 统一出口文案", async () => {
    state.fetch.mockResolvedValue(jsonResponse(401, {}));
    await expect(getDeconstructTask("t")).rejects.toThrow(/登录状态已失效/);
  });

  it("createDeconstructTask 成功/401/400 三分支", async () => {
    state.fetch.mockResolvedValueOnce(jsonResponse(200, { id: "n1" }));
    const r = await createDeconstructTask(new File(["x"], "a.txt"), {
      bookName: "a", apiConfigId: "c1", model: "m1", selectedDims: ["intro"],
    });
    expect(r.id).toBe("n1");
    expect((state.fetch.mock.calls[0][1].body as FormData).get("api_config_id")).toBe("c1");

    state.fetch.mockResolvedValueOnce(jsonResponse(401, {}));
    await expect(createDeconstructTask(new File(["x"], "a.txt"), { bookName: "a", apiConfigId: "c", model: "m", selectedDims: ["intro"] })).rejects.toThrow("Unauthorized");

    state.fetch.mockResolvedValueOnce(jsonResponse(400, { detail: "文件超过 50MB 上限，请拆分后重试" }));
    await expect(createDeconstructTask(new File(["x"], "a.txt"), { bookName: "a", apiConfigId: "c", model: "m", selectedDims: ["intro"] })).rejects.toThrow("50MB");
  });

  it("probeModel：ok / 无 status / 抛错", async () => {
    state.fetch.mockResolvedValueOnce(jsonResponse(200, { status: "ok" }));
    expect(await probeModel("c1", "m1")).toBe(true);
    state.fetch.mockResolvedValueOnce(jsonResponse(200, { ok: 1 }));
    expect(await probeModel("c1", "m1")).toBe(true);
    state.fetch.mockRejectedValueOnce(new Error("boom"));
    expect(await probeModel("c1", "m1")).toBe(false);
  });

  it("fetchModelOptions：字符串/数组 models、deleted 过滤、无 models 跳过", async () => {
    state.fetch.mockResolvedValueOnce(jsonResponse(200, [
      { id: "c1", name: "A", vendor: "v", models: '["m1","m2"]' },
      { id: "c2", name: "B", vendor: "v", models: ["m3"], status: "deleted" },
      { id: "c3", name: "C", vendor: "v" },
    ]));
    expect((await fetchModelOptions()).map((o) => o.model)).toEqual(["m1", "m2"]);
  });

  it("cancel/importBook/export/retryUpload 走对应端点", async () => {
    state.fetch.mockResolvedValue(jsonResponse(200, { ok: 1 }));
    await cancelDeconstructTask("t");
    await importBookFromTask("t");
    await exportTaskProducts("t", "/tmp/x", ["简介.md"]);
    await retryUploadDeconstructTask("t", new File(["x"], "a.txt"));
    const urls = state.fetch.mock.calls.map(([u]) => String(u));
    expect(urls.filter((u) => u.includes("/api/deconstruct/tasks/t")).length).toBe(4);
  });
});
