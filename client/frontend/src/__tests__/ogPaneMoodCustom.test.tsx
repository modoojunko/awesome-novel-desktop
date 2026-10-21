// 章纲·主情绪「自定义…」可输入（2026-10-21 用户反馈）：
// 受控 select 若只按 form.mood 反推选中项，选「自定义…」会先清空值 → 立刻回落
// 「请选择主情绪」→ 条件渲染的输入框永不出现。待输入态必须单独记。
import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import OgPane from "@/components/novel/workbench/OgPane";
import { EMPTY_OG_FORM, type OgForm } from "@/components/novel/workbench/chapterForm";

function Host({ initial, editing = true }: { initial?: OgForm; editing?: boolean }) {
  const [form, setForm] = useState<OgForm>(initial ?? { ...EMPTY_OG_FORM });
  return (
    <OgPane
      form={form}
      label="第1章 · 锚点"
      editing={editing}
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

const moodSelect = () => document.querySelector("#wf-mood select") as HTMLSelectElement;
const moodInput = () => screen.queryByPlaceholderText("输入自定义情绪（≤50 字）");

describe("章纲·主情绪自定义", () => {
  it("选中「自定义…」立即出现输入框，选中项不回落 placeholder", () => {
    render(<Host />);
    const sel = moodSelect();
    fireEvent.change(sel, { target: { value: "__custom" } });
    expect(sel.value).toBe("__custom");
    expect(moodInput()).not.toBeNull();
  });

  it("输入自定义情绪后选中项与值同源；清空可重输（待输入态不塌）", () => {
    render(<Host />);
    fireEvent.change(moodSelect(), { target: { value: "__custom" } });
    fireEvent.change(moodInput()!, { target: { value: "荒诞" } });
    expect((moodInput() as HTMLInputElement).value).toBe("荒诞");
    expect(moodSelect().value).toBe("__custom");

    fireEvent.change(moodInput()!, { target: { value: "" } });
    expect(moodInput()).not.toBeNull();
    expect(moodSelect().value).toBe("__custom");
  });

  it("切回预设档位：输入框收起、值落预设", () => {
    render(<Host />);
    fireEvent.change(moodSelect(), { target: { value: "__custom" } });
    fireEvent.change(moodInput()!, { target: { value: "荒诞" } });

    fireEvent.change(moodSelect(), { target: { value: "紧张" } });
    expect(moodInput()).toBeNull();
    expect(moodSelect().value).toBe("紧张");
  });

  it("落库值本身是自定义文本（载入/AI 填入）：直接进自定义态并回显", () => {
    render(<Host initial={{ ...EMPTY_OG_FORM, mood: "荒诞" }} />);
    expect((moodInput() as HTMLInputElement).value).toBe("荒诞");
    expect(moodSelect().value).toBe("__custom");
  });

  it("退出编辑态（切章回落查看态）清掉待输入态，下次进入按落库值判定", () => {
    const initial = { ...EMPTY_OG_FORM };
    const { rerender } = render(<Host initial={initial} editing />);
    fireEvent.change(moodSelect(), { target: { value: "__custom" } });
    expect(moodInput()).not.toBeNull();

    rerender(<Host initial={initial} editing={false} />);
    rerender(<Host initial={initial} editing />);
    expect(moodInput()).toBeNull();
    expect(moodSelect().value).toBe("");
  });
});
