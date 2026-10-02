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
  vi.unstubAllEnvs(); // 个别用例 stub 了 import.meta.env.DEV，不能漏到别的用例
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

// ---------------------------------------------------------------------------
// 覆盖补齐（覆盖率专项）：生产构建不打时间线 / 网络中断原样上抛 /
// 401 探测体读取失败按普通 401 / zhuque_auth 无 message 回落文案 /
// detail.code 语义码透传 / 完本与撤完本包装器
// ---------------------------------------------------------------------------

describe("request() 时间线日志开关", () => {
  it("DEV=true 打 [req-timeline] 诊断日志；DEV=false（生产构建）一条不打", async () => {
    const debugSpy = vi.spyOn(console, "debug").mockImplementation(() => {});
    fetchMock.mockResolvedValue(jsonRes(200, { ok: true }));

    await mod.request("/novels");
    expect(debugSpy).toHaveBeenCalledTimes(1);
    expect(String(debugSpy.mock.calls[0][0])).toContain("[req-timeline]");

    vi.stubEnv("DEV", false); // 模拟生产构建（import.meta.env.DEV 置 falsy）
    debugSpy.mockClear();
    await mod.request("/novels");
    expect(debugSpy).not.toHaveBeenCalled();
    debugSpy.mockRestore();
  });
});

describe("request() 网络中断：非 DOMException 的 AbortError 原样上抛", () => {
  it("fetch 拒绝为普通 Error 且 name=AbortError：不中文化包装、原样抛给调用方按取消处理", async () => {
    const abortErr = Object.assign(new Error("The user aborted a request."), { name: "AbortError" });
    fetchMock.mockRejectedValue(abortErr);
    await expect(mod.request("/novels", { signal: new AbortController().signal })).rejects.toBe(abortErr);
  });
});

describe("request() 401 探测体的两个兜底臂", () => {
  it("响应体读取失败（clone().json() 拒绝）：probe=null，按普通 401 走既有口径", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 401,
      clone: () => ({ json: () => Promise.reject(new Error("body unreadable")) }),
      json: async () => ({}),
    });
    const err = (await mod.request("/novels", { quiet: true }).catch((e) => e)) as Error & { status?: number };
    expect(err.status).toBe(401);
    expect(err.message).toBe("登录状态已失效，请重新登录");
    expect(localStorage.getItem("auth_token")).toBe("tok-edge"); // quiet：不清凭据、不导航
  });

  it("reason=zhuque_auth 但 detail 无 message：回落「API Key 无效或已失效」（不显示 undefined）", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 401,
      clone: () => ({ json: async () => ({ detail: { reason: "zhuque_auth" } }) }),
    });
    const err = (await mod.request("/novels", { quiet: true }).catch((e) => e)) as Error & {
      status?: number;
      reason?: string;
    };
    expect(err.status).toBe(401);
    expect(err.reason).toBe("zhuque_auth");
    expect(err.message).toBe("API Key 无效或已失效");
    expect(localStorage.getItem("auth_token")).toBe("tok-edge"); // 作者配错 Key 不是会话失效，不踢人
  });
});

describe("request() detail.code 语义码透传", () => {
  it("detail.code（建卡撞名 409 的 name_taken）挂到 Error 上供调用方分流", async () => {
    fetchMock.mockResolvedValue(jsonRes(409, { detail: { code: "name_taken", message: "卡片名已存在" } }));
    const err = (await mod.request("/novels/1/cards", { method: "POST" }).catch((e) => e)) as Error & {
      code?: string;
      status?: number;
    };
    expect(err.status).toBe(409);
    expect(err.code).toBe("name_taken");
    expect(err.message).toBe("卡片名已存在");
  });
});

describe("api 完本家族包装器", () => {
  it("finishNovel / reopenNovel：POST 到 finish / reopen，body 为空对象", async () => {
    fetchMock.mockResolvedValue(jsonRes(200, { id: "n1", name: "书", finished_at: null, updated_at: "t" }));
    await mod.api.finishNovel("n1");
    await mod.api.reopenNovel("n1");
    const calls = fetchMock.mock.calls as Array<[string, RequestInit]>;
    expect(calls.map(([u, i]) => `${i.method} ${String(u).replace(/^.*\/api/, "")}`)).toEqual([
      "POST /novels/n1/finish",
      "POST /novels/n1/reopen",
    ]);
    expect(JSON.parse(String(calls[0][1].body))).toEqual({});
    expect(JSON.parse(String(calls[1][1].body))).toEqual({});
  });
});
