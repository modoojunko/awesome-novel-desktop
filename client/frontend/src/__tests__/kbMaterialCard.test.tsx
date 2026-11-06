// 素材提示卡直测（c-kb-summarize）：提示文案/删除确认两臂/note/ busy 禁点——契约 100%。
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import KbMaterialCard from "@/components/tools/KbMaterialCard";

afterEach(() => cleanup());

describe("KbMaterialCard", () => {
  it("提示文案与删除按钮在位；confirm 取消不触发 onDelete", () => {
    const onDelete = vi.fn();
    const spy = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<KbMaterialCard onDelete={onDelete} />);
    expect(screen.getByText(/这是素材——/)).toBeTruthy();
    expect(screen.getByTestId("kb-material-delete")).toBeTruthy();
    fireEvent.click(screen.getByTestId("kb-material-delete"));
    expect(onDelete).not.toHaveBeenCalled();
    expect(spy).toHaveBeenCalledWith("删除这条素材？删除后不可恢复。");
    spy.mockRestore();
  });

  it("confirm 确认触发 onDelete", () => {
    const onDelete = vi.fn();
    const spy = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<KbMaterialCard onDelete={onDelete} />);
    fireEvent.click(screen.getByTestId("kb-material-delete"));
    expect(onDelete).toHaveBeenCalledTimes(1);
    spy.mockRestore();
  });

  it("busy 禁点", () => {
    const onDelete = vi.fn();
    render(<KbMaterialCard busy onDelete={onDelete} />);
    expect((screen.getByTestId("kb-material-delete") as HTMLButtonElement).disabled).toBe(true);
  });

  it("note 展示（删除失败等提示）", () => {
    render(<KbMaterialCard note="删除失败" onDelete={() => {}} />);
    expect(screen.getByText("删除失败")).toBeTruthy();
  });
});
