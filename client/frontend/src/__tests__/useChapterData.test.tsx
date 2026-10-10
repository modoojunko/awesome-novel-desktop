import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, renderHook } from "@testing-library/react";
import { resetChapterStoresForTest } from "@/hooks/useChapterData";

// ---------------------------------------------------------------------------
// useChapterData — 1.5s 防抖自动保存 / 保存四态（含重试）/ countChars / 卸载 flush
// 状态为每章单例 store（编辑器 + 状态栏双实例共享，防丢失更新）
// ---------------------------------------------------------------------------

const apiState = vi.hoisted(() => ({
  get: vi.fn(),
  put: vi.fn(),
  post: vi.fn(),
  delete: vi.fn(),
  patch: vi.fn(),
  fetchPhaseStatus: vi.fn(),
}));

vi.mock("@/lib/api", () => ({ api: apiState }));

const CHAPTER = {
  volume: 1,
  chapter: 1,
  title: "第一章",
  status: "outline",
  outline: { summary: "概要" },
  prose: "",
};

beforeEach(() => {
  apiState.get.mockReset();
  apiState.put.mockReset();
  apiState.post.mockReset();
  apiState.delete.mockReset();
  apiState.patch.mockReset();
  localStorage.clear();
  resetChapterStoresForTest();
});

afterEach(() => {
  vi.useRealTimers();
});

async function importHooks() {
  return await import("@/hooks/useChapterData");
}

async function mountHook(initialProps?: { projectId?: string; ref?: string }) {
  const { useChapterData } = await importHooks();
  const utils = renderHook(
    ({ projectId = "p1", ref = "vol-1-ch-1" }) => useChapterData(projectId, ref),
    { initialProps: initialProps ?? {} },
  );
  await act(async () => {}); // flush 初始 load
  return utils;
}

describe("countChars", () => {
  it("去空白中文字符数（B5 同口径）", async () => {
    const { countChars } = await importHooks();
    expect(countChars("")).toBe(0);
    expect(countChars("你好 世界")).toBe(4);
    expect(countChars("你\n好\t世 界")).toBe(4);
    expect(countChars("Hello World")).toBe(10);
  });
});

describe("载入与字数", () => {
  it("载入章节，字数按去空白统计，初始 saved 态", async () => {
    apiState.get.mockResolvedValue({ ...CHAPTER, prose: "你好 世界" });
    const { result } = await mountHook();
    expect(result.current.loading).toBe(false);
    expect(result.current.prose).toBe("你好 世界");
    expect(result.current.wordCount).toBe(4);
    expect(result.current.saveState).toBe("saved");
    expect(result.current.isDirty).toBe(false);
  });

  it("加载失败置 error，不抛", async () => {
    apiState.get.mockRejectedValue(new Error("章节不存在"));
    const { result } = await mountHook();
    expect(result.current.error).toBe("章节不存在");
    expect(result.current.loading).toBe(false);
  });
});

