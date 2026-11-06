// kbRelations 词表与句式直测（c-kb-relations-view）：六类出/入向句式逐类＋未知类型回退——
// 契约文件 100% 门禁的单源覆盖（组件测试只触达部分臂）。
import { describe, expect, it } from "vitest";

import {
  REL_TYPE_LABELS,
  relPhrase,
  relPhraseIn,
  relPhraseOut,
  relTypeLabel,
} from "@/lib/kbRelations";

describe("REL_TYPE_LABELS", () => {
  it("六类齐全且词固定（refines=细化 沿用整理面板现词）", () => {
    expect(REL_TYPE_LABELS).toEqual({
      refines: "细化",
      contradicts: "相冲",
      depends_on: "依赖",
      instance_of: "属于",
      derived_from: "源自",
      applies_to: "适用于",
    });
  });

  it("relTypeLabel 已知类型映射、未知回退原键", () => {
    expect(relTypeLabel("applies_to")).toBe("适用于");
    expect(relTypeLabel("refines")).toBe("细化");
    expect(relTypeLabel("made_up")).toBe("made_up");
  });
});

describe("relPhrase 出/入向六类句式", () => {
  const cases: [string, string, string][] = [
    ["applies_to", "适用于 冷峻短句", "短句文风 适用于本知识"],
    ["derived_from", "源自 冷峻短句", "短句文风 源自本知识"],
    ["instance_of", "属于 冷峻短句", "短句文风 属于本知识"],
    ["depends_on", "依赖 冷峻短句", "短句文风 依赖本知识"],
    ["contradicts", "与 冷峻短句 相冲", "与 短句文风 相冲"],
    ["refines", "细化 冷峻短句", "短句文风 细化本知识"],
  ];
  for (const [relType, outText, inText] of cases) {
    it(`${relType}：出「${outText}」/ 入「${inText}」`, () => {
      expect(relPhraseOut(relType, "冷峻短句")).toBe(outText);
      expect(relPhraseIn(relType, "短句文风")).toBe(inText);
      expect(relPhrase(relType, "out", "冷峻短句")).toBe(outText);
      expect(relPhrase(relType, "in", "短句文风")).toBe(inText);
    });
  }

  it("未知类型回退：出/入向均落「适用于」句式（默认臂）", () => {
    expect(relPhrase("made_up", "out", "某知识")).toBe("适用于 某知识");
    expect(relPhrase("made_up", "in", "某知识")).toBe("某知识 适用于本知识");
  });
});
