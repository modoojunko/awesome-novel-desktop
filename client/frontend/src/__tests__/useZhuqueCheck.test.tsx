// useZhuqueCheck 状态仓测试（c-zhuque-ai-detect）：模块级单例的会话语义。
// - 成功映射（segments/proseHash/summary）
// - 在途防抖与 abort（切章卸载中断）
// - 缓存命中不重发（切页签回来直接出结果）
// - stale 链（live 指纹 ≠ 送检指纹 → 变灰；重检恢复）
// - 错误族（401/503/422 透传 status+reason）
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  abortZhuque,
  useZhuqueCheck,
  zhuqueStoreGetState,
  zhuqueStoreReset,
  type ZhuqueResult,
} from "@/hooks/useZhuqueCheck";

function okResult(hash: string, segs = 3): ZhuqueResult {
  return {
    ok: true,
    prose_hash: hash,
    summary: { human_ratio: 0.71, suspect_ratio: 0.24, ai_ratio: 0.05, softmax_confidence: 0.18 },
    segments: Array.from({ length: segs }, (_, i) => ({
      paragraph_index: i,
      label: (i === 0 ? 0 : 2) as 0 | 2,
      confidence: 0.1 * (i + 1),
    })),
    usage_tokens: 777,
  };
}

type Call = { url: string; signal?: AbortSignal };
let calls: Call[] = [];
let responder: (url: string) => { status: number; body: unknown } | undefined;

beforeEach(() => {
  calls = [];
  zhuqueStoreReset();
  responder = undefined;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const u = String(url);
      calls.push({ url: u, signal: init?.signal as AbortSignal | undefined });
      const r = responder?.(u);
      if (r) {
        const bodyText = JSON.stringify(r.body);
        const res: any = {
          ok: r.status < 400,
          status: r.status,
          json: async () => r.body,
          text: async () => bodyText,
        };
        res.clone = () => res;
        return res;
      }
      if (u.includes("/zhuque-check"))
        return { ok: true, status: 200, json: async () => okResult("hash-1") };
      return { ok: true, status: 200, json: async () => ({}) };
    }),
  );
});

afterEach(() => {
  cleanup(); // RTL 自动清理需 vitest globals，未开——显式卸载（跨用例残留订阅会污染后续用例）
  zhuqueStoreReset();
  vi.unstubAllGlobals();
});

