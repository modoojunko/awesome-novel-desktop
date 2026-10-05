// loginless-data-exit 前端场景测试——specs「登录页升级引导」场景逐一对应：
// U1 协议失配就地引导（code=3 → UpgradeGate 替换主按钮+停轮询）
// U2 服务不可达不误闸（code=-1 维持常规态）
// U3 未点登录也能发现更新（本地 update-check has_update → 受阻态入口）
// U4 常驻免登导出入口（未受阻态可见）
// U5 免登导出全流程（选目录→start→进度→done 无配置包断言由后端 L1/L2 覆盖，
//    此处断言 UI 状态机与请求形态 include_config=false）
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const apiState = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: apiState,
  request: vi.fn(),
}));

//quiet 注入 window.matchMedia（landing.css 环境无）
beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  localStorage.clear();
  sessionStorage.setItem("manual_logout", "1"); // 跳过静默自动登录
});

async function renderLogin() {
  const LoginPage = (await import("@/pages/LoginPage")).default;
  return render(
    <MemoryRouter>
      <LoginPage />
    </MemoryRouter>,
  );
}

describe("LoginPage 升级引导（loginless-data-exit）", () => {
  it("U1 协议失配就地引导：check-auth code=3 → 升级卡替换主按钮", async () => {
    const { request } = await import("@/lib/api");
    const mocked = request as unknown as ReturnType<typeof vi.fn>;
    // 静默检测返回 code=3（U1 不设 manual_logout——静默路径正是首个消费方）
    sessionStorage.removeItem("manual_logout");
    mocked.mockResolvedValueOnce({
      code: 3,
      data: { client_outdated: true, latest_version: "0.25", download_url: "https://example.com/dl" },
    });
    apiState.get.mockResolvedValue({ code: 0, data: { present: false } });
    await renderLogin();
    await waitFor(() => {
      expect(screen.getByTestId("upgrade-gate")).toBeInTheDocument();
    });
    expect(screen.getByText("你的作品都在这台电脑上")).toBeInTheDocument();
    expect(screen.getByText("需要更新")).toBeInTheDocument();
    expect(screen.getByText("去下载新版")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "先备份作品" })).toBeInTheDocument();
    // 常规登录按钮不再渲染（死路不提供）
    expect(screen.queryByRole("button", { name: "打开浏览器登录" })).toBeNull();
  });

  it("U2 服务不可达不误闸：code=-1 维持常规登录态", async () => {
    const { request } = await import("@/lib/api");
    const mocked = request as unknown as ReturnType<typeof vi.fn>;
    mocked.mockResolvedValueOnce({ code: -1, msg: "S端 不可达" });
    apiState.get.mockResolvedValue({ code: 0, data: { present: false } });
    await renderLogin();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "打开浏览器登录" })).toBeInTheDocument();
    });
    expect(screen.queryByTestId("upgrade-gate")).toBeNull();
  });

  it("U4 常驻免登导出入口：未受阻态可见", async () => {
    const { request } = await import("@/lib/api");
    const mocked = request as unknown as ReturnType<typeof vi.fn>;
    mocked.mockResolvedValueOnce({ code: 1, data: {} });
    apiState.get.mockResolvedValue({ code: 0, data: { present: false } });
    await renderLogin();
    await waitFor(() => {
      expect(screen.getByText("不登录也能备份作品")).toBeInTheDocument();
    });
  });

  it("U5 点常驻入口打开免登备份弹窗并带 include_config=false 发起", async () => {
    const { request } = await import("@/lib/api");
    const mocked = request as unknown as ReturnType<typeof vi.fn>;
    mocked.mockResolvedValueOnce({ code: 1, data: {} });
    apiState.get.mockResolvedValue({ code: 0, data: { present: false } });
    apiState.post.mockResolvedValue({ code: 0 });
    await renderLogin();
    fireEvent.click(await screen.findByText("不登录也能备份作品"));
    expect(screen.getByText(/开始备份/)).toBeInTheDocument();
    // 填路径并发起
    const input = screen.getByPlaceholderText("或直接输入完整保存路径");
    fireEvent.change(input, { target: { value: "/tmp/out" } });
    fireEvent.click(screen.getByRole("button", { name: "开始备份" }));
    await waitFor(() => {
      expect(apiState.post).toHaveBeenCalledWith(
        "/backup/export/start",
        expect.objectContaining({ include_config: false, target_dir: "/tmp/out" }),
        expect.anything(),
      );
    });
  });

  it("U1 补充：升级卡「先备份作品」打开免登备份弹窗，可取消关闭", async () => {
    const { request } = await import("@/lib/api");
    const mocked = request as unknown as ReturnType<typeof vi.fn>;
    // 清掉前序用例遗留的 Once 队列（它们的静默检测被 manual_logout 跳过，Once 未消费会串味）
    (mocked as unknown as { mockReset: () => void }).mockReset();
    // 静默检测返回 code=3（进入升级卡）
    sessionStorage.removeItem("manual_logout");
    mocked.mockResolvedValue({
      code: 3,
      data: { client_outdated: true, latest_version: "0.25", download_url: "https://example.com/dl" },
    });
    apiState.get.mockResolvedValue({ code: 0, data: { present: false } });
    await renderLogin();
    await screen.findByTestId("upgrade-gate");
    // 「先备份作品」→ 受阻态（gate 入口）打开免登备份弹窗
    fireEvent.click(screen.getByRole("button", { name: "先备份作品" }));
    expect(screen.getByText(/无需登录即可完成备份/)).toBeInTheDocument();
    // 「取消」→ 关闭弹窗并回到升级卡
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    await waitFor(() => expect(screen.queryByText(/无需登录即可完成备份/)).toBeNull());
    expect(screen.getByTestId("upgrade-gate")).toBeInTheDocument();
  });

  it("U5 补充：主卡免登备份弹窗可取消关闭（关后回到登录卡）", async () => {
    const { request } = await import("@/lib/api");
    const mocked = request as unknown as ReturnType<typeof vi.fn>;
    mocked.mockResolvedValueOnce({ code: 1, data: {} });
    apiState.get.mockResolvedValue({ code: 0, data: { present: false } });
    await renderLogin();
    fireEvent.click(await screen.findByText("不登录也能备份作品"));
    expect(screen.getByText(/无需登录即可完成备份/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    await waitFor(() => expect(screen.queryByText(/无需登录即可完成备份/)).toBeNull());
    expect(screen.getByText("打开浏览器登录")).toBeInTheDocument();
  });
});
