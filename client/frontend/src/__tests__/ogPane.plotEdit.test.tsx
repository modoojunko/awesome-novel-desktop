// 章纲剧情区（c-plot-split 5.1）：空态直接输入框／加删／满 12 禁加／maxLength 硬夹／
// 编辑动作上抛（收回执＋软提示的信号源）。
import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import OgPane from "@/components/novel/workbench/OgPane";
import { EMPTY_OG_FORM, type OgForm } from "@/components/novel/workbench/chapterForm";

/** 受控表单的最小宿主：onPatch 回写本地 state */
function Host({ initial, onPlotEdit }: { initial: OgForm; onPlotEdit?: () => void }) {
  const [form, setForm] = useState<OgForm>(initial);
  return (
    <OgPane
      form={form}
      label="第2章 · 锚点"
      onPatch={(patch) => setForm((f) => ({ ...f, ...patch }))}
      onPlotEdit={onPlotEdit}
      gaps={[]}
      confirmed={false}
      saving={false}
      onSaveDraft={() => {}}
      onConfirm={() => {}}
      onGoWrite={() => {}}
    />
  );
}

const rows = () => screen.getAllByRole("textbox", { name: /第 \d+ 条剧情/ });

describe("章纲剧情区（列表编辑）", () => {
  it("空态直接就是一个空输入框＋引导 placeholder（无引导卡）", () => {
    render(<Host initial={{ ...EMPTY_OG_FORM, plots: [] }} />);
    expect(rows()).toHaveLength(1);
    expect(rows()[0]).toHaveAttribute("placeholder", expect.stringContaining("是场景不是正文"));
    expect(screen.getByText("加一条")).toBeInTheDocument();
  });

  it("加一条／删一条，留下的条目内容不丢", () => {
    render(<Host initial={{ ...EMPTY_OG_FORM, plots: ["甲登场"] }} />);
    fireEvent.click(screen.getByText("加一条"));
    expect(rows()).toHaveLength(2);
    fireEvent.change(rows()[1], { target: { value: "乙拦路" } });
    fireEvent.click(screen.getAllByLabelText("删掉这一条")[0]);
    expect(rows()).toHaveLength(1);
    expect(rows()[0]).toHaveValue("乙拦路");
  });

  it("满 12 条禁加（输入侧硬卡，不报错不冻结）", () => {
    const plots = Array.from({ length: 12 }, (_, i) => `第${i}条`);
    render(<Host initial={{ ...EMPTY_OG_FORM, plots }} />);
    expect(rows()).toHaveLength(12);
    expect(screen.getByText("加一条")).toBeDisabled();
  });

  it("单条 maxLength=200（输入侧硬夹）", () => {
    render(<Host initial={{ ...EMPTY_OG_FORM, plots: ["甲"] }} />);
    expect(rows()[0]).toHaveAttribute("maxlength", "200");
  });

  it("输入/加/删都上抛 onPlotEdit（收回执＋润色软提示的信号）", () => {
    const onPlotEdit = vi.fn();
    render(<Host initial={{ ...EMPTY_OG_FORM, plots: ["甲"] }} onPlotEdit={onPlotEdit} />);
    fireEvent.change(rows()[0], { target: { value: "甲改" } });
    expect(onPlotEdit).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByText("加一条"));
    expect(onPlotEdit).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getAllByLabelText("删掉这一条")[0]);
    expect(onPlotEdit).toHaveBeenCalledTimes(3);
  });
});
