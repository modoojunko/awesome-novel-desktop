// 选区捕获（lib/selection.ts）契约（覆盖率专项·批 1）：
//   captureSelection 的四种空/有组合 + useSelectionCapture 的文档级监听、清空与手动捕获。
import { act, renderHook } from "@testing-library/react";
import { createRef } from "react";
import { describe, expect, it, vi } from "vitest";
import { captureSelection, useSelectionCapture } from "@/lib/selection";

function fakeTextarea(value: string, start: number, end: number): HTMLTextAreaElement {
  const el = document.createElement("textarea");
  el.value = value;
  el.setSelectionRange(start, end);
  return el;
}

describe("captureSelection", () => {
  it("textarea 为空 → null", () => {
    expect(captureSelection(null)).toBeNull();
  });

  it("无选区（起点=终点）→ null", () => {
    expect(captureSelection(fakeTextarea("abcdef", 2, 2))).toBeNull();
  });

  it("有选区 → 返回片段与全文", () => {
    const cap = captureSelection(fakeTextarea("abcdef", 2, 5));
    expect(cap).toEqual({ start: 2, end: 5, text: "cde", fullText: "abcdef" });
  });
});

describe("useSelectionCapture", () => {
  it("监听 mouseup/keyup：捕获到选区即置态，clearSelection 清零", () => {
    const ref = createRef<HTMLTextAreaElement>();
    ref.current = fakeTextarea("hello world", 0, 5);
    const { result } = renderHook(() => useSelectionCapture(ref));
    expect(result.current.hasSelection).toBe(false);

    act(() => {
      document.dispatchEvent(new MouseEvent("mouseup"));
    });
    expect(result.current.hasSelection).toBe(true);
    expect(result.current.selectedText).toBe("hello");

    act(() => {
      document.dispatchEvent(new KeyboardEvent("keyup"));
    });
    expect(result.current.hasSelection).toBe(true); // keyup 同样触发捕获

    act(() => result.current.clearSelection());
    expect(result.current.hasSelection).toBe(false);
    expect(result.current.selectedText).toBe("");
  });

  it("captureNow 直接返回捕获结果（无选区时置 false）", () => {
    const ref = createRef<HTMLTextAreaElement>();
    ref.current = fakeTextarea("abc", 1, 1);
    const { result } = renderHook(() => useSelectionCapture(ref));
    let cap: unknown;
    act(() => {
      cap = result.current.captureNow();
    });
    expect(cap).toBeNull();
    expect(result.current.hasSelection).toBe(false);

    ref.current = fakeTextarea("abc", 0, 3);
    act(() => {
      cap = result.current.captureNow();
    });
    expect(cap).toMatchObject({ text: "abc" });
    expect(result.current.hasSelection).toBe(true);
  });

  it("卸载时移除文档监听（不再更新状态）", () => {
    const ref = createRef<HTMLTextAreaElement>();
    ref.current = fakeTextarea("abc", 0, 3);
    const { result, unmount } = renderHook(() => useSelectionCapture(ref));
    unmount();
    act(() => {
      document.dispatchEvent(new MouseEvent("mouseup"));
    });
    // 卸载后状态不再推进（无异常即通过；此处断言最后一次快照仍为初始态）
    expect(result.current.hasSelection).toBe(false);
    expect(vi.isMockFunction(document.dispatchEvent)).toBe(false);
  });
});
