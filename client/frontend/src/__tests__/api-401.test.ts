import { beforeEach, describe, expect, it, vi } from "vitest";

// ---------------------------------------------------------------------------
// 401 踢出口径（c-session-flip-stability）：
//   用户动作请求的 401 → 清凭据 + 回登录页（既有行为钉住）
//   探测类（quiet）401 → 零全局副作用：凭据保留、不导航，错误照抛
//   importParse（用户动作，无 quiet 形态）→ 仍踢出
// 显式失效信号（useAuthHeal code 1 + session_invalid）不经过 request()，
// 其行为由 useAuthHeal.test.tsx 覆盖。
// ---------------------------------------------------------------------------

function res401() {
  return {
    status: 401,
    ok: false,
    json: async () => ({ detail: "Unauthorized" }),
    text: async () => "Unauthorized",
  } as unknown as Response;
}

let request: typeof import("@/lib/api")["request"];
let importParse: typeof import("@/lib/api")["importParse"];

beforeEach(async () => {
  vi.clearAllMocks();
  vi.resetModules();
  vi.unstubAllGlobals();
  window.location.hash = "";
  localStorage.setItem("auth_token", "tok-123");
  localStorage.setItem("auth_username", "tester");
  const mod = await import("@/lib/api");
  request = mod.request;
  importParse = mod.importParse;
});

describe("request() 401 踢出口径", () => {
  it("用户动作 401：清凭据 + 回登录页 + 抛错带 status", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res401()));

    const err = await request("/novels").catch((e) => e);
    expect(err).toBeInstanceOf(Error);
    expect(err.status).toBe(401);
    expect(localStorage.getItem("auth_token")).toBeNull();
    expect(window.location.hash).toBe("#/login");
  });

  it("quiet 401：凭据保留、不导航，错误照抛（探测类零全局副作用）", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res401()));

    const err = await request("/auth/check-auth", { quiet: true }).catch((e) => e);
    expect(err).toBeInstanceOf(Error);
    expect(err.status).toBe(401);
    expect(localStorage.getItem("auth_token")).toBe("tok-123");
    expect(localStorage.getItem("auth_username")).toBe("tester");
    expect(window.location.hash).not.toBe("#/login");
  });
});

describe("importParse() 401（用户动作，不豁免）", () => {
  it("清凭据 + 回登录页", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res401()));

    const file = new File(["# 卷一"], "book.md", { type: "text/markdown" });
    await importParse(file).catch(() => {});
    expect(localStorage.getItem("auth_token")).toBeNull();
    expect(window.location.hash).toBe("#/login");
  });
});
