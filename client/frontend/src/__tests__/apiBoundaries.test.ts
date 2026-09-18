// lib/api.ts 边界分支补齐（覆盖率专项）：
//   503 三种响应体 / 403 member_required / 错误附件（novels·reason·field·current·rev）
//   api.* 包装器逐个发得出去 / importParse·importPersist·importTemplate
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "@/lib/toast";

vi.mock("@/lib/toast", () => ({
  toast: { error: vi.fn(), info: vi.fn(), success: vi.fn() },
}));

let mod: typeof import("@/lib/api");
let fetchMock: ReturnType<typeof vi.fn>;

const jsonRes = (status: number, body: unknown) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => body,
  text: async () => JSON.stringify(body),
});

beforeEach(async () => {
  vi.clearAllMocks(); // toast 是 mock 模块：不清调用记录会跨用例累积，负向断言必假红
  vi.resetModules();
  vi.unstubAllGlobals();
  localStorage.setItem("auth_token", "tok-edge");
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  mod = await import("@/lib/api");
});

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.removeItem("auth_token");
});

describe("request() 503 三态", () => {
  it("JSON detail 为字符串：透出该文案并按 infra 提示", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({ detail: "模型服务暂不可用" }),
      text: async () => JSON.stringify({ detail: "模型服务暂不可用" }),
    });
    const err = (await mod.request("/novels").catch((e) => e)) as Error & { status?: number };
    expect(err.status).toBe(503);
    expect(err.message).toBe("模型服务暂不可用");
    // 非 AI 前置 → infra 级全局提示（503 三种响应体里只有这一支该弹）
    expect(toast.info).toHaveBeenCalledWith("云端服务唤醒中（约 30–60 秒），请稍后重试");
  });

  it("detail 为对象（AI 前置三态）：reason 透传且不弹 infra 全局提示", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({ detail: { reason: "no_key", message: "尚未配置模型 API Key" } }),
      text: async () => JSON.stringify({ detail: { reason: "no_key", message: "尚未配置模型 API Key" } }),
    });
    const err = (await mod.request("/novels").catch((e) => e)) as Error & { reason?: string; status?: number };
    expect(err.reason).toBe("no_key");
    expect(err.status).toBe(503);
    expect(err.message).toBe("尚未配置模型 API Key");
    // AI 前置三态是「可操作引导」不是服务不可用 → 不得弹 infra 全局提示
    expect(toast.info).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("detail 为对象但无 message：兜底不炸（不显示 undefined）", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({ detail: { reason: "storage_busy" } }),
      text: async () => JSON.stringify({ detail: { reason: "storage_busy" } }),
    });
    const err = (await mod.request("/novels").catch((e) => e)) as Error & { reason?: string; status?: number };
    expect(err.status).toBe(503);
    expect(err.reason).toBe("storage_busy");
    expect(err.message).toBe("Service unavailable"); // detail 无 message → 503 兜底
  });

  it("响应体无 detail 字段：仍抛 503 且走兜底文案（else if 的假臂）", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({}),
      text: async () => "{}",
    });
    const err = (await mod.request("/novels").catch((e) => e)) as Error & { status?: number };
    expect(err.status).toBe(503);
    expect(err.message).toBe("Service unavailable");
  });

  it("quiet 形态：503 不弹任何全局提示（调用方就地提示）", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({ detail: "模型服务暂不可用" }),
      text: async () => JSON.stringify({ detail: "模型服务暂不可用" }),
    });
    await mod.request("/novels", { quiet: true }).catch(() => {});
    expect(toast.info).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("非 JSON 响应体（云托管冷启动）：不炸、抛 503", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 503,
      text: async () => {
        throw new Error("body unreadable");
      },
    });
    const err = (await mod.request("/novels").catch((e) => e)) as Error & { status?: number };
    expect(err.status).toBe(503);
  });
});

describe("request() 403 member_required", () => {
  it("抛错带 reason 并广播全局升级引导（非 quiet）", async () => {
    const seen: string[] = [];
    const onBlock = (e: Event) => seen.push((e as CustomEvent<{ message: string }>).detail.message);
    window.addEventListener("member-block", onBlock);
    fetchMock.mockResolvedValue(jsonRes(403, { detail: { reason: "member_required", message: "AI 是会员功能" } }));
    const err = (await mod.request("/novels/1/settings/ai/arc/draft", { method: "POST" }).catch((e) => e)) as Error & {
      reason?: string;
      status?: number;
    };
    window.removeEventListener("member-block", onBlock);
    expect(err.reason).toBe("member_required");
    expect(err.status).toBe(403);
    expect(seen).toEqual(["AI 是会员功能"]);
  });

  it("quiet 形态：抛错但零全局广播", async () => {
    const spy = vi.fn();
    window.addEventListener("member-block", spy);
    fetchMock.mockResolvedValue(jsonRes(403, { detail: { reason: "member_required" } }));
    await mod.request("/novels/1/settings/ai/arc/draft", { method: "POST", quiet: true }).catch(() => {});
    window.removeEventListener("member-block", spy);
    expect(spy).not.toHaveBeenCalled();
  });
});

