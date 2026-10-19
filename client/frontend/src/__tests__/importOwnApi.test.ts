import { beforeEach, describe, expect, it, vi } from "vitest";

function okJson(data: unknown) {
  return { status: 200, ok: true, json: async () => data } as unknown as Response;
}
function res401() {
  return { status: 401, ok: false, json: async () => ({ detail: "Unauthorized" }) } as unknown as Response;
}
function res503() {
  return { status: 503, ok: false, json: async () => ({ detail: "cold" }) } as unknown as Response;
}
function res400(detail: string) {
  return { status: 400, ok: false, json: async () => ({ detail }) } as unknown as Response;
}

let mod: typeof import("@/lib/api");

beforeEach(async () => {
  vi.clearAllMocks();
  vi.resetModules();
  vi.unstubAllGlobals();
  window.location.hash = "";
  localStorage.setItem("auth_token", "tok-123");
  localStorage.setItem("auth_username", "tester");
  mod = await import("@/lib/api");
});

describe("importOwnParse", () => {
  it("成功：POST /novels/import/own/parse，带 token 与 FormData", async () => {
    const payload = { import_id: "i1", chapter_count: 2, volumes: [], chapters: [], risk: { level: "ok" } };
    const fetchMock = vi.fn().mockResolvedValue(okJson(payload));
    vi.stubGlobal("fetch", fetchMock);
    const file = new File(["第1章 开端\n正文"], "book.txt", { type: "text/plain" });
    await expect(mod.importOwnParse(file)).resolves.toEqual(payload);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/novels/import/own/parse"),
      expect.objectContaining({ method: "POST", body: expect.any(FormData) }),
    );
  });

  it("无 token 也发（服务端 401 统一处理）", async () => {
    localStorage.clear();
    const fetchMock = vi.fn().mockResolvedValue(okJson({ import_id: "i2" }));
    vi.stubGlobal("fetch", fetchMock);
    await mod.importOwnParse(new File(["x"], "a.txt"));
    const headers = (fetchMock.mock.calls[0][1] as RequestInit).headers as Record<string, string>;
    expect(headers.Authorization).toBeUndefined();
  });

  it("401：清凭据 + 回登录页", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res401()));
    await mod.importOwnParse(new File(["x"], "a.txt")).catch(() => {});
    expect(localStorage.getItem("auth_token")).toBeNull();
    expect(window.location.hash).toBe("#/login");
  });

  it("503：转可读文案并带 status", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res503()));
    const err = await mod.importOwnParse(new File(["x"], "a.txt")).catch((e) => e);
    expect(err.message).toContain("云端服务暂时不可用");
    expect(err.status).toBe(503);
  });

  it("其它错误：透传服务端 detail", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res400("仅支持 .txt")));
    await expect(mod.importOwnParse(new File(["x"], "a.md"))).rejects.toThrow("仅支持 .txt");
  });

  it("错误无 detail：回落 HTTP 状态文案", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      status: 500, ok: false, json: async () => ({}),
    } as unknown as Response));
    await expect(mod.importOwnParse(new File(["x"], "a.txt"))).rejects.toThrow("HTTP 500");
  });

  it("错误体不可解析：也回落 HTTP 状态文案", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      status: 502, ok: false, json: async () => { throw new Error("not json"); },
    } as unknown as Response));
    await expect(mod.importOwnParse(new File(["x"], "a.txt"))).rejects.toThrow("HTTP 502");
  });
});

describe("importOwnPersist", () => {
  it("POST 持久化端点并返回 id/name", async () => {
    const post = vi.spyOn(mod.api, "post").mockResolvedValue({ id: "b1", name: "长夜灯" } as never);
    const body = {
      import_id: "i1", name: "长夜灯",
      volumes: [{ title: "风起", chapter_from: 1, chapter_to: 2 }],
      import_token: "t1", excluded_source_nos: [],
    };
    await expect(mod.importOwnPersist(body)).resolves.toEqual({ id: "b1", name: "长夜灯" });
    expect(post).toHaveBeenCalledWith("/novels/import/own/persist", body);
  });
});
