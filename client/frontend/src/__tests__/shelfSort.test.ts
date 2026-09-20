import { describe, expect, it } from "vitest";
import {
  SHELF_PAGE_SIZE,
  defaultFilters,
  slicePage,
  stageOfNovel,
  visibleBooks,
  type ShelfNovel,
} from "@/lib/shelfSort";

const H = 3600_000;
const now = Date.now();
const iso = (ms: number) => new Date(ms).toISOString();

function book(partial: Partial<ShelfNovel> & { name: string }): ShelfNovel {
  return {
    total_chapters: 0,
    total_archives: 0,
    finished_at: null,
    created_at: iso(now - 30 * 24 * H),
    updated_at: iso(now - H),
    word_count: 0,
    ...partial,
  };
}

// 四态各一本 + 同态第二本（words 与 created 序互相区分，用于证伪比较器）
const READY = book({ name: "星海拾遗", total_chapters: 17, total_archives: 17, word_count: 48210, created_at: iso(now - 90 * 24 * H), updated_at: iso(now - 2 * H) });
const WRITING_A = book({ name: "沙漏之下", total_chapters: 6, total_archives: 2, word_count: 21400, created_at: iso(now - 60 * 24 * H), updated_at: iso(now - 26 * H) });
const WRITING_B = book({ name: "潮汐图书馆", total_chapters: 4, total_archives: 1, word_count: 8600, created_at: iso(now - 30 * 24 * H), updated_at: iso(now - 3 * 24 * H) });
const SETTING = book({ name: "长夜灯", total_chapters: 0, total_archives: 0, word_count: 0, created_at: iso(now - 5 * 24 * H), updated_at: iso(now - 30 * H) });
const DONE = book({ name: "雾中法庭", total_chapters: 9, total_archives: 9, word_count: 12842, finished_at: iso(now - 72 * H), created_at: iso(now - 200 * 24 * H), updated_at: iso(now - 72 * H) });

const ALL = [WRITING_A, DONE, SETTING, READY, WRITING_B]; // 故意乱序输入

describe("stageOfNovel", () => {
  it("四态判据：完结 > 无章 > 全归档 > 其余", () => {
    expect(stageOfNovel(DONE)).toBe("done");
    expect(stageOfNovel(SETTING)).toBe("setting");
    expect(stageOfNovel(READY)).toBe("ready");
    expect(stageOfNovel(WRITING_A)).toBe("writing");
  });
});

describe("visibleBooks：状态 rank 恒优先", () => {
  it("默认排序（recency）下状态顺序恒为 待完本→写作中→设定中→已完结", () => {
    const names = visibleBooks(ALL, defaultFilters()).map((x) => x.book.name);
    expect(names).toEqual(["星海拾遗", "沙漏之下", "潮汐图书馆", "长夜灯", "雾中法庭"]);
  });

  it("任意排序键都不改变状态分组顺序（words 场景）", () => {
    const names = visibleBooks(ALL, { kind: "all", q: "", sort: "words" }).map((x) => x.book.name);
    expect(names).toEqual(["星海拾遗", "沙漏之下", "潮汐图书馆", "长夜灯", "雾中法庭"]);
  });

  it("写作中组内按 updated_at 倒序（证据：两本顺序随 recency 变化而非固有输入序）", () => {
    const a = visibleBooks([WRITING_B, WRITING_A], { kind: "all", q: "", sort: "recency" }).map((x) => x.book.name);
    expect(a).toEqual(["沙漏之下", "潮汐图书馆"]);
    const b = visibleBooks([WRITING_B, WRITING_A], { kind: "all", q: "", sort: "words" }).map((x) => x.book.name);
    expect(b).toEqual(["沙漏之下", "潮汐图书馆"]);
  });

  it("created 键：创建时间倒序（证伪数据——创建序 ≠ 书名序 ≠ 输入序）", () => {
    const names = visibleBooks(ALL, { kind: "all", q: "", sort: "created" }).map((x) => x.book.name);
    // 组内倒序：写作中组 潮汐(-30d) 新于 沙漏(-60d)
    expect(names).toEqual(["星海拾遗", "潮汐图书馆", "沙漏之下", "长夜灯", "雾中法庭"]);
  });

  it("title 键：组内 zh 书名升序（用 ASCII 可预期串避免 ICU 差异）", () => {
    const a = book({ name: "AAA", total_chapters: 3, total_archives: 1 });
    const b = book({ name: "BBB", total_chapters: 3, total_archives: 1 });
    const c = book({ name: "CCC", total_chapters: 3, total_archives: 1 });
    const names = visibleBooks([c, a, b], { kind: "all", q: "", sort: "title" }).map((x) => x.book.name);
    expect(names).toEqual(["AAA", "BBB", "CCC"]);
  });

  it("同 rank 同键全等时书名升序稳定 tie-break", () => {
    const a = book({ name: "AAA", total_chapters: 3, total_archives: 1, word_count: 5 });
    const b = book({ name: "BBB", total_chapters: 3, total_archives: 1, word_count: 5 });
    const names = visibleBooks([b, a], { kind: "all", q: "", sort: "words" }).map((x) => x.book.name);
    expect(names).toEqual(["AAA", "BBB"]);
  });
});

