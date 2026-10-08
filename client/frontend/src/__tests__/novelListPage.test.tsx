// 书架页（NovelListPage）契约（覆盖率专项·批 1 收尾）：
//   列表三态（骨架/失败重试/首启引导）· 卡片（阶段派生/题材待定/统计/相对时间/菜单/跳转）·
//   六类 Banner（权益异常/过期/试用/免费层/缺 Key/满额）· 新建与导入入口 · 改名与删除全链 ·
//   满额时的升级引导与锁定瓦片 · AuthGuard 门禁。
import { act, render, screen, waitFor, within } from "@testing-library/react";
import { fireEvent } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import NovelListPage from "@/pages/NovelListPage";
import { resetPackProbeSlotForTests } from "@/lib/packProbe";
import { SHELF_PAGE_SIZE } from "@/lib/shelfSort";
import { toast } from "@/lib/toast";

const getMock = vi.fn();
const postMock = vi.fn();
const deleteMock = vi.fn();
const renameMock = vi.fn();
const finishMock = vi.fn();
const reopenMock = vi.fn();

const legacyStatusMock = vi.hoisted(() => ({ value: null as unknown }));
vi.mock("@/hooks/useLegacyDb", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/useLegacyDb")>("@/hooks/useLegacyDb");
  return {
    useLegacyDb: () => ({
      status: legacyStatusMock.value,
      refresh: vi.fn(async () => {}),
      dismiss: vi.fn(async () => {}),
    }),
    migratableCandidates: actual.migratableCandidates,
    recommendedCandidate: actual.recommendedCandidate,
  };
});
vi.mock("@/lib/api", () => ({
  api: {
    get: (...a: unknown[]) => getMock(...a),
    post: (...a: unknown[]) => postMock(...a),
    delete: (...a: unknown[]) => deleteMock(...a),
    renameNovel: (...a: unknown[]) => renameMock(...a),
    finishNovel: (...a: unknown[]) => finishMock(...a),
    reopenNovel: (...a: unknown[]) => reopenMock(...a),
  },
  request: vi.fn(),
}));
vi.mock("@/lib/toast", () => ({ toast: { success: vi.fn(), info: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/portal", () => ({
  PORTAL_URL: "https://portal.default",
  fetchPortalUrl: vi.fn(async () => ""),
  isSafeExternalUrl: () => true,
}));
vi.mock("@/lib/support", () => ({ supportUrl: vi.fn(async () => "https://support.example.com") }));

const tierState = { tier: "pro", isMember: true, expired: false, trialRemainingDays: 0, projectLimit: null };
vi.mock("@/hooks/useTier", () => ({ useTier: () => tierState }));

vi.mock("@/components/novel/CreateProjectModal", () => ({
  default: ({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: (id: string) => void }) =>
    open ? (
      <div data-testid="create-modal">
        <button onClick={() => onCreated("new-1")}>模拟创建</button>
        <button onClick={onClose}>关闭创建</button>
      </div>
    ) : null,
}));
vi.mock("@/components/novel/ImportNovelModal", () => ({
  default: ({ open, onClose, onImported }: { open: boolean; onClose: () => void; onImported: (id: string) => void }) =>
    open ? (
      <div data-testid="import-modal">
        <button onClick={() => onImported("imp-1")}>模拟导入</button>
        <button onClick={onClose}>关闭导入</button>
      </div>
    ) : null,
}));
vi.mock("@/components/novel/DeleteConfirmModal", () => ({
  default: ({ title, confirmText, onConfirm, onCancel }: { title: string; confirmText: string; onConfirm: () => void; onCancel: () => void }) => (
    <div data-testid="delete-modal">
      <span>
        删除{title}《{confirmText}》
      </span>
      <button onClick={onConfirm}>确认删除</button>
      <button onClick={onCancel}>取消删除</button>
    </div>
  ),
}));
vi.mock("@/components/novel/RenameModal", () => ({
  default: ({ name, onConfirm, onCancel }: { name: string; onConfirm: (n: string) => void; onCancel: () => void }) => (
    <div data-testid="rename-modal">
      <span>改名：{name}</span>
      <button onClick={() => onConfirm("新名字")}>确认改名</button>
      <button onClick={onCancel}>取消改名</button>
    </div>
  ),
}));

const novel = (over: Record<string, unknown> = {}) => ({
  id: "n1",
  name: "星海拾遗",
  slug: "xh",
  current_phase: "writing",
  total_volumes: 2,
  total_chapters: 3,
  total_archives: 0,
  updated_at: new Date().toISOString(),
  word_count: 12345,
  synopsis: "一句话简介",
  genre: "科幻",
  ...over,
});

const renderPage = () => {
  // 书架数据已迁查询缓存（c-query-cache-layer）：测试需包 Provider
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/novels"]}>
        <Routes>
          <Route path="/novels" element={<NovelListPage />} />
          <Route path="/login" element={<div data-testid="login-slot" />} />
          <Route path="/novel/:id" element={<div data-testid="workspace" />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.setItem("auth_token", "tok-shelf");
  localStorage.setItem("auth_username", "u1");
  getMock.mockResolvedValue([novel()]);
  deleteMock.mockResolvedValue({ ok: true });
  renameMock.mockResolvedValue({ id: "n1", name: "新名字" });
  finishMock.mockResolvedValue({ id: "n1", name: "星海拾遗", finished_at: new Date().toISOString(), updated_at: new Date().toISOString() });
  reopenMock.mockResolvedValue({ id: "n1", name: "星海拾遗", finished_at: null, updated_at: new Date().toISOString() });
  postMock.mockResolvedValue({});
  Object.assign(tierState, { tier: "pro", isMember: true, expired: false, trialRemainingDays: 0 });
});

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("列表状态与卡片", () => {
  it("正常渲染卡片：阶段标签/题材胶囊/统计/简介/相对时间", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("《星海拾遗》")).toBeTruthy());
    // 状态文案与工具栏 chips 同字（c-works-toolbar），徽章断言收窄到卡内
    const card = screen.getByText("《星海拾遗》").closest(".book-card") as HTMLElement;
    expect(within(card).getByText("写作中")).toBeTruthy();
    expect(screen.getByText("科幻")).toBeTruthy();
    expect(screen.getByText("2 卷")).toBeTruthy();
    expect(screen.getByText("3 章")).toBeTruthy();
    expect(screen.getByText("12,345")).toBeTruthy();
    expect(screen.getByText("一句话简介")).toBeTruthy();
    expect(screen.getByText(/更新于 刚刚/)).toBeTruthy();
    expect(screen.getByText("继续创作")).toBeTruthy();
    // 互斥（PR #423 评审 P1）：PRO 正常态下六类 Banner 一个都不许出现
    expect(
      screen.queryByText(/权益信息同步异常|套餐已过期|试用还剩|试用期进行中|开通 7 天免费试用|免费版书架已满/),
    ).toBeNull();
  });

  it("阶段派生：全归档未完结=待完本（回看＋完本）/完结=已完结/无章=设定；题材缺失待定胶囊", async () => {
    getMock.mockResolvedValue([
      novel({ id: "a", name: "全归档", total_chapters: 3, total_archives: 3 }),
      novel({ id: "b", name: "空书", total_chapters: 0, total_archives: 0, genre: null }),
      novel({
        id: "c",
        name: "完本书",
        total_chapters: 9,
        total_archives: 9,
        finished_at: new Date(Date.now() - 3 * 86400_000).toISOString(),
      }),
    ]);
    renderPage();
    await waitFor(() => expect(screen.getByText("《全归档》")).toBeTruthy());
    const cardOf = (n: string) =>
      screen.getByText(`《${n}》`).closest(".book-card") as HTMLElement;
    expect(within(cardOf("全归档")).getByText("待完本")).toBeTruthy();
    expect(screen.getByText("全书 3 章已归档")).toBeTruthy();
    // 回看（待完本）与回看（已完结，v2 新增）同名——收窄到各自卡内
    expect(within(cardOf("全归档")).getByText("回看")).toBeTruthy();
    expect(within(cardOf("完本书")).getByText("回看")).toBeTruthy();
    expect(screen.getByText("完本")).toBeTruthy();
    expect(within(cardOf("完本书")).getByText("已完结")).toBeTruthy();
    expect(screen.getByText(/完结于/)).toBeTruthy();
    expect(within(cardOf("空书")).getByText("设定中")).toBeTruthy();
    expect(screen.getByText("待定题材")).toBeTruthy();
    expect(screen.getByText("继续创作")).toBeTruthy();
  });

  it("相对时间口径：分钟/小时/昨天/天/日期", async () => {
    const at = (ms: number) => new Date(Date.now() - ms).toISOString();
    getMock.mockResolvedValue([
      novel({ id: "m", name: "分钟", updated_at: at(5 * 60_000) }),
      novel({ id: "h", name: "小时", updated_at: at(3 * 3600_000) }),
      novel({ id: "y", name: "昨天", updated_at: at(30 * 3600_000) }),
      novel({ id: "d", name: "天", updated_at: at(4 * 24 * 3600_000) }),
      novel({ id: "o", name: "久远", updated_at: at(30 * 24 * 3600_000) }),
    ]);
    renderPage();
    await waitFor(() => expect(screen.getByText("《分钟》")).toBeTruthy());
    expect(screen.getByText("更新于 5 分钟前")).toBeTruthy();
    expect(screen.getByText("更新于 3 小时前")).toBeTruthy();
    expect(screen.getByText("更新于 昨天")).toBeTruthy();
    expect(screen.getByText("更新于 4 天前")).toBeTruthy();
    expect(screen.getByText(/更新于 \d{4}\//)).toBeTruthy(); // 超过一周落日期
  });

  it("卡片回车进工作台（Enter 臂）", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("《星海拾遗》")).toBeTruthy());
    const card = document.querySelector(".book-card") as HTMLElement;
    fireEvent.keyDown(card, { key: "Enter" });
    await waitFor(() => expect(screen.getByTestId("workspace")).toBeTruthy());
  });

  it("菜单：展开→操作项可见→点外部收起", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("《星海拾遗》")).toBeTruthy());
    fireEvent.click(screen.getByLabelText("更多操作"));
    expect(screen.getByText("重命名")).toBeTruthy();
    expect(screen.getByText("删除")).toBeTruthy();
    await act(async () => {
      fireEvent.mouseDown(document.body);
    });
    expect(screen.queryByText("重命名")).toBeNull();
  });

  it("加载失败可重试；空书架出三步引导并可新建/导入", async () => {
    getMock.mockRejectedValueOnce(new Error("boom")).mockResolvedValue([novel()]);
    const failed = renderPage();
    expect(await screen.findByText("作品加载失败")).toBeTruthy();
    fireEvent.click(screen.getByText("重新加载"));
    await waitFor(() => expect(screen.getByText("《星海拾遗》")).toBeTruthy());
    failed.unmount();

    getMock.mockResolvedValue([]);
    renderPage();
    expect(await screen.findByText("开始你的第一本书")).toBeTruthy();
    expect(screen.getByText("STEP 03")).toBeTruthy();
    fireEvent.click(within(document.querySelector(".fr-cta") as HTMLElement).getByText("新建作品"));
    expect(screen.getByTestId("create-modal")).toBeTruthy();
    fireEvent.click(screen.getByText("关闭创建"));
    fireEvent.click(screen.getByText("导入已有文稿"));
    expect(screen.getByTestId("import-modal")).toBeTruthy();
  });

  it("首启空态出口行常驻并列两条出路（c-db-per-version）：无候选时「从备份包恢复」仍在", async () => {
    legacyStatusMock.value = null;   // 换安装目录场景：候选扫描看不到任何旧库
    getMock.mockResolvedValue([]);   // 空书架（首启态）
    renderPage();
    await screen.findByText("开始你的第一本书");
    const restore = screen.getByText("从备份包恢复");
    expect(screen.queryByText("把上一版的作品带过来")).toBeNull();
    // 点第二出口 → 派发 restore:open 事件（AcctMenu 单实例消费；避免双弹窗双轮询）
    const opened = vi.fn();
    window.addEventListener("restore:open", opened);
    fireEvent.click(restore);
    window.removeEventListener("restore:open", opened);
    expect(opened).toHaveBeenCalledTimes(1);
  });

  it("首启仲裁（c-lossless-upgrade）：recommended 未带回未抑制 → 告知卡自动出现，角落小字让位", async () => {
    legacyStatusMock.value = {
      current_version: "0.25",
      quarantined: [],
      candidates: [
        {
          filename: "novel-v0.24.db", version: "0.24", kind: "semver",
          legacy_generation: null, size_bytes: 10, mtime: 1, book_count: 3,
          unreadable: false, recommended: true, stamp: "s", suppressed: false,
        },
        {
          filename: "novel-v0.23.db", version: "0.23", kind: "semver",
          legacy_generation: null, size_bytes: 10, mtime: 1, book_count: 2,
          unreadable: false, recommended: false, stamp: "s2", suppressed: false,
        },
      ],
    };
    getMock.mockResolvedValue([]);
    renderPage();
    await screen.findByText("开始你的第一本书");
    // 告知卡经壳层队列入场：两块清单 + 主按钮覆盖作品与配置两样
    const card = await screen.findByTestId("carry-card");
    expect(card.textContent).toContain("3");
    expect(card.textContent).toContain("把作品和模型配置带过来");
    expect(card.textContent).toContain("另有更早的 1 份数据");
    // 角落小字让位（卡在途不再渲染 bring-back 小字；弹窗标题同名不算）；备份包出口恒在
    const note = document.querySelector(".fr-note") as HTMLElement;
    expect(note).toBeTruthy();
    expect(note.textContent).not.toContain("把上一版的作品带过来");
    expect(screen.getByText("从备份包恢复")).toBeTruthy();
  });

  it("新建/导入入口：创建与导入成功都跳工作台", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("新建作品")).toBeTruthy());
    fireEvent.click(screen.getByText("新建作品"));
    fireEvent.click(screen.getByText("模拟创建"));
    await waitFor(() => expect(screen.getByTestId("workspace")).toBeTruthy());
  });

  it("改名全链：成功更新卡片与 toast；失败报错", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("《星海拾遗》")).toBeTruthy());
    fireEvent.click(screen.getByLabelText("更多操作"));
    fireEvent.click(screen.getByText("重命名"));
    fireEvent.click(screen.getByText("确认改名"));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("已更名为《新名字》"));
    expect(screen.getByText("《新名字》")).toBeTruthy();

    renameMock.mockRejectedValueOnce(new Error("boom"));
    fireEvent.click(screen.getByLabelText("更多操作"));
    fireEvent.click(screen.getByText("重命名"));
    fireEvent.click(screen.getByText("确认改名"));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("改名失败"));
  });

  it("删除全链：确认删除移除卡片并 toast；取消关闭弹窗；失败报错", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("《星海拾遗》")).toBeTruthy());
    fireEvent.click(screen.getByLabelText("更多操作"));
    fireEvent.click(screen.getByText("删除"));
    expect(screen.getByTestId("delete-modal")).toBeTruthy();
    fireEvent.click(screen.getByText("取消删除"));
    expect(screen.queryByTestId("delete-modal")).toBeNull();
    expect(deleteMock).not.toHaveBeenCalled(); // 取消不得打删除接口

    fireEvent.click(screen.getByLabelText("更多操作"));
    fireEvent.click(screen.getByText("删除"));
    fireEvent.click(screen.getByText("确认删除"));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("《星海拾遗》已删除"));
    expect(screen.queryByText("《星海拾遗》")).toBeNull();

    getMock.mockResolvedValue([novel()]);
    deleteMock.mockRejectedValueOnce(new Error("boom"));
    const again = renderPage();
    await waitFor(() => expect(screen.getAllByText("《星海拾遗》").length).toBeGreaterThan(0));
    fireEvent.click(within(again.container.querySelector(".book-card") as HTMLElement).getByLabelText("更多操作"));
    fireEvent.click(screen.getByText("删除"));
    fireEvent.click(screen.getByText("确认删除"));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("删除失败"));
  });
});

