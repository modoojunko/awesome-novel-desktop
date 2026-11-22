/** 人味标注章作用域记忆（切章清账）：编辑器单实例长驻、ProsePane 不随章重挂，
 *  report/settled 必须随章复位——否则旧章段号套到新章同序号段（串章标注）；
 *  在途重扫结果按调度章判弃；同章重渲（切页签回来）不清账。
 */
import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useRenweiChapterMemory } from "@/components/novel/workbench/useRenweiChapterMemory";
import type { RenweiReport } from "@/lib/renwei";

function report(): RenweiReport {
  return {
    ok: true,
    chars: 1600,
    paras: 20,
    score: null,
    priorities: [],
    metrics: [],
    findings: [],
    short_chapter: false,
    mtld_unconverged: false,
  };
}

describe("useRenweiChapterMemory（切章清账）", () => {
  it("切章清账：report/settled 全复位（标注退场由 marks effect 连带触发）", () => {
    const { result, rerender } = renderHook((props: { ref: string }) => useRenweiChapterMemory(props.ref), {
      initialProps: { ref: "vol-1-ch-1" },
    });
    act(() => {
      result.current.setReport(report());
      result.current.setSettled({ 3: "skip", 5: "done" });
    });
    expect(result.current.report).not.toBeNull();
    expect(Object.keys(result.current.settled).length).toBe(2);

    rerender({ ref: "vol-1-ch-2" });
    expect(result.current.report).toBeNull();
    expect(result.current.settled).toEqual({});
  });

  it("同章重渲不清账（同章切页签语义：标注与记账保留）", () => {
    const { result, rerender } = renderHook((props: { ref: string }) => useRenweiChapterMemory(props.ref), {
      initialProps: { ref: "vol-1-ch-1" },
    });
    act(() => {
      result.current.setReport(report());
      result.current.setSettled({ 1: "done" });
    });
    rerender({ ref: "vol-1-ch-1" });
    expect(result.current.report).not.toBeNull();
    expect(result.current.settled).toEqual({ 1: "done" });
  });

  it("在途重扫判章：切章后按调度章判弃，未切章不误伤", () => {
    const { result, rerender } = renderHook((props: { ref: string }) => useRenweiChapterMemory(props.ref), {
      initialProps: { ref: "c1" },
    });
    expect(result.current.staleResult("c1")).toBe(false);

    rerender({ ref: "c2" });
    expect(result.current.staleResult("c1")).toBe(true); // 链按 c1 调度、回来已在 c2
    expect(result.current.staleResult("c2")).toBe(false);
  });
});
