// 知识库页详情抽屉通用「字段」段测试（c-kb-entry-detail-fields）：规格原文
// 「条目详情抽屉：字段、正反例、证据只读」实现补课——payload 概念无关平铺。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = vi.hoisted(() => ({
  entries: vi.fn(),
  libraries: vi.fn(),
  genres: vi.fn(),
}));

vi.mock("@/lib/kbApi", async (orig) => {
  const actual = await orig<typeof import("@/lib/kbApi")>();
  return { ...actual, kbApi: { ...actual.kbApi, entries: api.entries, libraries: api.libraries, genres: api.genres } };
});

import KnowledgeBasePage, { payloadRows } from "@/pages/KnowledgeBasePage";
import type { KbEntry } from "@/lib/kbApi";

const ENTRY: KbEntry = {
  id: "kbentry-0001",
  genre: "悬疑",
  concept: "角色设定",
  concept_id: "悬疑:角色设定",
  title: "刘望津",
  instruction: "漂亮热情的农村出身姑娘，能识怪字、有阴阳眼。",
  payload: {
    archetype: "刘望津",
    persona: "漂亮热情的农村出身姑娘。",
    aliases: ["小刘", "津津"],
    gender: "女",
    age: "44",
    plot: "与李耀相亲；识怪字；出车祸丢魂昏迷。",
    empty_key: "",
    blank_arr: [],
    custom_note: "字段字典未收录的键",
  },
  example: "",
  negative_example: "",
  when: {},
  evidence: "怪字书",
  rev: 1,
  src_kind: "character_library_migration",
  src_novel_name: "怪字书",
  created_at: "2026-11-02T00:00:00",
  updated_at: "2026-11-02T00:00:00",
};

beforeEach(() => {
  api.entries.mockResolvedValue({ entries: [ENTRY], next_cursor: "" });
  api.libraries.mockResolvedValue([]);
  api.genres.mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("payloadRows（通用载荷平铺）", () => {
  it("字符串按存储序平铺、空值跳过、数组顿号连", () => {
    const rows = payloadRows(ENTRY.payload);
    expect(rows.map(([k]) => k)).toEqual([
      "archetype", "persona", "aliases", "gender", "age", "plot", "custom_note",
    ]);
    expect(rows[2]).toEqual(["aliases", "小刘、津津"]);
  });

  it("null/缺格跳过、对象走紧凑 JSON、数字转串", () => {
    const rows = payloadRows({
      n: null as unknown as string,
      obj: { a: 1 },
      num: 42,
      arrObj: [{ x: 1 }],
      emptyArr: [],
      emptyStr: "",
    });
    expect(rows).toEqual([
      ["obj", '{"a":1}'],
      ["num", "42"],
      ["arrObj", '{"x":1}'], // 单元素数组 join 无分隔符
    ]);
  });
});

describe("KnowledgeBasePage 详情抽屉", () => {
  it("点开条目：字段以中文标签逐格渲染（迁移卡属性全可见）", async () => {
    render(<KnowledgeBasePage />);
    await waitFor(() => expect(screen.getByText("刘望津")).toBeTruthy());
    fireEvent.click(screen.getByText("刘望津"));
    await waitFor(() => expect(screen.getByText("字段")).toBeTruthy());
    // 中文标签（通用字典），不露英文字段名
    expect(screen.getByText("性别")).toBeTruthy();
    expect(screen.getByText("名字")).toBeTruthy();
    expect(screen.getByText("一句话人设")).toBeTruthy();
    expect(screen.getByText("别名")).toBeTruthy();
    expect(screen.getByText("年龄")).toBeTruthy();
    expect(screen.getByText("剧情定位")).toBeTruthy();
    expect(screen.queryByText("gender")).toBeNull();
    expect(screen.queryByText("archetype")).toBeNull();
    // 值：标量与数组顿号连
    expect(screen.getByText("女")).toBeTruthy();
    expect(screen.getByText("小刘、津津")).toBeTruthy();
    expect(screen.getByText("与李耀相亲；识怪字；出车祸丢魂昏迷。")).toBeTruthy();
    // 空值键不出行；字典未收录的键回退原键（不编造中文）
    expect(screen.queryByText("empty_key")).toBeNull();
    expect(screen.queryByText("blank_arr")).toBeNull();
    expect(screen.getByText("custom_note")).toBeTruthy();
    expect(screen.getByText("字段字典未收录的键")).toBeTruthy();
    // 其余四段照旧
    expect(screen.getByText("指令")).toBeTruthy();
    expect(screen.getByText("证据")).toBeTruthy();
  });

  it("关闭抽屉后字段段退场", async () => {
    render(<KnowledgeBasePage />);
    await waitFor(() => expect(screen.getByText("刘望津")).toBeTruthy());
    fireEvent.click(screen.getByText("刘望津"));
    await waitFor(() => expect(screen.getByText("字段")).toBeTruthy());
    fireEvent.click(screen.getByText("✕"));
    await waitFor(() => expect(screen.queryByText("字段")).toBeNull());
  });
});
