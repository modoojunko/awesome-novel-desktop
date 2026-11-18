import { afterEach, describe, expect, it, vi } from "vitest";

import {
  adoptAssistantMessage,
  approveGate,
  clearAssistantPersona,
  clearWriterProfile,
  formatWan,
  loadAssistantPersona,
  loadAssistantSession,
  loadWriterProfile,
  pauseWriterProfile,
  resetAssistantSession,
  setPermissionTier,
  stopAssistantRun,
  streamAssistantChat,
  updateAssistantPersona,
  updateWriterProfile,
} from "@/lib/chatApi";

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

  it("HTTP 非 200 且响应体非 JSON → statusText 兜底（.catch 箭头）", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("boom", { status: 502 }))));
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
    expect(onError).toHaveBeenCalledWith(expect.stringContaining("HTTP 502"));
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



// ── 会话元数据／回执／批复／停止／人格／画像（c-agent-nav / c-agent-session-files / 决策档案回归面）──

const jsonOk = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const jsonErr = (detail: string, status = 400) =>
  new Response(JSON.stringify({ detail }), { status, headers: { "Content-Type": "application/json" } });

describe("loadAssistantSession", () => {
  it("200：返回会话元数据与消息（thread 走 query）", async () => {
    const fetchMock = vi.fn((..._a: unknown[]) =>
      Promise.resolve(jsonOk({ sessionId: "s1", pageCursor: "ch:og", grants: {}, messages: [{ id: "m1", seq: 1, role: "user", page: "", content: "hi", cardKind: "", status: "done", payload: {}, createdAt: "" }] })),
    );
    vi.stubGlobal("fetch", fetchMock);
    const out = await loadAssistantSession("b1", "ch:og");
    expect(out.sessionId).toBe("s1");
    expect(out.messages).toHaveLength(1);
    expect(String(fetchMock.mock.calls[0][0])).toContain("thread=ch%3Aog");
  });

  it("401 抛认证失效", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("{}", { status: 401 }))));
    await expect(loadAssistantSession("b1", "")).rejects.toThrow("登录状态已失效");
  });

  it("!ok 抛 detail 人话", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonErr("会话读取失败", 500))));
    await expect(loadAssistantSession("b1", "")).rejects.toThrow("会话读取失败");
    // 响应体非 JSON → detail 兜底（r.json().catch(() => null) 箭头）
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("not-json", { status: 502 }))));
    await expect(loadAssistantSession("b1", "")).rejects.toThrow("会话读取失败");
  });
});

describe("resetAssistantSession", () => {
  it("200 通过；!ok 抛错", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonOk({ ok: true }))));
    await expect(resetAssistantSession("b1", "ch:og")).resolves.toBeUndefined();
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("{}", { status: 401 }))));
    await expect(resetAssistantSession("b1", "")).rejects.toThrow("登录状态已失效");
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("not-json", { status: 500 }))));
    await expect(resetAssistantSession("b1", "")).rejects.toThrow("重置失败");
  });
});

describe("adoptAssistantMessage（apiJsonWithAuth 三态）", () => {
  it("200 通过", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonOk({ ok: true }))));
    await expect(adoptAssistantMessage("b1", "card1")).resolves.toBeUndefined();
  });
  it("401 抛认证失效；!ok 抛 detail", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("{}", { status: 401 }))));
    await expect(adoptAssistantMessage("b1", "c")).rejects.toThrow("登录状态已失效");
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonErr("操作失败", 500))));
    await expect(adoptAssistantMessage("b1", "c")).rejects.toThrow("操作失败");
  });
});

describe("approveGate", () => {
  it("200 通过；401/!ok 抛错", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonOk({ ok: true }))));
    await expect(approveGate("b1", "g1", "approved")).resolves.toBeUndefined();
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("{}", { status: 401 }))));
    await expect(approveGate("b1", "g1", "denied")).rejects.toThrow("登录状态已失效");
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("not-json", { status: 500 }))));
    await expect(approveGate("b1", "g1", "denied")).rejects.toThrow("批复失败");
  });
});

