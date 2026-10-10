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

// ── c-prose-gen-phases：流内阶段事件透传 ＋ 流无终态事件的失败收尾 ──────────

/** 用 ReadableStream 造真流式响应体（比 Response(string) 更接近真实分块） */
function stubStream(lines: string[]) {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(lines.join("")));
      controller.close();
    },
  });
  const fetchMock = vi.fn(
    async () =>
      new Response(body, {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("流内阶段事件与无终态事件兜底（c-prose-gen-phases）", () => {
  it("phase 事件透传 onPhase；done 到达不触发兜底", async () => {
    stubStream([
      'data: {"type":"phase","phase":"assemble"}\n\n',
      'data: {"type":"phase","phase":"model"}\n\n',
      'data: {"type":"chunk","text":"甲"}\n\n',
      'data: {"type":"done","full_text":"甲"}\n\n',
    ]);
    localStorage.setItem("auth_token", "tok");
    const onPhase = vi.fn();
    const onDone = vi.fn();
    const onError = vi.fn();
    streamChapterWrite("p1", "vol-1-ch-1", { onChunk: vi.fn(), onDone, onError, onPhase });
    await vi.waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(onPhase.mock.calls.map((c) => c[0])).toEqual(["assemble", "model"]);
    expect(onError).not.toHaveBeenCalled();
  });

  it("流干净结束但无 done/error：按失败补报恰一次（半截保留、可重试）", async () => {
    stubStream([
      'data: {"type":"phase","phase":"assemble"}\n\n',
      'data: {"type":"chunk","text":"半截"}\n\n',
    ]);
    localStorage.setItem("auth_token", "tok");
    const onError = vi.fn();
    const onDone = vi.fn();
    streamChapterWrite("p1", "vol-1-ch-1", { onChunk: vi.fn(), onDone, onError });
    await vi.waitFor(() => expect(onError).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 30)); // 静置再看有无第二次
    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError.mock.calls[0][0]).toContain("未收到完成信号");
    expect(onDone).not.toHaveBeenCalled();
  });

  it("error 事件后收流：不补报兜底（终态已出现）", async () => {
    stubStream(['data: {"type":"error","error":"AI 生成失败，可重试：上游挂了"}\n\n']);
    localStorage.setItem("auth_token", "tok");
    const onError = vi.fn();
    streamChapterWrite("p1", "vol-1-ch-1", { onChunk: vi.fn(), onDone: vi.fn(), onError });
    await vi.waitFor(() => expect(onError).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 30));
    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError.mock.calls[0][0]).toContain("上游挂了");
  });
});
