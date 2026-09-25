// c-plot-split 5.1 — plots ↔ plot_items 契约：
// 恒带键（presence-gate：显式 [] 是清空意图，缺键=误清数据）＋含换行单条完整保留
// （禁 \n 拼串切条）＋超长/超条数保存链硬夹＋空白条目不算一条。
// 另钉 ogHasDraftContent 不含剧情（AI 起草不惊动剧情列表）与 ogPatchFromFills 丢
// plot_items（fill-gaps 产物不带剧情，白名单外的键不落表单）。
import { describe, expect, it } from "vitest";
import {
  EMPTY_OG_FORM,
  PLOT_MAX_ITEMS,
  PLOT_MAX_LEN,
  ogHasDraftContent,
  ogPatchFromFills,
  ogToForm,
  ogToPartial,
} from "@/components/novel/workbench/chapterForm";

const asChapterData = (partial: Record<string, unknown>) =>
  ({ volume: 1, chapter: 1, title: "第一章", status: "draft", ...partial }) as never;

describe("plots ↔ plot_items round-trip（恒带键）", () => {
  it("ogToPartial 恒带 plot_items：空表显式 []（清空意图），不缺键", () => {
    const partial = ogToPartial({ ...EMPTY_OG_FORM, plots: [] });
    expect("plot_items" in partial).toBe(true);
    expect(partial.plot_items).toEqual([]);
  });

  it("ogToForm 映射 plot_items → plots（逐条 String）", () => {
    const form = ogToForm(asChapterData({ plot_items: ["甲登场", "乙拦路"] }));
    expect(form.plots).toEqual(["甲登场", "乙拦路"]);
  });

  it("round-trip：读出再写回不丢条目", () => {
    const d = asChapterData({ plot_items: ["第一段场景", "第二段场景"] });
    const partial = ogToPartial(ogToForm(d), ogToForm(d) as never);
    expect(partial.plot_items).toEqual(["第一段场景", "第二段场景"]);
  });

  it("含换行的条目单条完整保留（禁按 \\n 切条）", () => {
    const multiLine = "甲进门，坐下。\n乙从屏风后出来。";
    const form = ogToForm(asChapterData({ plot_items: [multiLine, "另一条"] }));
    expect(form.plots).toEqual([multiLine, "另一条"]);
    expect(ogToPartial(form).plot_items).toEqual([multiLine, "另一条"]);
  });
});

describe("保存链硬夹（输入侧 maxLength 之外的兜底）", () => {
  it("单条超 200 字硬夹到 200", () => {
    const long = "x".repeat(260);
    const partial = ogToPartial({ ...EMPTY_OG_FORM, plots: [long] });
    expect(partial.plot_items?.[0]).toHaveLength(PLOT_MAX_LEN);
  });

  it("超 12 条只存前 12 条", () => {
    const plots = Array.from({ length: 15 }, (_, i) => `第${i}条`);
    const partial = ogToPartial({ ...EMPTY_OG_FORM, plots });
    expect(partial.plot_items).toHaveLength(PLOT_MAX_ITEMS);
    expect(partial.plot_items?.[11]).toBe("第11条");
  });

  it("空白条目不算一条（过滤后不足 12 条不补位）", () => {
    const partial = ogToPartial({
      ...EMPTY_OG_FORM,
      plots: ["  ", "真条目", "", "\n"],
    });
    expect(partial.plot_items).toEqual(["真条目"]);
  });

  it("含换行的空白条目也不算一条（trim 判定）", () => {
    const partial = ogToPartial({ ...EMPTY_OG_FORM, plots: ["\n \n", "有内容"] });
    expect(partial.plot_items).toEqual(["有内容"]);
  });
});

describe("剧情与相邻通道的隔离", () => {
  it("ogHasDraftContent 不含剧情：plots 内容不改变判定", () => {
    // 判定基准（segs 占位行等既有口径）保持不动——剧情是唯一不参与的格子
    const base = ogHasDraftContent(EMPTY_OG_FORM);
    expect(ogHasDraftContent({ ...EMPTY_OG_FORM, plots: ["甲登场", "乙拦路"] })).toBe(base);
    expect(ogHasDraftContent({ ...EMPTY_OG_FORM, summary: "一句话" })).toBe(true);
  });

  it("ogPatchFromFills 丢 plot_items（fill-gaps 产物不碰剧情）", () => {
    const patch = ogPatchFromFills({
      plot_items: ["不该进来的"],
      summary: "补上的概要",
    });
    expect(patch).toEqual({ summary: "补上的概要" });
    expect("plots" in patch).toBe(false);
  });
});
