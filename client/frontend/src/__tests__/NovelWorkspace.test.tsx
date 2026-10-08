import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import NovelWorkspace from "@/components/novel/NovelWorkspace";
import { streamChapterWrite } from "@/lib/ai";
import { hooksApi } from "@/lib/hooksApi";
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
//   modnav 三态（设定/写作/预览）＝回各自默认主页（c-write-home-rail-anchor）；
//   three-col 常驻挂载：切设定/预览不卸载，点「写作」清选中回书主页；
//   免费态零 phase-status 请求；点章强制落章纲页签；
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

const writeMock = vi.mocked(streamChapterWrite);

// 流式写入挂起不结束：让 aiState.streaming 稳定为 true（回主页守卫的测试前提）。
// 返回真 AbortController（ProsePane 卸载时会调 .abort()），但永不回调 → 流式不结束。
// 其余 AI 函数保持真实现（本文件其它用例不触流式）。
// vi.fn 包装（c-prose-stream-guard）：现场保护用例可按需改写回调注入，其余用例行为不变。
vi.mock("@/lib/ai", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/ai")>();
  return {
    ...actual,
    streamChapterWrite: vi.fn(() => new AbortController()),
  };
});

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
    // 档位种子（tier-plan-four-tiers 6.2）：PRO/MAX 会话须带 features，plan.open
    // 的抽卡判据已改 hasAiPlan（useFeature 快照单源）——entitlement null 会让
    // 兜底落静态注册表，PRO 用例的抽卡弹层不再出现。
    entitlement: isMember
      ? { v: 2, features: ["ai-plan", "chapter-review", "settings-ai-fields",
          "style-suggest", "outline-advanced-fields", "ai-model",
          "ai-generate", "prompt-panel", "ai-detect"],
          limits: { max_projects: null } }
      : null,
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

/** 空卷树：中栏呈现起手卡「这本书怎么开始？」（c-0vol0ch-empty-state）。 */
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
  // useClientVersion 已迁 React Query（c-query-cache-layer）：渲染需包 Provider
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/novel/p1"]}>
        <TierProvider tier={tier}>
          <ProjectProvider>
            <Routes>
              <Route path="/novel/:id" element={<NovelWorkspace />} />
            </Routes>
          </ProjectProvider>
        </TierProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** 选中第一章并等待章对象工作台挂载（树默认全展开，无需先点卷）。
 *  行头归一后顶栏 bar-here 也显示章名，findByText 会歧义多命中，改定点树行。 */
async function selectFirstChapter() {
  const row = await waitFor(() => {
    const el = document.querySelector(".tree .ch");
    expect(el).toBeTruthy();
    return el as HTMLElement;
  });
  fireEvent.click(row);
  await screen.findByRole("tab", { name: /^章纲/ });
}

function threeColClass(): string {
  return document.querySelector(".view.three-col")?.className ?? "";
}

/** 空书阶段落点＝「设定」（novelStage 单一事实源；e2e landing-view.spec 覆盖该口径）。
 *  本文件关注写作视图 → 显式点「写作」进入（幂等；点击即标记已主动导航，落点不再回切），
 *  避免与落点异步应用的竞态（曾出现「单跑绿、同文件跑红」的时序抖动）。 */