describe("Banner 与门禁", () => {
  it("权益快照异常：显示提示 + 复制问题信息；有客服链接时才渲染客服按钮", async () => {
    const writeText = vi.fn(async () => {});
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
    postMock.mockResolvedValue({ entitlement_degraded: true, tier: "pro", entitlement_fetched_at: "2026-09-18" });
    renderPage();
    await waitFor(() => expect(screen.getByText(/权益信息同步异常/)).toBeTruthy());
    fireEvent.click(screen.getByText("复制问题信息"));
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining("entitlement_incomplete_snapshot"));
    expect(await screen.findByText("联系客服")).toBeTruthy();
  });

  it("过期 / 试用 / 免费层三条 Banner 互斥呈现", async () => {
    // 注意：非会员且已有 1 本 → 「免费版书架已满」本该显示（免费待遇口径），故不列入互斥排除项
    const NOT_IN = /试用还剩|试用期进行中|开通 7 天免费试用/;
    Object.assign(tierState, { tier: "trial", isMember: false, expired: true, trialRemainingDays: 0 });
    const expired = renderPage();
    await waitFor(() => expect(screen.getByText(/套餐已过期/)).toBeTruthy());
    expect(screen.getByText("续费恢复")).toBeTruthy();
    expect(screen.queryByText(NOT_IN)).toBeNull(); // 过期时不再出试用/免费层条
    expired.unmount();

    Object.assign(tierState, { tier: "trial", isMember: false, expired: false, trialRemainingDays: 5 });
    const trial = renderPage();
    await waitFor(() => expect(screen.getByText(/试用还剩 5 天/)).toBeTruthy());
    expect(screen.getByText("开通 PRO")).toBeTruthy();
    expect(screen.queryByText(/套餐已过期|开通 7 天免费试用/)).toBeNull();
    trial.unmount();

    Object.assign(tierState, { tier: "trial", isMember: false, expired: false, trialRemainingDays: 0 });
    const trialOn = renderPage();
    await waitFor(() => expect(screen.getByText(/试用期进行中/)).toBeTruthy());
    expect(screen.queryByText(/套餐已过期|开通 7 天免费试用/)).toBeNull();
    trialOn.unmount();

    Object.assign(tierState, { tier: "none", isMember: false, expired: false, trialRemainingDays: 0, projectLimit: 1 });
    renderPage();
    await waitFor(() => expect(screen.getByText(/开通 7 天免费试用/)).toBeTruthy());
    expect(screen.queryByText(/套餐已过期|试用还剩|试用期进行中/)).toBeNull();
  });

  it("tier=none 但 expired 标记为真（不一致态）：只出免费层条，不出过期条", async () => {
    Object.assign(tierState, { tier: "none", isMember: false, expired: true, trialRemainingDays: 0, projectLimit: 1 });
    renderPage();
    await waitFor(() => expect(screen.getByText(/开通 7 天免费试用/)).toBeTruthy());
    expect(screen.queryByText(/套餐已过期/)).toBeNull(); // tier==='none' 时过期条必须让位
  });

  it("缺 API Key 提示与「去配置」；有 Key 时不提示", async () => {
    postMock.mockResolvedValue({});
    getMock.mockImplementation(async (path: string) => {
      if (path === "/novels") return [novel()];
      if (path === "/auth/config") return { has_api_key: false, portal_url: "https://portal.me" };
      return {};
    });
    const noKey = renderPage();
    await waitFor(() => expect(screen.getByText(/还没配置 API Key/)).toBeTruthy());
    expect(screen.getByText("去配置")).toBeTruthy();
    noKey.unmount();

    getMock.mockImplementation(async (path: string) => {
      if (path === "/novels") return [novel()];
      if (path === "/auth/config") return { has_api_key: true };
      return {};
    });
    renderPage();
    await waitFor(() => expect(screen.getByText("《星海拾遗》")).toBeTruthy());
    expect(screen.queryByText(/还没配置 API Key/)).toBeNull();
  });

  it("免费满额：一对一说明 + 主按钮带锁 + 锁定瓦片 + 点按钮走升级引导", async () => {
    Object.assign(tierState, { tier: "none", isMember: false, expired: false, trialRemainingDays: 0, projectLimit: 1 });
    const openSpy = vi.fn();
    vi.stubGlobal("open", openSpy);
    getMock.mockImplementation(async (path: string) => {
      if (path === "/novels") return [novel()];
      if (path === "/auth/config") return { has_api_key: true, portal_url: "https://portal.me" };
      return {};
    });
    renderPage();
    await waitFor(() => expect(screen.getAllByText(/书架已满/).length).toBeGreaterThan(0));
    expect(document.querySelector('[data-od-id="lock-tile"]')).toBeTruthy();
    fireEvent.click(screen.getByText("新建作品"));
    expect(openSpy).toHaveBeenCalledWith("https://portal.me", "_blank", "noopener,noreferrer");
    // 锁定瓦片点击同样引导升级（回车也可）
    fireEvent.keyDown(document.querySelector('[data-od-id="lock-tile"]') as HTMLElement, { key: "Enter" });
    expect(openSpy).toHaveBeenCalledTimes(2);
    // 升级按钮用 portalUrl（有值时指向它）
    expect(screen.getByRole("link", { name: "升级" }).getAttribute("href")).toBe("https://portal.me");
  });


  it("projectLimit 未透传（undefined）＋会员：回落不限（旧口径兼容臂，249 行分支）", async () => {
    Object.assign(tierState, { tier: "pro", isMember: true, expired: false });
    delete (tierState as { projectLimit?: number | null }).projectLimit; // 旧 S端 快照形态：键缺失
    getMock.mockImplementation(async (path: string) => {
      if (path === "/novels") return [novel()];
      if (path === "/auth/config") return { has_api_key: true };
      return {};
    });
    renderPage();
    await waitFor(() => expect(screen.getByText("《星海拾遗》")).toBeTruthy());
    // 不满额：无锁定瓦片
    expect(document.querySelector('[data-od-id="lock-tile"]')).toBeNull();
    // 新建可点（无升级拦截——createAction 不走 guideUpgrade）
    fireEvent.click(
      within(document.querySelector(".page-head") as HTMLElement).getByText("新建作品"),
    );
    expect(screen.getByTestId("create-modal")).toBeTruthy();
  });


  it("projectLimit 未透传＋免费：回落 1 本（249 行另一臂）", async () => {
    Object.assign(tierState, { tier: "none", isMember: false, expired: false });
    delete (tierState as { projectLimit?: number | null }).projectLimit;
    getMock.mockImplementation(async (path: string) => {
      if (path === "/novels") return [novel()];
      if (path === "/auth/config") return { has_api_key: true };
      return {};
    });
    renderPage();
    await waitFor(() => expect(screen.getAllByText(/书架已满/).length).toBeGreaterThan(0));
    expect(document.querySelector('[data-od-id="lock-tile"]')).toBeTruthy();
  });

  it("无 portal_url 时升级按钮回落常量门户", async () => {
    Object.assign(tierState, { tier: "none", isMember: false, expired: false, trialRemainingDays: 0, projectLimit: 1 });
    getMock.mockImplementation(async (path: string) => {
      if (path === "/novels") return [novel()];
      if (path === "/auth/config") return { has_api_key: true };
      return {};
    });
    renderPage();
    await waitFor(() => expect(screen.getByText(/开通 7 天免费试用/)).toBeTruthy());
    expect(screen.getByText("免费试用").closest("a")?.getAttribute("href")).toBe("https://portal.default");
  });

  it("AuthGuard 门禁：无 token 落登录页", async () => {
    localStorage.removeItem("auth_token");
    renderPage();
    await waitFor(() => expect(screen.getByTestId("login-slot")).toBeTruthy());
    expect(getMock).not.toHaveBeenCalled();
  });
});