describe("visibleBooks：时间比较器容错", () => {
  it("缺 created_at / updated_at 字段归 0（不破坏排序、不 NaN）", () => {
    const x = book({ name: "AAA", total_chapters: 1, total_archives: 0, created_at: undefined, updated_at: undefined });
    const y = book({ name: "BBB", total_chapters: 1, total_archives: 0, created_at: iso(now - 1000), updated_at: iso(now - 1000) });
    const names = visibleBooks([x, y], { kind: "all", q: "", sort: "recency" }).map((i) => i.book.name);
    expect(names).toEqual(["BBB", "AAA"]); // 有时间的在前，归 0 的在后——不是原序
  });

  it("非法时间串归 0", () => {
    const x = book({ name: "AAA", total_chapters: 1, total_archives: 0, updated_at: "not-a-date" });
    const y = book({ name: "BBB", total_chapters: 1, total_archives: 0, updated_at: iso(now - 1000) });
    const names = visibleBooks([y, x], { kind: "all", q: "", sort: "recency" }).map((i) => i.book.name);
    expect(names).toEqual(["BBB", "AAA"]);
  });

  it("无时区 ISO 串（后端实际格式）可正常参与排序", () => {
    const x = book({ name: "AAA", total_chapters: 1, total_archives: 0, updated_at: "2026-09-20T03:53:13" });
    const y = book({ name: "BBB", total_chapters: 1, total_archives: 0, updated_at: "2026-09-19T03:53:13" });
    const names = visibleBooks([x, y], { kind: "all", q: "", sort: "recency" }).map((i) => i.book.name);
    expect(names).toEqual(["AAA", "BBB"]);
  });
});

describe("visibleBooks：过滤", () => {
  it("状态筛选只留该态", () => {
    const names = visibleBooks(ALL, { kind: "writing", q: "", sort: "recency" }).map((x) => x.book.name);
    expect(names).toEqual(["沙漏之下", "潮汐图书馆"]);
  });

  it("搜索 trim + 大小写不敏感包含匹配", () => {
    const en = book({ name: "My Novel", total_chapters: 1, total_archives: 0 });
    expect(visibleBooks([en], { kind: "all", q: "  my  ", sort: "recency" })).toHaveLength(1);
    expect(visibleBooks([en], { kind: "all", q: "nomatch", sort: "recency" })).toHaveLength(0);
  });

  it("状态与搜索组合", () => {
    const got = visibleBooks(ALL, { kind: "writing", q: "沙", sort: "recency" }).map((x) => x.book.name);
    expect(got).toEqual(["沙漏之下"]);
  });

  it("idx 回指原数组下标（供回看等动作）", () => {
    const got = visibleBooks(ALL, { kind: "ready", q: "", sort: "recency" });
    expect(got).toEqual([{ book: READY, idx: 3 }]);
  });
});

describe("分页", () => {
  it("默认 12/页切片", () => {
    const list = Array.from({ length: 20 }, (_, i) =>
      book({ name: `B${String(i).padStart(2, "0")}`, total_chapters: 1, total_archives: 0, updated_at: iso(now - i * H) }),
    );
    const visible = visibleBooks(list, defaultFilters());
    expect(SHELF_PAGE_SIZE).toBe(12);
    expect(slicePage(visible, SHELF_PAGE_SIZE)).toHaveLength(12);
    expect(slicePage(visible, 24)).toHaveLength(20);
  });
});
