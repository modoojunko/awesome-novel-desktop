import { describe, it, expect, vi, beforeEach } from "vitest";
import { introAi, genreAi, aiBlockReason, detailMessage } from "@/lib/ai";

// 简介 AI 调用层（genre-signup-redesign tasks 3.5 / D7）
describe("detailMessage 归一化", () => {
  it("字符串 detail 直接返回", () => {
    expect(detailMessage("请求出错", "兜底")).toBe("请求出错");
  });
  it("对象 detail 取 message（防 [object Object]）", () => {
    expect(detailMessage({ reason: "no_key", message: "先去模型配置" }, "兜底")).toBe(
      "先去模型配置",
    );
  });
  it("空/未知 detail 回退兜底", () => {
    expect(detailMessage(undefined, "兜底")).toBe("兜底");
    expect(detailMessage({}, "兜底")).toBe("兜底");
  });
});

describe("aiBlockReason 分派", () => {
  it("识别四种 AI 前置原因", () => {
    expect(aiBlockReason({ reason: "member_required" })).toBe("member_required");
    expect(aiBlockReason({ reason: "no_key" })).toBe("no_key");
    expect(aiBlockReason({ reason: "missing_model" })).toBe("missing_model");
    expect(aiBlockReason({ reason: "invalid" })).toBe("invalid");
  });
  it("非前置错误返回 null", () => {
    expect(aiBlockReason(new Error("网络错误"))).toBeNull();
    expect(aiBlockReason({ reason: "other" })).toBeNull();
  });
});

describe("introAi 请求形态", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("POST 到 /settings/ai/intro/{action}，入参 title + content（当前草稿）", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ six_segments: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await introAi("introspect", { title: "我的书", content: "草稿正文" }, "pid-1");
    const [url, init] = spy.mock.calls[0];
    expect(String(url)).toContain("/novels/pid-1/settings/ai/intro/introspect");
    expect(init?.method).toBe("POST");
    const body = JSON.parse(String(init?.body));
    expect(body).toEqual({ title: "我的书", content: "草稿正文" });
  });

  it("fill 带 missing_segments（仅补缺段）", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ missing: [], act: "insert" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await introAi(
      "fill",
      { title: "书", content: "草稿", missingSegments: ["本来的生活"] },
      "pid-2",
    );
    const body = JSON.parse(String(spy.mock.calls[0][1]?.body));
    expect(body.missing_segments).toEqual(["本来的生活"]);
  });
});

// tasks 9.1.7：题材字段 AI 的 URL/入参形态
describe("genreAi 请求形态", () => {
  beforeEach(() => vi.restoreAllMocks());

  it.each(["core_promise", "forbidden_list", "cost_ratio", "battlefield", "track"] as const)(
    "POST /settings/ai/genre/%s，入参 title + context",
    async (field) => {
      const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
        new Response(JSON.stringify({ value: "x" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
      await genreAi(field, { title: "我的书", context: { current: "旧值" } }, "pid-1");
      const [url, init] = spy.mock.calls[0];
      expect(String(url)).toContain(`/novels/pid-1/settings/ai/genre/${field}`);
      expect(init?.method).toBe("POST");
      expect(JSON.parse(String(init?.body))).toEqual({
        title: "我的书",
        context: { current: "旧值" },
      });
    },
  );

  it("context 缺省为空对象", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ value: 1 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await genreAi("cost_ratio", { title: "书" }, "p1");
    expect(JSON.parse(String(spy.mock.calls[0][1]?.body)).context).toEqual({});
  });
});

// 网关层 502（无 JSON 体）→ 人话提示，不把 "Bad Gateway" 丢给用户
describe("doJsonPost 5xx 文案（走 introAi 入口）", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("502 且响应体是 HTML（nginx 无上游）→ 「服务暂时不可用」", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("<html><body>502 Bad Gateway</body></html>", {
        status: 502,
        headers: { "Content-Type": "text/html" },
      }),
    );
    const err = await introAi("fill", { title: "书", content: "内容" }, "p1").catch((e) => e);
    expect(err.message).toContain("服务暂时不可用");
    expect(err.message).not.toContain("Bad Gateway");
  });

  it("502 带 JSON detail（应用层 AI 失败）→ 保留可读 detail", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "AI 生成失败，可重试：超时" }), {
        status: 502,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const err = await introAi("fill", { title: "书", content: "内容" }, "p1").catch((e) => e);
    expect(err.message).toContain("AI 生成失败，可重试");
  });
});
