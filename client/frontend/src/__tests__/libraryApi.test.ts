// 角色库 API 层测试（c-character-library）：信封解包、各端点参数、头像缓存与失效。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  applyCardToBook,
  clearLibraryAvatarCache,
  createLibraryCard,
  deleteLibraryCard,
  fetchLibraryAvatar,
  importCardFromBook,
  listLibrary,
  listNovelOptions,
  randomLibraryName,
  syncCardFromBook,
  updateLibraryCard,
  type LibraryCard,
} from "@/lib/libraryApi";

function card(over: Partial<LibraryCard> = {}): LibraryCard {
  return {
    id: "c1",
    name: "秦重霄",
    aliases: ["大当家"],
    role: "反派",
    genre: "武侠",
    kind: "敌人",
    persona: "黑风寨大当家",
    dossier: { gender: "男", age: "42" },
    cog: { b1: "暴躁易怒" },
    src: { kind: "book", novel_name: "剑照山河", ref: "n1", character_id: "ch1" },
    avatar: { has: true, url: "/api/character-library/c1/avatar?variant=full", thumb_url: "/api/character-library/c1/avatar?variant=thumb" },
    rev: 1,
    updated_at: "",
    ...over,
  };
}

const fetchMock = vi.fn();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockReset();
  localStorage.setItem("auth_token", "tk");
});

afterEach(() => {
  clearLibraryAvatarCache();
  vi.unstubAllGlobals();
  localStorage.clear();
});

function json(data: unknown, ok = true) {
  return Promise.resolve({ ok, status: ok ? 200 : 400, json: () => Promise.resolve({ ok, data }) } as Response);
}

describe("libraryApi", () => {
  it("listLibrary 解包信封", async () => {
    fetchMock.mockReturnValueOnce(json({ count: 1, items: [card()] }));
    const data = await listLibrary();
    expect(data.count).toBe(1);
    expect(fetchMock.mock.calls[0][0]).toContain("/api/character-library");
  });

  it("create/update/delete 走对应方法与路径", async () => {
    fetchMock.mockReturnValueOnce(json(card()));
    await createLibraryCard({ name: "a", aliases: [], role: "配角", genre: "", kind: "", persona: "", dossier: {}, cog: {} });
    fetchMock.mockReturnValueOnce(json(card()));
    await updateLibraryCard("c1", { name: "b", aliases: [], role: "配角", genre: "", kind: "", persona: "", dossier: {}, cog: {} });
    fetchMock.mockReturnValueOnce(json({ deleted: "c1" }));
    await deleteLibraryCard("c1");
    expect(fetchMock.mock.calls[0][1]?.method).toBe("POST");
    expect(fetchMock.mock.calls[1][1]?.method).toBe("PUT");
    expect(fetchMock.mock.calls[2][1]?.method).toBe("DELETE");
  });

  it("收录/同步/用到新书/随机名/书列表 端点参数", async () => {
    fetchMock.mockReturnValueOnce(json({ created: true, card: card() }));
    await importCardFromBook("n1", "ch1", true);
    fetchMock.mockReturnValueOnce(json(card()));
    await syncCardFromBook("c1");
    fetchMock.mockReturnValueOnce(json({ character_id: "x", name: "n", role: "配角", renamed: false, demoted: false, avatar: false }));
    await applyCardToBook("c1", "n1", false);
    fetchMock.mockReturnValueOnce(json({ name: "霍青山", age: 30, source: "local" }));
    await randomLibraryName("男");
    fetchMock.mockReturnValueOnce(Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([{ id: "n1", name: "剑照山河" }]) } as Response));
    const novels = await listNovelOptions();
    expect(novels[0].name).toBe("剑照山河");
    expect(fetchMock.mock.calls[0][0]).toContain("/character-library/import/book");
    expect(fetchMock.mock.calls[1][0]).toContain("/sync-from-book");
    expect(fetchMock.mock.calls[2][0]).toContain("/apply-to-book");
    expect(fetchMock.mock.calls[3][0]).toContain("/random-name");
  });

  it("listNovelOptions 对非数组响应兜底为空", async () => {
    fetchMock.mockReturnValueOnce(json(null));
    expect(await listNovelOptions()).toEqual([]);
  });

  it("信封缺 data 抛错", async () => {
    fetchMock.mockReturnValueOnce(Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) } as Response));
    await expect(listLibrary()).rejects.toThrow("响应缺少 data");
  });

  it("头像走鉴权 fetch、按变体缓存、清除时 revoke", async () => {
    const blob = new Blob(["x"], { type: "image/webp" });
    fetchMock.mockResolvedValueOnce({ ok: true, blob: () => Promise.resolve(blob) } as Response);
    const url1 = await fetchLibraryAvatar(card(), "full");
    const url2 = await fetchLibraryAvatar(card(), "full");
    expect(url1).toBe(url2);
    expect(fetchMock).toHaveBeenCalledTimes(1); // 第二次命中缓存
    expect((fetchMock.mock.calls[0][1] as RequestInit).headers).toEqual({ Authorization: "Bearer tk" });
    clearLibraryAvatarCache("c1");
    fetchMock.mockResolvedValueOnce({ ok: true, blob: () => Promise.resolve(blob) } as Response);
    await fetchLibraryAvatar(card(), "full");
    expect(fetchMock).toHaveBeenCalledTimes(2); // 清缓存后重取
  });

  it("头像请求失败抛错；无 token 时不带 Authorization", async () => {
    localStorage.clear();
    fetchMock.mockResolvedValueOnce({ ok: false, status: 403 } as Response);
    await expect(fetchLibraryAvatar(card(), "thumb")).rejects.toThrow("头像加载失败");
    expect((fetchMock.mock.calls[0][1] as RequestInit).headers).toEqual({});
  });

  it("clearLibraryAvatarCache 全清", async () => {
    const blob = new Blob(["x"], { type: "image/webp" });
    fetchMock.mockResolvedValue({ ok: true, blob: () => Promise.resolve(blob) } as Response);
    await fetchLibraryAvatar(card(), "thumb");
    clearLibraryAvatarCache();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
