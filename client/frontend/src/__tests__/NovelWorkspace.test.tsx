import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";
import NovelWorkspace from "@/components/novel/NovelWorkspace";
import {
  ProjectContext,
  type ProjectState,
} from "@/components/novel/license/ProjectShell";
import {
  TierContext,
  type TierState,
} from "@/components/novel/license/LicenseProvider";

// ---------------------------------------------------------------------------
// TE-16 — NovelWorkspace（PR3 book.html 复刻）：
//   modnav 三态（设定/写作/预览），默认落写作视图（three-col 常驻挂载）；
//   免费态零 phase-status 请求；点章强制落章纲页签；正文脏状态切视图不丢；
//   PRO 态工具栏 AI 生成正文入口 + 右栏真实工具卡。
// jsdom 无 CSS：视图切换断言走 .view.three-col 的 on class 而非可见性。
// ---------------------------------------------------------------------------

const apiState = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
  request: vi.fn(),
  fetchPhaseStatus: vi.fn(),
  fetchStory: vi.fn(),
}));

vi.mock("@/lib/api", () => ({ api: apiState, request: apiState.request }));

function TierProvider({ tier, children }: { tier: string; children: ReactNode }) {
  const isMember = tier !== "none";
  const value: TierState = {
    tier,
    isFree: !isMember,
    isMember,
    expired: false,
    expiresAt: "",
    isPro: isMember,
    trialRemainingDays: 0,
    entitlement: null,
    entitlementDegraded: false,
  syncFailed: false,
    loading: false,
    error: null,
    refetch: () => {},
  };
  return <TierContext.Provider value={value}>{children}</TierContext.Provider>;
}

function ProjectProvider({ children }: { children: ReactNode }) {
  const value: ProjectState = {
    project: { id: "p1", name: "测试小说", source: "manual", type: "" },
    loading: false,
    error: null,
    updateProject: vi.fn(),
  };
  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>;
}

/** 空卷树：中栏呈现「开始创作」空面板。 */
function mockEmptyTree() {
  apiState.get.mockImplementation((path: string) => {
    if (path === "/novels/p1/volumes") return Promise.resolve([]);
    if (path === "/novels/p1/readiness")
      return Promise.resolve({ complete: false, missing: [], warning: "" });
    return Promise.resolve({});
  });
  apiState.fetchStory.mockResolvedValue({ synopsis: "" });
}

/** 一卷一章 mock 数据（选中章 → 章对象工作台）。 */
const ONE_VOL_ONE_CHAPTER = [
  {
    ref: "vol-1",
    title: "第一卷",
    summary: "",
    chapter_count: 1,
    chapters: [
      {
        ref: "vol-1-ch-1",
        volume: 1,
        chapter: 1,
        title: "第一章",
        status: "outline",
        word_count: 0,
        has_prose: false,
        outline_status: "unfilled",
        archived: false,
      },
    ],
  },
];

const ONE_CHAPTER_DATA = {
  volume: 1,
  chapter: 1,
  title: "第一章",
  status: "outline",
  outline: { summary: "" },
  prose: "",
};

/** 一卷一章：默认全展开 → 直接点章 → 章对象工作台。 */
function mockOneChapterTree() {
  apiState.get.mockImplementation((path: string) => {
    if (path === "/novels/p1/volumes") return Promise.resolve(ONE_VOL_ONE_CHAPTER);
    if (path === "/novels/p1/chapters/vol-1-ch-1")
      return Promise.resolve(ONE_CHAPTER_DATA);
    if (path === "/novels/p1/readiness")
      return Promise.resolve({ complete: false, missing: [], warning: "" });
    return Promise.resolve({});
  });
  apiState.request.mockResolvedValue([]); // 提示词 quiet 探测 → 自动组装
  apiState.fetchStory.mockResolvedValue({ synopsis: "" });
  apiState.put.mockResolvedValue({});
  apiState.post.mockResolvedValue({});
}

