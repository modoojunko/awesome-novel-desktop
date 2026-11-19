// workbench/DataEnter：boot 闸＋挂载期淡入包装（打开书单波直达判例，2026-11-19）。
// 手法：fake timers 推进 600ms boot 窗口，真渲染断言类名冻结语义。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";
import {
  DataEnter,
  WorkbenchBootProvider,
  useWorkbenchBooting,
} from "@/components/novel/workbench/DataEnter";

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
});

function BootProbe() {
  return <span data-testid="booting">{useWorkbenchBooting() ? "in" : "out"}</span>;
}

describe("WorkbenchBootProvider", () => {
  it("boot 窗口内 booting=true，600ms 后翻转 false", () => {
    render(
      <WorkbenchBootProvider>
        <BootProbe />
      </WorkbenchBootProvider>
    );
    expect(screen.getByTestId("booting").textContent).toBe("in");
    act(() => {
      vi.advanceTimersByTime(600);
    });
    expect(screen.getByTestId("booting").textContent).toBe("out");
  });
});

describe("DataEnter", () => {
  it("boot 窗口内挂载：不播淡入，翻转后不回溯加类（冻结语义防闪烁）", () => {
    render(
      <WorkbenchBootProvider>
        <DataEnter className="col-editor">
          <span>内容</span>
        </DataEnter>
      </WorkbenchBootProvider>
    );
    const el = document.querySelector(".col-editor") as HTMLElement;
    expect(el.className).toBe("col-editor");
    act(() => {
      vi.advanceTimersByTime(600);
    });
    expect(el.className).toBe("col-editor");
    expect(screen.getByText("内容")).toBeTruthy();
  });

  it("boot 窗口内挂载且无 className：无 data-enter 类", () => {
    render(
      <WorkbenchBootProvider>
        <DataEnter>
          <i>裸</i>
        </DataEnter>
      </WorkbenchBootProvider>
    );
    expect(document.querySelector("div.data-enter")).toBeNull();
    expect(screen.getByText("裸")).toBeTruthy();
  });

  it("boot 后挂载：挂载即带 data-enter 且 className 透传、rest props 透传", () => {
    const { rerender } = render(<WorkbenchBootProvider>{null}</WorkbenchBootProvider>);
    act(() => {
      vi.advanceTimersByTime(600);
    });
    rerender(
      <WorkbenchBootProvider>
        <DataEnter className="col-panel vol-shell" data-testid="fx">
          <span>x</span>
        </DataEnter>
      </WorkbenchBootProvider>
    );
    expect(document.querySelector(".col-panel.vol-shell.data-enter")).not.toBeNull();
    expect(screen.getByTestId("fx")).toBeTruthy();
  });

  it("boot 后挂载且无 className：仅挂 data-enter 类", () => {
    const { rerender } = render(<WorkbenchBootProvider>{null}</WorkbenchBootProvider>);
    act(() => {
      vi.advanceTimersByTime(600);
    });
    rerender(
      <WorkbenchBootProvider>
        <DataEnter>
          <b>裸出窗</b>
        </DataEnter>
      </WorkbenchBootProvider>
    );
    const el = document.querySelector("div.data-enter") as HTMLElement;
    expect(el).not.toBeNull();
    expect(el.className).toBe("data-enter");
  });
});
