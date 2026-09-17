// 预览阅读器（preview-reader，c-preview-reader）组件契约：
//   三栏渲染 / 目录头计数 / 成稿状态标签（已归档优先）/ 章级导航首末禁用 /
//   initialRef 回退链 / 切章为预览本地态 / 阅读配置立即生效且落 localStorage。
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import PreviewView from "@/components/novel/workbench/PreviewView";
import { getBookFontSize } from "@/lib/prefs";

const apiGet = vi.fn();

vi.mock("@/lib/api", () => ({
  api: { get: (...args: unknown[]) => apiGet(...args) },
}));

function vol(name: string, no: number, title: string, chapters: Array<Record<string, unknown>>) {
  return { name, volume: no, title, chapters } as never;
}

const ch = (o: Record<string, unknown>) => ({
  title: "",
  word_count: 0,
  ...o,
});

const VOLUMES = [
  vol("vol-1", 1, "星海初航", [
    ch({ chapter: 1, title: "锚点", word_count: 1200, has_prose: true, archived: true }),
    ch({ chapter: 2, title: "跃迁", word_count: 800, has_prose: true, archived: false }),
    ch({ chapter: 3, title: "刻痕", word_count: 0, has_prose: false, archived: false }),
    ch({ chapter: 4, title: "空归档", word_count: 0, has_prose: false, archived: true }),
  ]),
];

function renderView(overrides: Partial<Parameters<typeof PreviewView>[0]> = {}) {
  const onRefresh = vi.fn();
  const onGoWrite = vi.fn();
  const onDownload = vi.fn();
  const props = {
    projectId: "p1",
    volumes: VOLUMES,
    onRefresh,
    initialRef: null as string | null,
    onGoWrite,
    onDownload,
    ...overrides,
  };
  const utils = render(<PreviewView {...props} />);
  return { ...utils, onRefresh, onGoWrite, onDownload };
}

describe("PreviewView — 三栏阅读器", () => {
  beforeEach(() => {
    localStorage.clear();
    apiGet.mockResolvedValue({ prose: "第一段正文\n第二段正文" });
  });

  it("三栏渲染：目录头主线计数 + 概览统计 + 四组阅读配置", async () => {
    renderView();
    await waitFor(() => expect(screen.getByTestId("pv-count")).toBeTruthy());
    expect(screen.getByTestId("pv-count").textContent).toContain("主线 4 章 · 1 卷 · 不含旧稿");
    const overview = screen.getByText("全书概览").closest(".pv-card")!;
    expect(overview.textContent).toContain("章节 4");
    expect(overview.textContent).toContain("字数 2000");
    expect(overview.textContent).toContain("已归档 2 · 草稿 1 · 拟定 1");
    for (const label of ["字号", "字体", "行距", "主题"]) {
      expect(screen.getByRole("group", { name: label })).toBeTruthy();
    }
  });

  it("目录行成稿状态：草稿 / 拟定 / 已归档（已归档优先于有无正文）", async () => {
    renderView();
    await waitFor(() => expect(document.querySelectorAll(".pv-ch").length).toBe(4));
    const rows = Array.from(document.querySelectorAll(".pv-ch"));
    // 第一章 已归档；第二章 草稿（有正文未归档）；第三章 拟定（无正文，无字数）
    expect(rows[0].textContent).toContain("已归档");
    expect(rows[1].textContent).toContain("草稿");
    expect(rows[1].textContent).toContain("800字");
    expect(rows[2].textContent).toContain("拟定");
    expect(rows[2].textContent).not.toContain("字");
    // 第四章 已归档但字数 0 —— 已归档优先，仍标已归档
    expect(rows[3].textContent).toContain("已归档");
  });

  it("首末章按钮禁用；目录切章为预览本地态（不回调写作侧）", async () => {
    const { onGoWrite } = renderView();
    await waitFor(() => expect(document.querySelectorAll(".pv-ch").length).toBe(4));
    expect(screen.getByTestId("pv-prev").getAttribute("aria-disabled")).toBe("true");
    expect(screen.getByTestId("pv-next").getAttribute("aria-disabled")).toBe("false");
    // 初始章 = initialRef 缺省回退首章
    expect(screen.getByTestId("pv-chapter").textContent).toContain("第一章 · 锚点");

    fireEvent.click(screen.getByTestId("pv-next"));
    expect(screen.getByTestId("pv-chapter").textContent).toContain("第二章 · 跃迁");
    expect(screen.getByTestId("pv-prev").getAttribute("aria-disabled")).toBe("false");
    // 末章：下一章禁用
    fireEvent.click(screen.getByTestId("pv-next"));
    fireEvent.click(screen.getByTestId("pv-next"));
    expect(screen.getByTestId("pv-next").getAttribute("aria-disabled")).toBe("true");
    // 本地态：无任何写作侧回调（onGoWrite 仅空书出口用）
    expect(onGoWrite).not.toHaveBeenCalled();
  });

  it("initialRef 定档；失效回退首章", async () => {
    const first = renderView({ initialRef: "vol-1-ch-2" });
    await waitFor(() =>
      expect(screen.getByTestId("pv-chapter").textContent).toContain("第二章 · 跃迁"),
    );
    first.unmount();
    renderView({ initialRef: "vol-1-ch-99" });
    await waitFor(() =>
      expect(screen.getByTestId("pv-chapter").textContent).toContain("第一章 · 锚点"),
    );
  });

  it("空书：目录与概览空态 + 去写作出口", async () => {
    const { onGoWrite } = renderView({ volumes: [] });
    await waitFor(() =>
      expect(screen.getByTestId("pv-count").textContent).toContain("还没有卷与章节"),
    );
    fireEvent.click(screen.getByRole("button", { name: "去写作" }));
    expect(onGoWrite).toHaveBeenCalledTimes(1);
  });

  it("阅读配置立即生效且落 localStorage；不污染写作偏好", async () => {
    localStorage.setItem("pref.book.p1.fs", "fs-s");
    const { container } = renderView();
    await waitFor(() => expect(screen.getByRole("group", { name: "主题" })).toBeTruthy());
    fireEvent.click(screen.getByRole("group", { name: "主题" }).children[2]); // 夜间
    fireEvent.click(screen.getByRole("group", { name: "字号" }).children[0]); // 小
    const root = container.querySelector(".view.preview-v")!;
    expect(root.className).toContain("pv-theme-night");
    expect((root as HTMLElement).style.getPropertyValue("--pv-size")).toBe("14px");
    expect(localStorage.getItem("pref.book.p1.read.theme")).toBe("night");
    expect(localStorage.getItem("pref.book.p1.read.size")).toBe("s");
    // 写作偏好原值不动
    expect(getBookFontSize("p1")).toBe("fs-s");
  });
});
