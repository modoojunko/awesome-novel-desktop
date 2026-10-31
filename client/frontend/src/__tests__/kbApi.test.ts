// 知识库 API 层测试（c-knowledge-base）：信封解包、各端点参数拼接、书内绑定（c-kb-snapshot）。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { kbApi } from "@/lib/kbApi";

const { bind, bindings, createEntry, deleteEntry, entries, entry, genres, libraries, syncBinding, unbind, concepts, updateEntry, usePrototype, graphAggregate, graphCell } = kbApi;

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

  it("libraries 带/不带 genre 与 novel_id（编码臂＋书内徽章参数）", async () => {
    fetchMock.mockReturnValueOnce(json([]));
    await libraries("仙侠/修真");
    expect(String(fetchMock.mock.calls[0][0])).toContain(`/api/kb/libraries?genre=${encodeURIComponent("仙侠/修真")}`);
    fetchMock.mockReturnValueOnce(json([]));
    await libraries();
    expect(String(fetchMock.mock.calls[1][0])).toBe("/api/kb/libraries");
    fetchMock.mockReturnValueOnce(json([]));
    await libraries("都市", "n1");
    const both = String(fetchMock.mock.calls[2][0]);
    expect(both).toContain("genre=%E9%83%BD%E5%B8%82");
    expect(both).toContain("novel_id=n1");
    fetchMock.mockReturnValueOnce(json([]));
    await libraries(undefined, "n2");
    expect(String(fetchMock.mock.calls[3][0])).toBe("/api/kb/libraries?novel_id=n2");
  });

  it("绑定四端点：bind/bindings/sync/unbind 路径与方法", async () => {
    fetchMock.mockReturnValueOnce(json({
      binding_id: "b1", library_id: "l1", genre: "都市", concept: "文风",
      library_name: "文风库", member_count: 2, landed: { "style.role": 1 }, replaced_bindings: 0,
    }));
    const bound = await bind("n1", "l1");
    expect(bound.member_count).toBe(2);
    expect(bound.landed["style.role"]).toBe(1);
    expect(fetchMock.mock.calls[0][1]?.method).toBe("POST");
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/kb/bindings");

    fetchMock.mockReturnValueOnce(json([{
      id: "b1", novel_id: "n1", library_id: "l1", enabled: true, genre: "都市",
      concept: "文风", library_name: "文风库", member_count: 2, scene_count: 1,
      added: 0, removed: 0, library_missing: false, synced_at: "",
    }]));
    const rows = await bindings("n1");
    expect(rows[0].scene_count).toBe(1);
    expect(String(fetchMock.mock.calls[1][0])).toBe("/api/kb/bindings?novel_id=n1");

    fetchMock.mockReturnValueOnce(json({ member_count: 3, landed: { "style.rules": 1 } }));
    const synced = await syncBinding("b1");
    expect(synced.member_count).toBe(3);
    expect(String(fetchMock.mock.calls[2][0])).toBe("/api/kb/bindings/b1/sync");
    expect(fetchMock.mock.calls[2][1]?.method).toBe("POST");

    fetchMock.mockReturnValueOnce(json({ unbound: "b1" }));
    const res = await unbind("b1", "n1");
    expect(res.unbound).toBe("b1");
    expect(String(fetchMock.mock.calls[3][0])).toBe("/api/kb/bindings/b1?novel_id=n1");
    expect(fetchMock.mock.calls[3][1]?.method).toBe("DELETE");
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

  it("usePrototype 计数回写", async () => {
    fetchMock.mockReturnValueOnce(json({ entry_id: "kb1", adopt_count: 2 }));
    const r = await usePrototype("kb1");
    expect(r.adopt_count).toBe(2);
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/kb/entries/kb1/prototype-use");
    expect(fetchMock.mock.calls[0][1]?.method).toBe("POST");
  });

  it("全局图两端点：聚合与下钻", async () => {
    fetchMock.mockReturnValueOnce(json({ nodes: [{ id: "g", kind: "genre", genre: "都市", concept: "", count: 3 }], links: [] }));
    const agg = await graphAggregate();
    expect(agg.nodes[0].count).toBe(3);
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/kb/graph/aggregate");
    fetchMock.mockReturnValueOnce(json({ nodes: [{ id: "e1", kind: "entry", genre: "都市", concept: "文风", title: "t", scope: "base" }] }));
    const cell = await graphCell("都市", "文风");
    expect(cell.nodes[0].id).toBe("e1");
    expect(String(fetchMock.mock.calls[1][0])).toContain("genre=%E9%83%BD%E5%B8%82");
    expect(String(fetchMock.mock.calls[1][0])).toContain("concept=");
  });

  it("条目写通道：PATCH/DELETE 路径与方法", async () => {
    fetchMock.mockReturnValueOnce(json({ id: "e1", rev: 2 }));
    const upd = await updateEntry("e1", { rev: 1, title: "改", payload: { archetype: "x" } });
    expect(upd.rev).toBe(2);
    const [u, ui] = fetchMock.mock.calls[0];
    expect(String(u)).toBe("/api/kb/entries/e1");
    expect(ui.method).toBe("PATCH");
    expect(JSON.parse(ui.body).rev).toBe(1);

    fetchMock.mockReturnValueOnce(json({ deleted: "e1" }));
    const del = await deleteEntry("e1");
    expect(del.deleted).toBe("e1");
    expect(fetchMock.mock.calls[1][1]?.method).toBe("DELETE");
  });

  it("信封缺 data 抛错", async () => {
    fetchMock.mockReturnValueOnce(Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) } as Response));
    await expect(genres()).rejects.toThrow("响应缺少 data");
  });
});