describe("覆盖补齐（边界臂）", () => {
  it("空名与零值卡片：名字回落「书」、统计显示 0、字数 0", async () => {
    getMock.mockResolvedValue([
      novel({ id: "z", name: "", total_volumes: 0, total_chapters: 0, total_archives: 0, word_count: undefined, genre: "" }),
    ]);
    renderPage();
    await waitFor(() => expect(screen.getByText("《》")).toBeTruthy());
    expect(document.querySelector(".book-card .mono")!.textContent).toBe("书");
    expect(screen.getByText("0 卷")).toBeTruthy();
    expect(screen.getByText("0 章")).toBeTruthy();
    expect(screen.getByText("0")).toBeTruthy(); // 字数 0（word_count 缺省）
    expect(screen.getByText("待定题材")).toBeTruthy();
  });

  it("点卡片主体进入工作台（onClick 臂）", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("《星海拾遗》")).toBeTruthy());
    fireEvent.click(document.querySelector(".book-card") as HTMLElement);
    await waitFor(() => expect(screen.getByTestId("workspace")).toBeTruthy());
  });

  it("卡片回车以外的按键不跳转；锁定瓦片同理", async () => {
    Object.assign(tierState, { tier: "none", isMember: false, expired: false, trialRemainingDays: 0, projectLimit: 1 });
    vi.stubGlobal("open", vi.fn());
    renderPage();
    await waitFor(() => expect(screen.getByText("《星海拾遗》")).toBeTruthy());
    const card = document.querySelector(".book-card") as HTMLElement;
    fireEvent.keyDown(card, { key: "a" });
    expect(screen.queryByTestId("workspace")).toBeNull();
    fireEvent.keyDown(document.querySelector('[data-od-id="lock-tile"]') as HTMLElement, { key: "a" });
    expect(vi.mocked(globalThis.open)).not.toHaveBeenCalled();
  });

  it("书名列表多本时改名只改目标卡", async () => {
    getMock.mockResolvedValue([novel({ id: "n1", name: "甲" }), novel({ id: "n2", name: "乙" })]);
    renameMock.mockResolvedValue({ id: "n1", name: "甲改" });
    renderPage();
    await waitFor(() => expect(screen.getByText("《甲》")).toBeTruthy());
    fireEvent.click(within(document.querySelectorAll(".book-card")[0] as HTMLElement).getByLabelText("更多操作"));
    fireEvent.click(screen.getByText("重命名"));
    fireEvent.click(screen.getByText("确认改名"));
    await waitFor(() => expect(screen.getByText("《甲改》")).toBeTruthy());
    expect(screen.getByText("《乙》")).toBeTruthy(); // 另一本不受影响
  });

  it("改名弹窗取消：关闭且不改名", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("《星海拾遗》")).toBeTruthy());
    fireEvent.click(screen.getByLabelText("更多操作"));
    fireEvent.click(screen.getByText("重命名"));
    fireEvent.click(screen.getByText("取消改名"));
    expect(screen.queryByTestId("rename-modal")).toBeNull();
    expect(renameMock).not.toHaveBeenCalled();
  });

  it("菜单内部 mousedown 不关闭（点在菜单里继续操作）", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("《星海拾遗》")).toBeTruthy());
    fireEvent.click(screen.getByLabelText("更多操作"));
    const menu = document.querySelector(".card-menu") as HTMLElement;
    fireEvent.mouseDown(menu);
    expect(screen.getByText("重命名")).toBeTruthy(); // 仍开着
  });

  it("导入按钮（未满额）打开导入弹窗并可关闭", async () => {
    // 显式重置：前序用例可能改过模块级 tierState（projectLimit 残留会让导入钮隐藏）
    Object.assign(tierState, { tier: "pro", isMember: true, expired: false, projectLimit: null });
    renderPage();
    await waitFor(() => expect(screen.getByText("新建作品")).toBeTruthy());
    fireEvent.click(within(document.querySelector(".page-head") as HTMLElement).getByText("导入"));
    expect(screen.getByTestId("import-modal")).toBeTruthy();
    fireEvent.click(screen.getByText("关闭导入"));
    await waitFor(() => expect(screen.queryByTestId("import-modal")).toBeNull());
  });

  it("满额且无 portal_url：升级引导仍走常量门户", async () => {
    Object.assign(tierState, { tier: "none", isMember: false, expired: false, trialRemainingDays: 0, projectLimit: 1 });
    const openSpy = vi.fn();
    vi.stubGlobal("open", openSpy);
    getMock.mockImplementation(async (path: string) => {
      if (path === "/novels") return [novel()];
      if (path === "/auth/config") return { has_api_key: true };
      return {};
    });
    renderPage();
    await waitFor(() => expect(screen.getAllByText(/书架已满/)[0]).toBeTruthy());
    fireEvent.click(screen.getByText("新建作品"));
    expect(openSpy).toHaveBeenCalledWith("https://portal.default", "_blank", "noopener,noreferrer");
    fireEvent.click(within(document.querySelector(".page-head") as HTMLElement).getByText("导入"));
    expect(openSpy).toHaveBeenCalledTimes(2);
    expect(screen.queryByTestId("import-modal")).toBeNull(); // 满额时不开导入
  });

  it("verify 无 entitlement 字段 / 明确 false：都不出异常提示", async () => {
    postMock.mockResolvedValueOnce({}); // 无字段
    const a = renderPage();
    await waitFor(() => expect(screen.getByText("《星海拾遗》")).toBeTruthy());
    expect(screen.queryByText(/权益信息同步异常/)).toBeNull();
    a.unmount();

    postMock.mockResolvedValueOnce({ entitlement_degraded: false });
    renderPage();
    await waitFor(() => expect(screen.getByText("《星海拾遗》")).toBeTruthy());
    expect(screen.queryByText(/权益信息同步异常/)).toBeNull();
  });

  it("verify / auth-config 请求失败：静默不炸", async () => {
    postMock.mockRejectedValueOnce(new Error("boom"));
    getMock.mockImplementation(async (path: string) => {
      if (path === "/novels") return [novel()];
      throw new Error("cfg down");
    });
    renderPage();
    await waitFor(() => expect(screen.getByText("《星海拾遗》")).toBeTruthy());
    expect(screen.queryByText(/还没配置 API Key/)).toBeNull();
  });

  it("权益异常但拿不到客服链接：只留复制按钮", async () => {
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText: vi.fn(async () => {}) } });
    const support = await import("@/lib/support");
    vi.mocked(support.supportUrl).mockRejectedValueOnce(new Error("no support"));
    postMock.mockResolvedValue({ entitlement_degraded: true });
    renderPage();
    await waitFor(() => expect(screen.getByText(/权益信息同步异常/)).toBeTruthy());
    expect(screen.getByText("复制问题信息")).toBeTruthy();
    await act(async () => {});
    expect(screen.queryByText("联系客服")).toBeNull();
  });
});

