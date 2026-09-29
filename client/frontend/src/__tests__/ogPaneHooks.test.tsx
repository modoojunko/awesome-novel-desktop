// 章纲回收/悬念两格接伏笔台账（c-og-hooks-projection）：
// 派生纯函数（due/维持口径/排序）＋查看态投影/理由句＋编辑态 chip 勾选落格。
import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import OgPane from "@/components/novel/workbench/OgPane";
import { EMPTY_OG_FORM, type OgForm } from "@/components/novel/workbench/chapterForm";
import type { ChapterLite, HookRow } from "@/hooks/useHooksLedger";
import { hookChipCandidates, ogHookHints } from "@/lib/hookHints";

const CH1: ChapterLite = { id: "ch-1", ref: "vol-1-ch-1", chapter: 1, title: "圣银到场" };
const CH2: ChapterLite = { id: "ch-2", ref: "vol-1-ch-2", chapter: 2, title: "验刃" };

const hook = (over: Partial<HookRow>): HookRow => ({
  id: "h",
  code: "H-0001",
  description: "钩子",
  type: "mystery",
  priority: 2,
  status: "active",
  introduced_chapter_id: null,
  planned_chapter_id: null,
  mentioned_chapter_id: null,
  resolved_chapter_id: null,
  ...over,
});

describe("ogHookHints 派生（纯函数）", () => {
  it("回收投影＝计划收 ≤ 本章；未设计划收不进投影但进编辑候选", () => {
    const hints = ogHookHints(
      [
        hook({ id: "a", code: "H-0001", planned_chapter_id: "ch-1" }),
        hook({ id: "b", code: "H-0002" }),
        hook({ id: "c", code: "H-0003", planned_chapter_id: "ch-2" }),
      ],
      [CH1, CH2],
      "ch-1",
      1,
    );
    expect(hints.mres.map((h) => h.code)).toEqual(["H-0001"]);
    expect(hints.mres[0].plannedLabel).toBe("计划收 第 1 章");
    expect(hints.active.map((h) => h.code)).toEqual(["H-0001", "H-0003", "H-0002"]);
    expect(hints.activeCount).toBe(3);
  });

  it("维持投影＝埋点 ≠ 本章；无埋点开书条目计入；本章埋设的不计", () => {
    const hints = ogHookHints(
      [
        hook({ id: "a", code: "H-0001", introduced_chapter_id: null }),
        hook({ id: "b", code: "H-0002", introduced_chapter_id: "ch-1" }),
        hook({ id: "c", code: "H-0003", introduced_chapter_id: "ch-2" }),
      ],
      [CH1, CH2],
      "ch-2",
      2,
    );
    expect(hints.mhold.map((h) => h.code)).toEqual(["H-0001", "H-0002"]);
    expect(hints.mhold[0].originLabel).toBe("埋于 开书");
    expect(hints.mhold[1].originLabel).toBe("埋于 第 1 章");
    expect(hints.carryCount).toBe(2);
  });

  it("废弃/已收条目不进任何投影", () => {
    const hints = ogHookHints(
      [
        hook({ id: "a", status: "abandoned", planned_chapter_id: "ch-1" }),
        hook({ id: "b", status: "resolved", introduced_chapter_id: null }),
      ],
      [CH1],
      "ch-1",
      1,
    );
    expect(hints.activeCount).toBe(0);
    expect(hints.mres).toEqual([]);
    expect(hints.mhold).toEqual([]);
  });

  it("候选 chips 过滤：本格已含编号的不再列", () => {
    const hints = ogHookHints(
      [
        hook({ id: "a", code: "H-0001" }),
        hook({ id: "b", code: "H-0002" }),
      ],
      [CH1],
      "ch-1",
      1,
    );
    expect(hookChipCandidates(hints.active, "[H-0001] 已勾的").map((h) => h.code)).toEqual([
      "H-0002",
    ]);
  });
});

/** 受控表单宿主：onPatch 回写本地 state（编辑态勾选落格断言用） */
function Host({
  initial,
  editing = true,
  hookHints,
}: {
  initial: OgForm;
  editing?: boolean;
  hookHints?: Parameters<typeof OgPane>[0]["hookHints"];
}) {
  const [form, setForm] = useState<OgForm>(initial);
  return (
    <OgPane
      form={form}
      label="第1章 · 锚点"
      editing={editing}
      hookHints={hookHints}
      onPatch={(patch) => setForm((f) => ({ ...f, ...patch }))}
      gaps={[]}
      confirmed={false}
      saving={false}
      onStartEdit={() => {}}
      onCancelEdit={() => {}}
      onGapClick={() => {}}
      onSaveDraft={() => {}}
      onConfirm={() => {}}
      onGoWrite={() => {}}
    />
  );
}