/** PRO 一卷一章：额外 mock phase-status（settings done → 无 OnboardingCard）。 */
function mockOneChapterTreePro() {
  apiState.get.mockImplementation((path: string) => {
    if (path === "/novels/p1/volumes") return Promise.resolve(ONE_VOL_ONE_CHAPTER);
    if (path === "/novels/p1/chapters/vol-1-ch-1")
      return Promise.resolve(ONE_CHAPTER_DATA);
    if (path === "/novels/p1/workflow/phase-status")
      return Promise.resolve({
        phases: {
          settings: "done",
          outline: "pending",
          prompt: "pending",
          write: "pending",
          archive: "pending",
        },
        warnings: [],
      });
    return Promise.resolve({});
  });
  apiState.request.mockResolvedValue([]);
  apiState.fetchStory.mockResolvedValue({ synopsis: "" });
  apiState.put.mockResolvedValue({});
  apiState.post.mockResolvedValue({});
}

function renderWorkspace(tier = "none") {
  return render(
    <MemoryRouter initialEntries={["/novel/p1"]}>
      <TierProvider tier={tier}>
        <ProjectProvider>
          <Routes>
            <Route path="/novel/:id" element={<NovelWorkspace />} />
          </Routes>
        </ProjectProvider>
      </TierProvider>
    </MemoryRouter>,
  );
}

/** 选中第一章并等待章对象工作台挂载（树默认全展开，无需先点卷）。 */
async function selectFirstChapter() {
  fireEvent.click(await screen.findByText("第一章"));
  await screen.findByRole("tab", { name: /^章纲/ });
}

function threeColClass(): string {
  return document.querySelector(".view.three-col")?.className ?? "";
}

beforeEach(() => {
  apiState.get.mockReset();
  apiState.post.mockReset();
  apiState.put.mockReset();
  apiState.patch.mockReset();
  apiState.delete.mockReset();
  apiState.request.mockReset();
  apiState.fetchStory.mockReset();
  apiState.request.mockResolvedValue([]);
  localStorage.clear();
});