function goWriteView() {
  fireEvent.click(screen.getByRole("button", { name: /^写作/ }));
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
    // 中栏空书起手卡（volume-plan-ai 作家口径）：眉标＋标题＋说明句
    expect(await screen.findByText("这本书怎么开始？")).toBeVisible();
    expect(screen.getByText("设定 0/7 已确认")).toBeVisible();
    expect(
      screen.getByText(
        "自己动手：先建一卷、排上第一章就能开写；想让 AI 按主线拆分卷，用右侧的 AI 助手。",
      ),
    ).toBeVisible();
    expect(document.querySelector(".bar-here .bh-k")?.textContent).toBe("空书");
    expect(screen.getByText("还没有卷与章节")).toBeVisible();
    // 空书态两处起手入口（中栏 CTA + 左栏底部）＝新增一卷 ×2 / 新增一章 ×2
    expect(document.querySelectorAll(".e-empty .be-acts .btn").length).toBe(2);
    expect(document.querySelector(".col-tree.empty-book .tree-add")).toBeTruthy();
    // 右栏「未选中」态（volume-plan-ai 空书）：规划第一卷入口＋分卷依据；四格统计退役
    expect(document.querySelector(".col-ai .plan-badge")).toBeTruthy(); // AI 助手卡（全局 ra-* 布局）
    expect(screen.getByTestId("plan-first-volume")).toBeDefined();
    expect(screen.getByTestId("plan-basis")).toBeDefined();
    expect(screen.queryByTestId("idle-rail-stats")).toBeNull();
    expect(document.querySelector(".col-ai .rail-stats")).toBeNull();
    // 常驻挂载态不占章 AI 面板（右栏只有分卷规划卡一张 AI 助手卡）
    expect(document.querySelectorAll(".col-ai .rail-assist").length).toBe(1);
    // 应用栏（行头归一）：书名在顶栏；免费标识收敛到账户档位徽（未登录不渲染，e2e 断言）
    expect(screen.getAllByText("测试小说").length).toBeGreaterThan(0);
    expect(screen.queryByText(/免费模式 · 写作功能完整/)).toBeNull();
    expect(document.querySelector(".appbar-wb .bar-here")).toBeTruthy();
    // modnav 三态 + 写作 tab on + three-col on（jsdom 无 CSS → 断言 class）
    expect(screen.getByRole("button", { name: /^设定/ })).toBeDefined();
    expect(screen.getByRole("button", { name: /^写作/ })).toBeDefined();
    expect(screen.getByRole("button", { name: "预览" })).toBeDefined();
    goWriteView();
    await waitFor(() => expect(threeColClass()).toContain("on"));
    expect(screen.getByRole("button", { name: /^写作/ }).className).toContain("on");
    // 免费态零 phase-status 请求（ProContainer 整棵不渲染）
    expect(apiState.get).not.toHaveBeenCalledWith(
      "/novels/p1/workflow/phase-status",
    );
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("空书起手链（c-0vol0ch-empty-state）", () => {
  it("「＋ 新增一章」先垫第一卷再排第一章；「＋ 新增一卷」开规划台", async () => {
    // 有状态的建卷/建章 mock：POST 后 GET /volumes 跟着长出来（原型 firstVol 口径）
    let vols: unknown[] = [];
    apiState.get.mockImplementation((path: string) => {
      if (path === "/novels/p1/volumes") return Promise.resolve(vols);
      if (path === "/novels/p1/readiness")
        return Promise.resolve({ complete: false, missing: [], warning: "" });
      return Promise.resolve({});
    });
    apiState.fetchStory.mockResolvedValue({ synopsis: "" });
    apiState.post.mockImplementation((path: string) => {
      if (path === "/novels/p1/volumes") {
        vols = [{ ref: "vol-1", title: "第一卷", summary: "", chapter_count: 0, chapters: [] }];
        return Promise.resolve({ ref: "vol-1" });
      }
      if (path === "/novels/p1/volumes/vol-1/chapters") {
        vols = [
          {
            ref: "vol-1",
            title: "第一卷",
            summary: "",
            chapter_count: 1,
            chapters: [
              {
                ref: "vol-1-ch-1", volume: 1, chapter: 1, title: "第一章",
                status: "outline", word_count: 0, has_prose: false,
                outline_status: "unfilled", archived: false,
              },
            ],
          },
        ];
        return Promise.resolve({ chapter_ref: "vol-1-ch-1" });
      }
      return Promise.resolve({});
    });

    renderWorkspace("none");
    await screen.findByText("这本书怎么开始？");
    // 三处「＋ 新增一卷」（顶栏空书卡 / 中栏空态 / 左栏底部）都开同一个规划流（免费＝四问页）
    for (const id of ["empty-add-vol", "empty-cta-vol", "add-volume"]) {
      expect(document.querySelector(`[data-od-id="${id}"]`)).toBeTruthy();
    }
    fireEvent.click(document.querySelector('[data-od-id="add-volume"]') as HTMLElement);
    // c-volume-antagonist：添加卷弹窗退役——统一接规划流（免费档＝四问手写页）
    await waitFor(() => expect(screen.getByTestId("volume-plan-modal")).toBeDefined());
    expect(screen.getByTestId("desk-create")).toBeDefined();
    expect(screen.queryByRole("heading", { name: "添加卷" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /先不规划/ }));

    // 中栏「＋ 新增一章」＝空书垫卷链（原型 firstVol → 新增一章）
    fireEvent.click(document.querySelector('[data-od-id="empty-cta-ch"]') as HTMLElement);
    await waitFor(() =>
      expect(apiState.post).toHaveBeenCalledWith("/novels/p1/volumes", { title: "第一卷" }),
    );
    await waitFor(() =>
      expect(apiState.post).toHaveBeenCalledWith("/novels/p1/volumes/vol-1/chapters", {
        title: "第一章",
      }),
    );
    // 度量（PRD §7）：垫卷排第一章记 first_chapter_in_vol
    await waitFor(() =>
      expect(apiState.post).toHaveBeenCalledWith(
        "/events",
        { event_type: "first_chapter_in_vol", payload: { vol_no: 1 } },
        { quiet: true },
      ),
    );
  });

  it("PRO 档：加号「＋ 新增一卷」进四问手写页（不弹抽卡）；抽卡只从右栏 AI 入口进", async () => {
    // PRO 档会挂 ProPhaseSurface（读 phase-status）→ 补该桩，避免上游抛错
    mockEmptyTree();
    const baseGet = apiState.get.getMockImplementation()!;
    apiState.get.mockImplementation((path: string) => {
      if (path === "/novels/p1/workflow/phase-status")
        return Promise.resolve({
          phases: { settings: "pending", outline: "pending", prompt: "pending", write: "pending", archive: "pending" },
          warnings: [],
        });
      return baseGet(path);
    });
    renderWorkspace("monthly");
    await screen.findByText("这本书怎么开始？");
    // 加号＝手动入口：恒进四问手写页
    fireEvent.click(document.querySelector('[data-od-id="empty-cta-vol"]') as HTMLElement);
    await waitFor(() => expect(screen.getByTestId("volume-plan-modal")).toBeDefined());
    expect(screen.queryByTestId("pick-modal")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /先不规划/ }));
    // 右栏 AI 入口：PRO 档＝三选一抽卡
    fireEvent.click(screen.getByTestId("plan-first-volume"));
    await waitFor(() => expect(screen.getByTestId("pick-modal")).toBeDefined());
  });

  it("入口埋点：三处「＋ 新增一卷」记 plan_entry_open{tier}", async () => {
    mockEmptyTree();
    renderWorkspace("none");
    await screen.findByText("这本书怎么开始？");
    fireEvent.click(document.querySelector('[data-od-id="empty-cta-vol"]') as HTMLElement);
    await waitFor(() =>
      expect(apiState.post).toHaveBeenCalledWith(
        "/events",
        { event_type: "plan_entry_open", payload: { tier: "free" } },
        { quiet: true },
      ),
    );
  });
});