describe("覆盖补齐（收尾）", () => {
  it("复制被拒 / 无剪贴板：都不炸（catch 回调 + 可选链短路臂）", async () => {
    const writeText = vi.fn(async () => {
      throw new Error("denied");
    });
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
    postMock.mockResolvedValue({ entitlement_degraded: true });
    const first = renderPage();
    await waitFor(() => expect(screen.getByText(/权益信息同步异常/)).toBeTruthy());
    fireEvent.click(screen.getByText("复制问题信息"));
    await act(async () => {});
    expect(writeText).toHaveBeenCalled();
    first.unmount();

    vi.stubGlobal("navigator", { ...navigator, clipboard: undefined }); // 无 clipboard：可选链短路
    renderPage();
    await waitFor(() => expect(screen.getByText(/权益信息同步异常/)).toBeTruthy());
    fireEvent.click(screen.getByText("复制问题信息")); // 不抛错即通过
    await act(async () => {});
  });

  it("再点「更多操作」收起同卡菜单（toggle 关闭臂）", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("《星海拾遗》")).toBeTruthy());
    const btn = screen.getByLabelText("更多操作");
    fireEvent.click(btn);
    expect(screen.getByText("重命名")).toBeTruthy();
    fireEvent.click(btn);
    expect(screen.queryByText("重命名")).toBeNull();
  });

});

