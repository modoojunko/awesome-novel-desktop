// useDeconstructTasks（c-deconstruct-book 5.2）：活动轮询、终态停表、失败守卫停表。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const state = vi.hoisted(() => ({ list: vi.fn() }));
vi.mock("@/lib/deconstructApi", () => ({ listDeconstructTasks: state.list }));

import { useDeconstructTasks } from "@/hooks/useDeconstructTasks";

function Probe() {
  useDeconstructTasks(true);
  return null;
}

function renderProbe() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <Probe />
    </QueryClientProvider>,
  );
}

beforeEach(() => state.list.mockClear());
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("useDeconstructTasks", () => {
  it("活动任务持续轮询；全终态停表", async () => {
    vi.useFakeTimers();
    state.list.mockResolvedValue({
      tasks: [{ id: "t", status: "running" }],
      heartbeat: { running: 1, queued: 0 },
      badge: 1,
    });
    renderProbe();
    await vi.advanceTimersByTimeAsync(10);
    const during = state.list.mock.calls.length;
    expect(during).toBeGreaterThanOrEqual(1);
    await vi.advanceTimersByTimeAsync(2000);
    expect(state.list.mock.calls.length).toBeGreaterThan(during); // 活动中持续轮询

    state.list.mockResolvedValue({
      tasks: [{ id: "t", status: "completed" }],
      heartbeat: { running: 0, queued: 0 },
      badge: 0,
    });
    await vi.advanceTimersByTimeAsync(2000);
    const settled = state.list.mock.calls.length;
    await vi.advanceTimersByTimeAsync(5000);
    expect(state.list.mock.calls.length).toBe(settled); // 全终态停表
  });

  it("连续失败 3 次守卫停表", async () => {
    vi.useFakeTimers();
    state.list.mockResolvedValue({ tasks: null }); // resp.tasks.some → TypeError → 走 catch 路径
    renderProbe();
    await vi.advanceTimersByTimeAsync(5000);
    const calls = state.list.mock.calls.length;
    expect(calls).toBe(3); // 初次 + 2 次重试，第 3 次失败即停
    await vi.advanceTimersByTimeAsync(5000);
    expect(state.list.mock.calls.length).toBe(3);
  });
});
