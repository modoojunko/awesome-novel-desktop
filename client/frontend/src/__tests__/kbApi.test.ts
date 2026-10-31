// 知识库 API 层测试（c-knowledge-base）：信封解包、各端点参数拼接（entries 全参/空参、libraries 体裁分支）。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { kbApi } from "@/lib/kbApi";

const { createEntry, entries, entry, genres, libraries, concepts } = kbApi;

const fetchMock = vi.fn();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockReset();
  localStorage.setItem("auth_token", "tk");
});

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

function json(data: unknown, ok = true) {
  return Promise.resolve({ ok, status: ok ? 200 : 400, json: () => Promise.resolve({ ok, data }) } as Response);
}

describe("kbApi", () => {
  it("genres 解包信封", async () => {
    fetchMock.mockReturnValueOnce(json([{ name: "都市", count: 3 }]));
    const data = await genres();
    expect(data[0].name).toBe("都市");
    expect(fetchMock.mock.calls[0][0]).toContain("/api/kb/genres");
  });

  it("entries 全参数拼接", async () => {
    fetchMock.mockReturnValueOnce(json({ entries: [], next_cursor: "" }));
    await entries({ genre: "仙侠/修真", concept: "手法", src: "deconstruct", q: "打斗", cursor: "c2" });
    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain("/api/kb/entries?");
    expect(url).toContain("genre=" + encodeURIComponent("仙侠/修真"));
    expect(url).toContain("concept=%E6%89%8B%E6%B3%95");
    expect(url).toContain("src=deconstruct");
    expect(url).toContain("q=");
    expect(url).toContain("cursor=c2");
  });

  it("entries 空参数不带查询串", async () => {
    fetchMock.mockReturnValueOnce(json({ entries: [], next_cursor: "" }));
    await entries({});
    // 模板恒带 ?，空参时查询串为空（无害）
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/kb/entries?");
  });

  it("entry(id) GET 详情", async () => {
    fetchMock.mockReturnValueOnce(json({ id: "e1" }));
    const data = await entry("e1");
    expect(data.id).toBe("e1");
    expect(String(fetchMock.mock.calls[0][0])).toContain("/api/kb/entries/e1");
  });

  it("libraries 带/不带 genre（编码臂）", async () => {
    fetchMock.mockReturnValueOnce(json([]));
    await libraries("仙侠/修真");
    expect(String(fetchMock.mock.calls[0][0])).toContain(`/api/kb/libraries?genre=${encodeURIComponent("仙侠/修真")}`);
    fetchMock.mockReturnValueOnce(json([]));
    await libraries();
    expect(String(fetchMock.mock.calls[1][0])).toBe("/api/kb/libraries");
  });

  it("concepts 概念元数据", async () => {
    fetchMock.mockReturnValueOnce(json({ concepts: [], themes: [] }));
    const data = await concepts();
    expect(data.themes).toEqual([]);
    expect(String(fetchMock.mock.calls[0][0])).toContain("/api/kb/concepts");
  });

  it("createEntry POST JSON", async () => {
    fetchMock.mockReturnValueOnce(json({ id: "e9" }));
    const data = await createEntry({ genre: "都市", concept: "", instruction: "先给果再补因。" });
    expect(data.id).toBe("e9");
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("/api/kb/entries");
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ genre: "都市", concept: "", instruction: "先给果再补因。" }));
    expect(init.headers["Content-Type"]).toBe("application/json");
  });

  it("信封缺 data 抛错", async () => {
    fetchMock.mockReturnValueOnce(Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) } as Response));
    await expect(genres()).rejects.toThrow("响应缺少 data");
  });
});
