// 全局图整形测试（c-kb-organize）：聚合/下钻图数据、邻域表、token 实色解析兜底、标签口径。
import { describe, expect, it } from "vitest";
import {
  adjacencyOf,
  cellLabel,
  genreLabel,
  toAggregateGraph,
  toCellGraph,
  tokenColors,
} from "@/lib/kbGraph";

describe("toAggregateGraph", () => {
  it("题材节点恒体积、格子随计数封顶、层级边保形", () => {
    const { nodes, links } = toAggregateGraph(
      [
        { id: "g1", kind: "genre", genre: "都市", concept: "", count: 9 },
        { id: "c1", kind: "cell", genre: "都市", concept: "文风", count: 3 },
        { id: "c2", kind: "cell", genre: "都市", concept: "文笔", count: 99 },
      ],
      [{ source: "g1", target: "c1" }, { source: "g1", target: "c2" }],
    );
    const genre = nodes.find((n) => n.kind === "genre")!;
    expect(genre.label).toBe("都市 9");
    expect(genre.val).toBe(7);
    const c1 = nodes.find((n) => n.id === "c1")!;
    expect(c1.label).toBe("文风 3");
    expect(c1.val).toBe(5);
    const c2 = nodes.find((n) => n.id === "c2")!;
    expect(c2.val).toBe(12); // 封顶 2+10
    expect(links).toEqual([{ source: "g1", target: "c1" }, { source: "g1", target: "c2" }]);
  });

  it("空聚合：零节点零边", () => {
    expect(toAggregateGraph([], [])).toEqual({ nodes: [], links: [] });
  });
});

describe("toCellGraph", () => {
  it("格子中心＋条目星形边；场景条目 scope 透传；空标题兜底概念名", () => {
    const { nodes, links } = toCellGraph(
      "都市",
      "文风",
      [
        { id: "e1", kind: "entry", genre: "都市", concept: "文风", title: "先果后因", scope: "base" },
        { id: "e2", kind: "entry", genre: "都市", concept: "文风", title: "", scope: "scene" },
      ],
    );
    expect(nodes[0]).toMatchObject({ id: "cell:都市:文风", kind: "cell", label: "文风 2", val: 7 });
    const e2 = nodes.find((n) => n.id === "e2")!;
    expect(e2.label).toBe("文风"); // 空标题兜底
    expect(e2.scope).toBe("scene");
    expect(links).toHaveLength(2);
    expect(links[0].source).toBe("cell:都市:文风");
  });

  it("跨题材通用格子 id 落 _general 段", () => {
    const { nodes } = toCellGraph("", "文笔", []);
    expect(nodes[0].id).toBe("cell:_general:文笔");
  });
});

describe("标签口径", () => {
  it("genreLabel/cellLabel 空题材走通用组", () => {
    expect(genreLabel("都市")).toBe("都市");
    expect(genreLabel("")).toBe("跨题材通用");
    expect(cellLabel("", "文笔")).toBe("跨题材通用 · 文笔");
  });
});

describe("adjacencyOf", () => {
  it("双向邻域；空边空表", () => {
    const adj = adjacencyOf([
      { source: "a", target: "b" },
      { source: "b", target: "c" },
      { source: "a", target: "c" }, // a 已在表（source 重复臂）
    ]);
    expect(adj.get("a")!.has("b")).toBe(true);
    expect(adj.get("b")!.has("a")).toBe(true);
    expect(adj.get("b")!.has("c")).toBe(true);
    expect(adjacencyOf([]).size).toBe(0);
  });
});

describe("tokenColors", () => {
  it("document 可用时读 token，缺失键回落", () => {
    const colors = tokenColors();
    expect(colors.accent).toBeTruthy();
    expect(colors.fg).toBeTruthy();
  });
});

describe("tokenColors 兜底臂", () => {
  it("token 取到实值原样透传", () => {
    const orig = globalThis.getComputedStyle;
    (globalThis as { getComputedStyle: unknown }).getComputedStyle = (() => ({
      getPropertyValue: (name: string) => (name === "--accent" ? "  #123456  " : "var-x"),
    })) as never;
    try {
      const c = tokenColors();
      expect(c.accent).toBe("#123456"); // trim 后透传
      expect(c.fg).toBe("var-x");
    } finally {
      (globalThis as { getComputedStyle: unknown }).getComputedStyle = orig;
    }
  });

  it("token 取到空值逐键回落", () => {
    const orig = globalThis.getComputedStyle;
    (globalThis as { getComputedStyle: unknown }).getComputedStyle = (() => ({
      getPropertyValue: () => "  ",
    })) as never;
    try {
      const c = tokenColors();
      expect(c.accent).toMatch(/^#/);
      expect(c.line).toMatch(/^#/);
    } finally {
      (globalThis as { getComputedStyle: unknown }).getComputedStyle = orig;
    }
  });

  it("getComputedStyle 抛错整体回落", () => {
    const orig = globalThis.getComputedStyle;
    (globalThis as { getComputedStyle: unknown }).getComputedStyle = () => {
      throw new Error("no doc");
    };
    try {
      const c = tokenColors();
      expect(c.muted).toMatch(/^#/);
    } finally {
      (globalThis as { getComputedStyle: unknown }).getComputedStyle = orig;
    }
  });
});
