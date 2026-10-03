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
let responder: ((url: string) => { status: number; body: unknown } | undefined) | undefined;

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
    let gate: Promise<void> | undefined;
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
    await waitFor(() => expect(zhuqueStoreGetState("p1", "ch1").status).toBe("idle"));
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
    await act(async () => {
      await result.current.clear();
    });
    expect(result.current.state.status).toBe("idle");
  });
});

// ── 水合（c-zhuque-persist）：仓空读库存档恢复；仓有状态不覆盖 ──


function storedBody(hash: string) {
  return {
    stored: true,
    prose_hash: hash,
    result: okResult(hash),
    checked_at: "2026-09-30T12:00:00+00:00",
  };
}

describe("useZhuqueCheck 水合（c-zhuque-persist）", () => {
  it("仓空且存档在：读库回填 ok＋checkedAt（单飞，不重复 GET）", async () => {
    responder = (u) =>
      u.includes("/zhuque-result") ? { status: 200, body: storedBody("hash-stored") } : undefined;
    const { result } = renderHook(() => useZhuqueCheck("p1", "vol-1-ch-1"));
    await waitFor(() => expect(result.current.state.status).toBe("ok"));
    expect(result.current.state.proseHash).toBe("hash-stored");
    expect(result.current.state.checkedAt).toBe("2026-09-30T12:00:00+00:00");
    const hydrateCalls = calls.filter((c) => c.url.includes("/zhuque-result")).length;
    // 重挂载（同 ref）不再 GET（单飞水位）
    const second = renderHook(() => useZhuqueCheck("p1", "vol-1-ch-1"));
    await act(async () => {});
    expect(calls.filter((c) => c.url.includes("/zhuque-result")).length).toBe(hydrateCalls);
    second.unmount();
  });

  it("仓已有状态（ok）：水合不覆盖会话单源", async () => {
    responder = (u) =>
      u.includes("/zhuque-result") ? { status: 200, body: storedBody("hash-old") } : undefined;
    const { result } = renderHook(() => useZhuqueCheck("p2", "vol-1-ch-2"));
    // 抢先注 ok 会话状态（模拟刚检测完）
    await act(async () => {
      const { runZhuqueCheck } = await import("@/hooks/useZhuqueCheck");
      responder = (u) => (u.includes("/zhuque-check") ? { status: 200, body: okResult("hash-fresh") } : undefined);
      await runZhuqueCheck("p2", "vol-1-ch-2");
    });
    const freshHash = result.current.state.proseHash;
    // 水合已在此前 idle 时单飞发起；此处强制再触发一次挂载，档不应顶掉会话结果
    const second = renderHook(() => useZhuqueCheck("p2", "vol-1-ch-2"));
    await act(async () => {});
    expect(result.current.state.proseHash).toBe(freshHash);
    second.unmount();
  });

  it("stored:false：维持 idle", async () => {
    responder = (u) => (u.includes("/zhuque-result") ? { status: 200, body: { stored: false } } : undefined);
    const { result } = renderHook(() => useZhuqueCheck("p3", "vol-1-ch-3"));
    await act(async () => {});
    expect(result.current.state.status).toBe("idle");
  });

  it("水合请求失败：静默降级 idle，不反复打", async () => {
    let n = 0;
    responder = (u) => {
      if (u.includes("/zhuque-result")) {
        n += 1;
        return { status: 500, body: { message: "boom" } };
      }
      return undefined;
    };
    const { result } = renderHook(() => useZhuqueCheck("p4", "vol-1-ch-4"));
    await act(async () => {});
    expect(result.current.state.status).toBe("idle");
    const second = renderHook(() => useZhuqueCheck("p4", "vol-1-ch-4"));
    await act(async () => {});
    expect(n).toBe(1); // 失败同样记水位，不反复打
    second.unmount();
  });
});


describe("复合键与清除连档删（c-zhuque-clear-keyscope）", () => {
  it("跨书同 ref 隔离：A 书 ok 态不顶 B 书水合（B 读到 B 的档）", async () => {
    responder = (u) => {
      if (u.includes("/novels/pB/chapters/vol-1-ch-1/zhuque-result"))
        return { status: 200, body: storedBody("hash-bookB") };
      return undefined;
    };
    // A 书：直接注 ok 会话状态
    const a = renderHook(() => useZhuqueCheck("pA", "vol-1-ch-1"));
    await act(async () => {
      const { runZhuqueCheck } = await import("@/hooks/useZhuqueCheck");
      responder = (u) => (u.includes("/zhuque-check") ? { status: 200, body: okResult("hash-bookA") } : undefined);
      await runZhuqueCheck("pA", "vol-1-ch-1");
    });
    expect(a.result.current.state.proseHash).toBe("hash-bookA");
    a.unmount();
    // 恢复 pB 档分支（上面为跑 A 书 check 覆盖过 responder）
    responder = (u) =>
      u.includes("/novels/pB/chapters/vol-1-ch-1/zhuque-result")
        ? { status: 200, body: storedBody("hash-bookB") }
        : undefined;
    // B 书同 ref：水合应读 B 的档（裸键下会被 A 的水位挡住）
    const b = renderHook(() => useZhuqueCheck("pB", "vol-1-ch-1"));
    await waitFor(() => expect(b.result.current.state.status).toBe("ok"));
    expect(b.result.current.state.proseHash).toBe("hash-bookB");
    b.unmount();
  });

  it("清除＝连存档删：DELETE 成功后 idle；DELETE 失败保态", async () => {
    // 成功路径
    responder = (u) => (u.includes("/zhuque-result") ? { status: 200, body: { ok: true } } : undefined);
    const h = renderHook(() => useZhuqueCheck("pC", "chC"));
    await act(async () => {
      const { runZhuqueCheck } = await import("@/hooks/useZhuqueCheck");
      responder = (u) => (u.includes("/zhuque-check") ? { status: 200, body: okResult("hash-c") } : undefined);
      await runZhuqueCheck("pC", "chC");
    });
    expect(h.result.current.state.status).toBe("ok");
    await act(async () => {
      await h.result.current.clear();
    });
    expect(h.result.current.state.status).toBe("idle");
    const delCalls = calls.filter((c) => c.url.includes("zhuque-result")).length;
    expect(delCalls).toBeGreaterThan(0);
    h.unmount();

    // 失败路径：DELETE 500 → 保持 ok（不清态）
    const h2 = renderHook(() => useZhuqueCheck("pD", "chD"));
    await act(async () => {
      const { runZhuqueCheck } = await import("@/hooks/useZhuqueCheck");
      responder = (u) => {
        if (u.includes("/zhuque-result")) return { status: 500, body: { message: "boom" } };
        if (u.includes("/zhuque-check")) return { status: 200, body: okResult("hash-d") };
        return undefined;
      };
      await runZhuqueCheck("pD", "chD");
    });
    expect(h2.result.current.state.status).toBe("ok");
    await act(async () => {
      await h2.result.current.clear();
    });
    expect(h2.result.current.state.status).toBe("ok"); // 删除失败保态
    h2.unmount();
  });
});
