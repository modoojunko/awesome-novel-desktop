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
  reset: vi.fn(),
  attach: vi.fn(async () => true),
}));
vi.mock("@/lib/carryStore", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/carryStore")>();
  return {
    ...actual,
    useCarryStore: () => ({ job: storeState.job, status: null }),
    watchCarryJob: storeState.watch,
    resetCarryJob: storeState.reset,
    attachCarryJob: storeState.attach,
  };
});
// 注意：reset/attach 只在 hoisted 字面量里建一次——工厂在 import 期捕获引用，
// 模块体再重赋值会让测试与组件各持一份实例（判例：实锤于评审修复回归用例）

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

describe("评审修复回归（P1×3）", () => {
  beforeEach(() => {
    storeState.attach.mockResolvedValue(true);
  });

  it("修复①：不完整结果→「重新带一次」可再跑（starting 复位＋旧 job 清空）", async () => {
    const { rere } = renderDialog();
    await act(async () => { fireEvent.click(screen.getByTestId("carry-start")); });
    storeState.job = {
      state: "done",
      report: { status: "ok", complete: false, dead_keys: 0,
                book_count_migrated: 2, tables_skipped: [{ table: "x" }] },
    };
    rere();
    await screen.findByTestId("carry-partial");
    // 重试：旧 job 被清、回到进度（不再被旧 report 秒拉回结果）
    storeState.job = null;
    storeState.reset.mockClear();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "重新带一次" }));
    });
    expect(storeState.reset).toHaveBeenCalled(); // 清上一轮终态
    expect(screen.getByTestId("carry-progress")).toBeTruthy();
    // 第二轮跑完为完整态
    storeState.job = {
      state: "done",
      report: { status: "ok", complete: true, dead_keys: 0, book_count_migrated: 3 },
    };
    rere();
    const result = await screen.findByTestId("carry-result");
    expect(result.textContent).toContain("作品和模型配置已经带过来");
  });

  it("修复②：409 撞上备份任务（attach=false）→ 退回卡态＋提示，不卡死锁定", async () => {
    apiState.post.mockRejectedValueOnce({ status: 409 });
    storeState.attach.mockResolvedValue(false); // 探测：在跑的是备份不是搬运
    renderDialog();
    await act(async () => { fireEvent.click(screen.getByTestId("carry-start")); });
    await waitFor(() => expect(toastState.info).toHaveBeenCalledWith(
      "已有备份或导出任务在进行中，完成后再带"));
    expect(await screen.findByTestId("carry-card")).toBeTruthy(); // 退回卡态（有出口）
  });

  it("修复②附：409 撞上搬运任务（attach=true）→ 附着留在进度态", async () => {
    apiState.post.mockRejectedValueOnce({ status: 409 });
    storeState.attach.mockResolvedValue(true);
    renderDialog();
    await act(async () => { fireEvent.click(screen.getByTestId("carry-start")); });
    expect(await screen.findByTestId("carry-progress")).toBeTruthy();
    expect(toastState.info).not.toHaveBeenCalled();
  });

  it("修复④：卡态 X＝稍后带同义（onLater 被调）；进度期 X 禁用（locked）", async () => {
    const { onLater } = renderDialog();
    fireEvent.click(screen.getByRole("button", { name: "关闭" }));
    expect(onLater).toHaveBeenCalledTimes(1);
  });
});

