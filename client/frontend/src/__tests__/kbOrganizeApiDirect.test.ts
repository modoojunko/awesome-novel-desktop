// organize 方法组/装载函数直测（c-kb-organize 批E）：组件测试 mock 命中的是 mock 对象，
// 真方法组的行覆盖由本文件直接驱动 fetch stub 补齐（全局 100% 口径）。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const fetchMock = vi.hoisted(() => vi.fn());

vi.stubGlobal("fetch", fetchMock);

// request 依赖 cookie/AbortController 等运行时态——直接 mock @/lib/api 的 request，
// 让真 kbApi.organize 方法组跑行（unwrap 信封解包也在被测行内）。
vi.mock("@/lib/api", async (orig) => {
  const actual = await orig<typeof import("@/lib/api")>();
  return { ...actual, request: fetchMock };
});

import { kbApi } from "@/lib/kbApi";

function okEnvelope(data: unknown) {
  // request() 直接返回 res.json()（信封 {ok,data} 由调用方 unwrap 剥）——mock 直接给 data
  return data;
}

beforeEach(() => {
  fetchMock.mockReset();
  fetchMock.mockImplementation(async () => ({ ok: true, data: {} }));
});

afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("kbApi.organize 方法组直测", () => {
  const cases: [string, () => Promise<unknown>][] = [
    ["run", () => kbApi.organize.run("玄幻")],
    ["run full", () => kbApi.organize.run("玄幻", true)],
    ["status", () => kbApi.organize.status("玄幻")],
    ["findings", () => kbApi.organize.findings("玄幻")],
    ["adoptFinding", () => kbApi.organize.adoptFinding("f1")],
    ["ignoreFinding", () => kbApi.organize.ignoreFinding("f1")],
    ["adoptRelation", () => kbApi.organize.adoptRelation("r1")],
    ["rejectRelation", () => kbApi.organize.rejectRelation("r1")],
    ["relationFeedback", () => kbApi.organize.relationFeedback("r1")],
    ["graphEntries", () => kbApi.organize.graphEntries("玄幻")],
    ["entryRelations", () => kbApi.organize.entryRelations("e1")],
  ];
  it.each(cases)("%s 走 POST/GET 且解信封", async (_name, fn) => {
    const r = await fn();
    expect(fetchMock).toHaveBeenCalled();
    expect(r).toBeDefined();
  });
});

