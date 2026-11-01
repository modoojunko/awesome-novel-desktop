/** 写法块 SSE 事件解析测试（c-kb-write-block 批D）：write_block 事件驱动回调、
 *  未知事件类型静默忽略（旧前端容错口径的回归钉）。 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { streamChapterWrite } from "@/lib/ai";

function sseResponse(lines: string[]) {
  const stream = new ReadableStream({
    start(controller) {
      const enc = new TextEncoder();
      for (const line of lines) controller.enqueue(enc.encode(`data: ${line}\n\n`));
      controller.close();
    },
  });
  return new Response(stream, { status: 200 });
}

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("streamChapterWrite write_block 事件", () => {
  it("write_block 事件 → onWriteBlock 收到载荷", async () => {
    const payload = {
      type: "write_block",
      block: "【本章写法指引】…红线与契约优先…",
      run_id: "run-1",
      items: [{ entry_id: "e1", clause: "手法", reason: "场面：打斗", score: 0.9, text: "交锋先让三招。" }],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => sseResponse([JSON.stringify({ type: "phase", phase: "model" }), JSON.stringify(payload)])),
    );
    localStorage.setItem("auth_token", "tok");
    const onWriteBlock = vi.fn();
    streamChapterWrite("p1", "vol-1-ch-1", {
      onChunk: vi.fn(),
      onDone: vi.fn(),
      onError: vi.fn(),
      onWriteBlock,
    });
    await vi.waitFor(() => expect(onWriteBlock).toHaveBeenCalled());
    expect(onWriteBlock.mock.calls[0][0].block).toContain("本章写法指引");
    expect(onWriteBlock.mock.calls[0][0].items[0].entry_id).toBe("e1");
  });

  it("未启用库（无 write_block 事件）→ 不触发；未知事件类型静默忽略", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        sseResponse([
          JSON.stringify({ type: "phase", phase: "model" }),
          JSON.stringify({ type: "future_unknown", x: 1 }),
          JSON.stringify({ type: "done", full_text: "正文" }),
        ]),
      ),
    );
    localStorage.setItem("auth_token", "tok");
    const onWriteBlock = vi.fn();
    const onDone = vi.fn();
    streamChapterWrite("p1", "vol-1-ch-1", {
      onChunk: vi.fn(),
      onDone,
      onError: vi.fn(),
      onWriteBlock,
    });
    await vi.waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(onWriteBlock).not.toHaveBeenCalled(); // 未启用书零渲染的服务端前提
  });
});