describe("setPermissionTier", () => {
  it("200 通过；!ok 抛错（无 401 分支——档位接口走本地鉴权）", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonOk({ ok: true }))));
    await expect(setPermissionTier("b1", "allow_book")).resolves.toBeUndefined();
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("not-json", { status: 500 }))));
    await expect(setPermissionTier("b1", "allow_all")).rejects.toThrow("档位设置失败");
  });
});

describe("stopAssistantRun", () => {
  it("200 stopped=false（幂等）通过；401/!ok 抛错", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonOk({ ok: true, stopped: false }))));
    await expect(stopAssistantRun("b1", "ch:og")).resolves.toBeUndefined();
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("{}", { status: 401 }))));
    await expect(stopAssistantRun("b1", "ch:og")).rejects.toThrow("登录状态已失效");
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("not-json", { status: 500 }))));
    await expect(stopAssistantRun("b1", "x")).rejects.toThrow("停止失败");
  });
});

describe("persona 三件", () => {
  it("load：200 返回 identity＋customized；401/!ok 抛错", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonOk({ identity: { name: "老编" }, customized: true }))));
    const out = await loadAssistantPersona("b1");
    expect(out.customized).toBe(true);
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("{}", { status: 401 }))));
    await expect(loadAssistantPersona("b1")).rejects.toThrow("登录状态已失效");
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("not-json", { status: 500 }))));
    await expect(loadAssistantPersona("b1")).rejects.toThrow("人格读取失败");
  });
  it("update：PUT 带 identity；200 返回；!ok 抛错", async () => {
    const fetchMock = vi.fn((..._a: unknown[]) => Promise.resolve(jsonOk({ identity: { name: "新" }, customized: true })));
    vi.stubGlobal("fetch", fetchMock);
    const out = await updateAssistantPersona("b1", { name: "新" });
    expect(out.identity.name).toBe("新");
    expect((fetchMock.mock.calls[0] as unknown[])[1] ? ((fetchMock.mock.calls[0][1] ?? {}) as { method?: string }).method : undefined).toBe("PUT");
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("{}", { status: 401 }))));
    await expect(updateAssistantPersona("b1", { name: "x" })).rejects.toThrow("登录状态已失效");
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("not-json", { status: 500 }))));
    await expect(updateAssistantPersona("b1", { name: "x" })).rejects.toThrow("人格保存失败");
  });
  it("clear：DELETE；!ok 抛错", async () => {
    const fetchMock = vi.fn((..._a: unknown[]) => Promise.resolve(jsonOk({ ok: true })));
    vi.stubGlobal("fetch", fetchMock);
    await expect(clearAssistantPersona("b1")).resolves.toBeUndefined();
    expect((fetchMock.mock.calls[0][1] as { method?: string }).method).toBe("DELETE");
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("{}", { status: 401 }))));
    await expect(clearAssistantPersona("b1")).rejects.toThrow("登录状态已失效");
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("not-json", { status: 500 }))));
    await expect(clearAssistantPersona("b1")).rejects.toThrow("恢复默认失败");
  });
});

describe("writer profile 四件", () => {
  it("load：200 返回 sections＋paused；401/!ok 抛错", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonOk({ sections: { naming: {} }, paused: false }))));
    const out = await loadWriterProfile("b1");
    expect(out.paused).toBe(false);
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("{}", { status: 401 }))));
    await expect(loadWriterProfile("b1")).rejects.toThrow("登录状态已失效");
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("not-json", { status: 500 }))));
    await expect(loadWriterProfile("b1")).rejects.toThrow("画像读取失败");
  });
  it("update/clear/pause：apiJsonWithAuth 三态", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonOk({ ok: true }))));
    await expect(updateWriterProfile("b1", { naming: {} })).resolves.toBeUndefined();
    await expect(clearWriterProfile("b1")).resolves.toBeUndefined();
    await expect(pauseWriterProfile("b1", true)).resolves.toBeUndefined();
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("{}", { status: 401 }))));
    await expect(updateWriterProfile("b1", {})).rejects.toThrow("登录状态已失效");
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("not-json", { status: 500 }))));
    await expect(clearWriterProfile("b1")).rejects.toThrow("操作失败");
    await expect(pauseWriterProfile("b1", false)).rejects.toThrow("操作失败");
  });
});