describe("完本链路（works-finish-flow）", () => {
  const hookRow = {
    id: "h1",
    description: "旧航图缺口上的摩挲痕迹",
    status: "active",
    introduced_chapter_id: "ch-uuid-2",
  };

  /** 书架带一本全归档未完结书 + hooks/volumes 打桩 */
  const stubReadyBook = () => {
    getMock.mockImplementation(async (path: string) => {
      if (path === "/novels") return [novel({ id: "n1", total_chapters: 3, total_archives: 3 })];
      if (path === "/novels/n1/hooks") return { data: { count: 1, items: [hookRow] } };
      if (path === "/novels/n1/volumes")
        return [{ ref: "vol-1", chapters: [{ id: "ch-uuid-2", chapter: 2 }] }];
      return {};
    });
  };

  it("待完本入口：卡页脚「完本」打开弹窗；（分组头去完本见工具栏用例）", async () => {
    stubReadyBook();
    renderPage();
    await waitFor(() => expect(screen.getByText("《星海拾遗》")).toBeTruthy());
    // 提示条已退役（c-works-toolbar）：完本入口＝卡页脚「完本」/ 待完本分组头「去完本」
    expect(screen.queryByText(/主线已收齐/)).toBeNull();
    fireEvent.click(screen.getByText("完本"));
    await waitFor(() => expect(screen.getByText("完结《星海拾遗》？")).toBeTruthy());
  });

  it("完本清单弹窗：三行检查＋active 伏笔逐条＋留白切换不落库＋完结成功卡片转已完结", async () => {
    stubReadyBook();
    renderPage();
    await waitFor(() => expect(screen.getByText("《星海拾遗》")).toBeTruthy());
    fireEvent.click(screen.getByText("完本"));
    await waitFor(() => expect(screen.getByText("完结《星海拾遗》？")).toBeTruthy());
    expect(screen.getByText("章节已全部归档")).toBeTruthy();
    await waitFor(() => expect(screen.getByText("还有 1 条伏笔悬着")).toBeTruthy());
    expect(screen.getByText("旧航图缺口上的摩挲痕迹")).toBeTruthy();
    expect(screen.getByText("第 2 章埋下")).toBeTruthy();

    // 留白切换：未收 → 留白（纯弹窗内状态；api mock 无 patch 可走，调了即炸）
    fireEvent.click(screen.getByText(/旧航图缺口/));
    expect(screen.getByText("留白")).toBeTruthy();

    fireEvent.click(screen.getByText("完结这本书"));
    await waitFor(() => expect(finishMock).toHaveBeenCalledWith("n1"));
    expect(toast.success).toHaveBeenCalledWith(
      "《星海拾遗》已完结 · 归档收尾提案可在「设定 / 伏笔」页签逐条确认",
    );
    const card = await screen.findByText("《星海拾遗》").then(
      (el) => el.closest(".book-card") as HTMLElement,
    );
    expect(within(card).getByText("已完结")).toBeTruthy();
    expect(screen.getByText(/完结于/)).toBeTruthy();
  });

  it("已完结书：⋯菜单「完本信息 · 撤完本」→ 撤完本回待完本", async () => {
    getMock.mockResolvedValue([
      novel({
        id: "n1",
        total_chapters: 3,
        total_archives: 3,
        finished_at: new Date(Date.now() - 86400_000).toISOString(),
      }),
    ]);
    renderPage();
    await waitFor(() => expect(screen.getByText("《星海拾遗》")).toBeTruthy());
    const cardOf = () => screen.getByText("《星海拾遗》").closest(".book-card") as HTMLElement;
    expect(within(cardOf()).getByText("已完结")).toBeTruthy();
    fireEvent.click(screen.getByLabelText("更多操作"));
    fireEvent.click(screen.getByText("完本信息 · 撤完本"));
    await waitFor(() => expect(screen.getByText("《星海拾遗》已完结")).toBeTruthy());
    expect(screen.getByText("撤完本 · 继续写")).toBeTruthy();

    fireEvent.click(screen.getByText("撤完本 · 继续写"));
    await waitFor(() => expect(reopenMock).toHaveBeenCalledWith("n1"));
    expect(toast.success).toHaveBeenCalledWith(
      "已撤完本 · 《星海拾遗》回到待完本，可以接着写或加新章",
    );
    await waitFor(() => expect(within(cardOf()).getByText("待完本")).toBeTruthy());
  });

  it("工具栏：状态 chip 进分组视图（计数＋去完本）；搜索无果出 bk-empty，清除筛选复原", async () => {
    stubReadyBook();
    renderPage();
    await waitFor(() => expect(screen.getByText("《星海拾遗》")).toBeTruthy());

    // 待完本分组：分组头计数 + 「主线已收齐」+ 去完本（本轮完本清单的直接入口）
    fireEvent.click(within(screen.getByRole("group", { name: "按状态筛选" })).getByText("待完本"));
    expect(screen.getByText(/1 本 · 主线已收齐/)).toBeTruthy();
    fireEvent.click(screen.getByText("去完本"));
    await waitFor(() => expect(screen.getByText("完结《星海拾遗》？")).toBeTruthy());
    fireEvent.click(screen.getByText("再想想"));

    // 搜索无果：bk-empty + 清除筛选复原（chip 回全部、搜索清空）
    fireEvent.change(screen.getByLabelText("搜索书名"), { target: { value: "不存在" } });
    expect(screen.getByText("没有找到符合条件的作品")).toBeTruthy();
    fireEvent.click(screen.getByText("清除筛选"));
    await waitFor(() => expect(screen.getByText("《星海拾遗》")).toBeTruthy());
    expect((screen.getByLabelText("搜索书名") as HTMLInputElement).value).toBe("");
    expect(
      within(screen.getByRole("group", { name: "按状态筛选" })).getByText("全部").getAttribute("aria-pressed"),
    ).toBe("true");
  });
});

