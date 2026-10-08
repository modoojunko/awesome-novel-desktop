/** c-lossless-upgrade — 壳层弹窗队列（shell-dialog-queue）单测。
 *  钉：去重、优先级（数据>能力）、finish 放行下一条、clear、稍后带不出队。 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  clearDialogQueue,
  dialogQueueHead,
  dialogQueueSnapshot,
  enqueueDialog,
  finishDialog,
} from "@/lib/dialogQueue";

beforeEach(() => {
  clearDialogQueue();
});

describe("dialogQueue", () => {
  it("队首立即放行", () => {
    const carry = vi.fn();
    enqueueDialog("carry", 1, carry);
    expect(carry).toHaveBeenCalledTimes(1);
    expect(dialogQueueHead()).toBe("carry");
  });

  it("同 id 重复入队去重（StrictMode 双挂载）", () => {
    const a = vi.fn();
    const b = vi.fn();
    enqueueDialog("carry", 1, a);
    enqueueDialog("carry", 1, b);
    expect(a).toHaveBeenCalledTimes(1);
    expect(b).not.toHaveBeenCalled();
  });

  it("数据优先于能力：carry 在队时 pack 不入场，finish 后才放行", () => {
    const carry = vi.fn();
    const pack = vi.fn();
    enqueueDialog("carry", 1, carry);
    enqueueDialog("pack", 2, pack);
    expect(pack).not.toHaveBeenCalled(); // 队列只延迟呈现
    finishDialog("carry"); // 用户点「完成确认」
    expect(pack).toHaveBeenCalledTimes(1);
  });

  it("已放行的条目不被抢占：能力先开、数据后到 → 数据等其收尾（无半路掀窗）", () => {
    const pack = vi.fn();
    const carry = vi.fn();
    enqueueDialog("pack", 2, pack);
    enqueueDialog("carry", 1, carry);
    expect(pack).toHaveBeenCalledTimes(1); // pack 已是队首被放行（呈现在前是既成事实）
    expect(carry).not.toHaveBeenCalled(); // carry 优先级高但不抢占已放行条目，等 pack finish
    finishDialog("pack");
    expect(carry).toHaveBeenCalledTimes(1);
  });

  it("稍后带＝不出队：队列继续被占住（放行条件＝完成确认）", () => {
    const carry = vi.fn();
    const pack = vi.fn();
    enqueueDialog("carry", 1, carry);
    enqueueDialog("pack", 2, pack);
    // 「稍后带」只收卡——不调用 finishDialog
    expect(dialogQueueSnapshot()).toBe("carry*,pack");
    expect(pack).not.toHaveBeenCalled();
  });

  it("clear 清空队列与放行态（登出/换号）", () => {
    const carry = vi.fn();
    enqueueDialog("carry", 1, carry);
    clearDialogQueue();
    expect(dialogQueueHead()).toBeNull();
    const again = vi.fn();
    enqueueDialog("carry", 1, again); // 清后可重新入队
    expect(again).toHaveBeenCalledTimes(1);
  });

  it("finish 不存在的 id 无副作用", () => {
    expect(() => finishDialog("nonsense")).not.toThrow();
  });
});