describe("自动保存（1.5s 防抖）", () => {
  it("编辑置 unsaved；防抖窗口内不保存；1500ms 后经 /prose 端点保存回 saved", async () => {
    vi.useFakeTimers();
    apiState.get.mockResolvedValue({ ...CHAPTER });
    apiState.put.mockResolvedValue({});
    const { result } = await mountHook();

    act(() => result.current.setProse("你好世界"));
    expect(result.current.isDirty).toBe(true);
    expect(result.current.saveState).toBe("unsaved");

    await act(async () => {
      vi.advanceTimersByTime(1000);
    });
    expect(apiState.put).not.toHaveBeenCalled();

    await act(async () => {
      vi.advanceTimersByTime(500);
    });
    await act(async () => {});
    expect(apiState.put).toHaveBeenCalledTimes(1);
    expect(apiState.put).toHaveBeenCalledWith(
      "/novels/p1/chapters/vol-1-ch-1/prose",
      { prose: "你好世界" },
    );
    expect(result.current.saveState).toBe("saved");
    expect(result.current.isDirty).toBe(false);
  });

  it("保存期间进 autosaving 态", async () => {
    vi.useFakeTimers();
    apiState.get.mockResolvedValue({ ...CHAPTER });
    let resolvePut!: (v: unknown) => void;
    apiState.put.mockImplementation(
      () => new Promise((res) => (resolvePut = res)),
    );
    const { result } = await mountHook();

    act(() => result.current.setProse("你好世界"));
    await act(async () => {
      vi.advanceTimersByTime(1500);
    });
    // PUT 挂起中 → autosaving
    expect(result.current.saveState).toBe("autosaving");

    await act(async () => {
      resolvePut({});
    });
    expect(result.current.saveState).toBe("saved");
  });

  it("保存期间内容又变（AI 生成收尾覆盖）：在途早退后补排保存，最终落新稿", async () => {
    // 场景（c-prose-regen-replace 评审遗留）：flush/防抖 PUT 在飞时生成完成
    // setProse 新稿 → 防抖定时器打到 doSave 早退（saving=true）且不排定时器——
    // 修复前新稿搁浅到下次输入/卸载；修复后第一个 PUT 完成即补排一次防抖保存。
    vi.useFakeTimers();
    apiState.get.mockResolvedValue({ ...CHAPTER, prose: "旧稿" });
    let resolvePut!: (v: unknown) => void;
    let putCall = 0;
    apiState.put.mockImplementation(() => {
      putCall += 1;
      // 仅第一笔挂起（在飞窗口）；第二笔即完成
      return putCall === 1
        ? new Promise((res) => (resolvePut = res))
        : Promise.resolve({});
    });
    const { result } = await mountHook();

    act(() => result.current.setProse("旧稿二")); // 第一笔：触发保存（flush 前置角色）
    await act(async () => {
      vi.advanceTimersByTime(1500);
    });
    expect(result.current.saveState).toBe("autosaving");

    // 第二笔：PUT 在飞时生成收尾覆盖
    act(() => result.current.setProse("生成稿"));
    await act(async () => {
      vi.advanceTimersByTime(1500);
    });
    await act(async () => {});
    // 在途早退：未发第二次 PUT（保持串行，不与第一笔乱序）
    expect(apiState.put).toHaveBeenCalledTimes(1);
    expect(apiState.put).toHaveBeenCalledWith(
      "/novels/p1/chapters/vol-1-ch-1/prose",
      { prose: "旧稿二" },
    );

    await act(async () => {
      resolvePut({});
    });
    // 第一笔完成（initial=旧稿二）→ 补排定时器 → 第二笔落新稿
    await act(async () => {
      vi.advanceTimersByTime(1500);
    });
    await act(async () => {});
    expect(apiState.put).toHaveBeenCalledTimes(2);
    expect(apiState.put).toHaveBeenLastCalledWith(
      "/novels/p1/chapters/vol-1-ch-1/prose",
      { prose: "生成稿" },
    );
    expect(result.current.saveState).toBe("saved");
    expect(result.current.isDirty).toBe(false);
  });

  it("保存端点降级：/prose 404（结构性缺失）→ 重取最新章合并后全量 PUT", async () => {
    vi.useFakeTimers();
    apiState.get.mockResolvedValue({ ...CHAPTER });
    const notFound: Error & { status?: number } = new Error("Not Found");
    notFound.status = 404;
    apiState.put.mockRejectedValueOnce(notFound);
    apiState.put.mockResolvedValueOnce({});
    const { result } = await mountHook();

    act(() => result.current.setProse("降级保存"));
    await act(async () => {
      vi.advanceTimersByTime(1500);
    });
    await act(async () => {});
    expect(apiState.put).toHaveBeenCalledTimes(2);
    expect(apiState.put).toHaveBeenNthCalledWith(
      1,
      "/novels/p1/chapters/vol-1-ch-1/prose",
      { prose: "降级保存" },
    );
    // 全量 PUT 的 outline 来自降级前的重取（最新值），而非陈旧快照
    expect(apiState.put).toHaveBeenNthCalledWith(
      2,
      "/novels/p1/chapters/vol-1-ch-1",
      expect.objectContaining({ prose: "降级保存", outline: { summary: "概要" } }),
    );
    expect(result.current.saveState).toBe("saved");
  });

  it("网络错误不降级：/prose 网络错误 → 直接 failed，不发起全量 PUT", async () => {
    vi.useFakeTimers();
    apiState.get.mockResolvedValue({ ...CHAPTER });
    apiState.put.mockRejectedValueOnce(new Error("网络错误"));
    const { result } = await mountHook();

    act(() => result.current.setProse("新增内容"));
    await act(async () => {
      vi.advanceTimersByTime(1500);
    });
    await act(async () => {});
    expect(apiState.put).toHaveBeenCalledTimes(1);
    expect(result.current.saveState).toBe("failed");
    expect(result.current.error).toBe("网络错误");
  });
});

