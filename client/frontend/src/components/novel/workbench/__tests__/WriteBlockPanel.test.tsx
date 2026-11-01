/** 本章写法块只读条组件测试（c-kb-write-block 批D）：渲染/标记回写/可改口/零条目。 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const prefMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/kbApi", () => ({ kbApi: { pref: prefMock } }));

import WriteBlockPanel from "../WriteBlockPanel";

const ITEMS = [
  { entry_id: "e1", clause: "手法", reason: "场面：打斗", score: 0.9, text: "交锋先让三招。" },
  { entry_id: "e2", clause: "写法", reason: "通用场景", score: 0.7, text: "一句不超过22字。" },
];

describe("WriteBlockPanel", () => {
  beforeEach(() => {
    prefMock.mockReset().mockResolvedValue({ entry_id: "", adopt_count: 1, drop_count: 0, useful_rate: 1 });
  });

  it("渲染标题、块文本与逐条清单", () => {
    render(<WriteBlockPanel block="【本章写法指引】…红线与契约优先…" runId="r1" items={ITEMS} />);
    expect(screen.getByTestId("write-block-panel")).toBeTruthy();
    expect(screen.getByText(/本章写法块/)).toBeTruthy();
    expect(screen.getByText(/自动注入 · 不落库/)).toBeTruthy();
    expect(screen.getByText(/红线与契约优先/)).toBeTruthy();
    expect(screen.getByTestId("write-block-items").children.length).toBe(2);
    expect(screen.getByText("交锋先让三招。")).toBeTruthy();
  });

  it("点「没用」回写 pref false，再点「有用」改口", async () => {
    render(<WriteBlockPanel block="块" runId="r1" items={ITEMS} />);
    fireEvent.click(screen.getByTestId("wb-useless-e1"));
    await waitFor(() => expect(prefMock).toHaveBeenCalledWith("e1", false));
    fireEvent.click(screen.getByTestId("wb-useful-e1"));
    await waitFor(() => expect(prefMock).toHaveBeenCalledWith("e1", true));
  });

  it("清单空（全量化转影子等）→ 只显示块不渲染清单区", () => {
    render(<WriteBlockPanel block="块体" runId="r2" items={[]} />);
    expect(screen.getByTestId("write-block-panel")).toBeTruthy();
    expect(screen.queryByTestId("write-block-items")).toBeNull();
  });

  it("pref 失败静默（不炸组件，可重试）", async () => {
    prefMock.mockRejectedValueOnce(new Error("网络断了"));
    render(<WriteBlockPanel block="块" runId="r3" items={ITEMS} />);
    fireEvent.click(screen.getByTestId("wb-useless-e2"));
    await waitFor(() => expect(prefMock).toHaveBeenCalled());
    // 组件仍在、按钮仍可点
    expect(screen.getByTestId("wb-useless-e2")).toBeTruthy();
  });

  it("busy 期间连点被拒（防抖位）", async () => {
    let release: (v?: unknown) => void = () => {};
    prefMock.mockImplementationOnce(() => new Promise((res) => (release = res)));
    render(<WriteBlockPanel block="块" runId="r4" items={ITEMS} />);
    fireEvent.click(screen.getByTestId("wb-useless-e1"));
    fireEvent.click(screen.getByTestId("wb-useful-e1")); // busy=true：第二次点击被拒
    release();
    await waitFor(() => expect(prefMock).toHaveBeenCalledTimes(1)); // 只发一次
  });
});