describe("request() 错误附件透传", () => {
  it("detail 是对象但无 message：回落中文通用文案（不漏 undefined）", async () => {
    fetchMock.mockResolvedValue(jsonRes(409, { detail: { novels: ["a"] } }));
    const err = (await mod.request("/novels", { method: "POST" }).catch((e) => e)) as Error & {
      novels?: string[];
      message: string;
    };
    expect(err.novels).toEqual(["a"]);
    expect(err.message).toBe("请求失败（HTTP 409）");
  });
  it("detail 的 novels / reason / field / current / rev 全部挂到 Error 上", async () => {
    fetchMock.mockResolvedValue(
      jsonRes(409, {
        detail: {
          message: "冲突",
          novels: ["a", "b"],
          reason: "rev_conflict",
          field: "hook_3",
          current: { v: 1 },
          rev: 7,
        },
      }),
    );
    const err = (await mod.request("/novels/1/settings/hooks", { method: "PUT" }).catch((e) => e)) as Error & {
      novels?: string[];
      reason?: string;
      field?: string;
      current?: unknown;
      rev?: number;
      status?: number;
    };
    expect(err.status).toBe(409);
    expect(err.novels).toEqual(["a", "b"]);
    expect(err.reason).toBe("rev_conflict");
    expect(err.field).toBe("hook_3");
    expect(err.current).toEqual({ v: 1 });
    expect(err.rev).toBe(7);
  });
});

describe("api.* 包装器逐个发得出去（URL / 方法 / body）", () => {
  it("novels 与 story-arc 家族", async () => {
    fetchMock.mockResolvedValue(jsonRes(200, { ok: true }));
    await mod.api.fetchPhaseStatus("n1");
    await mod.api.createNovel({ name: "书", genre: "科幻" });
    await mod.api.renameNovel("n1", "新名");
    await mod.api.fetchStory("n1");
    await mod.api.updateStory("n1", "简介");
    await mod.api.fetchStoryArc("n1");
    await mod.api.updateStoryArc("n1", { fullstory: "x" });
    await mod.api.runArcAi("n1", "draft", { input: "词" });
    const calls = fetchMock.mock.calls as Array<[string, RequestInit]>;
    expect(calls.map(([u, i]) => `${i.method ?? "GET"} ${String(u).replace(/^.*\/api/, "")}`)).toEqual([
      "GET /novels/n1/workflow/phase-status",
      "POST /novels",
      "PATCH /novels/n1",
      "GET /novels/n1/story",
      "PUT /novels/n1/story",
      "GET /novels/n1/story/arc",
      "PUT /novels/n1/story/arc",
      "POST /novels/n1/settings/ai/arc/draft",
    ]);
    expect(JSON.parse(String(calls[1][1].body))).toEqual({ name: "书", genre: "科幻" });
    expect(JSON.parse(String(calls[2][1].body))).toEqual({ name: "新名" });
    expect(JSON.parse(String(calls[4][1].body))).toEqual({ synopsis: "简介" });
    expect(JSON.parse(String(calls[7][1].body))).toEqual({ input: "词" });
});

  it("post/put/patch 不带 body：仍发得出去（body 缺省分支）", async () => {
    fetchMock.mockResolvedValue(jsonRes(200, { ok: true }));
    await mod.api.post("/novels/1/confirm");
    await mod.api.put("/novels/1/story");
    await mod.api.patch("/novels/1");
    const calls = fetchMock.mock.calls as Array<[string, RequestInit]>;
    expect(calls.map(([, i]) => i.method)).toEqual(["POST", "PUT", "PATCH"]);
    for (const [, init] of calls) expect(init.body).toBeUndefined();
  });
});

describe("导入端点", () => {
  it("importParse 成功：返回解析结果", async () => {
    fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => ({ title: "书", volumes: [] }) });
    const file = new File(["# x"], "b.md", { type: "text/markdown" });
    await expect(mod.importParse(file)).resolves.toEqual({ title: "书", volumes: [] });
  });

  it("importPersist 包装器：POST 到 persist 并带 token", async () => {
    fetchMock.mockResolvedValue(jsonRes(200, { ok: true }));
    await mod.importPersist({ name: "书", volumes: [] });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(String(url)).toContain("/novels/import/persist");
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok-edge");
  });

  it("downloadTemplate 无 token：不发 Authorization 头", async () => {
    localStorage.removeItem("auth_token");
    fetchMock.mockResolvedValue({ ok: true, status: 200, text: async () => "模板" });
    await expect(mod.downloadTemplate()).resolves.toBe("模板");
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((init.headers as Record<string, string>).Authorization).toBeUndefined();
  });

  it("downloadTemplate：成功取文本；失败抛中文", async () => {
    fetchMock.mockResolvedValue({ ok: true, status: 200, text: async () => "模板正文" });
    await expect(mod.downloadTemplate()).resolves.toBe("模板正文");
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok-edge");

    fetchMock.mockResolvedValue({ ok: false, status: 404, text: async () => "" });
    await expect(mod.downloadTemplate()).rejects.toThrow("模板下载失败");
  });
});
