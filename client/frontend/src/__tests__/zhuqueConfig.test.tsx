// c-zhuque-ai-detect 前端接线测试：模型配置页双页签（添加按钮随页签、?tab 深链、
// ?add 组合优先级）、朱雀面板两态（未配置保存并测试／已配置掩码＋开关）、
// 显示开关写 prefs 并广播事件。
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ApiKeyConfigPage from "@/pages/ApiKeyConfigPage";
import ZhuquePanel from "@/components/api-config/ZhuquePanel";
import { getZhuqueShow, setZhuqueShow } from "@/lib/prefs";
import { toast } from "@/lib/toast";

vi.mock("@/lib/toast", () => ({
  toast: { success: vi.fn(), info: vi.fn(), error: vi.fn() },
}));

type Call = { url: string; method: string };
let calls: Call[] = [];
let zqConfigured = false;

function stubApi() {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    calls.push({ url: String(url), method });
    const u = String(url);
    if (u.includes("/user/profile")) return { ok: true, json: async () => ({ migration_completed: true }) };
    if (u.includes("/api-configs/usage-summary"))
      return { ok: true, json: async () => ({ total_all_time: 0, total_this_month: 0, total_today: 0, by_config: [] }) };
    if (u.includes("/api-configs/status")) return { ok: true, json: async () => [] };
    if (u.includes("/api-configs")) return { ok: true, json: async () => [] };
    if (u.includes("/api/v1/zhuque/config")) {
      if (method === "PUT") {
        zqConfigured = true;
        return { ok: true, json: async () => ({ configured: true, api_key_masked: "eo-****st" }) };
      }
      if (method === "DELETE") {
        zqConfigured = false;
        return { ok: true, json: async () => ({ ok: true }) };
      }
      return {
        ok: true,
        json: async () => (zqConfigured ? { configured: true, api_key_masked: "eo-****st" } : { configured: false }),
      };
    }
    if (u.includes("/api/v1/zhuque/test"))
      return { ok: true, json: async () => ({ ok: true, status: "ok", error: null }) };
    return { ok: true, json: async () => ({}) };
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const tabLlm = () => document.querySelector('[data-od-id="cfg-tab-llm"]') as HTMLElement;
const tabZq = () => document.querySelector('[data-od-id="cfg-tab-zhuque"]') as HTMLElement;
const zhuqueCard = () => document.querySelector('[data-od-id="zhuque-card"]') as HTMLElement;
const zhuqueToggle = () => document.querySelector('[data-od-id="zhuque-show-toggle"]') as HTMLElement;

const renderPage = (entry = "/config") =>
  render(
    <MemoryRouter initialEntries={[entry]}>
      <ApiKeyConfigPage />
    </MemoryRouter>,
  );

beforeEach(() => {
  calls = [];
  zqConfigured = false;
  stubApi();
  localStorage.clear();
  // 登录态（页面 useEffect 依据 isLoggedIn 跳登录页）
  localStorage.setItem("auth_token", "test-token");
  localStorage.setItem("auth_username", "tester");
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("模型配置页双页签（c-zhuque-ai-detect）", () => {
  it("默认落大模型页签：添加按钮可见、朱雀面板隐藏", async () => {
    renderPage();
    await waitFor(() => expect(tabLlm()).toBeInTheDocument());
    expect(tabZq()).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /添加 API Key/ })).toBeInTheDocument();
    fireEvent.click(tabZq());
    await waitFor(() => expect(zhuqueCard()).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /添加 API Key/ })).toBeNull();
    // 深链返回大模型页签后按钮恢复（页签可逆）
    fireEvent.click(tabLlm());
    expect(screen.getByRole("button", { name: /添加 API Key/ })).toBeInTheDocument();
  });

  it("?tab=zhuque 深链直达朱雀页签", async () => {
    renderPage("/config?tab=zhuque");
    await waitFor(() => expect(zhuqueCard()).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /添加 API Key/ })).toBeNull();
  });

  it("?add 与 ?tab=zhuque 组合：强制大模型页签（添加弹窗只属大模型域）", () => {
    renderPage("/config?tab=zhuque&add");
    expect(tabLlm()).toHaveClass("on");
    expect(screen.getByRole("button", { name: /添加 API Key/ })).toBeInTheDocument();
  });

  it("朱雀未配置态：粘贴 Key 保存并测试（PUT→test 链）", async () => {
    renderPage("/config?tab=zhuque");
    const input = await screen.findByPlaceholderText("粘贴 EdgeOne Makers API Key");
    fireEvent.change(input, { target: { value: "eo-mk-live" } });
    fireEvent.click(screen.getByRole("button", { name: "保存并测试" }));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("已保存 · 连接正常"));
    const zqCalls = calls.filter((c) => c.url.includes("/api/v1/zhuque"));
    expect(zqCalls.some((c) => c.method === "PUT")).toBe(true);
    expect(zqCalls.some((c) => c.method === "POST" && c.url.includes("/test"))).toBe(true);
  });

  it("朱雀已配置态：掩码/测试连接/删除/开关齐全", async () => {
    zqConfigured = true;
    renderPage("/config?tab=zhuque");
    await waitFor(() => expect(zhuqueToggle()).toBeInTheDocument());
    expect(screen.getByDisplayValue("eo-****st")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "测试连接" }));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("连接正常"));
    // 删除走确认弹窗（DeleteConfirmDialog）：打开→确认→DELETE
    fireEvent.click(screen.getByRole("button", { name: "删除 Key" }));
    await waitFor(() => expect(screen.getByText("确认删除")).toBeInTheDocument());
    fireEvent.click(screen.getByText("确认删除"));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("已删除朱雀 Key"));
  });

  it("显示开关写 prefs 并广播事件（三消费点单源）", async () => {
    setZhuqueShow(true);
    const spy = vi.fn();
    window.addEventListener("zhuque-show-changed", spy);
    zqConfigured = true;
    render(<ZhuquePanel />);
    // 已配置态：开关出现（未配置态不出开关，功能未激活）
    const sw = await screen.findByRole("switch");
    expect(sw.getAttribute("aria-checked")).toBe("true");
    fireEvent.click(sw);
    expect(sw.getAttribute("aria-checked")).toBe("false");
    expect(getZhuqueShow()).toBe(false);
    expect(spy).toHaveBeenCalledTimes(1);
    // 未配置态不出开关
    zqConfigured = false;
    cleanup();
    render(<ZhuquePanel />);
    await waitFor(() => expect(screen.getByText("保存并测试")).toBeInTheDocument());
    expect(screen.queryByRole("switch")).toBeNull();
    window.removeEventListener("zhuque-show-changed", spy);
    setZhuqueShow(true);
  });
});
