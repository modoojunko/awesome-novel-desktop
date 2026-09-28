import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { resetChapterStoresForTest } from "@/hooks/useChapterData";

// ---------------------------------------------------------------------------
// useChapterData 归档受理制（c-chapter-dossier）：受理≠归档——archiveJob 跟踪
// 后台提取；chapter:archived 事件只在服务端真置位后派发；提取中软锁；
// 模型未就绪同步归档保持旧行为；skip/retry 驱动。
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

const LONG_PROSE = "灯火在雨里摇晃。".repeat(20);

function chapterPayload(over: Record<string, unknown> = {}) {
  return {
    volume: 1,
    chapter: 1,
    title: "第一章",
    status: "writing",
    outline: { summary: "概要" },
    prose: LONG_PROSE,
    ...over,
  };
}

function dossierPayload(over: Record<string, unknown> = {}) {
  return {
    rows: [],
    progress: { pending: 0, accepted: 0, rejected: 0 },
    extraction: { state: "extracting", domains: {}, error: "" },
    not_extracted: false,
    stale: false,
    archived: false,
    accepted_count: 0,
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  resetChapterStoresForTest();
});

afterEach(() => {
  vi.restoreAllMocks();
});

async function mountHook() {
  const { useChapterData } = await import("@/hooks/useChapterData");
  const utils = renderHook(
    ({ projectId = "p1", ref = "vol-1-ch-1" }) => useChapterData(projectId, ref),
    { initialProps: {} as Record<string, never> },
  );
  await act(async () => {});
  return utils;
}

describe("归档受理制（archiveJob）", () => {
  it("受理成功：status 不动、archiveJob=extracting、不派发事件", async () => {
    apiState.get.mockResolvedValue(chapterPayload());
    apiState.post.mockResolvedValue({
      accepted: true, model_ready: true, state: "extracting", job_id: "j1",
    });
    const { result } = await mountHook();
    const events: string[] = [];
    window.addEventListener("chapter:archived", () => events.push("fired"));

    let ok = false;
    await act(async () => {
      ok = await result.current.archive();
    });
    expect(ok).toBe(true);
    expect(result.current.status).toBe("writing"); // 不乐观置位
    expect(result.current.archiveJob?.state).toBe("extracting");
    expect(events).toEqual([]);
  });

  it("提取中软锁：setProse/setStatus 被忽略；重复 archive 幂等", async () => {
    apiState.get.mockResolvedValue(chapterPayload());
    apiState.post.mockResolvedValue({ accepted: true, state: "extracting" });
    const { result } = await mountHook();
    await act(async () => {
      await result.current.archive();
    });
    act(() => {
      result.current.setProse("改一个字");
      result.current.setStatus("confirmed");
    });
    expect(result.current.prose).toBe(LONG_PROSE);
    expect(result.current.status).toBe("writing");
    let calls = apiState.post.mock.calls.length;
    await act(async () => {
      await result.current.archive(); // 幂等：不再发受理请求
    });
    expect(apiState.post.mock.calls.length).toBe(calls);
  });

  it("轮询到 ok：重拉置 archived＋派发事件＋archiveJob=done", async () => {
    apiState.get.mockResolvedValueOnce(chapterPayload()); // 初始载入
    apiState.post.mockResolvedValue({ accepted: true, state: "extracting" });
    // 轮询 dossier（extracting → ok 两次）；随后 load() 重拉已归档章
    apiState.get.mockResolvedValueOnce(dossierPayload({ extraction: { state: "extracting", domains: {}, error: "" } }))
      .mockResolvedValueOnce(dossierPayload({ extraction: { state: "ok", domains: {}, error: "" }, archived: true }))
      .mockResolvedValue(chapterPayload({ status: "archived" }));

    const { result } = await mountHook();
    const events: string[] = [];
    window.addEventListener("chapter:archived", () => events.push("fired"));
    await act(async () => {
      await result.current.archive();
    });
    await waitFor(
      () => expect(result.current.archiveJob?.state).toBe("done"),
      { timeout: 4000 },
    );
    expect(result.current.status).toBe("archived");
    expect(events).toEqual(["fired"]);
  });

  it("轮询到 failed：archiveJob=failed、章保持未归档", async () => {
    apiState.get.mockResolvedValueOnce(chapterPayload());
    apiState.post.mockResolvedValue({ accepted: true, state: "extracting" });
    apiState.get.mockResolvedValueOnce(
      dossierPayload({ extraction: { state: "extracting", domains: {}, error: "" } }),
    ).mockResolvedValue(
      dossierPayload({ extraction: { state: "failed", domains: {}, error: "parse: 不可解析" } }),
    );
    const { result } = await mountHook();
    await act(async () => {
      await result.current.archive();
    });
    await waitFor(
      () => expect(result.current.archiveJob?.state).toBe("failed"),
      { timeout: 4000 },
    );
    expect(result.current.archiveJob?.error).toContain("parse");
    expect(result.current.status).toBe("writing");
  });

  it("模型未就绪：同步归档（旧行为）——直接置 archived＋派发事件", async () => {
    apiState.get.mockResolvedValue(chapterPayload());
    apiState.post.mockResolvedValue({
      accepted: true, model_ready: false, state: "archived",
      archive_path: "archives/x.md", summary: "摘要",
    });
    const { result } = await mountHook();
    const events: string[] = [];
    window.addEventListener("chapter:archived", () => events.push("fired"));
    await act(async () => {
      await result.current.archive();
    });
    expect(result.current.status).toBe("archived");
    expect(result.current.archiveJob?.state).toBe("done");
    expect(events).toEqual(["fired"]);
  });

  it("skipArchive：跳过提取仍归档（重拉＋事件）", async () => {
    apiState.get.mockResolvedValueOnce(chapterPayload())
      .mockResolvedValue(chapterPayload({ status: "archived" }));
    apiState.post.mockResolvedValue({ ok: true });
    const { result } = await mountHook();
    const events: string[] = [];
    window.addEventListener("chapter:archived", () => events.push("fired"));
    await act(async () => {
      await result.current.skipArchive();
    });
    expect(result.current.status).toBe("archived");
    expect(events).toEqual(["fired"]);
  });

  it("retryExtraction：受理置 extracting＋轮询", async () => {
    apiState.get.mockResolvedValue(chapterPayload());
    apiState.post.mockResolvedValue({ accepted: true, state: "extracting" });
    const { result } = await mountHook();
    await act(async () => {
      await result.current.retryExtraction();
    });
    expect(result.current.archiveJob?.state).toBe("extracting");
    expect(
      apiState.post,
    ).toHaveBeenCalledWith("/novels/p1/chapters/vol-1-ch-1/dossier/extract", {});
  });

  it("切章返回恢复：载入后探测到服务端仍在提取", async () => {
    apiState.get.mockResolvedValueOnce(chapterPayload()) // 初始
      .mockResolvedValue(
        dossierPayload({ extraction: { state: "extracting", domains: {}, error: "" } }),
      );
    const { result } = await mountHook();
    await waitFor(
      () => expect(result.current.archiveJob?.state).toBe("extracting"),
      { timeout: 3000 },
    );
    expect(result.current.status).toBe("writing");
  });
});