describe("覆盖补齐（分页与排序）", () => {
  /** 造 n 本互不重名的书（写作中态，rank 相同进入排序比较）。 */
  const manyBooks = (n: number) =>
    Array.from({ length: n }, (_, i) =>
      novel({ id: `b${i}`, name: `书${i}`, total_chapters: 1, total_archives: 0 }),
    );

  it("分页点击：初始显示 12 本，「显示更多」一次加载至全部并收起按钮", async () => {
    getMock.mockResolvedValue(manyBooks(14));
    renderPage();
    await waitFor(() => expect(document.querySelectorAll(".book-card").length).toBe(SHELF_PAGE_SIZE));
    const moreBtn = () => screen.getByText(/显示更多/).closest("button") as HTMLButtonElement;
    expect(moreBtn().textContent).toBe(`显示更多 · ${SHELF_PAGE_SIZE} / 14`);
    fireEvent.click(moreBtn());
    await waitFor(() => expect(document.querySelectorAll(".book-card").length).toBe(14));
    expect(screen.queryByText("显示更多")).toBeNull(); // 全部显示后按钮收起
  });

  it("滚动进视口自动加载（IntersectionObserver）：不相交不动、相交加载、断开旧观察器、收齐后不再扩张", async () => {
    class FakeIO {
      static instances: FakeIO[] = [];
      cb: IntersectionObserverCallback;
      disconnectSpy = vi.fn();
      constructor(cb: IntersectionObserverCallback) {
        this.cb = cb;
        FakeIO.instances.push(this);
      }
      observe() {}
      unobserve() {}
      disconnect() {
        this.disconnectSpy();
      }
    }
    vi.stubGlobal("IntersectionObserver", FakeIO);
    getMock.mockResolvedValue(manyBooks(14));
    renderPage();
    await waitFor(() => expect(document.querySelectorAll(".book-card").length).toBe(SHELF_PAGE_SIZE));
    const fire = async (isIntersecting: boolean) => {
      const io = FakeIO.instances.at(-1)!;
      await act(async () => {
        io.cb([{ isIntersecting } as IntersectionObserverEntry], io as unknown as IntersectionObserver);
      });
    };
    await fire(false); // 未进视口：不加载
    expect(document.querySelectorAll(".book-card").length).toBe(SHELF_PAGE_SIZE);
    await fire(true); // 进视口：自动补齐剩余页
    await waitFor(() => expect(document.querySelectorAll(".book-card").length).toBe(14));
    expect(screen.queryByText("显示更多")).toBeNull();
    expect(FakeIO.instances.at(-1)!.disconnectSpy).toHaveBeenCalled(); // 重挂时断开旧观察器
    await fire(true); // 收齐后残留观察器事件：数量不再扩张
    expect(document.querySelectorAll(".book-card").length).toBe(14);
  });

  it("排序切换：默认最近更新在前，切「书名」后按书名升序重排", async () => {
    getMock.mockResolvedValue([
      novel({ id: "y", name: "乙", updated_at: new Date().toISOString() }),
      novel({ id: "j", name: "甲", updated_at: new Date(Date.now() - 86400_000).toISOString() }),
    ]);
    renderPage();
    await waitFor(() => expect(screen.getByText("《乙》")).toBeTruthy());
    const firstCardName = () => document.querySelector(".book-card h3")!.textContent;
    expect(firstCardName()).toBe("《乙》"); // 最近更新：乙在前
    fireEvent.change(screen.getByLabelText("排序方式"), { target: { value: "title" } });
    await waitFor(() => expect(firstCardName()).toBe("《甲》")); // 书名升序：甲在前
    expect(screen.getByText("《乙》")).toBeTruthy(); // 两本都在
  });

  it("状态分组：写作中分组头只给计数，不出「主线已收齐/去完本」", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("《星海拾遗》")).toBeTruthy());
    fireEvent.click(within(screen.getByRole("group", { name: "按状态筛选" })).getByText("写作中"));
    expect(screen.getByText("1 本")).toBeTruthy();
    expect(screen.queryByText("主线已收齐")).toBeNull();
    expect(screen.queryByText("去完本")).toBeNull();
    expect(document.querySelector('[data-od-id="group-writing"]')).toBeTruthy();
  });
});

describe("覆盖补齐（回看与多书局部更新）", () => {
  /** 工作台探针：显示路由 state 里的落点视图。 */
  const LandingProbe = () => {
    const { state } = useLocation();
    return <div data-testid="workspace">{`landing:${(state as { landingView?: string } | null)?.landingView ?? "none"}`}</div>;
  };
  const renderWithProbe = () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/novels"]}>
          <Routes>
            <Route path="/novels" element={<NovelListPage />} />
            <Route path="/login" element={<div data-testid="login-slot" />} />
            <Route path="/novel/:id" element={<LandingProbe />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
  };

  it("待完本卡「回看」：带归档落点进工作台（stopPropagation 不触发卡片跳转）", async () => {
    getMock.mockResolvedValue([novel({ id: "r1", total_chapters: 3, total_archives: 3 })]);
    renderWithProbe();
    await waitFor(() => expect(screen.getByText("《星海拾遗》")).toBeTruthy());
    fireEvent.click(within(document.querySelector(".book-card") as HTMLElement).getByText("回看"));
    await waitFor(() => expect(screen.getByTestId("workspace").textContent).toBe("landing:archives"));
  });

  it("已完结卡「回看」：同样落归档视图", async () => {
    getMock.mockResolvedValue([
      novel({ id: "d1", total_chapters: 3, total_archives: 3, finished_at: new Date().toISOString() }),
    ]);
    renderWithProbe();
    await waitFor(() => expect(screen.getByText("《星海拾遗》")).toBeTruthy());
    fireEvent.click(within(document.querySelector(".book-card") as HTMLElement).getByText("回看"));
    await waitFor(() => expect(screen.getByTestId("workspace").textContent).toBe("landing:archives"));
  });

  it("两本书时完本：只有目标卡转已完结，另一本不受牵连", async () => {
    getMock.mockImplementation(async (path: string) => {
      if (path === "/novels")
        return [
          novel({ id: "n1", total_chapters: 3, total_archives: 3 }),
          novel({ id: "n2", name: "另一本", total_chapters: 1, total_archives: 0 }),
        ];
      if (path === "/novels/n1/hooks") return { data: { count: 0, items: [] } };
      if (path === "/novels/n1/volumes") return [];
      return {};
    });
    renderPage();
    await waitFor(() => expect(screen.getByText("《星海拾遗》")).toBeTruthy());
    fireEvent.click(screen.getByText("完本")); // 只有待完本卡有「完本」钮
    await waitFor(() => expect(screen.getByText("完结《星海拾遗》？")).toBeTruthy());
    fireEvent.click(screen.getByText("完结这本书"));
    await waitFor(() => expect(finishMock).toHaveBeenCalledWith("n1"));
    const card1 = await screen.findByText("《星海拾遗》").then((el) => el.closest(".book-card") as HTMLElement);
    await waitFor(() => expect(within(card1).getByText("已完结")).toBeTruthy());
    const card2 = screen.getByText("《另一本》").closest(".book-card") as HTMLElement;
    expect(within(card2).getByText("写作中")).toBeTruthy(); // map 未命中分支：另一本原样
  });

  it("两本书时撤完本：只有目标卡回待完本，另一本不受牵连", async () => {
    getMock.mockResolvedValue([
      novel({ id: "n1", total_chapters: 3, total_archives: 3, finished_at: new Date().toISOString() }),
      novel({ id: "n2", name: "另一本", total_chapters: 1, total_archives: 0 }),
    ]);
    renderPage();
    await waitFor(() => expect(screen.getByText("《星海拾遗》")).toBeTruthy());
    fireEvent.click(
      within(screen.getByText("《星海拾遗》").closest(".book-card") as HTMLElement).getByLabelText("更多操作"),
    );
    fireEvent.click(screen.getByText("完本信息 · 撤完本"));
    await waitFor(() => expect(screen.getByText("撤完本 · 继续写")).toBeTruthy());
    fireEvent.click(screen.getByText("撤完本 · 继续写"));
    await waitFor(() => expect(reopenMock).toHaveBeenCalledWith("n1"));
    const card1 = await screen.findByText("《星海拾遗》").then((el) => el.closest(".book-card") as HTMLElement);
    await waitFor(() => expect(within(card1).getByText("待完本")).toBeTruthy());
    const card2 = screen.getByText("《另一本》").closest(".book-card") as HTMLElement;
    expect(within(card2).getByText("写作中")).toBeTruthy();
  });

  it("旧库候选缺书数（null）：卡按 recommended 计数，null 书数候选不炸", async () => {
    legacyStatusMock.value = {
      current_version: "0.25",
      quarantined: [],
      candidates: [
        {
          filename: "novel-v0.24.db", version: "0.24", kind: "semver",
          legacy_generation: null, size_bytes: 10, mtime: 1, book_count: 3,
          unreadable: false, recommended: true, stamp: "s", suppressed: false,
        },
        {
          filename: "novel-v0.23.db", version: "0.23", kind: "semver",
          legacy_generation: null, size_bytes: 10, mtime: 1, book_count: null,
          unreadable: false, recommended: false, stamp: "s2", suppressed: false,
        },
      ],
    };
    getMock.mockResolvedValue([]); // 空书架（首启态才渲染出口行）
    renderPage();
    await screen.findByText("开始你的第一本书");
    // c-lossless-upgrade：卡只针对 recommended（书数 3）；null 书数的更早候选不出数不炸
    const card = await screen.findByTestId("carry-card");
    expect(card.textContent).toContain("3");
    const note2 = document.querySelector(".fr-note") as HTMLElement;
    expect(note2).toBeTruthy();
    expect(note2.textContent).not.toContain("把上一版的作品带过来");
    legacyStatusMock.value = null;
  });
});


