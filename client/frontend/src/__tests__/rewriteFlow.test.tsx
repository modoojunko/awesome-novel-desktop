import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { RewriteModal } from "@/components/novel/workbench/modals";
import { SettingsChangelogPane } from "@/components/novel/workbench/SettingsChangelogPane";

// ---------------------------------------------------------------------------
// C 组（chapter-rewrite）前端：重写确认弹窗三行影响面／设定投影 stale 提示／
// 右栏「下游挂着旧设定」统计接线。
// ---------------------------------------------------------------------------

const apiState = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/lib/api", () => ({ api: apiState }));

beforeEach(() => {
  apiState.get.mockReset();
});

describe("RewriteModal（影响面确认）", () => {
  it("渲染旧稿/后续/设定三行且确认回调可用；busy 锁定", () => {
    const onConfirm = vi.fn();
    const onClose = vi.fn();
    const { rerender } = render(
      <RewriteModal
        open
        onClose={onClose}
        chapterLabel="第 2 章 · 风起渡口"
        onConfirm={onConfirm}
      />,
    );
    expect(screen.getByText(/第 2 章 · 风起渡口/)).toBeTruthy();
    expect(screen.getByText(/存入版本历史/)).toBeTruthy();
    expect(screen.getByText(/基于旧设定/)).toBeTruthy();
    expect(screen.getByText(/开书设定永不改写/)).toBeTruthy();
    fireEvent.click(screen.getByTestId("rewrite-confirm"));
    expect(onConfirm).toHaveBeenCalledTimes(1);

    rerender(
      <RewriteModal open onClose={onClose} chapterLabel="第 2 章" busy onConfirm={onConfirm} />,
    );
    expect((screen.getByTestId("rewrite-confirm") as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByText("取消") as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("SettingsChangelogPane stale 呈现", () => {
  it("本章基于旧设定 → 顶部提示可见", async () => {
    apiState.get.mockImplementation(async (p: string) => {
      if (p.includes("/chapters/")) {
        return { stale: true, outline: { characters: [] } };
      }
      if (p.endsWith("/characters")) return [];
      if (p.endsWith("/characters/relations")) return [];
      if (p.endsWith("/volumes")) return [];
      if (p.endsWith("/settings/world")) return {};
      throw new Error("unexpected " + p);
    });
    render(<SettingsChangelogPane projectId="p1" chapterRef="vol-1-ch-2" />);
    expect(await screen.findByTestId("ch-stale-note")).toBeTruthy();
  });
});
