import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
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

// 流式写入挂起不结束：让 aiState.streaming 稳定为 true（回主页守卫的测试前提）。
// 返回真 AbortController（ProsePane 卸载时会调 .abort()），但永不回调 → 流式不结束。
// 其余 AI 函数保持真实现（本文件其它用例不触流式）。
vi.mock("@/lib/ai", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/ai")>();
  return {
    ...actual,
    streamChapterWrite: () => new AbortController(),
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
    // workbench-storyline-hooks：伏笔页签全档位 → 免费 7 个
    // （章纲/正文/设定/文风/角色关系/伏笔/操作）
    const tabs = screen.getAllByRole("tab");
    expect(tabs.length).toBe(7);
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
    expect(screen.getByText(/未解锁 · 升级 PRO 后本书 AI 即可用/)).toBeVisible();
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
    expect(within(rail).getByRole("button", { name: /续写建议/ })).toBeDefined();
    expect(within(rail).getByRole("button", { name: /去AI味/ })).toBeDefined();
    expect(within(rail).getByRole("button", { name: /场景扩写/ })).toBeDefined();
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
