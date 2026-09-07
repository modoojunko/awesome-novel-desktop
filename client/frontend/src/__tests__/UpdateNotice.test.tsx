import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const requestMock = vi.fn();

beforeEach(() => {
  requestMock.mockReset();
  vi.resetModules();
  vi.doMock("@/lib/api", () => ({ request: requestMock }));
});

function state(over: Partial<Record<string, unknown>> = {}) {
  return {
    current: "0.11",
    latest: "0.13",
    has_update: true,
    notes: "提升章纲 AI 起草的稳定性，修复若干问题",
    notes_url: "https://www.awesomenovel.com/download/v0.13/notes.html",
    download_url: "https://www.awesomenovel.com",
    ...over,
  };
}

async function mountAt(path: string) {
  const { default: UpdateNotice } = await import("@/components/UpdateNotice");
  return render(
    <MemoryRouter initialEntries={[path]}>
      <UpdateNotice />
    </MemoryRouter>,
  );
}

describe("UpdateNotice", () => {
  it("有更新：呈现版本号与当前版本对照、摘要与三个动作；外链为 target=_blank 锚点", async () => {
    requestMock.mockResolvedValue(state());
    await mountAt("/novels");

    expect(await screen.findByText("发现新版本 v0.13（当前 v0.11）")).toBeTruthy();
    expect(requestMock).toHaveBeenCalledWith("/update-check", { quiet: true });
    expect(screen.getByText("提升章纲 AI 起草的稳定性，修复若干问题")).toBeTruthy();
    const download = screen.getByRole("link", { name: "去下载" }) as HTMLAnchorElement;
    const notes = screen.getByRole("link", { name: "查看更新内容" }) as HTMLAnchorElement;
    expect(download.href).toBe("https://www.awesomenovel.com/");
    expect(download.target).toBe("_blank");
    expect(download.rel).toContain("noopener");
    expect(notes.href).toBe(
      "https://www.awesomenovel.com/download/v0.13/notes.html",
    );
    expect(screen.getByRole("button", { name: "知道了" })).toBeTruthy();
  });

  it("有更新但响应缺失 current：对照文案退回仅含新版本号", async () => {
    requestMock.mockResolvedValue(state({ current: "" }));
    await mountAt("/novels");
    expect(await screen.findByText("发现新版本 v0.13")).toBeTruthy();
  });

  it("无更新 / 检测失败：不渲染任何更新元素", async () => {
    requestMock.mockResolvedValue(state({ has_update: false, latest: "0.11" }));
    const { container } = await mountAt("/novels");
    await waitFor(() => expect(requestMock).toHaveBeenCalled());
    expect(container.querySelector(".update-strip")).toBeNull();

    requestMock.mockRejectedValue(new Error("network down"));
    const again = await mountAt("/novels");
    await waitFor(() => expect(requestMock).toHaveBeenCalled());
    expect(again.container.querySelector(".update-strip")).toBeNull();
  });

  it("「知道了」按版本关闭：调 dismiss 且提示条立即消失", async () => {
    requestMock.mockImplementation(async (path: string) =>
      path === "/update-check" ? state() : { dismissed: "0.13" },
    );
    const { container } = await mountAt("/novels");
    await screen.findByText("发现新版本 v0.13（当前 v0.11）");

    fireEvent.click(screen.getByRole("button", { name: "知道了" }));
    await waitFor(() =>
      expect(requestMock).toHaveBeenCalledWith("/update-check/dismiss", {
        method: "POST",
        body: JSON.stringify({ version: "0.13" }),
        quiet: true,
      }),
    );
    expect(container.querySelector(".update-strip")).toBeNull();
  });

  it("工作台路由用沉浸全宽变体，书架用居中变体", async () => {
    requestMock.mockResolvedValue(state());
    const imm = await mountAt("/novel/abc");
    await waitFor(() => expect(imm.container.querySelector(".update-strip")).toBeTruthy());
    expect(imm.container.querySelector(".update-strip")!.className).toContain(
      "update-strip--imm",
    );

    const list = await mountAt("/config");
    await waitFor(() => expect(list.container.querySelector(".update-strip")).toBeTruthy());
    expect(list.container.querySelector(".update-strip")!.className).not.toContain(
      "update-strip--imm",
    );
  });
});
