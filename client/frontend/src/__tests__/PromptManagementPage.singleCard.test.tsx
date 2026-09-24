// ai-prompt-crafting 7.2 — PromptManagementPage 整章单卡：
// 概览单条「整章写作提示词」行 + 状态徽标（无分段列表/生成按钮）；
// 查看 → 编辑保存（PUT write）；「AI 润色」换稿；无存量空态引导。
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import PromptManagementPage from "@/components/novel/PromptManagementPage";

const apiState = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
}));
const reqState = vi.hoisted(() => ({ request: vi.fn() }));
const polishState = vi.hoisted(() => ({ polishWritePrompt: vi.fn() }));
const toastState = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
}));

vi.mock("@/lib/api", () => ({ api: apiState, request: reqState.request }));
vi.mock("@/lib/ai", () => ({ polishWritePrompt: polishState.polishWritePrompt }));
vi.mock("@/lib/toast", () => ({ toast: toastState }));
vi.mock("@/lib/auth", () => ({ getToken: () => "t" }));
vi.mock("@/lib/env", () => ({ getApiBaseUrl: () => "" }));

const STORED = "vol-1-ch-1-write-prompt.md";

function mockVolumes() {
  apiState.get.mockResolvedValue([
    { ref: "vol-1", chapters: [{ ref: "vol-1-ch-1", title: "第一章", chapter: 1 }] },
  ]);
}

function mockFetchText(text: string) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve(text),
    }),
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
  mockVolumes();
  // 总览走批量端点（c-silent-data-guards：N+1 收口）——桩给聚合形状
  reqState.request.mockResolvedValue({
    chapters: [{ ref: "vol-1-ch-1", has_stored: true }],
  });
  apiState.put.mockResolvedValue({});
});

describe("概览：整章单卡", () => {
  it("有存量 → 单条「整章写作提示词」行 + 已保存徽标；无分段列表与生成按钮", async () => {
    render(<PromptManagementPage projectId="p1" chapterRef="vol-1-ch-1" />);
    await waitFor(() => expect(screen.getByTestId("pm-write-row")).toBeTruthy());
    expect(screen.getByText("整章写作提示词")).toBeTruthy();
    // 徽标由 request 回包异步翻转，不能假设与行同帧就绪（全量并发下偶发挂）
    await waitFor(() => expect(screen.getByText("已保存")).toBeTruthy());
    // 批量端点一次取全书（N+1 收口）：总览取数只发一次 request
    expect(reqState.request).toHaveBeenCalledTimes(1);
    expect(reqState.request).toHaveBeenCalledWith("/novels/p1/prompt-summary", { soft503: true });
    // 分段链路退役：不渲染段落数/分段行/生成按钮
    expect(screen.queryByText("生成段落提示词")).toBeNull();
    expect(screen.queryByText(/段/)).toBeNull();
  });

  it("无存量 → 未生成徽标", async () => {
    reqState.request.mockResolvedValue({
      chapters: [{ ref: "vol-1-ch-1", has_stored: false }],
    });
    render(<PromptManagementPage projectId="p1" chapterRef="vol-1-ch-1" />);
    await waitFor(() => expect(screen.getByText("未生成")).toBeTruthy());
  });
});

describe("查看 / 编辑 / 润色", () => {
  it("查看：分节渲染存量内容", async () => {
    mockFetchText("## 角色定位\n小说家\n\n## 任务指示\n写完这一章");
    render(<PromptManagementPage projectId="p1" chapterRef="vol-1-ch-1" />);
    await waitFor(() => expect(screen.getByTestId("pm-write-row")).toBeTruthy());
    fireEvent.click(screen.getByTestId("pm-write-row"));
    await waitFor(() => expect(screen.getByTestId("pm-write-view")).toBeTruthy());
    expect(screen.getByText("角色定位")).toBeTruthy();
    expect(screen.getByText("小说家")).toBeTruthy();
    expect(screen.getByTestId("pm-polish")).toBeTruthy();
  });

  it("无存量 → 空态引导 + AI 润色后换稿并标已润色", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 404, text: () => Promise.resolve("") }),
    );
    render(<PromptManagementPage projectId="p1" chapterRef="vol-1-ch-1" />);
    await waitFor(() => expect(screen.getByTestId("pm-write-row")).toBeTruthy());
    fireEvent.click(screen.getByTestId("pm-write-row"));
    await waitFor(() => expect(screen.getByTestId("pm-write-empty")).toBeTruthy());

    polishState.polishWritePrompt.mockResolvedValue("## 任务指示\n润色稿");
    fireEvent.click(screen.getByTestId("pm-polish"));
    await waitFor(() =>
      expect(screen.getByText("润色稿")).toBeTruthy(),
    );
    expect(polishState.polishWritePrompt).toHaveBeenCalledWith("p1", "vol-1-ch-1");
    expect(toastState.success).toHaveBeenCalled();
    // 返回概览：状态徽标变「已润色」
    fireEvent.click(screen.getByText("返回"));
    await waitFor(() => expect(screen.getByText("已润色")).toBeTruthy());
  });

  it("编辑保存：PUT write 端点 + 徽标变已修改", async () => {
    mockFetchText("## 角色定位\n旧稿");
    render(<PromptManagementPage projectId="p1" chapterRef="vol-1-ch-1" />);
    await waitFor(() => expect(screen.getByTestId("pm-write-row")).toBeTruthy());
    fireEvent.click(screen.getByTestId("pm-write-row"));
    await waitFor(() => expect(screen.getByTestId("pm-write-view")).toBeTruthy());
    fireEvent.click(screen.getByText("编辑"));
    fireEvent.change(screen.getByTestId("pm-editor"), {
      target: { value: "## 角色定位\n作家手改" },
    });
    fireEvent.click(screen.getByTestId("pm-save"));
    await waitFor(() =>
      expect(apiState.put).toHaveBeenCalledWith(
        "/novels/p1/chapters/vol-1-ch-1/prompts/write",
        { content: "## 角色定位\n作家手改" },
      ),
    );
    fireEvent.click(screen.getByText("返回"));
    await waitFor(() => expect(screen.getByText("已修改")).toBeTruthy());
  });
});
