// 章纲剧情区（c-plot-split 5.1）：空态直接输入框／加删／满 12 禁加／maxLength 硬夹／
// 编辑动作上抛（收回执＋软提示的信号源）。
import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import OgPane from "@/components/novel/workbench/OgPane";
import { EMPTY_OG_FORM, type OgForm } from "@/components/novel/workbench/chapterForm";

/** 受控表单的最小宿主：onPatch 回写本地 state；editing 控制查看/编辑两态（默认编辑） */
function Host({
  initial,
  onPlotEdit,
  editing = true,
  archived = false,
  confirmed = false,
  onUnconfirm,
  onStartEdit,
  onGapClick,
}: {
  initial: OgForm;
  onPlotEdit?: () => void;
  editing?: boolean;
  /** 归档章（c-og-archived-readonly）：恒查看态＋动作区不提供 */
  archived?: boolean;
  confirmed?: boolean;
  onUnconfirm?: () => void;
  onStartEdit?: () => void;
  onGapClick?: (key: string) => void;
}) {
  const [form, setForm] = useState<OgForm>(initial);
  return (
    <OgPane
      form={form}
      label="第2章 · 锚点"
      editing={editing}
      archived={archived}
      onPatch={(patch) => setForm((f) => ({ ...f, ...patch }))}
      onPlotEdit={onPlotEdit}
      gaps={[{ key: "changes", label: "必须完成的变化" }]}
      confirmed={confirmed}
      onUnconfirm={onUnconfirm}
      saving={false}
      onStartEdit={onStartEdit ?? (() => {})}
      onCancelEdit={() => {}}
      onGapClick={onGapClick ?? (() => {})}
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

describe("章纲查看/编辑两态（c-ch-og-readonly）", () => {
  it("查看态＝只读一页纸：内容可见、无剧情输入框、缺口 chip／编辑章纲可进编辑", () => {
    const onStartEdit = vi.fn();
    const onGapClick = vi.fn();
    render(
      <Host
        initial={{ ...EMPTY_OG_FORM, summary: "陆沉查舱段结构", plots: ["甲登场", "乙拦路"] }}
        editing={false}
        onStartEdit={onStartEdit}
        onGapClick={onGapClick}
      />,
    );
    // 只读一页纸渲染内容
    expect(screen.getByTestId("og-view")).toBeInTheDocument();
    expect(screen.getByText("陆沉查舱段结构")).toBeInTheDocument();
    expect(screen.getByText("甲登场")).toBeInTheDocument();
    // 没有表单输入框（剧情区是文本不是 textarea）
    expect(screen.queryByLabelText("第 1 条剧情")).toBeNull();
    // 缺口 chip（role=button，区别于同名的只读行标签）上抛 onGapClick
    fireEvent.click(screen.getByRole("button", { name: "必须完成的变化" }));
    expect(onGapClick).toHaveBeenCalledWith("changes");
    // 编辑章纲按钮上抛 onStartEdit
    fireEvent.click(screen.getByTestId("og-edit"));
    expect(onStartEdit).toHaveBeenCalledTimes(1);
  });

  it("编辑态＝表单可写：剧情输入框出现，编辑章纲按钮不在", () => {
    render(<Host initial={{ ...EMPTY_OG_FORM, plots: ["甲登场"] }} />);
    expect(screen.queryByTestId("og-view")).toBeNull();
    expect(screen.getByLabelText("第 1 条剧情")).toHaveValue("甲登场");
    expect(screen.queryByTestId("og-edit")).toBeNull();
  });
});

describe("归档章章纲只读（c-og-archived-readonly）", () => {
  it("查看态不提供动作区：撤回确认/去写正文/确认章纲/编辑章纲全不在场，一页纸本体保留", () => {
    render(
      <Host
        initial={{ ...EMPTY_OG_FORM, summary: "陆沉查舱段结构" }}
        editing={false}
        archived
        confirmed
        onUnconfirm={() => {}}
      />,
    );
    expect(screen.getByTestId("og-view")).toBeInTheDocument();
    expect(screen.getByText("陆沉查舱段结构")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "确认章纲" })).toBeNull();
    expect(screen.queryByRole("button", { name: "去写正文" })).toBeNull();
    expect(screen.queryByTestId("og-edit")).toBeNull();
    expect(screen.queryByTestId("og-unconfirm")).toBeNull();
  });

  it("编辑态残留（归档前进过表单）也强制回查看态：不渲染表单控件", () => {
    render(<Host initial={{ ...EMPTY_OG_FORM, plots: ["甲登场"] }} editing archived />);
    expect(screen.getByTestId("og-view")).toBeInTheDocument();
    expect(screen.queryByLabelText("第 1 条剧情")).toBeNull();
    expect(screen.queryByTestId("og-edit")).toBeNull();
  });
});
