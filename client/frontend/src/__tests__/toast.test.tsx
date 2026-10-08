// 全站 toast 基线（c-toast-dismiss）：默认 3 秒自动消失＋× 手动关闭；sticky 常驻已退役。
// 配方注意（模块级单例 _toasts 无 reset API）：
//   · 必须先 render <Toaster/> 再发 toast——useToasts 初值 useState([]) 不回放挂载前的 toast；
//   · afterEach 跑完所有挂起 timer 让 _toasts 归零，跨用例零泄漏；
//   · 推进时间必须包 act()，否则 notify→setToasts 不刷新。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { toast, Toaster } from "@/lib/toast";

beforeEach(() => {
  vi.useFakeTimers();
  render(<Toaster />); // 空态：toasts.length === 0 提前 return null（先渲染后发，见头注）
});

afterEach(() => {
  act(() => vi.runAllTimers());
  vi.useRealTimers();
});

describe("toast 3 秒自动消失基线", () => {
  it("2999ms 仍在、3000ms 消失", () => {
    act(() => {
      toast.success("已保存");
    });
    expect(screen.getByText("已保存")).toBeTruthy();
    act(() => {
      vi.advanceTimersByTime(2999);
    });
    expect(screen.getByText("已保存"), "2999ms 时仍在场").toBeTruthy();
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(screen.queryByText("已保存"), "3000ms 自动消失").toBeNull();
  });

  it("× 点击立即收掉且不影响他条", () => {
    act(() => {
      toast.info("第一条");
      toast.info("第二条");
    });
    const closes = screen.getAllByRole("button", { name: "关闭" });
    expect(closes.length).toBe(2);
    fireEvent.click(closes[0]);
    expect(screen.queryByText("第一条"), "× 立即收掉该条").toBeNull();
    expect(screen.getByText("第二条"), "他条不受影响").toBeTruthy();
    act(() => {
      vi.runAllTimers();
    });
    expect(screen.queryByText("第二条")).toBeNull();
  });

  it("多条叠放各自计时（先到先走）", () => {
    act(() => {
      toast.error("甲");
      vi.advanceTimersByTime(2000);
      toast.success("乙");
    });
    act(() => {
      vi.advanceTimersByTime(1000); // 甲满 3 秒，乙才 1 秒
    });
    expect(screen.queryByText("甲")).toBeNull();
    expect(screen.getByText("乙")).toBeTruthy();
    act(() => {
      vi.advanceTimersByTime(2000); // 乙满 3 秒
    });
    expect(screen.queryByText("乙")).toBeNull();
  });
});

describe("toast 形态与动作入口", () => {
  it("error 带 err 类；action 点击照常生效（不依赖 toast 收口）", () => {
    const onClick = vi.fn();
    act(() => {
      toast.error("章纲保存失败，请重试", { action: { label: "去补填", onClick } });
    });
    const el = screen.getByText("章纲保存失败，请重试").closest(".toast");
    expect(el?.className).toContain("err");
    fireEvent.click(screen.getByRole("button", { name: "去补填" }));
    expect(onClick).toHaveBeenCalledTimes(1);
    expect(screen.getByText("章纲保存失败，请重试"), "点动作不强制收 toast（按基线自动收口）").toBeTruthy();
  });

  it("success/info 图标臂与无 action 形态", () => {
    act(() => {
      toast.success("成功一条");
      toast.info("提示一条");
    });
    expect(screen.getByText("成功一条")).toBeTruthy();
    expect(screen.getByText("提示一条")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "去补填" })).toBeNull();
  });

  it("dismiss 主动收掉（编辑即收等提前收口语义）", () => {
    let id = 0;
    act(() => {
      id = toast.info("会被主动收掉的");
    });
    act(() => {
      toast.dismiss(id);
    });
    expect(screen.queryByText("会被主动收掉的")).toBeNull();
  });
});