describe("useZhuqueCheck 状态仓", () => {
  it("run 成功：状态转 ok、segments 透传、flush 被调用", async () => {
    const flush = vi.fn(async () => {});
    const { result } = renderHook(() => useZhuqueCheck("p1", "ch1"));
    await act(async () => {
      await result.current.run({ flush });
    });
    expect(flush).toHaveBeenCalledOnce();
    expect(result.current.state.status).toBe("ok");
    expect(result.current.state.proseHash).toBe("hash-1");
    expect(result.current.state.result?.segments.length).toBe(3);
    expect(result.current.state.stale).toBe(false);
  });

  it("在途防抖：running 期间重复 run 不发第二发", async () => {
    const { result } = renderHook(() => useZhuqueCheck("p1", "ch1"));
    let release: () => void = () => {};
    responder = (u) => {
      if (u.includes("/zhuque-check")) {
        return undefined; // 挂起由 gate 控制
      }
      return undefined;
    };
    // 用未 resolve 的 fetch 挂起第一发
    let gate: Promise<void>;
    const pending = new Promise<void>((r) => (release = r));
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        calls.push({ url: String(url) });
        if (String(url).includes("/zhuque-check")) {
          await pending;
          return { ok: true, status: 200, json: async () => okResult("hash-hang") };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      }),
    );
    const first = result.current.run();
    await waitFor(() => expect(result.current.state.status).toBe("running"));
    await act(async () => {
      await result.current.run(); // 防抖：应直接返回
    });
    expect(calls.filter((c) => c.url.includes("/zhuque-check")).length).toBe(1);
    release();
    await act(async () => {
      await first;
    });
    expect(result.current.state.status).toBe("ok");
    void gate;
  });

  it("切章 abort：卸载时中断在途请求", async () => {
    let aborted = false;
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (url: string, init?: RequestInit) =>
          new Promise((_, reject) => {
            calls.push({ url: String(url) });
            init?.signal?.addEventListener("abort", () => {
              aborted = true;
              reject(new DOMException("aborted", "AbortError"));
            });
          }),
      ),
    );
    const { result, unmount } = renderHook(() => useZhuqueCheck("p1", "ch1"));
    const runP = result.current.run().catch(() => {}); // 被中断的 promise 排空，防跨用例泄漏
    await waitFor(() => expect(result.current.state.status).toBe("running"));
    unmount(); // 切章/离开 → cleanup abort
    await waitFor(() => expect(aborted).toBe(true));
    // 卸载后快照冻结：直读仓状态断言（store 已转 idle）
    await waitFor(() => expect(zhuqueStoreGetState("ch1").status).toBe("idle"));
    await act(async () => {
      await runP; // 排空中断后的 rejection
    });
  });

  it("缓存命中：同 ref 二次挂载不重发，直接出结果", async () => {
    const first = renderHook(() => useZhuqueCheck("p1", "ch1"));
    await act(async () => {
      await first.result.current.run();
    });
    expect(calls.filter((c) => c.url.includes("/zhuque-check")).length).toBe(1);
    first.unmount();
    const second = renderHook(() => useZhuqueCheck("p1", "ch1"));
    expect(second.result.current.state.status).toBe("ok"); // 会话内缓存直接恢复
    expect(calls.filter((c) => c.url.includes("/zhuque-check")).length).toBe(1);
  });

  it("stale 链：live 指纹变化 → 变灰；重检恢复", async () => {
    const { result } = renderHook(() => useZhuqueCheck("p1", "ch1"));
    await act(async () => {
      await result.current.run(); // proseHash=hash-1
    });
    act(() => {
      result.current.evaluateStale("hash-1"); // 未变
    });
    expect(result.current.state.stale).toBe(false);
    act(() => {
      result.current.evaluateStale("hash-2"); // 正文已修改
    });
    expect(result.current.state.stale).toBe(true);
    expect(result.current.state.status).toBe("ok"); // 结果保留（变灰不消失）
    // 重检恢复
    responder = (u) =>
      u.includes("/zhuque-check") ? { status: 200, body: okResult("hash-2") } : undefined;
    await act(async () => {
      await result.current.run();
    });
    expect(result.current.state.stale).toBe(false);
    expect(result.current.state.proseHash).toBe("hash-2");
  });

  it.each([
    [401, "zhuque_auth", "API Key 无效或已失效——去「模型配置 → 朱雀」检查或更换"],
    [503, "zhuque_not_configured", "尚未配置朱雀 Key——去「模型配置 → 朱雀」粘贴"],
    [422, "prose_too_long", "正文超出单次检测上限（30000 字），请分段处理"],
    [429, "zhuque_quota", "触发限流或本月免费额度已用完，以腾讯云控制台为准"],
  ])("错误族 %i：透传 status 与可读 message", async (status, reason, message) => {
    const { result } = renderHook(() => useZhuqueCheck("p1", "ch1"));
    responder = (u) =>
      u.includes("/zhuque-check")
        ? { status, body: { detail: { reason, message } } }
        : undefined;
    await act(async () => {
      await result.current.run();
    });
    expect(result.current.state.status).toBe("error");
    expect(result.current.state.error?.status).toBe(status);
    expect(result.current.state.error?.message).toBe(message);
  });

  it("clear：清除标注=结果与标注一并退场", async () => {
    const { result } = renderHook(() => useZhuqueCheck("p1", "ch1"));
    await act(async () => {
      await result.current.run();
    });
    act(() => {
      result.current.clear();
    });
    expect(result.current.state.status).toBe("idle");
  });
});
