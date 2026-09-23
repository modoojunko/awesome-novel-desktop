// 完本弹窗 · 伏笔清单失败守卫（c-silent-data-guards）：
// 清单加载失败 ≠ 「无伏笔」——失败态可见＋确认钮禁用，重试成功后恢复。
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const apiState = vi.hoisted(() => ({
  finishNovel: vi.fn(),
  reopenNovel: vi.fn(),
}));
const hooksState = vi.hoisted(() => ({
  list: vi.fn(),
  volumes: vi.fn(),
}));
const toastState = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));

vi.mock("@/lib/api", () => ({ api: apiState, errMessage: (e: any, f: string) => e?.message || f }));
vi.mock("@/lib/hooksApi", () => ({ hooksApi: hooksState }));
vi.mock("@/lib/toast", () => ({ toast: toastState }));

import FinishModal from "@/components/novel/FinishModal";

const TARGET = {
  id: "n1",
  name: "测试书",
  total_volumes: 1,
  total_chapters: 3,
  word_count: 1000,
  finished_at: null,
  updated_at: "2026-09-23T00:00:00",
};

beforeEach(() => {
  vi.clearAllMocks();
  hooksState.list.mockResolvedValue({ items: [] });
  hooksState.volumes.mockResolvedValue([]);
});

describe("完本弹窗 · 伏笔清单失败守卫", () => {
  it("清单失败：失败态可见＋「完结这本书」禁用；重试成功后确认恢复", async () => {
    hooksState.list.mockRejectedValue(new Error("503"));
    hooksState.volumes.mockRejectedValue(new Error("503"));
    render(<FinishModal target={TARGET} onClose={vi.fn()} onFinished={vi.fn()} onReopened={vi.fn()} />);
    await waitFor(() => expect(screen.getByText("伏笔清单没加载出来")).toBeInTheDocument());
    expect(screen.getByTestId("finish-confirm")).toBeDisabled();
    // 重试成功 → 失败态退场、确认可点
    hooksState.list.mockResolvedValue({ items: [] });
    hooksState.volumes.mockResolvedValue([]);
    fireEvent.click(screen.getByTestId("finish-reload"));
    await waitFor(() => expect(screen.getByText("伏笔都已回收")).toBeInTheDocument());
    expect(screen.getByTestId("finish-confirm")).not.toBeDisabled();
  });

  it("确无伏笔：确认可点（不因失败态误伤正常路径）", async () => {
    render(<FinishModal target={TARGET} onClose={vi.fn()} onFinished={vi.fn()} onReopened={vi.fn()} />);
    await waitFor(() => expect(screen.getByText("伏笔都已回收")).toBeInTheDocument());
    expect(screen.getByTestId("finish-confirm")).not.toBeDisabled();
  });
});