describe("免费态：选中章 → 章对象工作台", () => {
  it("点章强制落章纲页签；正文页有编辑器、无 AI 入口；右栏 locked", async () => {
    mockOneChapterTree();
    renderWorkspace("none");
    await selectFirstChapter();
    // 页签（章纲默认选中；提示词子 label PRO-only：免费隐藏 ai-prompt-crafting）
    // c-chapter-dossier IA 对齐（09-28）：无独立变化页签 → 免费 7 个
    // （章纲/正文/设定/文风/角色关系/伏笔/操作）
    const tabs = screen.getAllByRole("tab");
    expect(tabs.length).toBe(7);
    expect(screen.queryByRole("tab", { name: /^章档/ })).toBeNull();
    const ogTab = screen.getByRole("tab", { name: /^章纲/ });
    expect(ogTab.getAttribute("aria-selected")).toBe("true");
    expect(screen.queryByRole("tab", { name: /^提示词/ })).toBeNull();
    expect(screen.getByRole("tab", { name: /^正文/ })).toBeDefined();
    // 工具栏章名（树行 + 工具栏两处「第一章」→ chMeta 对齐成功的证据）
    expect(screen.getAllByText("第一章").length).toBeGreaterThanOrEqual(2);
    // bar-here（顶栏主线定位）：默认名「第一章」不重复序号（nodeLabel 同口径）
    expect(document.querySelector(".bar-here .bh-t")?.textContent).toBe("第 1 章");
    // 章纲面板必填字段在渲染（c-og-slim-v2 两项口径）
    expect(screen.queryAllByText(/必须完成的变化/).length).toBeGreaterThan(0);
    // 点「正文」→ contenteditable 编辑器挂载；免费无 AI 按钮
    fireEvent.click(screen.getByRole("tab", { name: /^正文/ }));
    await waitFor(() => expect(document.querySelector(".editor")).toBeTruthy());
    expect(screen.queryByRole("button", { name: "AI 生成正文" })).toBeNull();
    // 右栏免费 locked 卡 + 规划中（章模式三卡）
    expect(document.querySelector(".col-ai .rail-assist.locked")).toBeTruthy(); // 免费态整卡锁定
    // 卡头角标＝当前档位（不再写死 PRO）；套餐文案已不进卡头
    expect(screen.getAllByTestId("plan-badge")[0].textContent).toBe("免费版");
    expect(screen.queryByText(/你的 PRO 已包含|未解锁 · 开通后本书 AI 即可用/)).toBeNull();
  });
});

describe("bar-here 续写（上次写作会话）", () => {
  it("last_write 章优先为主线端点＋续写按钮在", async () => {
    mockOneChapterTree();
    localStorage.setItem(
      "pref.book.p1.last_write",
      JSON.stringify({ ref: "vol-1-ch-1", scroll: 0.5, ts: 123 }),
    );
    renderWorkspace("none");
    await selectFirstChapter();
    expect(document.querySelector(".bar-here .bh-t")?.textContent).toBe("第 1 章");
    expect(screen.getByRole("button", { name: "续写" })).toBeDefined();
  });
});

describe("设定视图懒挂载 / 离开卸载", () => {
  it("经 modnav「设定」进入设定视图，点「写作」返回后卸载", async () => {
    mockEmptyTree();
    renderWorkspace("none");
    await screen.findByText("这本书怎么开始？");
    goWriteView();
    await waitFor(() => expect(threeColClass()).toContain("on"));

    fireEvent.click(screen.getByRole("button", { name: /^设定/ }));
    await waitFor(() =>
      expect(screen.getAllByText("伏笔").length).toBeGreaterThan(0),
    );
    // 写作视图常驻挂载：仅摘掉 on class（jsdom 断言 class 而非可见性）
    expect(threeColClass()).not.toContain("on");

    fireEvent.click(screen.getByRole("button", { name: /^写作/ }));
    await waitFor(() =>
      expect(screen.queryAllByText("伏笔").length).toBe(0),
    );
    expect(threeColClass()).toContain("on");
  });
});

describe("写作视图常驻挂载：切到设定编辑器不卸载（点「写作」才清选中回主页）", () => {
  it("选中章输入后切到设定，正文编辑器仍挂载（不卸载）", async () => {
    mockOneChapterTree();
    renderWorkspace("none");
    await selectFirstChapter();
    fireEvent.click(screen.getByRole("tab", { name: /^正文/ }));
    const editor = await waitFor(() => {
      const el = document.querySelector(".editor");
      expect(el).toBeTruthy();
      return el as HTMLElement;
    });
    // 正文查看/编辑两态（c-prose-edit-gate）：输入前先点「编辑正文」
    fireEvent.click(screen.getByTestId("prose-edit"));
    await waitFor(() => expect(editor).toHaveAttribute("contenteditable", "true"));
    editor.innerHTML = "<p>我在专注写作</p>";
    fireEvent.input(editor);

    // 切到设定：three-col 只摘 on class，编辑器仍在 DOM（jsdom 无 CSS → 断言 class 与节点）
    fireEvent.click(screen.getByRole("button", { name: /^设定/ }));
    await waitFor(() =>
      expect(screen.getAllByText("伏笔").length).toBeGreaterThan(0),
    );
    expect(threeColClass()).not.toContain("on");
    expect(document.querySelector(".editor")?.textContent).toBe("我在专注写作");
  });
});

