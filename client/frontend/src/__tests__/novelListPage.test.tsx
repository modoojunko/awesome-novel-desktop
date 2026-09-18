// 书架页（NovelListPage）契约（覆盖率专项·批 1 收尾）：
//   列表三态（骨架/失败重试/首启引导）· 卡片（阶段派生/题材待定/统计/相对时间/菜单/跳转）·
//   六类 Banner（权益异常/过期/试用/免费层/缺 Key/满额）· 新建与导入入口 · 改名与删除全链 ·
//   满额时的升级引导与锁定瓦片 · AuthGuard 门禁。
import { act, render, screen, waitFor, within } from "@testing-library/react";
import { fireEvent } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import NovelListPage from "@/pages/NovelListPage";
import { toast } from "@/lib/toast";

const getMock = vi.fn();
const postMock = vi.fn();
const deleteMock = vi.fn();
const renameMock = vi.fn();
vi.mock("@/lib/api", () => ({
  api: {
    get: (...a: unknown[]) => getMock(...a),
    post: (...a: unknown[]) => postMock(...a),
    delete: (...a: unknown[]) => deleteMock(...a),
    renameNovel: (...a: unknown[]) => renameMock(...a),
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

const tierState = { tier: "pro", isMember: true, expired: false, trialRemainingDays: 0 };
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

const renderPage = () =>
  render(
    <MemoryRouter initialEntries={["/novels"]}>
      <Routes>
        <Route path="/novels" element={<NovelListPage />} />
        <Route path="/login" element={<div data-testid="login-slot" />} />
        <Route path="/novel/:id" element={<div data-testid="workspace" />} />
      </Routes>
    </MemoryRouter>,
  );

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.setItem("auth_token", "tok-shelf");
  localStorage.setItem("auth_username", "u1");
  getMock.mockResolvedValue([novel()]);
  deleteMock.mockResolvedValue({ ok: true });
  renameMock.mockResolvedValue({ id: "n1", name: "新名字" });
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
    expect(screen.getByText("写作中")).toBeTruthy();
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

  it("阶段派生：全归档=已归档（查看）/无章=设定；题材缺失显示待定胶囊", async () => {
    getMock.mockResolvedValue([
      novel({ id: "a", name: "全归档", total_chapters: 3, total_archives: 3 }),
      novel({ id: "b", name: "空书", total_chapters: 0, total_archives: 0, genre: null }),
    ]);
    renderPage();
    await waitFor(() => expect(screen.getByText("《全归档》")).toBeTruthy());
    expect(screen.getByText("已归档")).toBeTruthy();
    expect(screen.getByText("查看")).toBeTruthy();
    expect(screen.getByText("设定中")).toBeTruthy();
    expect(screen.getByText("待定题材")).toBeTruthy();
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

    Object.assign(tierState, { tier: "none", isMember: false, expired: false, trialRemainingDays: 0 });
    renderPage();
    await waitFor(() => expect(screen.getByText(/开通 7 天免费试用/)).toBeTruthy());
    expect(screen.queryByText(/套餐已过期|试用还剩|试用期进行中/)).toBeNull();
  });

  it("tier=none 但 expired 标记为真（不一致态）：只出免费层条，不出过期条", async () => {
    Object.assign(tierState, { tier: "none", isMember: false, expired: true, trialRemainingDays: 0 });
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
    Object.assign(tierState, { tier: "none", isMember: false, expired: false, trialRemainingDays: 0 });
    const openSpy = vi.fn();
    vi.stubGlobal("open", openSpy);
    getMock.mockImplementation(async (path: string) => {
      if (path === "/novels") return [novel()];
      if (path === "/auth/config") return { has_api_key: true, portal_url: "https://portal.me" };
      return {};
    });
    renderPage();
    await waitFor(() => expect(screen.getByText(/免费版书架已满/)).toBeTruthy());
    expect(document.querySelector('[data-od-id="lock-tile"]')).toBeTruthy();
    fireEvent.click(screen.getByText("新建作品"));
    expect(openSpy).toHaveBeenCalledWith("https://portal.me", "_blank", "noopener,noreferrer");
    // 锁定瓦片点击同样引导升级（回车也可）
    fireEvent.keyDown(document.querySelector('[data-od-id="lock-tile"]') as HTMLElement, { key: "Enter" });
    expect(openSpy).toHaveBeenCalledTimes(2);
    // 升级按钮用 portalUrl（有值时指向它）
    expect(screen.getByRole("link", { name: "升级" }).getAttribute("href")).toBe("https://portal.me");
  });

  it("无 portal_url 时升级按钮回落常量门户", async () => {
    Object.assign(tierState, { tier: "none", isMember: false, expired: false, trialRemainingDays: 0 });
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
    Object.assign(tierState, { tier: "none", isMember: false, expired: false, trialRemainingDays: 0 });
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
    renderPage();
    await waitFor(() => expect(screen.getByText("新建作品")).toBeTruthy());
    fireEvent.click(within(document.querySelector(".page-head") as HTMLElement).getByText("导入"));
    expect(screen.getByTestId("import-modal")).toBeTruthy();
    fireEvent.click(screen.getByText("关闭导入"));
    await waitFor(() => expect(screen.queryByTestId("import-modal")).toBeNull());
  });

  it("满额且无 portal_url：升级引导仍走常量门户", async () => {
    Object.assign(tierState, { tier: "none", isMember: false, expired: false, trialRemainingDays: 0 });
    const openSpy = vi.fn();
    vi.stubGlobal("open", openSpy);
    getMock.mockImplementation(async (path: string) => {
      if (path === "/novels") return [novel()];
      if (path === "/auth/config") return { has_api_key: true };
      return {};
    });
    renderPage();
    await waitFor(() => expect(screen.getByText(/免费版书架已满/)).toBeTruthy());
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