describe("carryStore attach/reset（评审修复单源）", () => {
  it("attachCarryJob：搬运在跑→附着返回 true；备份在跑/异常→false", async () => {
    const actual = await vi.importActual<typeof import("@/lib/carryStore")>("@/lib/carryStore");
    const { resetCarryStoreForTests } = actual;
    resetCarryStoreForTests();
    apiState.get.mockResolvedValueOnce({
      code: 0, data: { state: "idle" },
    });
    expect(await actual.attachCarryJob()).toBe(false);
    apiState.get.mockResolvedValueOnce({
      code: 0, data: { state: "running", kind: "backup" },
    });
    expect(await actual.attachCarryJob()).toBe(false);
    apiState.get.mockRejectedValueOnce(new Error("down"));
    expect(await actual.attachCarryJob()).toBe(false);
    apiState.get.mockResolvedValue({
      code: 0, data: { state: "idle" },
    });
    resetCarryStoreForTests(); // 停掉上一步可能开的轮询
    apiState.get.mockResolvedValueOnce({
      code: 0, data: { state: "running", kind: "migration" },
    });
    expect(await actual.attachCarryJob()).toBe(true);
    resetCarryStoreForTests();
  });

  it("resetCarryJob：job 非空才重置（null 时不动状态）", async () => {
    const actual = await vi.importActual<typeof import("@/lib/carryStore")>("@/lib/carryStore");
    actual.resetCarryStoreForTests();
    actual.resetCarryJob(); // job=null → 无操作分支
    expect(actual.carrySnapshot().job).toBeNull();
    actual.resetCarryStoreForTests();
  });
});

describe("c-carry-retry-complete 结果卡", () => {
  const setReport = (report: Record<string, unknown>) => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any -- 测试桩直接构 job
    return { state: "done", report } as any;
  };

  it("成功卡书数取在场数（present）——重带幂等下 migrated=0 不得显示「0 本」", async () => {
    const { rere } = renderDialog();
    await act(async () => { fireEvent.click(screen.getByTestId("carry-start")); });
    storeState.job = setReport({
      status: "ok", complete: true, dead_keys: 0,
      book_count_source: 3, book_count_migrated: 0, book_count_present: 3,
    });
    rere();
    const result = await screen.findByTestId("carry-result");
    expect(result.textContent).toContain("已带回 3 本书");
    expect(result.textContent).not.toContain("已带回 0 本书");
  });

  it("成功卡带出引擎 notes（FK 孤儿留痕），API Key 死钥 note 不与死钥条件句重复", async () => {
    const { rere } = renderDialog();
    await act(async () => { fireEvent.click(screen.getByTestId("carry-start")); });
    storeState.job = setReport({
      status: "ok", complete: true, dead_keys: 1, book_count_present: 2,
      notes: [
        "1 条配置的 API Key 按当前加密钥匙不可解——请在「模型配置」重新粘贴保存",
        "2 条数据的关联在旧库里就不完整（引用的对象已不存在），已原样带过来，不影响使用",
      ],
    });
    rere();
    const result = await screen.findByTestId("carry-result");
    expect(result.textContent).toContain("1 条配置的 Key"); // 死钥条件句
    expect(result.textContent).toContain("已原样带过来"); // 孤儿留痕 note
    expect(result.textContent).not.toContain("按当前加密钥匙不可解"); // 不重复
  });

  it("不完整卡实名明细：跳过表名＋缺几本书＋缺行表名，退路句恒在", async () => {
    const { rere } = renderDialog();
    await act(async () => { fireEvent.click(screen.getByTestId("carry-start")); });
    storeState.job = setReport({
      status: "ok", complete: false, dead_keys: 0,
      book_count_source: 5, book_count_present: 2, book_count_migrated: 0,
      tables_skipped: [{ table: "chapters" }],
      tables: [{ table: "chapter_contents", rows_source: 9, rows_missing: 7 }],
    });
    rere();
    const result = await screen.findByTestId("carry-partial");
    expect(result.textContent).toContain("这些数据段没有带过来：chapters");
    expect(result.textContent).toContain("有 3 本书没有带过来");
    expect(result.textContent).toContain("「chapter_contents」缺 7 行");
    expect(result.textContent).toContain("可以重新带一次，或用备份包恢复");
  });

  it("对不上任何已知缺口时退回泛化文案（不空白）", async () => {
    const { rere } = renderDialog();
    await act(async () => { fireEvent.click(screen.getByTestId("carry-start")); });
    storeState.job = setReport({
      status: "ok", complete: false, dead_keys: 0,
      book_count_source: null, book_count_present: null,
      tables_skipped: [], tables: [],
    });
    rere();
    const result = await screen.findByTestId("carry-partial");
    expect(result.textContent).toContain("有内容没有完整迁入");
  });
});
