// 知识库 API 层测试（c-knowledge-base）：信封解包、各端点参数拼接、书内绑定（c-kb-snapshot）。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { kbApi } from "@/lib/kbApi";

const { bind, bindings, createEntry, deleteEntry, entries, entry, genres, libraries, syncBinding, unbind, concepts, updateEntry, usePrototype, graphAggregate, graphCell, pref, baselineOverride, clearBaselineOverride, baselineStatus, baselineSync, bookScopeImport, bookScopeDiff, bookScopeDecline } = kbApi;

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

  it("书级知识副本：补平与差异计数（c-kb-book-scope 批D）", async () => {
    fetchMock.mockReturnValueOnce(json({ imported: 2, skipped: 1 }));
    const imp = await bookScopeImport("n1");
    expect(imp.imported).toBe(2);
    const last = fetchMock.mock.calls.at(-1)!;
    const [u1, i1] = last;
    expect(String(u1)).toBe("/api/kb/book-scope/import");
    expect(JSON.parse(i1!.body)).toEqual({ novel_id: "n1" });

    fetchMock.mockReturnValueOnce(json({ new_count: 3, declined: false }));
    const d = await bookScopeDiff("n1");
    expect(d.new_count).toBe(3);
    expect(d.declined).toBe(false);
    const lastDiff = fetchMock.mock.calls.at(-1)!;
    expect(String(lastDiff[0])).toBe("/api/kb/book-scope/diff?novel_id=n1");

    fetchMock.mockReturnValueOnce(json({ declined: true }));
    const dec = await bookScopeDecline("n1");
    expect(dec.declined).toBe(true);
    const lastDec = fetchMock.mock.calls.at(-1)!;
    expect(String(lastDec[0])).toBe("/api/kb/book-scope/decline");
    expect(JSON.parse(lastDec[1]!.body)).toEqual({ novel_id: "n1", declined: true });
  });

  it("信封缺 data 抛错", async () => {
    fetchMock.mockReturnValueOnce(Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) } as Response));
    await expect(genres()).rejects.toThrow("响应缺少 data");
  });

  it("有用/没用回写（c-kb-write-block 批D）：POST pref 载荷与信封", async () => {
    fetchMock.mockReturnValueOnce(
      json({ entry_id: "e9", adopt_count: 0, drop_count: 1, useful_rate: 0.2 }),
    );
    const r = await pref("e9", false);
    expect(r.useful_rate).toBe(0.2);
    const [u, init] = fetchMock.mock.calls[0];
    expect(String(u)).toBe("/api/kb/entries/e9/pref");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ useful: false });
  });

  it("官方精选覆盖：PUT hide/edit 与 DELETE 恢复（c-kb-baseline 批B）", async () => {
    fetchMock.mockReturnValueOnce(json({ entry_id: "b1", action: "hide" }));
    const hid = await baselineOverride("b1", "hide");
    expect(hid.action).toBe("hide");
    const [u1, i1] = fetchMock.mock.calls[0];
    expect(String(u1)).toBe("/api/kb/entries/b1/baseline-override");
    expect(i1.method).toBe("PUT");
    expect(JSON.parse(i1.body)).toEqual({ action: "hide", instruction: "" });

    fetchMock.mockReturnValueOnce(json({ entry_id: "b1", action: "edit" }));
    await baselineOverride("b1", "edit", "我的写法。");
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({
      action: "edit", instruction: "我的写法。",
    });

    fetchMock.mockReturnValueOnce(json({ entry_id: "b1", restored: true }));
    const back = await clearBaselineOverride("b1");
    expect(back.restored).toBe(true);
    expect(fetchMock.mock.calls[2][1]?.method).toBe("DELETE");
  });

  it("官方精选同步状态与手动重试（c-kb-baseline）", async () => {
    fetchMock.mockReturnValueOnce(json({ version: 3, entries: 42 }));
    const st = await baselineStatus();
    expect(st).toEqual({ version: 3, entries: 42 });
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/kb/baseline/status");

    fetchMock.mockReturnValueOnce(json({ status: "synced", version: 4 }));
    const r = await baselineSync();
    expect(r.status).toBe("synced");
    const [u, init] = fetchMock.mock.calls[1];
    expect(String(u)).toBe("/api/kb/baseline/sync");
    expect(init.method).toBe("POST");
  });

  describe("题材知识导入进度流（c-kb-book-scope 弹窗二选一）", () => {
    /** 假 SSE 响应：按 chunk 逐次 read，覆盖跨块拼行与坏行/坏 JSON 跳过。 */
    function sse(chunks: string[], init: { ok?: boolean; status?: number } = {}) {
      let i = 0;
      const enc = new TextEncoder();
      return {
        ok: init.ok ?? true,
        status: init.status ?? 200,
        body: {
          getReader: () => ({
            read: async () =>
              i < chunks.length
                ? { done: false, value: enc.encode(chunks[i++]) }
                : { done: true, value: undefined },
          }),
        },
      } as unknown as Response;
    }

    it("逐事件解析：跨块拼行＋非 data 行/坏 JSON 跳过", async () => {
      fetchMock.mockReturnValueOnce(
        Promise.resolve(
          sse([
            'event: ping\ndata: {"type":"phase","phase":"copy","total":2}\n',
            'data: {"type":"phase","phase":"copy","concept":"手',
            '法","done":1,"total":2}\n\nnot-a-data-line\ndata: {broken\n',
            'data: {"type":"done","imported":2,"skipped":0}\n\n',
          ]),
        ),
      );
      const events: Record<string, unknown>[] = [];
      const ctrl = kbApi.bookScopeImportStream("n1", (ev) => events.push(ev as unknown as Record<string, unknown>));
      expect(ctrl).toBeInstanceOf(AbortController);
      await vi.waitFor(() => expect(events).toHaveLength(3));
      expect(events[0]).toMatchObject({ type: "phase", phase: "copy", total: 2 });
      expect(events[1]).toMatchObject({ concept: "手法", done: 1 });
      expect(events[2]).toMatchObject({ type: "done", imported: 2 });
      const [u, init] = fetchMock.mock.calls[0];
      expect(String(u)).toContain("/api/kb/book-scope/import/stream");
      expect(init.method).toBe("POST");
      expect(JSON.parse(init.body)).toEqual({ novel_id: "n1" });
      expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tk");
    });

    it("HTTP 失败：detail 字符串直出；非字符串/坏 JSON 走兜底文案", async () => {
      fetchMock.mockReturnValueOnce(
        Promise.resolve({
          ok: false,
          status: 404,
          json: async () => ({ detail: "Book not found" }),
        } as unknown as Response),
      );
      const a: Record<string, unknown>[] = [];
      kbApi.bookScopeImportStream("n1", (ev) => a.push(ev as unknown as Record<string, unknown>));
      await vi.waitFor(() => expect(a).toHaveLength(1));
      expect(a[0]).toMatchObject({ type: "error", message: "Book not found" });

      fetchMock.mockReturnValueOnce(
        Promise.resolve({
          ok: false,
          status: 500,
          json: async () => {
            throw new Error("not json");
          },
        } as unknown as Response),
      );
      const b: Record<string, unknown>[] = [];
      kbApi.bookScopeImportStream("n1", (ev) => b.push(ev as unknown as Record<string, unknown>));
      await vi.waitFor(() => expect(b).toHaveLength(1));
      expect(b[0]).toMatchObject({ type: "error", message: "导入失败（HTTP 500）" });
    });

    it("响应无 body：报「无法读取响应流」", async () => {
      fetchMock.mockReturnValueOnce(
        Promise.resolve({ ok: true, status: 200, body: null } as unknown as Response),
      );
      const events: Record<string, unknown>[] = [];
      kbApi.bookScopeImportStream("n1", (ev) => events.push(ev as unknown as Record<string, unknown>));
      await vi.waitFor(() => expect(events).toHaveLength(1));
      expect(events[0]).toMatchObject({ type: "error", message: "无法读取响应流" });
    });

    it("网络失败：AbortError 静默；其余报错", async () => {
      const abortErr = new DOMException("aborted", "AbortError");
      fetchMock.mockReturnValueOnce(Promise.reject(abortErr));
      const a: Record<string, unknown>[] = [];
      kbApi.bookScopeImportStream("n1", (ev) => a.push(ev as unknown as Record<string, unknown>));
      await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
      await Promise.resolve();
      expect(a).toHaveLength(0);

      fetchMock.mockReturnValueOnce(Promise.reject(new Error("断网了")));
      const b: Record<string, unknown>[] = [];
      kbApi.bookScopeImportStream("n1", (ev) => b.push(ev as unknown as Record<string, unknown>));
      await vi.waitFor(() => expect(b).toHaveLength(1));
      expect(b[0]).toMatchObject({ type: "error", message: "断网了" });

      // 空 message → 兜底文案
      fetchMock.mockReturnValueOnce(Promise.reject(new Error("")));
      const c: Record<string, unknown>[] = [];
      kbApi.bookScopeImportStream("n1", (ev) => c.push(ev as unknown as Record<string, unknown>));
      await vi.waitFor(() => expect(c).toHaveLength(1));
      expect(c[0]).toMatchObject({ type: "error", message: "网络错误" });
    });

    it("未登录：不带 Authorization 头", async () => {
      localStorage.removeItem("auth_token");
      fetchMock.mockReturnValueOnce(
        Promise.resolve(sse(['data: {"type":"done","imported":0,"skipped":0}\n\n'])),
      );
      const events: Record<string, unknown>[] = [];
      kbApi.bookScopeImportStream("n1", (ev) => events.push(ev as unknown as Record<string, unknown>));
      await vi.waitFor(() => expect(events).toHaveLength(1));
      const init = fetchMock.mock.calls[0][1] as RequestInit;
      expect((init.headers as Record<string, string>).Authorization).toBeUndefined();
    });
  });
});
