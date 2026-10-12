// useDeconstructTasks（RQ refetchInterval＋failRef 守卫版）：
// 决策纯函数全分支＋集成：活动轮询、终态停表、连续失败守卫停表。
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

const state = vi.hoisted(() => ({ list: vi.fn() }));
vi.mock("@/lib/deconstructApi", () => ({ listDeconstructTasks: state.list }));

import {
  deconstructRefetchInterval,
  useDeconstructTasks,
} from "@/hooks/useDeconstructTasks";

function renderProbe() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  function Probe() {
    useDeconstructTasks(true);
    return null;
  }
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Probe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return () => state.list.mock.calls.length;
}

const ACTIVE_RESP = {
  tasks: [{ id: "t", status: "running" }],
  heartbeat: { running: 1, queued: 0 },
  badge: 1,
};
const DONE_RESP = {
  tasks: [{ id: "t", status: "completed" }],
  heartbeat: { running: 0, queued: 0 },
  badge: 0,
};

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("deconstructRefetchInterval 决策", () => {
  it("failures≥3 → false（守卫停表）", () => {
    expect(deconstructRefetchInterval(ACTIVE_RESP as never, 3)).toBe(false);
    expect(deconstructRefetchInterval(undefined, 5)).toBe(false);
  });
  it("无数据 → 1500（先轮一次）", () => {
    expect(deconstructRefetchInterval(undefined, 0)).toBe(1500);
  });
  it("有活动任务 → 1500；全终态 → false", () => {
    expect(deconstructRefetchInterval(ACTIVE_RESP as never, 0)).toBe(1500);
    expect(deconstructRefetchInterval(DONE_RESP as never, 0)).toBe(false);
  });
});

describe("useDeconstructTasks 集成", () => {

  it("enabled=false 不轮询", async () => {
    vi.useFakeTimers();
    state.list.mockResolvedValue(ACTIVE_RESP);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    function Off() {
      useDeconstructTasks(false);
      return null;
    }
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <Off />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await vi.advanceTimersByTimeAsync(5000);
    expect(state.list.mock.calls.length).toBe(0);
  });

  it("活动任务轮询；全终态停表", async () => {
    vi.useFakeTimers();
    state.list.mockResolvedValue(ACTIVE_RESP);
    const getCalls = renderProbe();
    await vi.advanceTimersByTimeAsync(10);
    const during = getCalls();
    expect(during).toBeGreaterThanOrEqual(1);
    await vi.advanceTimersByTimeAsync(4500);
    expect(getCalls()).toBeGreaterThan(during);

    state.list.mockResolvedValue(DONE_RESP);
    await vi.advanceTimersByTimeAsync(2000);
    const settled = getCalls();
    await vi.advanceTimersByTimeAsync(5000);
    expect(getCalls()).toBe(settled); // 终态停表
  });


  it("queryFn 非 Error 值拒绝 → 包装为加载失败", async () => {
    vi.useFakeTimers();
    state.list.mockRejectedValue("plain-string-reason");
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    function Probe() {
      const { error } = useDeconstructTasks(true);
      if (error) console.log("[probe] err=", String(error).slice(0, 60));
      return null;
    }
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <Probe />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await vi.advanceTimersByTimeAsync(10);
    // 第 2、3 次失败：failRef 达 3 → queryFn 抛包装后的「加载失败」（三元假臂）
    state.list.mockRejectedValue(new Error("third"));
    await vi.advanceTimersByTimeAsync(4000);
    cleanup();
    vi.useRealTimers();
  });

  it("连续失败守卫：3 次失败后停表不再增长", async () => {
    vi.useFakeTimers();
    state.list.mockImplementation(async () => {
      throw new Error("down");
    });
    const getCalls = renderProbe();
    await vi.advanceTimersByTimeAsync(6000);
    const stalled = getCalls();
    expect(stalled).toBeGreaterThanOrEqual(3); // 失败期确实在轮询
    await vi.advanceTimersByTimeAsync(8000);
    expect(getCalls()).toBe(stalled); // 守卫停表（failRef≥3 → refetchInterval false）
  });
});
