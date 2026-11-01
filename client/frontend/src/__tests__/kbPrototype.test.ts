// 角色原型渲染映射测试（c-kb-character）：全格/缺格/空 payload 三态。
import { describe, expect, it } from "vitest";
import { prototypeOf, renderPrototype } from "@/lib/kbPrototype";

describe("renderPrototype", () => {
  it("全格复制：archetype＝persona、档案三格、认知三格", () => {
    const r = renderPrototype({
      archetype: "落魄天才",
      look: "青衫落拓",
      background: "家道中落的宗门弟子",
      speech: "话少，开口即刀",
      w1: "不服",
      s1: "憋着",
      v1: "要赢回来",
      relation_slot: "仇敌",
      arc: "从谷底爬回",
    });
    expect(r.persona).toBe("落魄天才");
    expect(r.dossier).toEqual({ look: "青衫落拓", background: "家道中落的宗门弟子", speech: "话少，开口即刀" });
    expect(r.cog).toEqual({ w1: "不服", s1: "憋着", v1: "要赢回来" });
  });

  it("缺格不落空键；首尾空白剔除", () => {
    const r = renderPrototype({ archetype: "谋士", look: "  ", speech: "慢条斯理" });
    expect(r.persona).toBe("谋士");
    expect(r.dossier).toEqual({ speech: "慢条斯理" });
    expect(r.cog).toEqual({});
  });

  it("空 payload：persona 空串、两格空对象", () => {
    const r = renderPrototype({});
    expect(r.persona).toBe("");
    expect(r.dossier).toEqual({});
    expect(r.cog).toEqual({});
  });

  it("prototypeOf 从条目取 payload，缺 payload 兜底", () => {
    expect(prototypeOf({ payload: { archetype: "反派打手" } }).persona).toBe("反派打手");
    expect(prototypeOf({ payload: null as never }).persona).toBe("");
  });
});
