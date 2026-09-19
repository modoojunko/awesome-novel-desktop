// 流式 AI 请求的错误反馈（qa-night 2026-09-19 P1 附加项回归）：
// 生成失败必须可读、可感知——非 2xx 时 onError 携带「后端 detail＋HTTP 状态码」，
// 不再只剩一句英文「Not Found」（路由 404 时用户完全看不懂发生了什么）。
import { afterEach, describe, expect, it, vi } from "vitest";
import { streamChapterWrite } from "@/lib/ai";

const URL_MATCH = /\/novels\/p1\/chapters\/vol-1-ch-1\/write$/;

function stubFetch(status: number, body: unknown) {
  const fetchMock = vi.fn(
    async () =>
      new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("streamChapterWrite 失败反馈", () => {
  it("404 路由错位：onError 带后端 detail 与 HTTP 状态码", async () => {
    stubFetch(404, { detail: "Not Found" });
    localStorage.setItem("auth_token", "tok");

    const onError = vi.fn();
    streamChapterWrite("p1", "vol-1-ch-1", { onError, onChunk: vi.fn(), onDone: vi.fn() });

    await vi.waitFor(() => expect(onError).toHaveBeenCalled());
    expect(onError).toHaveBeenCalledWith("Not Found（HTTP 404）");
  });

  it("业务失败（409 守卫）：透传后端 detail 并附状态码", async () => {
    stubFetch(409, { detail: "还有主线章节未归档" });
    localStorage.setItem("auth_token", "tok");

    const onError = vi.fn();
    streamChapterWrite("p1", "vol-1-ch-1", { onError, onChunk: vi.fn(), onDone: vi.fn() });

    await vi.waitFor(() => expect(onError).toHaveBeenCalled());
    expect(onError).toHaveBeenCalledWith("还有主线章节未归档（HTTP 409）");
  });

  it("请求打的是单段 /write（不带 body 也走 POST + Bearer）", async () => {
    const fetchMock = stubFetch(500, { detail: "boom" });
    localStorage.setItem("auth_token", "tok");

    streamChapterWrite("p1", "vol-1-ch-1", { onError: vi.fn(), onChunk: vi.fn(), onDone: vi.fn() });

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const call = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    const [url, init] = call;
    expect(String(url).replace(/^https?:\/\/[^/]+/, "")).toMatch(URL_MATCH);
    expect(String(url)).not.toContain("/write/write");
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok");
  });
});