describe("页签回默认主页（c-write-home-rail-anchor）", () => {
  it("有章时点「写作」→ 书主页卡（清选中）；点「续写」回到该章", async () => {
    mockOneChapterTree();
    renderWorkspace("none");
    await selectFirstChapter();
    expect(document.querySelector(".editor") ?? document.querySelector(".col-panel")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /^写作/ }));
    const home = await screen.findByTestId("write-home");
    // 进度眉标 + 建书双入口 + 续写（与顶栏同判据）
    expect(screen.getByTestId("home-progress").textContent).toContain("1 卷 · 1 章");
    expect(screen.getByTestId("home-add-volume")).toBeTruthy();
    expect(screen.getByTestId("home-add-chapter")).toBeTruthy();
    expect(home.textContent).toContain("在左侧目录里选一章");
    // 清选中 → 章工作台卸载（tab 条消失）
    await waitFor(() => expect(screen.queryByRole("tab", { name: /^章纲/ })).toBeNull());

    fireEvent.click(screen.getByTestId("home-resume"));
    await waitFor(() => expect(screen.getByRole("tab", { name: /^章纲/ })).toBeTruthy());
  });

  it("重复点「写作」也回书主页（不是无操作）", async () => {
    mockOneChapterTree();
    renderWorkspace("none");
    await selectFirstChapter();
    fireEvent.click(screen.getByRole("button", { name: /^写作/ }));
    await screen.findByTestId("write-home");
    await selectFirstChapter();
    fireEvent.click(screen.getByRole("button", { name: /^写作/ }));
    await screen.findByTestId("write-home");
    expect(screen.queryByRole("tab", { name: /^章纲/ })).toBeNull();
  });

  it("重复点「设定」把面板拨回默认项（简介）", async () => {
    mockEmptyTree();
    renderWorkspace("none");
    fireEvent.click(screen.getByRole("button", { name: /^设定/ }));
    await waitFor(() =>
      expect(document.querySelector(".s-item.on .nm")?.textContent).toBe("简介"),
    );
    // 切到「世界」面板
    fireEvent.click(screen.getByText("世界"));
    await waitFor(() =>
      expect(document.querySelector(".s-item.on .nm")?.textContent).toBe("世界"),
    );
    // 重复点「设定」→ 拨回默认面板
    fireEvent.click(screen.getByRole("button", { name: /^设定/ }));
    await waitFor(() =>
      expect(document.querySelector(".s-item.on .nm")?.textContent).toBe("简介"),
    );
  });

  it("设定脏表单时重复点「设定」先确认：取消留原面板，确认拨回默认", async () => {
    mockEmptyTree();
    renderWorkspace("none");
    fireEvent.click(screen.getByRole("button", { name: /^设定/ }));
    await waitFor(() =>
      expect(document.querySelector(".s-item.on .nm")?.textContent).toBe("简介"),
    );
    fireEvent.click(screen.getByText("世界"));
    await waitFor(() =>
      expect(document.querySelector(".s-item.on .nm")?.textContent).toBe("世界"),
    );
    // 弄脏世界面板（舞台输入）
    const stage = await waitFor(() => {
      const el = document.querySelector('[data-od-id="stage-input"]');
      expect(el).toBeTruthy();
      return el as HTMLTextAreaElement;
    });
    fireEvent.change(stage, { target: { value: "边境城邦" } });

    // 取消分支：confirm 返回 false → 留在世界面板、输入保留
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    fireEvent.click(screen.getByRole("button", { name: /^设定/ }));
    expect(confirmSpy).toHaveBeenCalledWith(expect.stringContaining("回到默认面板将丢失"));
    expect(document.querySelector(".s-item.on .nm")?.textContent).toBe("世界");
    expect((document.querySelector('[data-od-id="stage-input"]') as HTMLTextAreaElement).value).toBe(
      "边境城邦",
    );

    // 确认分支：拨回默认面板
    confirmSpy.mockReturnValue(true);
    fireEvent.click(screen.getByRole("button", { name: /^设定/ }));
    await waitFor(() =>
      expect(document.querySelector(".s-item.on .nm")?.textContent).toBe("简介"),
    );
    confirmSpy.mockRestore();
  });

  it("AI 流式中点「写作」先确认：取消留在原章不回主页", async () => {
    mockOneChapterTreePro();
    renderWorkspace("monthly");
    await selectFirstChapter();
    // 生成正文入口在正文页签面板（c-prose-write-entry：右栏常驻工具卡退役）
    fireEvent.click(screen.getByRole("tab", { name: /^正文/ }));
    // 右栏「生成正文」→ AiModal 确认 → 流式开始（@/lib/ai 的 streamChapterWrite 已桩为挂起）
    fireEvent.click(screen.getByTestId("ai-write-btn"));
    fireEvent.click(await screen.findByTestId("ai-confirm"));

    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    fireEvent.click(screen.getByRole("button", { name: /^写作/ }));
    expect(confirmSpy).toHaveBeenCalledWith(expect.stringContaining("会中断这次生成"));
    // 取消 → 留在原章（章对象工作台仍在，未回书主页）
    expect(screen.queryByTestId("write-home")).toBeNull();
    expect(screen.getByRole("tab", { name: /^章纲/ })).toBeTruthy();
    confirmSpy.mockRestore();
  });
});

