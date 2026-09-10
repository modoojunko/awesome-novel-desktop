import { describe, expect, it } from "vitest";
import {
  STAGE_LABEL,
  landingViewFor,
  stageFromChapters,
} from "@/lib/novelStage";

// 默认落点规则（用户 2026-09-10 拍板）：
//   第一次创建的书（无章节）→ 设定；写完第一个章节后（有章节未全归档）→ 写作；
//   小说写完后（全部章节已归档）→ 预览。
describe("stageFromChapters（阶段判据只看章节，不看 current_phase）", () => {
  it("无章节 → setting（刚建的书）", () => {
    expect(stageFromChapters(0, 0)).toBe("setting");
  });

  it("有章节未全归档 → writing", () => {
    expect(stageFromChapters(1, 0)).toBe("writing");
    expect(stageFromChapters(10, 3)).toBe("writing");
  });

  it("全部章节已归档 → done（写完）", () => {
    expect(stageFromChapters(1, 1)).toBe("done");
    expect(stageFromChapters(10, 10)).toBe("done");
  });

  it("归档数超过总数（脏数据）也判 done，不崩", () => {
    expect(stageFromChapters(3, 5)).toBe("done");
  });
});

describe("landingViewFor（打开书的默认落点）", () => {
  it("setting → 设定页", () => {
    expect(landingViewFor("setting")).toBe("advanced-settings");
  });
  it("writing → 写作", () => {
    expect(landingViewFor("writing")).toBe("workbench");
  });
  it("done → 预览", () => {
    expect(landingViewFor("done")).toBe("archives");
  });
});

describe("STAGE_LABEL 单源", () => {
  it("三态文案", () => {
    expect(STAGE_LABEL).toEqual({ setting: "设定中", writing: "写作中", done: "已归档" });
  });
});