const HINTS = ogHookHints(
  [
    hook({ id: "a", code: "H-0001", description: "猎血短刃的异常威力", planned_chapter_id: "ch-1", priority: 1 }),
    hook({ id: "b", code: "H-0002", description: "屋顶黑影的身份" }),
  ],
  [CH1, CH2],
  "ch-1",
  1,
);

describe("章纲查看态：两格接台账投影", () => {
  it("空格显示投影与来源注脚，不显示（未填）", () => {
    render(<Host initial={{ ...EMPTY_OG_FORM }} editing={false} hookHints={HINTS} />);
    const proj = screen.getByTestId("og-mres-proj");
    expect(proj.textContent).toContain("[H-0001] 猎血短刃的异常威力");
    expect(proj.textContent).toContain("计划收 第 1 章 · 该收了");
    expect(proj.textContent).toContain("来自伏笔台账");
    // 两格本体不出现（未填）占位（其余格照旧，全局查会误伤）
    expect(proj.closest(".fro")!.textContent).not.toContain("（未填）");
    const mholdProj = screen.getByTestId("og-mhold-proj");
    expect(mholdProj.textContent).toContain("[H-0001]");
    expect(mholdProj.closest(".fro")!.textContent).not.toContain("（未填）");
  });

  it("投影为空给理由句：未设计划收 / 均由本章埋设 / 台账全空", () => {
    // 台账有悬置但都未设计划收 → 回收格理由句；本章之前无埋设 → 维持格理由句
    const only = ogHookHints([hook({ id: "b", code: "H-0002", introduced_chapter_id: "ch-1" })], [CH1], "ch-1", 1);
    const { unmount } = render(<Host initial={{ ...EMPTY_OG_FORM }} editing={false} hookHints={only} />);
    expect(screen.getByText(/计划收都不在本章/)).toBeInTheDocument();
    expect(screen.getByText(/均由本章埋设/)).toBeInTheDocument();
    unmount();
    // 台账全空
    const empty = ogHookHints([], [CH1], "ch-1", 1);
    render(<Host initial={{ ...EMPTY_OG_FORM }} editing={false} hookHints={empty} />);
    expect(screen.getAllByText("无——台账暂无悬置伏笔")).toHaveLength(2);
  });

  it("格非空只显示格内内容，不并列投影", () => {
    render(
      <Host
        initial={{ ...EMPTY_OG_FORM, mres: "[H-0009] 作者手填的条目" }}
        editing={false}
        hookHints={HINTS}
      />,
    );
    expect(screen.getByText("[H-0009] 作者手填的条目")).toBeInTheDocument();
    expect(screen.queryByTestId("og-mres-proj")).toBeNull();
  });

  it("台账不可用（undefined）回落（未填）占位", () => {
    render(<Host initial={{ ...EMPTY_OG_FORM }} editing={false} />);
    expect(screen.getAllByText("（未填）").length).toBeGreaterThanOrEqual(2);
  });
});

describe("章纲编辑态：台账候选勾选落格", () => {
  it("点 chip 追加一行编号条目，走 onPatch；本格已有编号不再列", () => {
    render(
      <Host
        initial={{ ...EMPTY_OG_FORM, mres: "[H-0002] 屋顶黑影的身份" }}
        editing
        hookHints={HINTS}
      />,
    );
    // mres 格：H-0002 已在 → 只剩 H-0001 候选（断言只看候选框，格值里本就有 H-0002）
    const mresBox = screen.getByTestId("og-hooks-mres");
    const mresField = mresBox.closest(".field")!;
    const textarea = mresField.querySelector("textarea")!;
    expect(mresBox.textContent).toContain("H-0001");
    expect(mresBox.textContent).not.toContain("H-0002");
    fireEvent.click(screen.getByTestId("og-hook-mres-H-0001"));
    expect(textarea).toHaveValue(
      "[H-0002] 屋顶黑影的身份\n[H-0001] 猎血短刃的异常威力",
    );
    // 勾选后候选消失
    expect(screen.queryByTestId("og-hooks-mres")).toBeNull();
  });

  it("维持格候选＝本章之前埋设的悬置伏笔，点选落 mhold 格", () => {
    render(<Host initial={{ ...EMPTY_OG_FORM }} editing hookHints={HINTS} />);
    const mholdField = screen.getByTestId("og-hooks-mhold").closest(".field")!;
    const textarea = mholdField.querySelector("textarea")!;
    // HINTS 场景：两条都无埋点（开书）→ 都进维持候选
    fireEvent.click(screen.getByTestId("og-hook-mhold-H-0002"));
    expect(textarea).toHaveValue("[H-0002] 屋顶黑影的身份");
  });
});