describe("双实例单例（编辑器 + 状态栏共享一章状态）", () => {
  it("同一章两个实例：单次防抖只 PUT 一次；状态栏 save() 用的是最新 prose（防丢失更新）", async () => {
    vi.useFakeTimers();
    apiState.get.mockResolvedValue({ ...CHAPTER });
    apiState.put.mockResolvedValue({});
    // 顺序挂载两个实例（并发 mount 会产生重叠 act 告警）
    const a = await mountHook();
    const b = await mountHook();

    // 编辑器实例输入
    act(() => a.result.current.setProse("第一句"));
    expect(b.result.current.saveState).toBe("unsaved");

    await act(async () => {
      vi.advanceTimersByTime(1500);
    });
    await act(async () => {});
    // 全章唯一 timer → 只有一次保存
    expect(apiState.put).toHaveBeenCalledTimes(1);
    expect(apiState.put).toHaveBeenCalledWith(
      "/novels/p1/chapters/vol-1-ch-1/prose",
      { prose: "第一句" },
    );
    expect(a.result.current.saveState).toBe("saved");
    expect(b.result.current.saveState).toBe("saved");

    // 状态栏实例（prose 停留在旧值）点保存 → 必须落盘编辑器里的最新正文
    act(() => a.result.current.setProse("第一句+第二句"));
    expect(b.result.current.saveState).toBe("unsaved");
    act(() => b.result.current.save());
    await act(async () => {});
    expect(apiState.put).toHaveBeenLastCalledWith(
      "/novels/p1/chapters/vol-1-ch-1/prose",
      { prose: "第一句+第二句" },
    );
    expect(a.result.current.saveState).toBe("saved");
  });

  it("切章：旧章 store 卸载 flush，新章独立拉取", async () => {
    vi.useFakeTimers();
    apiState.get.mockResolvedValue({ ...CHAPTER });
    apiState.put.mockResolvedValue({});
    const { result, rerender, unmount } = await mountHook();

    act(() => result.current.setProse("切章前的未保存内容"));
    rerender({ projectId: "p1", ref: "vol-1-ch-2" });
    await act(async () => {});
    // 旧章 flush 落盘
    expect(apiState.put).toHaveBeenCalledWith(
      "/novels/p1/chapters/vol-1-ch-1/prose",
      { prose: "切章前的未保存内容" },
    );
    // 新章独立 GET
    expect(apiState.get).toHaveBeenCalledWith("/novels/p1/chapters/vol-1-ch-2");
    unmount();
  });
});

describe("失败与重试", () => {
  it("主端点与降级端点均失败 → failed 态 + error；retry 成功回 saved", async () => {
    vi.useFakeTimers();
    apiState.get.mockResolvedValue({ ...CHAPTER });
    // /prose 失败 → 降级 /chapters 也失败 → failed
    apiState.put.mockRejectedValueOnce(new Error("网络错误"));
    apiState.put.mockRejectedValueOnce(new Error("网络错误"));
    const { result } = await mountHook();

    act(() => result.current.setProse("新增内容"));
    await act(async () => {
      vi.advanceTimersByTime(1500);
    });
    await act(async () => {});
    expect(result.current.saveState).toBe("failed");
    expect(result.current.error).toBe("网络错误");

    apiState.put.mockReset();
    apiState.put.mockResolvedValue({});
    act(() => result.current.retry());
    await act(async () => {});
    expect(result.current.saveState).toBe("saved");
  });
});

