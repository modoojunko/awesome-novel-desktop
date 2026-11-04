// toolsBadgeSeen（c-tools-badge-seen）：顶栏徽标「看过不再引导」本地账——读写合并、
// 上限裁剪、坏账容错（非 JSON/非数组/非字符串/存储抛错一律退回「没看过」且不炸）、
// 账变广播（useSeenTaskIds 订阅者实时重算；写失败不广播＝徽标不跟着假清零）。
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import { markTasksSeen, seenTaskIds, useSeenTaskIds } from "@/lib/toolsBadgeSeen";

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("toolsBadgeSeen", () => {
  it("空账：没看过返回空集；markTasksSeen 空入参不写", () => {
    expect(seenTaskIds().size).toBe(0);
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    markTasksSeen([]);
    expect(setItem).not.toHaveBeenCalled();
  });

  it("消账合并写回：多次 mark 累积；读回即 seen 集", () => {
    markTasksSeen(["t1", "t2"]);
    markTasksSeen(["t2", "t3"]);
    expect([...seenTaskIds()]).toEqual(["t1", "t2", "t3"]);
  });

  it("超上限裁最旧的（CAP=500）：最早记的 id 被淘汰", () => {
    markTasksSeen(["old-1", "old-2"]);
    markTasksSeen(Array.from({ length: 500 }, (_, i) => `n${i}`));
    const seen = seenTaskIds();
    expect(seen.size).toBe(500);
    expect(seen.has("old-1")).toBe(false);
    expect(seen.has("n499")).toBe(true);
  });

  it("坏账容错：非 JSON／非数组／非字符串条目一律当没看过；mark 不因存储抛错炸", () => {
    localStorage.setItem("tools_badge_seen_v1", "{bad json");
    expect(seenTaskIds().size).toBe(0);
    localStorage.setItem("tools_badge_seen_v1", JSON.stringify({ k: 1 }));
    expect(seenTaskIds().size).toBe(0);
    localStorage.setItem("tools_badge_seen_v1", JSON.stringify(["t1", 2, null, "t3"]));
    expect([...seenTaskIds()]).toEqual(["t1", "t3"]);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota");
    });
    expect(() => markTasksSeen(["t1"])).not.toThrow();
  });

  it("getItem 抛错（隐私模式等）＝没看过", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(seenTaskIds().size).toBe(0);
  });
});

describe("toolsBadgeSeen 账变广播", () => {
  let renders = 0;
  function Probe() {
    const seen = useSeenTaskIds();
    renders += 1;
    return <span data-od-id="seen-probe">{seen.size}</span>;
  }

  it("markTasksSeen 写成功广播订阅者，useSeenTaskIds 当场拿到新账；写失败不广播", () => {
    render(<Probe />);
    expect(screen.getByText("0")).toBeInTheDocument();
    const rendersBefore = renders;
    act(() => markTasksSeen(["a", "b"]));
    expect(screen.getByText("2")).toBeInTheDocument(); // 广播 → 重渲染 → 新账
    expect(renders).toBeGreaterThan(rendersBefore);
    // 写失败＝账没变：不广播、不重渲染（徽标不跟着假清零）
    const rendersAfterNotify = renders;
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota");
    });
    act(() => markTasksSeen(["c"]));
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(renders).toBe(rendersAfterNotify);
  });
});
