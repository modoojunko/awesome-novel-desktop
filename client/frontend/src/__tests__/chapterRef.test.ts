import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  chapterNoOf,
  isGhostRef,
  parseChapterRef,
  volNoOf,
} from "@/lib/chapterRef";

describe("chapterRef 双形制解析", () => {
  it("主线 ref", () => {
    expect(parseChapterRef("vol-1-ch-12")).toEqual({ kind: "mainline", vol: 1, ch: 12 });
    expect(isGhostRef("vol-1-ch-12")).toBe(false);
    expect(chapterNoOf("vol-1-ch-12")).toBe(12);
    expect(volNoOf("vol-2-ch-3")).toBe(2);
  });

  it("旧稿 ref（内容寻址后缀）", () => {
    const ref = "vol-1-ch-2-rabcd1234";
    expect(parseChapterRef(ref)).toEqual({
      kind: "ghost",
      vol: 1,
      ch: 2,
      of: "vol-1-ch-2",
      hash: "abcd1234",
    });
    expect(isGhostRef(ref)).toBe(true);
    // 章号取源章号（面板/投影按同一章号工作）
    expect(chapterNoOf(ref)).toBe(2);
  });

  it("非法输入返回 null（调用方必须显式处理，不许静默吞）", () => {
    expect(parseChapterRef("vol-1-ch-2-rXYZ")).toBeNull();
    expect(parseChapterRef("nonsense")).toBeNull();
    expect(chapterNoOf("nonsense")).toBe(0);
  });
});

describe("ref 解析源码守卫", () => {
  it("裸 `-ch-(\\d+)` 正则只允许出现在 lib/chapterRef.ts", () => {
    const root = path.join(__dirname, "..");
    const offenders: string[] = [];
    const walk = (dir: string) => {
      for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, ent.name);
        if (ent.isDirectory()) {
          if (ent.name === "__tests__" || ent.name === "node_modules") continue;
          walk(full);
          continue;
        }
        if (!/\.(ts|tsx)$/.test(ent.name)) continue;
        if (full.endsWith(path.join("lib", "chapterRef.ts"))) continue;
        const text = fs.readFileSync(full, "utf-8");
        if (/-ch-\(\\d\+\)/.test(text) || /\\^vol-\(\\d\+\)-ch-/.test(text)) {
          offenders.push(path.relative(root, full));
        }
      }
    };
    walk(root);
    expect(offenders, `请改用 @/lib/chapterRef：${offenders.join(", ")}`).toEqual([]);
  });
});