describe("PRO 态：徽标 + phase-status + AI 入口", () => {
  it("PRO 渲染 pill 徽并请求 phase-status；正文页可见 AI 生成正文", async () => {
    mockOneChapterTreePro();
    renderWorkspace("monthly");
    // PRO 徽随行头归一迁入账户胶囊（未登录不渲染）；顶栏本体在即可
    expect(document.querySelector(".appbar-wb")).toBeTruthy();
    expect(screen.queryByText(/免费模式/)).toBeNull();
    expect(screen.queryByRole("button", { name: "升级 PRO" })).toBeNull();
    await waitFor(() =>
      expect(apiState.get).toHaveBeenCalledWith(
        "/novels/p1/workflow/phase-status",
      ),
    );

    await selectFirstChapter();
    fireEvent.click(screen.getByRole("tab", { name: /^正文/ }));
    // AI 入口唯一化右栏（2026-09-20）：章 body 无「AI 生成正文」按钮，
    // 右栏 AI 助手卡有「生成正文」（data-testid=ai-write-btn）＋真实工具卡
    expect(screen.queryByRole("button", { name: "AI 生成正文" })).toBeNull();
    const rail = document.querySelector(".col-ai") as HTMLElement;
    expect(within(rail).getByTestId("ai-write-btn")).toBeDefined();
    // 顶栏 bar-here 也有「续写」CTA（行头归一），右栏工具卡断言限定右栏范围
    expect(within(rail).getByTestId("ai-write-btn")).toBeDefined();
    // c-retire-selection-transforms：去AI味单卡（扩写/压缩退役缺席钉）
    // c-retire-selection-transforms：去AI味单卡（未选中置灰），扩写/压缩退役
    const polishCard = within(rail).getByTestId("ai-polish") as HTMLButtonElement;
    expect(polishCard).toBeDefined();
    expect(within(rail).queryByText(/^场景扩写$/)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// chapter-rewrite：操作页签「重写这一章」卡门槛（无正文不渲染）
// ---------------------------------------------------------------------------

const ONE_CHAPTER_WITH_PROSE = { ...ONE_CHAPTER_DATA, prose: "第一章的正文内容。" };

describe("重写入口门槛（chapter-rewrite）", () => {
  it("无正文章：操作页签不渲染「重写这一章」卡", async () => {
    mockOneChapterTree(); // ONE_CHAPTER_DATA.prose = ""
    renderWorkspace("none");
    await selectFirstChapter();
    // 点章后回落章纲的竞态：重试式切「操作」直到面板挂载
    await waitFor(() => {
      fireEvent.click(screen.getByRole("tab", { name: /^操作/ }));
      expect(document.querySelector('[data-od-id="actions-pane"]')).toBeTruthy();
    });
    expect(screen.queryByTestId("rewrite-btn")).toBeNull();
    // 回退卡仍在（其余操作不受影响；该按钮注册在 data-od-id）
    expect(document.querySelector('[data-od-id="revert-btn"]')).toBeTruthy();
  });

  it("有正文章：渲染「重写这一章」卡（点击出确认弹窗）", async () => {
    apiState.get.mockImplementation((path: string) => {
      if (path === "/novels/p1/volumes") return Promise.resolve(ONE_VOL_ONE_CHAPTER);
      if (path === "/novels/p1/chapters/vol-1-ch-1")
        return Promise.resolve(ONE_CHAPTER_WITH_PROSE);
      if (path === "/novels/p1/readiness")
        return Promise.resolve({ complete: false, missing: [], warning: "" });
      return Promise.resolve({});
    });
    apiState.request.mockResolvedValue([]);
    apiState.fetchStory.mockResolvedValue({ synopsis: "" });
    apiState.put.mockResolvedValue({});
    apiState.post.mockResolvedValue({});
    renderWorkspace("none");
    await selectFirstChapter();
    await waitFor(() => {
      fireEvent.click(screen.getByRole("tab", { name: /^操作/ }));
      expect(document.querySelector('[data-od-id="actions-pane"]')).toBeTruthy();
    });
    const btn = screen.getByTestId("rewrite-btn");
    fireEvent.click(btn);
    // 影响面确认弹窗三行（限定在弹窗列表内，避开卡片同款文案）
    const rwList = document.querySelector('[role="dialog"] .rw-list');
    expect(rwList?.textContent).toContain("转入旧稿支线");
    expect(rwList?.textContent).toContain("基于旧设定");
    expect(screen.getByTestId("rewrite-confirm")).toBeTruthy();
  });
});

describe("写作徽标归档投影（c-og-badge-archived-confirm）", () => {
  it("全归档树 → modnav 徽标 1/1 章纲（归档章计入确认计数）", async () => {
    apiState.get.mockImplementation((path: string) => {
      if (path === "/novels/p1/volumes") {
        return Promise.resolve([
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
                status: "archived",
                word_count: 1200,
                has_prose: true,
                outline_status: "in_progress",
                archived: true,
              },
            ],
          },
        ]);
      }
      if (path === "/novels/p1/tree") {
        return Promise.resolve({
          volumes: [
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
                  status: "archived",
                  word_count: 1200,
                  has_prose: true,
                  archived: true,
                },
              ],
            },
          ],
        });
      }
      if (path === "/novels/p1/readiness")
        return Promise.resolve({ complete: false, missing: [], warning: "" });
      return Promise.resolve({});
    });
    apiState.fetchStory.mockResolvedValue({ synopsis: "" });
    renderWorkspace("none");
    await waitFor(() => {
      const cnts = Array.from(document.querySelectorAll(".modnav .cnt"));
      const outlineCnt = cnts.find((el) => el.textContent?.includes("章纲"));
      expect(outlineCnt?.textContent).toBe("1/1 章纲");
    });
  });
});

