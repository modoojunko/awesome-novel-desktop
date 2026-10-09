/**
 * 章节默认字数模块（c-chapter-default-words）：归一 / 缓存读写 / 变更订阅 /
 * 后端 book-prefs 读写。覆盖率契约文件（coverage-contract.ts）——四支 100%。
 */

import { beforeEach, describe, expect, it, vi } from "vitest";

const apiState = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }));
vi.mock("@/lib/api", () => ({ api: apiState }));

import {
  CHAPTER_WORD_TARGET_DEFAULT,
  CHAPTER_WORD_TARGET_MAX,
  CHAPTER_WORD_TARGET_MIN,
  cacheChapterWordTarget,
  getCachedChapterWordTarget,
  loadChapterWordTarget,
  normalizeChapterWordTarget,
  saveChapterWordTarget,
  subscribeChapterWordTarget,
} from "@/lib/chapterTarget";

beforeEach(() => {
  localStorage.clear();
  apiState.get.mockReset();
  apiState.put.mockReset();
});

describe("normalizeChapterWordTarget", () => {
  it("合法值原样（含字符串形态），四舍五入到整字", () => {
    expect(normalizeChapterWordTarget(3000)).toBe(3000);
    expect(normalizeChapterWordTarget("2800")).toBe(2800);
    expect(normalizeChapterWordTarget(2500.4)).toBe(2500);
    expect(normalizeChapterWordTarget(CHAPTER_WORD_TARGET_MIN)).toBe(500);
    expect(normalizeChapterWordTarget(CHAPTER_WORD_TARGET_MAX)).toBe(6000);
  });

  it("空/非数/越界一律回落缺省 2500", () => {
    expect(normalizeChapterWordTarget(undefined)).toBe(CHAPTER_WORD_TARGET_DEFAULT);
    expect(normalizeChapterWordTarget(null)).toBe(CHAPTER_WORD_TARGET_DEFAULT);
    expect(normalizeChapterWordTarget("")).toBe(CHAPTER_WORD_TARGET_DEFAULT);
    expect(normalizeChapterWordTarget("abc")).toBe(CHAPTER_WORD_TARGET_DEFAULT);
    expect(normalizeChapterWordTarget(NaN)).toBe(CHAPTER_WORD_TARGET_DEFAULT);
    expect(normalizeChapterWordTarget(400)).toBe(CHAPTER_WORD_TARGET_DEFAULT);
    expect(normalizeChapterWordTarget(6001)).toBe(CHAPTER_WORD_TARGET_DEFAULT);
  });
});

describe("缓存读写与订阅", () => {
  it("未缓存 → 缺省；缓存值 → 归一读回", () => {
    expect(getCachedChapterWordTarget("p1")).toBe(2500);
    localStorage.setItem("pref.book.p1.chapter_words", "3200");
    expect(getCachedChapterWordTarget("p1")).toBe(3200);
    localStorage.setItem("pref.book.p1.chapter_words", "99999");
    expect(getCachedChapterWordTarget("p1")).toBe(2500);
  });

  it("localStorage 读取抛错 → 缺省（隐私模式兜底）", () => {
    const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("denied");
    });
    expect(getCachedChapterWordTarget("p1")).toBe(2500);
    spy.mockRestore();
  });

  it("cacheChapterWordTarget 写缓存并派发变更事件（订阅者收到）", () => {
    const seen: number[] = [];
    const off = subscribeChapterWordTarget(() => seen.push(1));
    const safe = cacheChapterWordTarget("p1", 3000);
    expect(safe).toBe(3000);
    expect(localStorage.getItem("pref.book.p1.chapter_words")).toBe("3000");
    expect(seen).toHaveLength(1);
    off();
    cacheChapterWordTarget("p1", 2600);
    expect(seen).toHaveLength(1);
  });

  it("跨页签 storage 事件同样触发订阅回调", () => {
    const fn = vi.fn();
    const off = subscribeChapterWordTarget(fn);
    window.dispatchEvent(new StorageEvent("storage"));
    expect(fn).toHaveBeenCalledTimes(1);
    off();
  });

  it("localStorage 写入抛错 → 不派发事件但仍返回归一值", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota");
    });
    const fn = vi.fn();
    const off = subscribeChapterWordTarget(fn);
    expect(cacheChapterWordTarget("p1", 3000)).toBe(3000);
    expect(fn).not.toHaveBeenCalled();
    off();
    spy.mockRestore();
  });
});

describe("后端读写", () => {
  it("load 读回后端值并回灌缓存", async () => {
    apiState.get.mockResolvedValue({ chapter_word_target: 3000 });
    await expect(loadChapterWordTarget("p1")).resolves.toBe(3000);
    expect(apiState.get).toHaveBeenCalledWith("/novels/p1/settings/book-prefs");
    expect(localStorage.getItem("pref.book.p1.chapter_words")).toBe("3000");
  });

  it("load 空态（未设置/响应缺字段）→ 缺省并回灌", async () => {
    apiState.get.mockResolvedValue({});
    await expect(loadChapterWordTarget("p1")).resolves.toBe(2500);
    apiState.get.mockResolvedValue(null);
    await expect(loadChapterWordTarget("p1")).resolves.toBe(2500);
  });

  it("save PUT 归一值，成功后才更新缓存", async () => {
    apiState.put.mockResolvedValue({ chapter_word_target: 3200 });
    await expect(saveChapterWordTarget("p1", "3200")).resolves.toBe(3200);
    expect(apiState.put).toHaveBeenCalledWith("/novels/p1/settings/book-prefs", {
      chapter_word_target: 3200,
    });
    expect(localStorage.getItem("pref.book.p1.chapter_words")).toBe("3200");
  });

  it("save 越界值先归一为本档缺省再提交", async () => {
    apiState.put.mockResolvedValue({ chapter_word_target: 2500 });
    await expect(saveChapterWordTarget("p1", 99999)).resolves.toBe(2500);
    expect(apiState.put).toHaveBeenCalledWith("/novels/p1/settings/book-prefs", {
      chapter_word_target: 2500,
    });
  });

  it("save 响应缺字段 → 用提交值回写缓存", async () => {
    apiState.put.mockResolvedValue({});
    await expect(saveChapterWordTarget("p1", 2800)).resolves.toBe(2800);
    expect(localStorage.getItem("pref.book.p1.chapter_words")).toBe("2800");
  });

  it("save 失败抛错且不动缓存（调用方保持可重试）", async () => {
    localStorage.setItem("pref.book.p1.chapter_words", "2600");
    apiState.put.mockRejectedValue(new Error("500"));
    await expect(saveChapterWordTarget("p1", 3000)).rejects.toThrow("500");
    expect(localStorage.getItem("pref.book.p1.chapter_words")).toBe("2600");
  });
});
