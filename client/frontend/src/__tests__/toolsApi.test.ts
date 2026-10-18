// deconstructApi 真实现全分支（c-deconstruct-book）：fetch 打桩。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.stubGlobal("fetch", state.fetch);

import {
  cancelDeconstructTask,
  deleteDeconstructTask,
  resumeDeconstructTask,
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

function jsonRejectResponse(status: number) {
  return { ok: status < 300, status, json: async () => { throw new Error("bad json"); } };
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


  it("create/retry 的 JSON 解析失败 → 兜底文案 catch 臂", async () => {
    state.fetch.mockResolvedValueOnce(jsonRejectResponse(400));
    await expect(createDeconstructTask(new File(["x"], "a.txt"), { bookName: "a", apiConfigId: "c", model: "m", selectedDims: ["intro"] })).rejects.toThrow("创建失败");
    state.fetch.mockResolvedValueOnce(jsonRejectResponse(400));
    await expect(retryUploadDeconstructTask("t", new File(["x"], "a.txt"))).rejects.toThrow("重传失败");
  });

  it("probeModel json 拒绝 → false", async () => {
    state.fetch.mockResolvedValueOnce(jsonRejectResponse(200));
    expect(await probeModel("c1", "m1")).toBe(false);
  });

  it("fetchModelOptions：models 非串非数组 → 跳过", async () => {
    state.fetch.mockResolvedValueOnce(jsonResponse(200, [
      { id: "c9", name: "N", vendor: "v", models: 123 },
      { id: "c10", name: "E", vendor: "v", models: "" },
    ]));
    expect(await fetchModelOptions()).toEqual([]);
  });


  it("authHeaders：有 token 时注入 Bearer（真臂）", async () => {
    localStorage.setItem("auth_token", "tok-123");
    state.fetch.mockResolvedValueOnce(jsonResponse(200, { id: "n1" }));
    await createDeconstructTask(new File(["x"], "a.txt"), { bookName: "a", apiConfigId: "c", model: "m", selectedDims: ["intro"] });
    const headers = state.fetch.mock.calls[0][1].headers as Record<string, string>;
    expect(headers["Authorization"]).toBe("Bearer tok-123");
    localStorage.removeItem("token");
  });

  it("drop 解析失败臂：create 走 bad-json 兜底后不崩", async () => {
    state.fetch.mockResolvedValueOnce(jsonRejectResponse(500));
    await expect(createDeconstructTask(new File(["x"], "a.txt"), { bookName: "a", apiConfigId: "c", model: "m", selectedDims: ["intro"] })).rejects.toThrow("创建失败");
  });

  it("probeModel：ok / 无 status / 抛错", async () => {
    state.fetch.mockResolvedValueOnce(jsonResponse(200, { status: "ok" }));
    expect(await probeModel("c1", "m1")).toBe(true);
    state.fetch.mockResolvedValueOnce(jsonResponse(200, { ok: 1 }));
    expect(await probeModel("c1", "m1")).toBe(true);
    state.fetch.mockRejectedValueOnce(new Error("boom"));
    expect(await probeModel("c1", "m1")).toBe(false);
  });


  it("retryUploadDeconstructTask 401/失败/成功三态", async () => {
    state.fetch.mockResolvedValueOnce(jsonResponse(401, {}));
    await expect(retryUploadDeconstructTask("t", new File(["x"], "a.txt"))).rejects.toThrow("Unauthorized");
    state.fetch.mockResolvedValueOnce(jsonResponse(400, { detail: "文件超过 50MB 上限，请拆分后重试" }));
    await expect(retryUploadDeconstructTask("t", new File(["x"], "a.txt"))).rejects.toThrow("50MB");
    state.fetch.mockResolvedValueOnce(jsonResponse(200, { status: "queued" }));
    expect((await retryUploadDeconstructTask("t", new File(["x"], "a.txt"))).status).toBe("queued");
  });

  it("importBookFromTask 与 exportTaskProducts 走 request（返回值透传）", async () => {
    state.fetch.mockResolvedValueOnce(jsonResponse(200, { book_id: "b1" }));
    expect((await importBookFromTask("t")).book_id).toBe("b1");
    expect(JSON.parse(state.fetch.mock.calls[0][1].body)).toEqual({});  // 无 items＝旧口径（空 body）
    state.fetch.mockResolvedValueOnce(jsonResponse(200, { book_id: "b2" }));
    await importBookFromTask("t", ["world", "relations"]);
    expect(JSON.parse(state.fetch.mock.calls[1][1].body)).toEqual({ items: ["world", "relations"] });
    state.fetch.mockResolvedValueOnce(jsonResponse(200, { written: ["简介.md"], readme: "README.md", dest: "/tmp/x" }));
    const r = await exportTaskProducts("t", "/tmp/x", ["简介.md"]);
    expect(r.dest).toBe("/tmp/x");
  });


  it("deleteDeconstructTask 走 DELETE 端点", async () => {
    state.fetch.mockResolvedValueOnce(jsonResponse(200, { deleted: "t" }));
    await deleteDeconstructTask("t");
    expect(String(state.fetch.mock.calls[0][0])).toContain("/api/deconstruct/tasks/t");
    expect(state.fetch.mock.calls[0][1].method).toBe("DELETE");
  });

  it("resumeDeconstructTask 走 resume 端点", async () => {
    state.fetch.mockResolvedValueOnce(jsonResponse(200, { status: "queued" }));
    const r = await resumeDeconstructTask("t");
    expect(r.status).toBe("queued");
    expect(String(state.fetch.mock.calls[0][0])).toContain("/resume");
    expect(state.fetch.mock.calls[0][1].body).toBe("{}");
  });

  it("resumeDeconstructTask 换模型续拆 → 携 api_config_id/ai_model（c-deconstruct-resilience）", async () => {
    state.fetch.mockResolvedValueOnce(jsonResponse(200, { status: "queued" }));
    await resumeDeconstructTask("t", { apiConfigId: "cfg-9", model: "m-9" });
    expect(JSON.parse(state.fetch.mock.calls[0][1].body)).toEqual({
      api_config_id: "cfg-9",
      ai_model: "m-9",
    });
  });


  it("listDeconstructTasks 401 → 统一出口文案", async () => {
    state.fetch.mockResolvedValueOnce(jsonResponse(401, {}));
    await expect(listDeconstructTasks()).rejects.toThrow(/登录状态已失效/);
  });

  it("importBookFromTask 409 → HTTP 文案", async () => {
    state.fetch.mockResolvedValueOnce(jsonResponse(409, {}));
    await expect(importBookFromTask("t")).rejects.toThrow(/HTTP 409/);
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