describe("streamAssistantChat 边界", () => {
  it("response.body 缺失 → onError「无法读取响应流」", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(null, { status: 200 }))));
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
    expect(onError).toHaveBeenCalledWith("无法读取响应流");
  });

  it("effect 事件照常转发（c-agent-nav navigate 即时事件）", async () => {
    okFetch([
      'data: {"type":"effect","action":"navigate","domain":"ui","target":"prose","description":"切到正文"}',
      'data: {"type":"run_end","runId":"r1"}',
      "",
    ]);
    const events: string[] = [];
    await new Promise<void>((resolve) => {
      streamAssistantChat("p1", { message: "x", page: "" }, {
        onEvent: (e) => events.push(e.type),
        onDone: () => resolve(),
        onError: () => resolve(),
      });
    });
    expect(events).toEqual(["effect", "run_end"]);
  });

  it("fetch 网络异常 → onError 带原始消息；AbortError 静默吞（主动中断不算错）", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("ECONNREFUSED"))));
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
    expect(onError).toHaveBeenCalledWith("ECONNREFUSED");
    // 无 message 错误 →「连接失败」兜底
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error())));
    const onError3 = vi.fn();
    await new Promise<void>((resolve) => {
      streamAssistantChat("p1", { message: "x", page: "" }, {
        onEvent: () => undefined,
        onError: (m) => {
          onError3(m);
          resolve();
        },
      });
    });
    expect(onError3).toHaveBeenCalledWith("连接失败");

    const abortErr = new Error("The user aborted a request.");
    abortErr.name = "AbortError";
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(abortErr)));
    const onError2 = vi.fn();
    await new Promise<void>((resolve) => {
      streamAssistantChat("p1", { message: "x", page: "" }, {
        onEvent: () => undefined,
        onError: () => {
          onError2();
          resolve();
        },
        onDone: () => resolve(),
      });
      setTimeout(resolve, 80); // AbortError 静默分支：无任何回调——超时兜底收口
    });
    expect(onError2).not.toHaveBeenCalled();
  });

  it("非 JSON data 行跳过不炸", async () => {
    okFetch(["data: not-json", 'data: {"type":"run_end","runId":"r"}', ""]);
    const events: string[] = [];
    await new Promise<void>((resolve) => {
      streamAssistantChat("p1", { message: "x", page: "" }, {
        onEvent: (e) => events.push(e.type),
        onDone: () => resolve(),
        onError: () => resolve(),
      });
    });
    expect(events).toEqual(["run_end"]);
  });
});

describe("streamAssistantChat 返回的 abort 句柄", () => {
  it("调用返回的 abort 函数 → AbortError 被吞（不炸不误报）", async () => {
    // 永不完成的流——abort 中断
    const never = new ReadableStream<Uint8Array>({ start() {} });
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(never, { status: 200 }))));
    const onError = vi.fn();
    await new Promise<void>((resolve) => {
      const abort = streamAssistantChat("p1", { message: "x", page: "" }, {
        onEvent: () => undefined,
        onError: () => {
          onError();
          resolve();
        },
        onDone: () => resolve(),
      });
      setTimeout(() => {
        abort();
        setTimeout(resolve, 60);
      }, 40);
    });
    expect(onError).not.toHaveBeenCalled();
  });
});
