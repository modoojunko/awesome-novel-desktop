// 章节默认字数（c-chapter-default-words，内测反馈#10）：章纲表单「留空默认 XXX」文案、
// placeholder 与查看态默认值跟随作品偏好（defaultWordTarget），缺省仍是 2500。
import { describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import OgPane from "@/components/novel/workbench/OgPane";
import { EMPTY_OG_FORM } from "@/components/novel/workbench/chapterForm";

vi.mock("@/lib/toast", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

function renderPane(opts: { editing: boolean; defaultWordTarget?: number }) {
  render(
    <OgPane
      form={{ ...EMPTY_OG_FORM, summary: "夜巡" }}
      label="第02章 · 夜巡"
      editing={opts.editing}
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
      defaultWordTarget={opts.defaultWordTarget}
    />,
  );
}

describe("章节默认字数进章纲表单", () => {
  it("查看态：未填显示本书默认值；填了显示填值", () => {
    renderPane({ editing: false, defaultWordTarget: 3200 });
    expect(screen.getByText("默认 3200")).toBeTruthy();
  });

  it("查看态缺省（未传 prop）仍显示 2500（存量行为不变）", () => {
    renderPane({ editing: false });
    expect(screen.getByText("默认 2500")).toBeTruthy();
  });

  it("编辑态：提示文案与 placeholder 跟随本书默认", () => {
    renderPane({ editing: true, defaultWordTarget: 3200 });
    expect(screen.getByText("500-6000，留空默认 3200")).toBeTruthy();
    expect(
      document.getElementById("wf-wt")?.getAttribute("placeholder"),
    ).toBe("3200");
  });

  it("编辑态缺省：文案与 placeholder 保持 2500", () => {
    renderPane({ editing: true });
    expect(screen.getByText("500-6000，留空默认 2500")).toBeTruthy();
    expect(
      document.getElementById("wf-wt")?.getAttribute("placeholder"),
    ).toBe("2500");
  });
});

describe("建议条数展示（c-scene-density）", () => {
  it("编辑态：字数框与剧情区按生效字数显示建议条数", () => {
    renderPane({ editing: true, defaultWordTarget: 3200 });
    expect(
      screen.getByText("按本章 3200 字，建议拆 8–10 条场景"),
    ).toBeTruthy();
    expect(
      screen.getByText("按本章 3200 字，建议拆 8–10 条场景（现 0 条）"),
    ).toBeTruthy();
  });

  it("留空走本书默认：2500 → 建议 6–8 条场景", () => {
    renderPane({ editing: true });
    expect(
      screen.getByText("按本章 2500 字，建议拆 6–8 条场景"),
    ).toBeTruthy();
  });

  it("填了用填值：4000 → 10–12 条", () => {
    renderPane({ editing: true });
    // renderPane 固定 EMPTY_OG_FORM，这里直接改用带 wt 的表单重渲
    cleanup();
    render(
      <OgPane
        form={{ ...EMPTY_OG_FORM, wt: "4000" }}
        label="第03章 · 长街"
        editing
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
      />,
    );
    expect(
      screen.getByText("按本章 4000 字，建议拆 10–12 条场景"),
    ).toBeTruthy();
  });

  it("查看态：剧情区显示建议行", () => {
    renderPane({ editing: false, defaultWordTarget: 2000 });
    expect(
      screen.getByText("按本章 2000 字，建议拆 6–8 条场景"),
    ).toBeTruthy();
  });
});
