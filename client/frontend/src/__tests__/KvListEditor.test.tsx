import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import KvListEditor from "@/components/novel/settings/world/KvListEditor";

describe("KvListEditor", () => {
  beforeEach(() => vi.clearAllMocks());

  it("建议名目点选即加一条", () => {
    const onChange = vi.fn();
    render(<KvListEditor rows={[]} onChange={onChange} suggests={["能力上限", "感情底线"]} />);
    fireEvent.click(screen.getByText("能力上限"));
    expect(onChange).toHaveBeenCalledWith([{ key: "能力上限", value: "" }]);
  });

  it("已用名目从建议区隐藏", () => {
    render(
      <KvListEditor
        rows={[{ key: "感情底线", value: "" }]}
        onChange={vi.fn()}
        suggests={["能力上限", "感情底线"]}
      />,
    );
    expect(screen.queryByText("感情底线")).toBeNull();
    expect(screen.getByText("能力上限")).toBeTruthy();
  });

  it("满员：加一条按钮隐藏、建议 chips 禁点", () => {
    const onChange = vi.fn();
    render(
      <KvListEditor
        rows={[
          { key: "一", value: "" },
          { key: "二", value: "" },
        ]}
        onChange={onChange}
        suggests={["三"]}
        maxItems={2}
      />,
    );
    expect(screen.queryByText(/加一条/)).toBeNull();
    const chip = screen.getByText("三").closest("button")!;
    expect(chip.disabled).toBe(true);
    fireEvent.click(chip);
    expect(onChange).not.toHaveBeenCalled();
  });

  it("删行：点删除图标回调少一行", () => {
    const onChange = vi.fn();
    render(
      <KvListEditor
        rows={[
          { key: "甲", value: "1" },
          { key: "乙", value: "2" },
        ]}
        onChange={onChange}
      />,
    );
    const dels = screen.getAllByLabelText("删除本条");
    fireEvent.click(dels[0]);
    expect(onChange).toHaveBeenCalledWith([{ key: "乙", value: "2" }]);
  });
});