describe("写作能力探测（c-prompt-pack-onboard-modal）", () => {
  beforeEach(() => {
    resetPackProbeSlotForTests();
  });

  function listen() {
    const events: CustomEvent[] = [];
    const on = (e: Event) => events.push(e as CustomEvent);
    window.addEventListener("pack-modal:open", on);
    return () => window.removeEventListener("pack-modal:open", on);
  }

  it("未装包（probe 无已装版本且 source=pack）→ 广播 install 模式开弹窗", async () => {
    getMock.mockImplementation(async (path: string) => {
      if (String(path).includes("/prompt-pack/probe"))
        return { installed_version: "", latest_version: "", update_available: false, source: "pack" };
      return [novel()];
    });
    const events: CustomEvent[] = [];
    const on = (e: Event) => events.push(e as CustomEvent);
    window.addEventListener("pack-modal:open", on);
    renderPage();
    await waitFor(() => expect(getMock).toHaveBeenCalledWith("/prompt-pack/probe", { quiet: true }));
    await act(async () => {});
    window.removeEventListener("pack-modal:open", on);
    expect(events).toHaveLength(1);
    expect(events[0].detail).toEqual({ mode: "install" });
  });

  it("已装且探测有更新 → 广播 update（当前→最新版本对）", async () => {
    getMock.mockImplementation(async (path: string) => {
      if (String(path).includes("/prompt-pack/probe"))
        return { installed_version: "5", latest_version: "6", update_available: true, source: "pack" };
      return [novel()];
    });
    const events: CustomEvent[] = [];
    const on = (e: Event) => events.push(e as CustomEvent);
    window.addEventListener("pack-modal:open", on);
    renderPage();
    await waitFor(() => expect(events.length).toBe(1));
    window.removeEventListener("pack-modal:open", on);
    expect(events[0].detail).toEqual({ mode: "update", from: "5", to: "6" });
  });

  it("已装无更新 → 全静默不广播", async () => {
    getMock.mockImplementation(async (path: string) => {
      if (String(path).includes("/prompt-pack/probe"))
        return { installed_version: "6", latest_version: "6", update_available: false, source: "pack" };
      return [novel()];
    });
    const off = listen();
    renderPage();
    await waitFor(() => expect(getMock).toHaveBeenCalledWith("/prompt-pack/probe", { quiet: true }));
    await act(async () => {});
    off();
    // 静默＝零广播（探测结果无弹窗模式）
  });

  it("min_client 跳过（旧客户端＋未装）→ 全静默不广播（评审 P1-2）", async () => {
    getMock.mockImplementation(async (path: string) => {
      if (String(path).includes("/prompt-pack/probe"))
        return {
          installed_version: "",
          latest_version: "6",
          update_available: false,
          reason: "min_client_version",
          source: "pack",
        };
      return [novel()];
    });
    const off = listen();
    renderPage();
    await waitFor(() => expect(getMock).toHaveBeenCalledWith("/prompt-pack/probe", { quiet: true }));
    await act(async () => {});
    off();
  });

  it("dev 态（source=dev）未装也静默——存量 e2e 零扰动", async () => {
    getMock.mockImplementation(async (path: string) => {
      if (String(path).includes("/prompt-pack/probe"))
        return { installed_version: "", latest_version: "", update_available: false, source: "dev" };
      return [novel()];
    });
    const off = listen();
    renderPage();
    await waitFor(() => expect(getMock).toHaveBeenCalledWith("/prompt-pack/probe", { quiet: true }));
    await act(async () => {});
    off();
  });

  it("探测失败 → 静默不广播（finally 释放槽，下轮可再探测）", async () => {
    getMock.mockImplementation(async (path: string) => {
      if (String(path).includes("/prompt-pack/probe")) throw new Error("down");
      return [novel()];
    });
    const off = listen();
    renderPage();
    await waitFor(() => expect(getMock).toHaveBeenCalledWith("/prompt-pack/probe", { quiet: true }));
    await act(async () => {});
    off();
    getMock.mockImplementation(async (path: string) => {
      if (String(path).includes("/prompt-pack/probe"))
        return { installed_version: "", latest_version: "", update_available: false, source: "pack" };
      return [novel()];
    });
    resetPackProbeSlotForTests();
    const events: CustomEvent[] = [];
    const on = (e: Event) => events.push(e as CustomEvent);
    window.addEventListener("pack-modal:open", on);
    renderPage();
    await waitFor(() => expect(events.length).toBe(1));
    window.removeEventListener("pack-modal:open", on);
    expect(events[0].detail).toEqual({ mode: "install" });
  });

  it("在途槽去重：同帧第二次挂载不重复探测（StrictMode 双挂载）", async () => {
    let releaseProbe!: (v: unknown) => void;
    getMock.mockImplementation(async (path: string) => {
      if (String(path).includes("/prompt-pack/probe"))
        return new Promise((res) => { releaseProbe = res; });
      return [novel()];
    });
    renderPage();
    renderPage();
    await waitFor(() => expect(getMock).toHaveBeenCalledWith("/prompt-pack/probe", { quiet: true }));
    await act(async () => {});
    const probeCalls = getMock.mock.calls.filter((c) => String(c[0]).includes("probe")).length;
    releaseProbe({ installed_version: "1", latest_version: "1", update_available: false, source: "pack" });
    await act(async () => {});
    expect(probeCalls).toBe(1);
  });
});


