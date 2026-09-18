// request() 错误文案口径（c-manuscript-download 评审收口）：
//   errMessage：只有 4xx（确有后端响应）透出原文，网络层/5xx 回落调用方中文兜底
//   网络层失败（fetch 拒绝）统一中文化，避免 Failed to fetch / Load failed 漏给用户
//   非 JSON 响应的兜底文案中文化（不再漏 "Unprocessable Entity" 类 statusText）
//   api.* 透传 quiet（后台轮询探测类请求需要）
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

let request: typeof import("@/lib/api")["request"];
let api: typeof import("@/lib/api")["api"];
let errMessage: typeof import("@/lib/api")["errMessage"];
let importParse: typeof import("@/lib/api")["importParse"];

beforeEach(async () => {
  vi.clearAllMocks();
  vi.resetModules();
  vi.unstubAllGlobals();
  window.location.hash = "";
  localStorage.setItem("auth_token", "tok-err");
  const mod = await import("@/lib/api");
  request = mod.request;
  api = mod.api;
  errMessage = mod.errMessage;
  importParse = mod.importParse;
});

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.removeItem("auth_token");
});

describe("errMessage：只透出可行动的后端 4xx 文案", () => {
  it("4xx（status 存在）→ 透出原文", () => {
    const e = Object.assign(new Error("作品不存在"), { status: 404 });
    expect(errMessage(e, "兜底")).toBe("作品不存在");
  });

  it("网络层失败（无 status）→ 回落兜底，不漏英文", () => {
    expect(errMessage(new TypeError("Failed to fetch"), "下载发起失败，请重试")).toBe(
      "下载发起失败，请重试",
    );
  });

  it("5xx → 回落兜底（503 兜底文案是英文 Service unavailable）", () => {
    const e = Object.assign(new Error("Service unavailable"), { status: 503 });
    expect(errMessage(e, "请重试")).toBe("请重试");
  });

  it("非 Error 值 → 回落兜底", () => {
    expect(errMessage("boom", "请重试")).toBe("请重试");
    expect(errMessage(undefined, "请重试")).toBe("请重试");
  });
});

describe("request() 文案与副作用口径", () => {
  it("网络层失败：抛中文 message，不带 status", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const err = (await request("/novels").catch((e) => e)) as Error & { status?: number };
    expect(err.message).toBe("网络连接失败，请重试");
    expect(err.status).toBeUndefined();
  });

  it("非 JSON 的 4xx 响应：兜底文案中文化（不再漏 statusText）", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        statusText: "Unprocessable Entity",
        json: async () => {
          throw new Error("not json");
        },
      }),
    );
    const err = (await request("/novels").catch((e) => e)) as Error & { status?: number };
    expect(err.status).toBe(422);
    expect(err.message).toBe("请求失败（HTTP 422）");
  });

  it("api.get(path, { quiet }) 透传：401 零全局副作用（凭据保留、不导航）", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({ detail: "未提供认证信息" }),
      }),
    );
    await api.get("/manuscript/download/status", { quiet: true }).catch(() => {});
    expect(localStorage.getItem("auth_token")).toBe("tok-err");
    expect(window.location.hash).not.toBe("#/login");
  });

  it("api.get 不带 quiet：401 仍踢出（用户动作请求口径不变）", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({ detail: "未提供认证信息" }),
      }),
    );
    await api.get("/novels").catch(() => {});
    expect(localStorage.getItem("auth_token")).toBeNull();
    expect(window.location.hash).toBe("#/login");
  });

  it("api.put/patch/delete：方法、body 与 quiet 透传齐全", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ ok: true }) });
    vi.stubGlobal("fetch", fetchMock);
    await api.put("/novels/1/story", { synopsis: "x" });
    await api.patch("/novels/1", { name: "y" });
    await api.delete("/configs/1", { quiet: true });
    const calls = fetchMock.mock.calls as Array<[string, RequestInit]>;
    expect(calls.map(([, i]) => i.method)).toEqual(["PUT", "PATCH", "DELETE"]);
    expect(JSON.parse(String(calls[0][1].body))).toEqual({ synopsis: "x" });
    expect(JSON.parse(String(calls[1][1].body))).toEqual({ name: "y" });
    for (const [, init] of calls) {
      expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok-err");
    }
  });
});

describe("importParse() 错误文案", () => {
  it("JSON detail：透出后端原文", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        json: async () => ({ detail: "不支持的稿件格式" }),
      }),
    );
    const file = new File(["# 卷一"], "book.md", { type: "text/markdown" });
    const err = (await importParse(file).catch((e) => e)) as Error;
    expect(err.message).toBe("不支持的稿件格式");
  });

  it("非 JSON 响应：中文兜底（不漏英文 statusText）", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        statusText: "Internal Server Error",
        json: async () => {
          throw new Error("not json");
        },
      }),
    );
    const file = new File(["# 卷一"], "book.md", { type: "text/markdown" });
    const err = (await importParse(file).catch((e) => e)) as Error;
    expect(err.message).toBe("导入失败（HTTP 500）");
  });
});