// ---------------------------------------------------------------------------
// 正文生成中的现场保护（c-prose-stream-guard）：
//   徽章提升页签行（非正文页签可见）、生成中左栏树锁定（点「停止」恢复）、
//   切章/回主页收尾保留半截落库、流式态复位（不残留确认/锁定）。
// ---------------------------------------------------------------------------
describe("正文生成中的现场保护（c-prose-stream-guard）", () => {
  const TWO_CHAPTER_DATA_CH2 = {
    volume: 1,
    chapter: 2,
    title: "第二章",
    status: "outline",
    outline: { summary: "" },
    prose: "",
  };

  function mockTwoChapterTreePro() {
    apiState.get.mockImplementation((path: string) => {
      if (path === "/novels/p1/volumes")
        return Promise.resolve([
          {
            ...ONE_VOL_ONE_CHAPTER[0],
            chapter_count: 2,
            chapters: [
              ...ONE_VOL_ONE_CHAPTER[0].chapters,
              {
                ref: "vol-1-ch-2",
                volume: 1,
                chapter: 2,
                title: "第二章",
                status: "outline",
                word_count: 0,
                has_prose: false,
                outline_status: "unfilled",
                archived: false,
              },
            ],
          },
        ]);
      if (path === "/novels/p1/chapters/vol-1-ch-1")
        return Promise.resolve(ONE_CHAPTER_DATA);
      if (path === "/novels/p1/chapters/vol-1-ch-2")
        return Promise.resolve(TWO_CHAPTER_DATA_CH2);
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

  /** 选第一章 → 正文页签 → 右栏「生成正文」→ AiModal 确认 → 流式启动（writeMock 挂起） */
  async function startStreaming() {
    mockTwoChapterTreePro();
    renderWorkspace("monthly");
    await selectFirstChapter();
    fireEvent.click(screen.getByRole("tab", { name: /^正文/ }));
    fireEvent.click(screen.getByTestId("ai-write-btn"));
    fireEvent.click(await screen.findByTestId("ai-confirm"));
    await waitFor(() => expect(writeMock).toHaveBeenCalled());
  }

  beforeEach(() => {
    writeMock.mockImplementation(() => new AbortController());
  });
  afterEach(() => {
    writeMock.mockImplementation(() => new AbortController());
  });

  it("生成中徽章挂在页签行：章纲页签下仍可见，且全文档仅一处", async () => {
    await startStreaming();
    expect(screen.getByTestId("ai-streaming-badge")).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: /^章纲/ }));
    expect(screen.getByTestId("ai-streaming-badge")).toBeTruthy();
    expect(document.querySelectorAll(".ai-streaming").length).toBe(1);
  });

  it("生成中左栏树锁定：点另一章被拦（不加载该章＋置灰指路），点「停止」后恢复可切", async () => {
    await startStreaming();
    const rows = () => document.querySelectorAll(".tree .ch");
    const aside = () => document.querySelector(".col-tree");
    expect(rows().length).toBe(2);
    // 锁定态：ai-lock 类＋title 指路（jsdom 无 Toaster 挂载，toast 文案归 e2e 断言）
    expect(aside()?.classList.contains("ai-lock")).toBe(true);
    expect(aside()?.getAttribute("title") ?? "").toContain("生成中");
    fireEvent.click(rows()[1]);
    expect(apiState.get).not.toHaveBeenCalledWith("/novels/p1/chapters/vol-1-ch-2");
    expect(screen.getByTestId("ai-streaming-badge")).toBeTruthy();

    // 「停止」→ 收尾复位：徽章消失、树解锁恢复可切
    fireEvent.click(
      within(screen.getByTestId("ai-streaming-badge")).getByRole("button", { name: "停止" }),
    );
    await waitFor(() => expect(screen.queryByTestId("ai-streaming-badge")).toBeNull());
    await waitFor(() => expect(aside()?.classList.contains("ai-lock")).toBe(false));
    fireEvent.click(rows()[1]);
    await waitFor(() =>
      expect(apiState.get).toHaveBeenCalledWith("/novels/p1/chapters/vol-1-ch-2"),
    );
  });

  it("流式中断保留半截：回主页确认中断 → 半截内容照「停止」语义落旧章", async () => {
    mockTwoChapterTreePro();
    renderWorkspace("monthly");
    await selectFirstChapter();
    fireEvent.click(screen.getByRole("tab", { name: /^正文/ }));
    let captured: { onChunk: (t: string) => void } | null = null;
    writeMock.mockImplementation(((_pid: string, _ref: string, cbs: { onChunk: (t: string) => void }) => {
      captured = cbs;
      return new AbortController();
    }) as unknown as typeof streamChapterWrite);
    fireEvent.click(screen.getByTestId("ai-write-btn"));
    fireEvent.click(await screen.findByTestId("ai-confirm"));
    await waitFor(() => expect(captured).toBeTruthy());
    captured!.onChunk("雨落在铁皮屋顶上，像一场迟到的道歉。");

    // 回主页确认中断 → ChapterWorkspace 卸载 → cleanup 照「停止」收尾
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    fireEvent.click(screen.getByRole("button", { name: /^写作/ }));
    await waitFor(() =>
      expect(apiState.put).toHaveBeenCalledWith("/novels/p1/chapters/vol-1-ch-1/prose", {
        prose: expect.stringContaining("雨落在铁皮屋顶上"),
      }),
    );
    confirmSpy.mockRestore();
  });

  it("切章收尾复位流式态：中断回主页后重进本章，再点「写作」不再弹确认", async () => {
    await startStreaming();
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    fireEvent.click(screen.getByRole("button", { name: /^写作/ }));
    await waitFor(() => expect(screen.queryByRole("tab", { name: /^章纲/ })).toBeNull());
    // 重进第一章
    fireEvent.click(document.querySelectorAll(".tree .ch")[0]);
    await screen.findByRole("tab", { name: /^章纲/ });
    // 流式态已复位：再次回主页不走流式确认
    fireEvent.click(screen.getByRole("button", { name: /^写作/ }));
    expect(confirmSpy).toHaveBeenCalledTimes(1);
    confirmSpy.mockRestore();
  });
});