describe("默认落写作视图（免费）", () => {
  it("渲染后即呈现 three-col 写作工作台，无阶段催促 UI", async () => {
    mockEmptyTree();
    renderWorkspace("none");
    // 中栏空面板 + 左树空态
    expect(await screen.findByText("开始创作")).toBeVisible();
    expect(
      screen.getByText("还没有卷与章节。点击左上「＋」添加第一卷。"),
    ).toBeVisible();
    // novelbar：书名 + 免费提示
    expect(screen.getAllByText("测试小说").length).toBeGreaterThan(0);
    expect(screen.getByText(/免费模式 · 写作功能完整/)).toBeVisible();
    // modnav 三态 + 写作 tab on + three-col on（jsdom 无 CSS → 断言 class）
    expect(screen.getByRole("button", { name: /^设定/ })).toBeDefined();
    expect(screen.getByRole("button", { name: /^写作/ })).toBeDefined();
    expect(screen.getByRole("button", { name: "预览" })).toBeDefined();
    expect(screen.getByRole("button", { name: /^写作/ }).className).toContain("on");
    expect(threeColClass()).toContain("on");
    // 免费态零 phase-status 请求（ProContainer 整棵不渲染）
    expect(apiState.get).not.toHaveBeenCalledWith(
      "/novels/p1/workflow/phase-status",
    );
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("免费态：选中章 → 章对象工作台", () => {
  it("点章强制落章纲页签；正文页有编辑器、无 AI 入口；右栏 locked", async () => {
    mockOneChapterTree();
    renderWorkspace("none");
    await selectFirstChapter();
    // 两页签（章纲默认选中；提示词子 label PRO-only：免费隐藏 ai-prompt-crafting）
    const tabs = screen.getAllByRole("tab");
    expect(tabs.length).toBe(2);
    const ogTab = screen.getByRole("tab", { name: /^章纲/ });
    expect(ogTab.getAttribute("aria-selected")).toBe("true");
    expect(screen.queryByRole("tab", { name: /^提示词/ })).toBeNull();
    expect(screen.getByRole("tab", { name: /^正文/ })).toBeDefined();
    // 工具栏章名（树行 + 工具栏两处「第一章」→ chMeta 对齐成功的证据）
    expect(screen.getAllByText("第一章").length).toBeGreaterThanOrEqual(2);
    // 章纲面板必填字段在渲染
    expect(screen.queryAllByText(/核心任务/).length).toBeGreaterThan(0);
    // 点「正文」→ contenteditable 编辑器挂载；免费无 AI 按钮
    fireEvent.click(screen.getByRole("tab", { name: /^正文/ }));
    await waitFor(() => expect(document.querySelector(".editor")).toBeTruthy());
    expect(screen.queryByRole("button", { name: "AI 生成正文" })).toBeNull();
    // 右栏免费 locked 卡 + 规划中（章模式三卡）
    expect(screen.getByText(/解锁后可由「设定 \+ 章纲」生成正文/)).toBeVisible();
    expect(screen.getByText("续写建议")).toBeVisible();
  });
});

describe("设定视图懒挂载 / 离开卸载", () => {
  it("经 modnav「设定」进入设定视图，点「写作」返回后卸载", async () => {
    mockEmptyTree();
    renderWorkspace("none");
    await screen.findByText("开始创作");
    expect(threeColClass()).toContain("on");

    fireEvent.click(screen.getByRole("button", { name: /^设定/ }));
    await waitFor(() =>
      expect(screen.getAllByText("AI痕迹控制").length).toBeGreaterThan(0),
    );
    // 写作视图常驻挂载：仅摘掉 on class（jsdom 断言 class 而非可见性）
    expect(threeColClass()).not.toContain("on");

    fireEvent.click(screen.getByRole("button", { name: /^写作/ }));
    await waitFor(() =>
      expect(screen.queryAllByText("AI痕迹控制").length).toBe(0),
    );
    expect(threeColClass()).toContain("on");
  });
});

describe("写作视图常驻挂载：切视图 prose 不丢", () => {
  it("选中章输入后切到设定再返回，正文内容保留", async () => {
    mockOneChapterTree();
    renderWorkspace("none");
    await selectFirstChapter();
    fireEvent.click(screen.getByRole("tab", { name: /^正文/ }));
    const editor = await waitFor(() => {
      const el = document.querySelector(".editor");
      expect(el).toBeTruthy();
      return el as HTMLElement;
    });
    editor.innerHTML = "<p>我在专注写作</p>";
    fireEvent.input(editor);

    // 切到设定 → 经 modnav「写作」返回
    fireEvent.click(screen.getByRole("button", { name: /^设定/ }));
    await waitFor(() =>
      expect(screen.getAllByText("AI痕迹控制").length).toBeGreaterThan(0),
    );
    fireEvent.click(screen.getByRole("button", { name: /^写作/ }));

    // prose 保留（ProsePane hidden 切换、不卸载）
    await waitFor(() =>
      expect(document.querySelector(".editor")?.textContent).toBe("我在专注写作"),
    );
  });
});

describe("PRO 态：徽标 + phase-status + AI 入口", () => {
  it("PRO 渲染 pill 徽并请求 phase-status；正文页可见 AI 生成正文", async () => {
    mockOneChapterTreePro();
    renderWorkspace("monthly");
    expect(document.querySelector(".pill-pro")).toBeTruthy();
    expect(screen.queryByText(/免费模式/)).toBeNull();
    expect(screen.queryByRole("button", { name: "升级 PRO" })).toBeNull();
    await waitFor(() =>
      expect(apiState.get).toHaveBeenCalledWith(
        "/novels/p1/workflow/phase-status",
      ),
    );

    await selectFirstChapter();
    fireEvent.click(screen.getByRole("tab", { name: /^正文/ }));
    // 工具栏 AI 入口（PRO-only）+ 右栏真实工具卡
    expect(
      await screen.findByRole("button", { name: "AI 生成正文" }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "续写" })).toBeDefined();
    expect(screen.getByRole("button", { name: "润色选段" })).toBeDefined();
    expect(screen.getByRole("button", { name: "扩写选段" })).toBeDefined();
  });
});
