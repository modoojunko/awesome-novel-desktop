// 名单区两态承接（c-character-intro 4.1）：查看态 .fro 出场角色逐名渲染（chip＋没卡标
// ＋行级建卡入口）；编辑态 og-char-picker 追加非候选名字 chip（textarea 照旧）；
// 别名展开候选后不误标没卡。
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import OgPane from "@/components/novel/workbench/OgPane";
import { EMPTY_OG_FORM, type OgForm } from "@/components/novel/workbench/chapterForm";

const FORM: OgForm = {
  ...EMPTY_OG_FORM,
  summary: "林野夜巡",
  chars: "林野\n秦伯\n小野",
  plots: ["巷口又见袭击"],
};

function renderPane(editing: boolean, onQuickCreateChar = vi.fn()) {
  render(
    <OgPane
      form={FORM}
      characterNames={["林野", "小野"]} // 小野＝林野别名（已展开进候选）
      label="第02章 · 夜巡"
      editing={editing}
      loading={false}
      onPatch={vi.fn()}
      gaps={[]}
      confirmed={false}
      saving={false}
      onStartEdit={vi.fn()}
      onCancelEdit={vi.fn()}
      onGapClick={vi.fn()}
      onSaveDraft={vi.fn()}
      onConfirm={vi.fn()}
      onGoWrite={vi.fn()}
      onQuickCreateChar={onQuickCreateChar}
    />,
  );
  return onQuickCreateChar;
}

describe("名单两态：没卡标＋行级建卡入口", () => {
  it("查看态：.fro 出场角色逐名渲染——chip＋没卡标＋建卡入口；别名不误标", () => {
    const onQuick = renderPane(false);
    const view = screen.getByTestId("og-cast-view");
    expect(view.textContent).toContain("林野");
    // 秦伯（角色表没有）→ 没卡标＋建卡入口
    const claim = screen.getByTestId("claim-秦伯");
    expect(claim.previousElementSibling?.textContent).toBe("没卡");
    // 林野（有名有卡）不带没卡标
    expect(screen.queryByTestId("claim-林野")).toBeNull();
    // 小野（林野别名）不误标没卡
    expect(screen.queryByTestId("claim-小野")).toBeNull();
    expect(view.querySelectorAll(".no-card")).toHaveLength(1);
    // 行级建卡入口只预填称呼
    fireEvent.click(claim);
    expect(onQuick).toHaveBeenCalledWith("秦伯");
  });

  it("编辑态：og-char-picker 追加非候选名字 chip（没卡标＋建卡）；textarea 照旧", () => {
    const onQuick = renderPane(true);
    const picker = screen.getByLabelText("从角色卡选择出场角色");
    // 候选 chips（角色卡）
    expect(screen.getByRole("button", { name: "林野" })).toBeTruthy();
    // 非候选名字 chip（秦伯）：没卡标＋建卡
    const claim = screen.getByTestId("claim-秦伯");
    expect(claim.closest(".chip")?.textContent).toContain("秦伯");
    expect(claim.closest(".chip")?.querySelector(".no-card")).toBeTruthy();
    fireEvent.click(claim);
    expect(onQuick).toHaveBeenCalledWith("秦伯");
    // textarea 照旧（一行一个名字）
    const ta = document.getElementById("wf-chars") as HTMLTextAreaElement;
    expect(ta.value).toBe("林野\n秦伯\n小野");
    // 别名不误标（编辑态同口径）
    expect(screen.queryByTestId("claim-小野")).toBeNull();
    expect(picker).toBeTruthy();
  });
});