// ---------------------------------------------------------------------------
// 页签「待确认」泡泡（c-chtab-confirm-bubbles）：
//   设定/角色关系＝本章变化按域 pending（accent 计数泡泡，与页签内「全部采纳（N）」
//   同口径）；伏笔＝「该收 N」（warn，ogHookHints.mres 台账共享判定）。
//   提取收口即取（无轮询）；DOSSIER_CHANGED_EVENT 即时递减；未归档章无泡；
//   hooksApi 变更广播 HOOKS_CHANGED_EVENT → 台账重取 → 泡泡刷新。
// ---------------------------------------------------------------------------
describe("页签待确认泡泡（c-chtab-confirm-bubbles）", () => {
  const DOSSIER_ROWS_FULL = [
    { id: "r1", domain: "settings", status: "pending" },
    { id: "r2", domain: "items", status: "pending" },
    { id: "r3", domain: "knowledge", status: "pending" },
    { id: "r4", domain: "settings", status: "pending" },
    { id: "r5", domain: "settings", status: "accepted" },
    { id: "r6", domain: "relations", status: "pending" },
    { id: "r7", domain: "relations", status: "pending" },
    { id: "r8", domain: "relations", status: "pending" },
  ];

  /** 台账种子（可变引用：收束用例在 patch 前就地改 status，重取才拿得到新态）。 */
  const hookItems = [
    { id: "h1", code: "#H-0001", description: "半块玉佩", status: "active",
      planned_chapter_id: "vol-1-ch-1", introduced_chapter_id: null,
      mentioned_chapter_id: null, resolved_chapter_id: null },
    { id: "h2", code: "#H-0002", description: "六指之谜", status: "active",
      planned_chapter_id: null, introduced_chapter_id: null,
      mentioned_chapter_id: null, resolved_chapter_id: null },
  ];

  /** 已归档一章树（archived: true → 工作台拉 dossier 元数据）。 */
  function mockArchivedChapterTree(dossierRows: unknown[] = DOSSIER_ROWS_FULL) {
    const archivedCh = {
      ref: "vol-1-ch-1",
      volume: 1,
      chapter: 1,
      title: "第一章",
      status: "archived",
      word_count: 1200,
      has_prose: true,
      outline_status: "in_progress",
      archived: true,
    };
    apiState.get.mockImplementation((path: string) => {
      if (path === "/novels/p1/volumes")
        return Promise.resolve([
          { ref: "vol-1", title: "第一卷", summary: "", chapter_count: 1, chapters: [archivedCh] },
        ]);
      if (path === "/novels/p1/chapters/vol-1-ch-1")
        return Promise.resolve(ONE_CHAPTER_DATA);
      if (path === "/novels/p1/chapters/vol-1-ch-1/dossier")
        return Promise.resolve({
          rows: dossierRows,
          progress: {
            pending: dossierRows.filter((r) => (r as { status: string }).status === "pending").length,
            accepted: 1,
            rejected: 0,
          },
          extraction: null,
          not_extracted: false,
          stale: false,
          archived: true,
          accepted_count: 1,
        });
      if (path === "/novels/p1/hooks")
        return Promise.resolve({ data: { items: hookItems } });
      if (path === "/novels/p1/readiness")
        return Promise.resolve({ complete: false, missing: [], warning: "" });
      return Promise.resolve({});
    });
    apiState.request.mockResolvedValue([]);
    apiState.fetchStory.mockResolvedValue({ synopsis: "" });
    apiState.put.mockResolvedValue({});
    apiState.post.mockResolvedValue({});
    apiState.patch.mockResolvedValue({ data: { id: "h1" } });
  }

  it("已归档章：设定 4／关系 3 accent 泡泡＋伏笔「该收 1」warn 泡泡", async () => {
    mockArchivedChapterTree();
    renderWorkspace("none");
    await selectFirstChapter();
    // 设定泡＝settings+items+knowledge 三域 pending（r1/r2/r3/r4；r5 已采纳不计）
    await waitFor(() => expect(screen.getByTestId("chtab-bubble-settings")).toBeTruthy());
    expect(screen.getByTestId("chtab-bubble-settings").textContent).toBe("4");
    expect(screen.getByTestId("chtab-bubble-settings").className).toContain("pill-accent");
    // 关系泡＝relations 域 pending
    expect(screen.getByTestId("chtab-bubble-relations").textContent).toBe("3");
    expect(screen.getByTestId("chtab-bubble-relations").className).toContain("pill-accent");
    // 伏笔泡＝台账该收了（h1 计划章 ≤ 本章；h2 未设计划章不计），warn 款「该收 N」
    expect(screen.getByTestId("chtab-bubble-hooks").textContent).toBe("该收 1");
    expect(screen.getByTestId("chtab-bubble-hooks").className).toContain("pill-warn");
  });

  it("逐条确认广播 DOSSIER_CHANGED_EVENT → 泡泡即时递减到消失", async () => {
    mockArchivedChapterTree();
    renderWorkspace("none");
    await selectFirstChapter();
    await waitFor(() => expect(screen.getByTestId("chtab-bubble-settings")).toBeTruthy());
    // 确认全部本章变化行 → 重取后 pending 归零 → 泡泡退场（关系/伏笔不动）
    mockArchivedChapterTree([
      { id: "r1", domain: "settings", status: "accepted" },
      { id: "r6", domain: "relations", status: "pending" },
    ]);
    window.dispatchEvent(
      new CustomEvent("dossier-relations-changed", {
        detail: { projectId: "p1", chapterRef: "vol-1-ch-1" },
      }),
    );
    await waitFor(() =>
      expect(screen.queryByTestId("chtab-bubble-settings")).toBeNull(),
    );
    expect(screen.getByTestId("chtab-bubble-relations").textContent).toBe("1");
  });

  it("未归档章无泡泡", async () => {
    mockOneChapterTree();
    renderWorkspace("none");
    await selectFirstChapter();
    await screen.findByRole("tab", { name: /^章纲/ });
    expect(screen.queryByTestId("chtab-bubble-settings")).toBeNull();
    expect(screen.queryByTestId("chtab-bubble-relations")).toBeNull();
    expect(screen.queryByTestId("chtab-bubble-hooks")).toBeNull();
  });

  it("hooksApi 变更广播 HOOKS_CHANGED_EVENT → 台账重取 →「该收」泡泡消失", async () => {
    mockArchivedChapterTree();
    renderWorkspace("none");
    await selectFirstChapter();
    await waitFor(() => expect(screen.getByTestId("chtab-bubble-hooks")).toBeTruthy());
    // 就地收束 h1 → 经 hooksApi patch（真实模块；api.patch 落 mock）→ 广播 → 重取得新态
    hookItems[0].status = "resolved";
    await hooksApi.patch("p1", "h1", { status: "resolved" });
    await waitFor(() => expect(screen.queryByTestId("chtab-bubble-hooks")).toBeNull());
    // 台账确实重取过（/hooks 第二次命中）
    const hookCalls = apiState.get.mock.calls.filter(([p]) => p === "/novels/p1/hooks");
    expect(hookCalls.length).toBeGreaterThanOrEqual(2);
  });

  it("取消归档：设定/关系泡泡随章退出归档态退场，伏笔该收泡不受影响", async () => {
    // 评审 P2 修复回归：归档（泡在）→ 恢复编辑（unarchive）→ 树翻 draft。
    // 后端 unarchive 不清章档行，泡泡若只跟着数据走就会挂在可编辑章上。
    hookItems[0].status = "active"; // 前一用例把 h1 收束了，复位
    let chArchived = true;
    const archivedCh = () => ({
      ref: "vol-1-ch-1",
      volume: 1,
      chapter: 1,
      title: "第一章",
      status: chArchived ? "archived" : "outline",
      word_count: 1200,
      has_prose: true,
      outline_status: "in_progress",
      archived: chArchived,
    });
    apiState.get.mockImplementation((path: string) => {
      if (path === "/novels/p1/volumes")
        return Promise.resolve([
          { ref: "vol-1", title: "第一卷", summary: "", chapter_count: 1, chapters: [archivedCh()] },
        ]);
      if (path === "/novels/p1/chapters/vol-1-ch-1")
        return Promise.resolve(ONE_CHAPTER_DATA);
      if (path === "/novels/p1/chapters/vol-1-ch-1/dossier")
        return Promise.resolve({
          rows: DOSSIER_ROWS_FULL,
          progress: { pending: 7, accepted: 1, rejected: 0 },
          extraction: null,
          not_extracted: false,
          stale: false,
          archived: true,
          accepted_count: 1,
        });
      if (path === "/novels/p1/hooks") return Promise.resolve({ data: { items: hookItems } });
      if (path === "/novels/p1/readiness")
        return Promise.resolve({ complete: false, missing: [], warning: "" });
      return Promise.resolve({});
    });
    apiState.request.mockResolvedValue([]);
    apiState.fetchStory.mockResolvedValue({ synopsis: "" });
    apiState.put.mockResolvedValue({});
    apiState.post.mockResolvedValue({ ok: true });
    apiState.patch.mockResolvedValue({ data: { id: "h1" } });

    renderWorkspace("none");
    await selectFirstChapter();
    await waitFor(() => expect(screen.getByTestId("chtab-bubble-settings")).toBeTruthy());

    // 走横幅「恢复编辑」实链：confirm → POST unarchive → chapter:archived → 树翻 draft
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    chArchived = false; // 服务端已回退；树重取（chapter:archived 触发）拿到新态
    fireEvent.click(screen.getByRole("button", { name: "恢复编辑" }));
    await waitFor(() =>
      expect(screen.queryByTestId("chtab-bubble-settings")).toBeNull(),
    );
    expect(screen.queryByTestId("chtab-bubble-relations")).toBeNull();
    // 伏笔「该收」＝台账章视角投影，与归档态无关——保留
    expect(screen.getByTestId("chtab-bubble-hooks")).toBeTruthy();
    confirmSpy.mockRestore();
  });
});
