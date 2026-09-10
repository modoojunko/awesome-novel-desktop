import { describe, expect, it } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useDirtyState } from "@/hooks/useDirtyState";

describe("useDirtyState.isDirty", () => {
  it("快照就绪前为 false；current 偏离快照后变 true", () => {
    const { result, rerender } = renderHook(
      ({ v }: { v: { scenes: string } }) => useDirtyState(v, undefined),
      { initialProps: { v: { scenes: "" } } },
    );
    // 初始：无快照，不报脏
    expect(result.current.isDirty).toBe(false);

    // 快照就绪（与当前值一致）→ 不脏
    act(() => result.current.snapshotLoaded({ scenes: "" }));
    expect(result.current.isDirty).toBe(false);

    // 编辑 → 偏离快照 → 脏
    rerender({ v: { scenes: "边境城邦" } });
    expect(result.current.isDirty).toBe(true);
  });

  it("snapshotLoaded / markSaved 均复位 isDirty", () => {
    const { result, rerender } = renderHook(
      ({ v }: { v: { scenes: string } }) => useDirtyState(v, undefined),
      { initialProps: { v: { scenes: "" } } },
    );
    act(() => result.current.snapshotLoaded({ scenes: "" }));
    rerender({ v: { scenes: "x" } });
    expect(result.current.isDirty).toBe(true);

    // 重新加载（如切换角色）→ 复位
    act(() => result.current.snapshotLoaded({ scenes: "x" }));
    expect(result.current.isDirty).toBe(false);

    // 再编辑 → 脏
    rerender({ v: { scenes: "y" } });
    expect(result.current.isDirty).toBe(true);

    // 保存 → 复位
    act(() => result.current.markSaved());
    expect(result.current.isDirty).toBe(false);
  });
});

  it("markDirty：save 成功但 confirm 400 时强制回到 dirty（D14/O-4）", () => {
    const { result, rerender } = renderHook(
      ({ v }: { v: { scenes: string } }) => useDirtyState(v, undefined),
      { initialProps: { v: { scenes: "" } } },
    );
    act(() => result.current.snapshotLoaded({ scenes: "" }));
    rerender({ v: { scenes: "x" } });
    act(() => result.current.markSaved());
    expect(result.current.isDirty).toBe(false);

    act(() => result.current.markDirty());
    expect(result.current.isDirty).toBe(true);
  });
