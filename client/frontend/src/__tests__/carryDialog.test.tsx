/** c-lossless-upgrade — 带回四步卡（CarryDialog）＋数据层单例（carryStore）。
 *  钉：两块平级清单／一次点击覆盖两样、进度锁定（无取消/收起）、结果两变体、
 *  完成确认＝finishDialog 放行队列、稍后带＝不出队、单例单请求。 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import CarryDialog from "@/components/CarryDialog";
import type { LegacyCandidate } from "@/hooks/useLegacyDb";

// ── 桩：api／toast／dialogQueue／carryStore ──────────────────────────────
const apiState = vi.hoisted(() => ({
  post: vi.fn(async (_path: string, _body?: unknown) => ({ code: 0 })),
  get: vi.fn(async (_path: string, _opts?: unknown) => ({ code: 0, data: {} })),
}));
vi.mock("@/lib/api", () => ({ api: apiState }));

const queueState = vi.hoisted(() => ({
  finish: vi.fn(),
  enqueue: vi.fn(),
}));
vi.mock("@/lib/dialogQueue", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/dialogQueue")>();
  return {
    ...actual,
    finishDialog: queueState.finish,
    enqueueDialog: queueState.enqueue,
  };
});

const storeState = vi.hoisted(() => ({
  job: null as null | Record<string, unknown>,
  watch: vi.fn(),
}));
vi.mock("@/lib/carryStore", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/carryStore")>();
  return {
    ...actual,
    useCarryStore: () => ({ job: storeState.job, status: null }),
    watchCarryJob: storeState.watch,
  };
});

const toastState = vi.hoisted(() => ({
  success: vi.fn(), error: vi.fn(), info: vi.fn(), dismiss: vi.fn(),
}));
vi.mock("@/lib/toast", () => ({ toast: toastState }));

const CAND: LegacyCandidate = {
  filename: "novel-v0.28.2.db",
  version: "0.28.2",
  kind: "semver",
  legacy_generation: null,
  size_bytes: 1,
  mtime: 1,
  book_count: 3,
  unreadable: false,
  recommended: true,
  stamp: "s1",
  suppressed: false,
  manifest: {
    books: [
      { name: "长夜灯行", words: 126000 },
      { name: "观星者手记", words: 31000 },
      { name: "河湾旧事", words: 284000 },
    ],
    books_total: 3,
    configs: [{ name: "DeepSeek" }, { name: "朱雀 AI 检测" }],
    configs_total: 2,
  },
};

function renderDialog(over: Partial<Parameters<typeof CarryDialog>[0]> = {}) {
  const qc = new QueryClient();
  const onLater = vi.fn();
  const onConfirmed = vi.fn();
  // 每次全新元素：rerender(同一引用) 会被 React bailout（Object.is 相等跳过渲染）
  const makeEl = () => (
    <QueryClientProvider client={qc}>
      <CarryDialog
        candidate={CAND}
        others={1}
        open
        onLater={onLater}
        onConfirmed={onConfirmed}
        {...over}
      />
    </QueryClientProvider>
  );
  const utils = render(makeEl());
  // job 桩更新不会自动触发重渲染——rere 强制按当前 storeState.job 重画
  const rere = () => act(() => { utils.rerender(makeEl()); });
  return { ...utils, onLater, onConfirmed, rere };
}

beforeEach(() => {
  vi.clearAllMocks();
  storeState.job = null;
});

describe("CarryDialog 四步", () => {
  it("告知卡：作品与模型配置两块平级清单＋更早候选提示行", () => {
    renderDialog();
    const card = screen.getByTestId("carry-card");
    expect(card.textContent).toContain("长夜灯行");
    expect(card.textContent).toContain("12.6 万字");
    expect(card.textContent).toContain("DeepSeek");
    expect(card.textContent).toContain("朱雀 AI 检测");
    expect(card.textContent).toContain("含 API Key 与用量统计");
    expect(card.textContent).toContain("另有更早的 1 份数据");
    expect(screen.getByTestId("carry-start").textContent)
      .toBe("把作品和模型配置带过来"); // 一次点击覆盖两样
  });

  it("清单缺失（老载荷）时降级为数量口径，不阻塞", () => {
    renderDialog({
      candidate: { ...CAND, manifest: null },
    });
    expect(screen.getByTestId("carry-card").textContent).toContain("模型配置随作品一并带过来");
  });

  it("同意→进度锁定：无取消/收起出口，文案明示保持窗口开启", async () => {
    renderDialog();
    await act(async () => {
      fireEvent.click(screen.getByTestId("carry-start"));
    });
    const prog = screen.getByTestId("carry-progress");
    expect(prog.textContent).toContain("请保持本窗口开启");
    expect(prog.textContent).not.toContain("后台继续");
    expect(prog.querySelector("button")).toBeNull(); // 锁定：零按钮
    expect(storeState.watch).toHaveBeenCalled();
  });

  it("完成：正常结果卡→点确认＝finishDialog('carry')＋onConfirmed", async () => {
    const { rere } = renderDialog();
    await act(async () => {
      fireEvent.click(screen.getByTestId("carry-start"));
    });
    // job done（完整）——rere 强制按新 job 重渲染
    storeState.job = {
      state: "done",
      report: {
        status: "ok", complete: true, dead_keys: 0,
        book_count_migrated: 3, tables_skipped: [],
      },
    };
    rere();
    const result = await screen.findByTestId("carry-result");
    expect(result.textContent).toContain("作品和模型配置已经带过来");
    expect(result.textContent).toContain("不用重新粘贴");
    await act(async () => {
      fireEvent.click(screen.getByTestId("carry-confirm"));
    });
    expect(queueState.finish).toHaveBeenCalledWith("carry"); // 队列放行条件＝完成确认
  });

  it("不完整结果卡：警示块＋「先这样/重新带一次」，无「不再提醒」", async () => {
    const { rere } = renderDialog();
    await act(async () => {
      fireEvent.click(screen.getByTestId("carry-start"));
    });
    storeState.job = {
      state: "done",
      report: {
        status: "ok", complete: false, dead_keys: 0,
        book_count_migrated: 2, tables_skipped: [{ table: "x" }],
      },
    };
    rere();
    const result = await screen.findByTestId("carry-result");
    expect(screen.getByTestId("carry-partial")).toBeTruthy();
    expect(result.textContent).toContain("重新带一次");
    expect(result.textContent).toContain("先这样，开始写作");
    expect(result.textContent).not.toContain("不再提醒");
  });

  it("死钥条件句：dead_keys>0 才出现「重新粘贴」", async () => {
    const { rere } = renderDialog();
    await act(async () => {
      fireEvent.click(screen.getByTestId("carry-start"));
    });
    storeState.job = {
      state: "done",
      report: { status: "ok", complete: true, dead_keys: 2, book_count_migrated: 3 },
    };
    rere();
    const result = await screen.findByTestId("carry-result");
    expect(result.textContent).toContain("2 条配置的 Key");
  });

  it("稍后带：收卡但不出队（queue.finish 不被调）", () => {
    const { onLater } = renderDialog();
    fireEvent.click(screen.getByTestId("carry-later"));
    expect(onLater).toHaveBeenCalled();
    expect(queueState.finish).not.toHaveBeenCalled(); // 队列继续被 carry 占住
  });
});

describe("carryStore 单例（5.1）", () => {
  it("并发 refresh 去重为一发请求；轮询仅在 running 时开启", async () => {
    const actual = await vi.importActual<typeof import("@/lib/carryStore")>("@/lib/carryStore");
    const { refreshCarry, resetCarryStoreForTests, watchCarryJob } = actual;
    resetCarryStoreForTests();
    apiState.get.mockClear();
    await Promise.all([refreshCarry(), refreshCarry(), refreshCarry()]);
    const candidatesCalls = apiState.get.mock.calls
      .filter(([url]) => url === "/backup/db-migration/candidates");
    expect(candidatesCalls.length).toBe(1); // 书架+账户菜单同时挂载＝单请求
    // running → 轮询开（status 会被周期打）；idle → 停
    apiState.get.mockResolvedValue({
      code: 0,
      data: { state: "idle", kind: "migration" },
    });
    watchCarryJob();
    await new Promise((r) => setTimeout(r, 50));
    resetCarryStoreForTests();
    const statusCalls = apiState.get.mock.calls
      .filter(([url]) => url === "/backup/db-migration/status").length;
    expect(statusCalls).toBeGreaterThanOrEqual(1);
  });
});
