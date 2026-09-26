// c-plot-split 2.3 — 剧情条目预算不进 ogFormIssues 整表问题清单：
// issues 非空会连坐冻结自动保存（ChapterWorkspace），所以超长/超条数只在
// 输入侧硬夹（maxLength=200 ＋满 12 禁加），保存链静默夹、永不 422。
// 本测试钉「表单带超预算 plots 时 ogFormIssues 逐字等于不带 plots 的结果」——
// 5.1 把 plots 接进 OgForm 后此钉仍须成立（预算永不进 issues）。
import { describe, expect, it } from "vitest";
import {
  EMPTY_OG_FORM,
  ogFormIssues,
  type OgForm,
} from "@/components/novel/workbench/chapterForm";

describe("剧情条目预算不进整表问题清单（不冻结自动保存）", () => {
  it("超预算 plots 不产生任何 ogFormIssues", () => {
    const base: OgForm = { ...EMPTY_OG_FORM, title: "第一章" };
    const overBudget = {
      ...base,
      plots: ["x".repeat(500), ...Array.from({ length: 15 }, (_, i) => `第${i}条`)],
    } as unknown as OgForm;
    expect(ogFormIssues(overBudget)).toEqual([]);
    expect(ogFormIssues(overBudget)).toEqual(ogFormIssues(base));
  });

  it("空 plots / 缺 plots 同样零问题（不填也能写）", () => {
    const withEmpty = { ...EMPTY_OG_FORM, plots: [] } as unknown as OgForm;
    expect(ogFormIssues(withEmpty)).toEqual(ogFormIssues(EMPTY_OG_FORM));
    expect(ogFormIssues(EMPTY_OG_FORM)).toEqual([]);
  });
});
