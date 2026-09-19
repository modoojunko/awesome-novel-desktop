import { describe, expect, it } from "vitest";
import {
  STAGE_LABEL,
  landingViewFor,
  stageFromChapters,
} from "@/lib/novelStage";

// 默认落点规则（用户 2026-09-10 拍板；c-works-finish-flow 扩四态）：
//   第一次创建的书（无章节）→ 设定；有章节未全归档 → 写作；
//   全部章节已归档未完结 → 待完本（仍落写作）；完本（finished_at）→ 已完结落预览。
describe("stageFromChapters（阶段判据只看章节与完结状态，不看 current_phase）", () => {
  it("finished_at 非空 → done（已完结），章节再多也完结", () => {
    expect(stageFromChapters(0, 0, "2026-09-19T00:00:00")).toBe("done");
    expect(stageFromChapters(3, 1, "2026-09-19T00:00:00")).toBe("done");
  });

  it("无章节且未完结 → setting（刚建的书）", () => {
    expect(stageFromChapters(0, 0)).toBe("setting");
    expect(stageFromChapters(0, 0, null)).toBe("setting");
  });

  it("有章节未全归档 → writing", () => {
    expect(stageFromChapters(1, 0)).toBe("writing");
    expect(stageFromChapters(10, 3)).toBe("writing");
  });

  it("全部章节已归档未完结 → ready（待完本，「已归档」退役）", () => {
    expect(stageFromChapters(1, 1)).toBe("ready");
    expect(stageFromChapters(10, 10)).toBe("ready");
  });

  it("归档数超过总数（脏数据）也判 ready，不崩", () => {
    expect(stageFromChapters(3, 5)).toBe("ready");
  });
});

describe("landingViewFor（打开书的默认落点）", () => {
  it("setting → 设定页", () => {
    expect(landingViewFor("setting")).toBe("advanced-settings");
  });
  it("writing → 写作", () => {
    expect(landingViewFor("writing")).toBe("workbench");
  });
  it("ready → 写作（待完本仍可加章/改稿，预览走书架「回看」）", () => {
    expect(landingViewFor("ready")).toBe("workbench");
  });
  it("done → 预览", () => {
    expect(landingViewFor("done")).toBe("archives");
  });
});

describe("STAGE_LABEL 单源", () => {
  it("四态文案（done 语义=已完结；「已归档」退役）", () => {
    expect(STAGE_LABEL).toEqual({
      setting: "设定中",
      writing: "写作中",
      ready: "待完本",
      done: "已完结",
    });
  });
});