describe("StrictMode 模拟卸载（开发态）", () => {
  /** 真实复现 dev 双跑：React 19 StrictMode 下 mount 即「卸载→重挂」，useMemo 持有的
   *  store 实例在 release() 里被置 disposed 并逐出注册表——修复前 load() 命中
   *  `if (this.disposed) return` 把章数据丢弃，章节恒 0 字（接口数据正常、零报错）。
   *  注意：必须用 render+组件形态——renderHook 不触发 StrictMode 双跑（实测）。 */
  function useProbe(journal: string[]) {
    const { useChapterData } = hooksRef.current!;
    return useChapterData("p1", "vol-1-ch-1");
  }
  const hooksRef: { current: typeof import("@/hooks/useChapterData") | null } = { current: null };

  it("disposed 后再次 acquire 复活：load 结果照常落地（章节不再恒 0 字）", async () => {
    hooksRef.current = await importHooks();
    apiState.get.mockResolvedValue({
      ...CHAPTER,
      prose: "原有的正文，载入不应进撤销史。",
      status: "writing",
    });
    let snap: { prose: string; status: string; loading: boolean } | null = null;
    function Comp() {
      const d = useProbe([]);
      snap = { prose: d.prose, status: d.status, loading: d.loading };
      return null;
    }
    render(
      <React.StrictMode>
        <Comp />
      </React.StrictMode>,
    );
    await act(async () => {});
    expect(snap!.loading).toBe(false);
    expect(snap!.prose).toBe("原有的正文，载入不应进撤销史。");
    expect(snap!.status).toBe("writing");
  });

  it("复活实例重新收编注册表：双消费者共享同一 store", async () => {
    hooksRef.current = await importHooks();
    apiState.get.mockResolvedValue({ ...CHAPTER });
    let aProse = "";
    function Comp() {
      const d = useProbe([]);
      aProse = d.prose;
      return null;
    }
    render(
      <React.StrictMode>
        <Comp />
      </React.StrictMode>,
    );
    await act(async () => {});
    // 同章第二个消费者（经注册表拿到同一实例）写入 → 首个消费者可见
    const { useChapterData } = hooksRef.current!;
    function CompB() {
      const d = useChapterData("p1", "vol-1-ch-1");
      act(() => d.setProse("共享的一段"));
      return null;
    }
    render(
      <React.StrictMode>
        <CompB />
      </React.StrictMode>,
    );
    await act(async () => {});
    expect(aProse).toBe("共享的一段");
  });
});

describe("卸载 / 切章 flush", () => {
  it("卸载时 flush 未保存内容（不丢失防抖窗口内输入）", async () => {
    vi.useFakeTimers();
    apiState.get.mockResolvedValue({ ...CHAPTER });
    apiState.put.mockResolvedValue({});
    const { result, unmount } = await mountHook();

    act(() => result.current.setProse("未保存内容"));
    act(() => unmount());
    await act(async () => {});
    expect(apiState.put).toHaveBeenCalledWith(
      "/novels/p1/chapters/vol-1-ch-1/prose",
      { prose: "未保存内容" },
    );
  });
});

describe("目标字数与归档", () => {
  it("目标字数持久化到 localStorage 并实时更新进度口径", async () => {
    apiState.get.mockResolvedValue({ ...CHAPTER });
    const { result } = await mountHook();
    expect(result.current.targetWords).toBe(2500);

    act(() => result.current.setTargetWords(5000));
    expect(result.current.targetWords).toBe(5000);
    expect(localStorage.getItem("target-words-p1-vol-1-ch-1")).toBe("5000");
  });

  it("归档：非空正文 POST archive → status 置 archived + saved", async () => {
    apiState.get.mockResolvedValue({ ...CHAPTER });
    apiState.post.mockResolvedValue({});
    const { result } = await mountHook();

    act(() => result.current.setProse("正文内容"));
    await act(async () => {
      await result.current.archive();
    });
    expect(apiState.post).toHaveBeenCalledWith(
      "/novels/p1/chapters/vol-1-ch-1/archive",
      { full_text: "正文内容", ai_summary: true },
    );
    expect(result.current.status).toBe("archived");
    expect(result.current.saveState).toBe("saved");
  });

  it("归档：传 aiSummary:false → POST 体带 ai_summary:false（设置里关掉 AI 摘要）", async () => {
    apiState.get.mockResolvedValue({ ...CHAPTER });
    apiState.post.mockResolvedValue({});
    const { result } = await mountHook();

    act(() => result.current.setProse("正文内容"));
    await act(async () => {
      await result.current.archive({ aiSummary: false });
    });
    expect(apiState.post).toHaveBeenCalledWith(
      "/novels/p1/chapters/vol-1-ch-1/archive",
      { full_text: "正文内容", ai_summary: false },
    );
  });

  it("归档成功 dispatch chapter:archived 事件（树 📦 同步）", async () => {
    apiState.get.mockResolvedValue({ ...CHAPTER });
    apiState.post.mockResolvedValue({});
    const received: Array<{ projectId: string; ref: string }> = [];
    const listener = (e: Event) =>
      received.push((e as CustomEvent).detail as { projectId: string; ref: string });
    window.addEventListener("chapter:archived", listener);
    const { result } = await mountHook();

    act(() => result.current.setProse("正文内容"));
    await act(async () => {
      await result.current.archive();
    });
    window.removeEventListener("chapter:archived", listener);
    expect(received).toEqual([{ projectId: "p1", ref: "vol-1-ch-1" }]);
  });
});
