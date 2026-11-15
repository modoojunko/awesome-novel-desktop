import { afterEach, describe, expect, it, vi } from "vitest";

import { formatWan, streamAssistantChat } from "@/lib/chatApi";

// SSE 流解析契约（沿用 prose-stream 测试口径：mock ReadableStream）
function sseResponse(lines: string[]): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const line of lines) controller.enqueue(encoder.encode(`${line}\n`));
      controller.close();
    },
  });
  return new Response(stream, { status: 200 });
}

const okFetch = (lines: string[]) =>
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(sseResponse(lines))));

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("chatApi streamAssistantChat", () => {
  it("逐事件转发：run_start/narration/artifact/run_end", async () => {
    okFetch([
      'data: {"type":"run_start","runId":"r1"}',
      'data: {"type":"narration","text":"先读主线"}',
      'data: {"type":"artifact","runId":"r1","cardId":"c1","kind":"text","payload":{"x":1}}',
      'data: {"type":"run_end","runId":"r1"}',
      "",
    ]);
    const events: string[] = [];
    const done = vi.fn();
    await new Promise<void>((resolve) => {
      streamAssistantChat(
        "p1",
        { message: "铺一下", page: "volume" },
        {
          onEvent: (e) => events.push(e.type),
          onDone: () => {
            done();
            resolve();
          },
          onError: () => resolve(),
        },
      );
    });
    expect(events).toEqual(["run_start", "narration", "artifact", "run_end"]);
    expect(done).toHaveBeenCalled();
  });

  it("无终态＝按失败收尾（c-prose-stream-silent-hang 同口径）", async () => {
    okFetch(['data: {"type":"run_start","runId":"r1"}', ""]);
    const onError = vi.fn();
    await new Promise<void>((resolve) => {
      streamAssistantChat("p1", { message: "x", page: "" }, {
        onEvent: () => undefined,
        onError: (m) => {
          onError(m);
          resolve();
        },
      });
    });
    expect(onError).toHaveBeenCalledWith(expect.stringContaining("连接中断"));
  });

  it("401 走认证失效统一出口", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("{}", { status: 401 }))));
    const onError = vi.fn();
    await new Promise<void>((resolve) => {
      streamAssistantChat("p1", { message: "x", page: "" }, {
        onEvent: () => undefined,
        onError: (m) => {
          onError(m);
          resolve();
        },
      });
    });
    expect(onError).toHaveBeenCalledWith("登录状态已失效，请重新登录");
  });

  it("HTTP 非 200 转可读错误（带状态码）", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response('{"detail":"message 不能为空"}', { status: 422 }))),
    );
    const onError = vi.fn();
    await new Promise<void>((resolve) => {
      streamAssistantChat("p1", { message: "", page: "" }, {
        onEvent: () => undefined,
        onError: (m) => {
          onError(m);
          resolve();
        },
      });
    });
    expect(onError).toHaveBeenCalledWith(expect.stringContaining("message 不能为空"));
  });
});

describe("formatWan（上下文容量口语刻度）", () => {
  it("≥1万 → 万刻度一位小数（整数位不带 .0）；<1万 → 原数", () => {
    expect(formatWan(128000)).toBe("12.8万");
    expect(formatWan(588000)).toBe("58.8万");
    expect(formatWan(1000000)).toBe("100万");
    expect(formatWan(9999)).toBe("9999");
    expect(formatWan(0)).toBe("0");
  });
});

