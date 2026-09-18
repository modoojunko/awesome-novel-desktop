// 卷/章序号标签（lib/nodeTitle.ts）契约：
//   中文数字 1~999、≥1000 回退阿拉伯（与后端 manuscript/render.py::cn_num 同族同回退）。
//   CN_NUM_CASES 是对拍表——backend/tests/test_shared_constants_parity.py 会正则抽取
//   本表逐项与 python 侧比对，改一侧忘另一侧会被 CI 拦住。
import { describe, expect, it } from "vitest";
import { cnNum, editName, isDefaultTitle, nodeLabel } from "@/lib/nodeTitle";

const CN_NUM_CASES: Array<[number, string]> = [
  [9, "九"],
  [12, "十二"],
  [21, "二十一"],
  [102, "一百二"],
  [999, "九百九十九"],
  [1000, "1000"],
  [1234, "1234"],
];

describe("cnNum", () => {
  it.each(CN_NUM_CASES)("cnNum(%i) === %s", (n, expected) => {
    expect(cnNum(n)).toBe(expected);
  });

  it("非正整数原样字符串化（不被回退分支吞掉）", () => {
    expect(cnNum(0)).toBe("0");
    expect(cnNum(-3)).toBe("-3");
    expect(cnNum(1.5)).toBe("1.5");
  });
});

describe("千章边界（P3：修复前 1000+ 渲染成「第undefined百…章」）", () => {
  it("第1000章：默认序号形态不重复拼名称", () => {
    expect(nodeLabel("章", 1000, "第1000章")).toBe("第1000章");
    expect(isDefaultTitle("章", 1000, "第1000章")).toBe(true);
    expect(editName("章", 1000, "第1000章")).toBe("");
  });

  it("第1000章 · 终局：用户起过名照拼", () => {
    expect(nodeLabel("章", 1000, "终局")).toBe("第1000章 · 终局");
    expect(isDefaultTitle("章", 1000, "终局")).toBe(false);
    expect(editName("章", 1000, "终局")).toBe("终局");
  });

  it("999 及以下仍是中文数字（回退只影响四位及以上）", () => {
    expect(nodeLabel("章", 999, "第999章")).toBe("第九百九十九章");
    expect(nodeLabel("卷", 12, null)).toBe("第十二卷");
  });

  it("第一千零一章：中文千位序号也算默认序号（正则含 千万两）", () => {
    expect(isDefaultTitle("章", 1000, "第一千零一章")).toBe(true);
    expect(nodeLabel("章", 1000, "第一千零一章")).toBe("第1000章");
    expect(isDefaultTitle("章", 1000, "第一千两百章")).toBe(true);
    // 带了名字就不算默认序号
    expect(isDefaultTitle("章", 1000, "第一千零一章 终局")).toBe(false);
  });

  it("不出现 undefined 字样（回退失效的特征）", () => {
    for (const n of [1000, 1001, 9999]) {
      expect(nodeLabel("章", n, null)).not.toContain("undefined");
    }
  });
});