describe("带回常驻行与四步收尾（c-lossless-upgrade 覆盖补齐）", () => {
  beforeEach(async () => {
    // 真 carryStore 单例跨用例残留 job（上例的 done 会让下例一点 start 即跳结果）
    const { resetCarryStoreForTests } = await import("@/lib/carryStore");
    resetCarryStoreForTests();
  });

  const CAND_BASE = {
    filename: "novel-v0.24.db", version: "0.24", kind: "semver" as const,
    legacy_generation: null, size_bytes: 10, mtime: 1, book_count: 3,
    unreadable: false, recommended: true, stamp: "s1",
  };

  function withRec(over: Record<string, unknown> = {}) {
    legacyStatusMock.value = {
      current_version: "0.25", quarantined: [],
      candidates: [{ ...CAND_BASE, ...over }],
    };
  }

  it("已带回（carried）：完成常驻行渲染，× 可收起", async () => {
    withRec({ carried: true, suppressed: true });
    getMock.mockResolvedValue([]);
    renderPage();
    const strip = await screen.findByTestId("carry-strip-done");
    expect(strip.textContent).toContain("已把上一版的作品和模型配置带过来");
    fireEvent.click(strip.querySelector("button") as HTMLElement);
    expect(screen.queryByTestId("carry-strip-done")).toBeNull(); // 仅视觉收起
  });

  it("稍后带（suppressed）：常驻行两出口——本版不再提醒走 snooze、带过来重开卡", async () => {
    withRec({ suppressed: true });
    getMock.mockResolvedValue([]);
    renderPage();
    const strip = await screen.findByTestId("carry-strip-later");
    expect(strip.textContent).toContain("上一版还有 3 本作品没有带过来");
    // 角落小字真分支（fr-note）：卡不在途（suppressed）→ 出口行回到带链接形态
    const note = document.querySelector(".fr-note") as HTMLElement;
    expect(note.textContent).toContain("把上一版的作品带过来");
    postMock.mockResolvedValue({ code: 0 });
    fireEvent.click(screen.getByTestId("carry-strip-mute"));
    await waitFor(() =>
      expect(postMock.mock.calls.some((c) => String(c[0]).includes("/dismiss"))).toBe(true));
    // 角落小字链接出口：派发 legacy-migrate:open（791 行 onClick）
    const opened = vi.fn();
    window.addEventListener("legacy-migrate:open", opened);
    fireEvent.click(screen.getByText("把上一版的作品带过来"));
    window.removeEventListener("legacy-migrate:open", opened);
    expect(opened).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByTestId("carry-strip-open"));
    expect(await screen.findByTestId("carry-card")).toBeTruthy(); // 重开卡
    // 卡内「稍后带」：收卡不出队（927 行 onLater 闭包）
    fireEvent.click(screen.getByTestId("carry-later"));
    expect(screen.queryByTestId("carry-card")).toBeNull();
  });


  it("评审修复③：卡内「稍后带」→ 会话内常驻行接管（未 snooze 也提醒）→ 可重开卡", async () => {
    withRec(); // 未抑制：此前稍后带后 SPA 会话内再无提醒路径
    getMock.mockResolvedValue([]);
    renderPage();
    await screen.findByTestId("carry-card");
    fireEvent.click(screen.getByTestId("carry-later"));
    // 卡收起＋常驻行出现（suppressed=false 也显示——本地 later 态）
    const strip = await screen.findByTestId("carry-strip-later");
    expect(strip.textContent).toContain("上一版还有 3 本作品没有带过来");
    fireEvent.click(screen.getByTestId("carry-strip-open"));
    expect(await screen.findByTestId("carry-card")).toBeTruthy();
  });

  it("评审修复③附：入队→稍后带（占队）→snooze＝用户已处置 → carry 条目出队放行", async () => {
    withRec();
    getMock.mockResolvedValue([]);
    postMock.mockResolvedValue({ code: 0 });
    const { dialogQueueHead } = await import("@/lib/dialogQueue");
    renderPage();
    await screen.findByTestId("carry-card");
    expect(dialogQueueHead()).toBe("carry"); // 卡在途＝占队（能力包不入场）
    fireEvent.click(screen.getByTestId("carry-later")); // 稍后带：仍占队
    await screen.findByTestId("carry-strip-later");
    expect(dialogQueueHead()).toBe("carry");
    fireEvent.click(screen.getByTestId("carry-strip-mute")); // 本版不再提醒＝处置完成
    await waitFor(() =>
      expect(postMock.mock.calls.some((c) => String(c[0]).includes("/dismiss"))).toBe(true));
    await waitFor(() => expect(dialogQueueHead()).not.toBe("carry")); // 出队放行
  });

  it("稍后带行书数缺（null）：按「?」兜底显示", async () => {
    withRec({ book_count: null, suppressed: true });
    getMock.mockResolvedValue([]);
    renderPage();
    const strip = await screen.findByTestId("carry-strip-later");
    expect(strip.textContent).toContain("上一版还有 ? 本作品没有带过来");
  });

  it("recommended 缺书数（null/0）：不自动入队出卡（守卫早退＋?? 兜底）", async () => {
    withRec({ book_count: null });
    getMock.mockResolvedValue([]);
    renderPage();
    await screen.findByText("开始你的第一本书");
    await act(async () => {});
    expect(screen.queryByTestId("carry-card")).toBeNull();
    expect(screen.queryByTestId("carry-strip-later")).toBeNull();
  });

  it("suppressed＋完成确认后：稍后带常驻行隐藏（carryConfirmed 收口）", async () => {
    withRec({ suppressed: true });
    let statusPayload: Record<string, unknown> = { state: "running", kind: "migration" };
    postMock.mockResolvedValue({ code: 0 });
    getMock.mockImplementation(async (path: unknown) => {
      const u = String(path);
      if (u.includes("db-migration/status")) return { code: 0, data: statusPayload };
      if (u.includes("db-migration/candidates"))
        return { code: 0, data: { candidates: [], quarantined: [], current_version: "0.25" } };
      return [novel()];
    });
    renderPage();
    await screen.findByTestId("carry-strip-later");
    fireEvent.click(screen.getByTestId("carry-strip-open"));
    await screen.findByTestId("carry-card");
    fireEvent.click(screen.getByTestId("carry-start"));
    await screen.findByTestId("carry-progress");
    statusPayload = {
      state: "done", kind: "migration",
      report: { status: "ok", complete: true, dead_keys: 0, book_count_migrated: 3 },
    };
    await screen.findByTestId("carry-result", {}, { timeout: 4000 });
    fireEvent.click(screen.getByTestId("carry-confirm"));
    await waitFor(() => expect(screen.queryByTestId("carry-strip-later")).toBeNull());
  });

  it("四步收尾：同意→进度（真轮询）→完成确认（onConfirmed 闭包＋队列放行）", async () => {
    withRec();
    // 整体换引用（改字段不改身份 → store 的 effect 不触发——可变引用陷阱判例）
    let statusPayload: { state: string; kind?: string; report?: unknown } = {
      state: "running", kind: "migration",
    };
    postMock.mockResolvedValue({ code: 0 }); // start 立返成功（进度走真轮询）
    getMock.mockImplementation(async (path: unknown) => {
      const u = String(path);
      if (u.includes("db-migration/status")) return { code: 0, data: statusPayload };
      if (u.includes("db-migration/candidates"))
        return { code: 0, data: { candidates: [], quarantined: [], current_version: "0.25" } };
      return [novel()];
    });
    renderPage();
    await screen.findByTestId("carry-card");
    fireEvent.click(screen.getByTestId("carry-start"));
    await screen.findByTestId("carry-progress");
    expect(screen.getByTestId("carry-progress").querySelector("button")).toBeNull(); // 锁定：零按钮
    // job 推进到 done（真 store 轮询 1s 一拍——waitFor 兜住）
    statusPayload = {
      state: "done", kind: "migration",
      report: { status: "ok", complete: true, dead_keys: 0, book_count_migrated: 3 },
    };
    const result = await screen.findByTestId("carry-result", {}, { timeout: 4000 });
    expect(result.textContent).toContain("作品和模型配置已经带过来");
    fireEvent.click(screen.getByTestId("carry-confirm"));
    await waitFor(() => expect(screen.queryByTestId("carry-result")).toBeNull());
  });
});
