// c-zhuque-ai-detect 前端接线测试：模型配置页双页签（添加按钮随页签、?tab 深链、
// ?add 组合优先级）、朱雀面板两态（未配置保存并测试／已配置掩码＋开关）、
// 显示开关写 prefs 并广播事件。
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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

afterEach(() => cleanup()); // RTL 自动清理需 vitest globals，未开——显式卸载防跨用例 DOM 堆积
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

describe("ZhuquePanel 分支补齐（覆盖率契约 perFile 100）", () => {
  it("配置查询失败：按未配置兜底不崩", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("net");
      }),
    );
    render(<ZhuquePanel />);
    await waitFor(() => expect(screen.getByText("保存并测试")).toBeInTheDocument());
  });

  it("loading 态：查询中占位", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise((_r) => {
            /* 挂起 */
          }),
      ),
    );
    render(<ZhuquePanel />);
    expect(screen.getByText("查询中…")).toBeInTheDocument();
  });

  it("保存并测试：PUT 失败 → toast.error 兜底", async () => {
    zqConfigured = false;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const u = String(url);
        if (u.includes("/v1/zhuque/config") && (init?.method ?? "GET") === "PUT")
          return { ok: false, status: 500, json: async () => ({ detail: "保存失败（HTTP 500）" }) };
        if (u.includes("/v1/zhuque/config"))
          return { ok: true, json: async () => ({ configured: false }) };
        if (u.includes("/v1/zhuque/test"))
          return { ok: true, json: async () => ({ ok: true, error: null }) };
        return { ok: true, json: async () => ({}) };
      }),
    );
    render(<ZhuquePanel />);
    const input = await screen.findByPlaceholderText("粘贴 EdgeOne Makers API Key");
    fireEvent.change(input, { target: { value: "eo-mk-x" } });
    fireEvent.click(screen.getByRole("button", { name: "保存并测试" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("保存失败（HTTP 500）"));
  });

  it("保存并测试：连接测试 not ok → toast.error 带检查提示", async () => {
    zqConfigured = false;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const u = String(url);
        const method = init?.method ?? "GET";
        if (u.includes("/v1/zhuque/config")) {
          if (method === "PUT")
            return { ok: true, json: async () => ({ configured: true, api_key_masked: "eo-****st" }) };
          return { ok: true, json: async () => ({ configured: false }) };
        }
        if (u.includes("/v1/zhuque/test"))
          return { ok: true, json: async () => ({ ok: false, error: "连接失败，请检查 Key" }) };
        return { ok: true, json: async () => ({}) };
      }),
    );
    render(<ZhuquePanel />);
    const input = await screen.findByPlaceholderText("粘贴 EdgeOne Makers API Key");
    fireEvent.change(input, { target: { value: "eo-mk-y" } });
    fireEvent.click(screen.getByRole("button", { name: "保存并测试" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("已保存 · 连接失败，请检查 Key"));
  });

  it("Key 输入框 Enter 提交（走同一 saveAndTest 链）", async () => {
    zqConfigured = false;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const u = String(url);
        const method = init?.method ?? "GET";
        if (u.includes("/v1/zhuque/config")) {
          if (method === "PUT")
            return { ok: true, json: async () => ({ configured: true, api_key_masked: "eo-****en" }) };
          return { ok: true, json: async () => ({ configured: false }) };
        }
        if (u.includes("/v1/zhuque/test"))
          return { ok: true, json: async () => ({ ok: true, error: null }) };
        return { ok: true, json: async () => ({}) };
      }),
    );
    render(<ZhuquePanel />);
    const input = await screen.findByPlaceholderText("粘贴 EdgeOne Makers API Key");
    fireEvent.change(input, { target: { value: "eo-mk-enter" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("已保存 · 连接正常"));
  });

  it("已配置：last_tested_at 有值渲染时间；更换 Key 打开/取消替换行", async () => {
    zqConfigured = true;
    render(<ZhuquePanel />);
    await waitFor(() => expect(screen.getByText("上次连接测试")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "更换 Key" }));
    await waitFor(() => expect(document.getElementById("zhuque-key-replace")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    expect(document.getElementById("zhuque-key-replace")).toBeNull();
  });

  it("已配置：last_tested_at 为 null 时占位 —", async () => {
    zqConfigured = true;
    // stub 返回不带 last_tested_at（findby 后覆盖为 null 场景）
    render(<ZhuquePanel />);
    await waitFor(() => expect(screen.getByText("—")).toBeInTheDocument());
  });

  it("测试连接失败与异常双臂", async () => {
    zqConfigured = true;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (String(url).includes("/v1/zhuque/test"))
          return { ok: true, json: async () => ({ ok: false, error: "连接失败，请重试" }) };
        if (String(url).includes("/v1/zhuque/config"))
          return { ok: true, json: async () => ({ configured: true, api_key_masked: "eo-****st" }) };
        return { ok: true, json: async () => ({}) };
      }),
    );
    render(<ZhuquePanel />);
    const btn = await screen.findByRole("button", { name: "测试连接" });
    fireEvent.click(btn);
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("连接失败，请重试"));
  });

  it("删除 Key：DELETE 失败 → toast.error 兜底", async () => {
    zqConfigured = true;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const u = String(url);
        const method = init?.method ?? "GET";
        if (u.includes("/v1/zhuque/config") && method === "DELETE")
          return { ok: false, status: 500, json: async () => ({ detail: "删除失败（HTTP 500）" }) };
        if (u.includes("/v1/zhuque/config"))
          return { ok: true, json: async () => ({ configured: true, api_key_masked: "eo-****st" }) };
        return { ok: true, json: async () => ({}) };
      }),
    );
    render(<ZhuquePanel />);
    fireEvent.click(await screen.findByRole("button", { name: "删除 Key" }));
    fireEvent.click(await screen.findByText("确认删除"));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("删除失败（HTTP 500）"));
  });
});

describe("ZhuquePanel 分支补齐第二轮（catch 臂/替换行/掩码兜底）", () => {
  it("测试连接网络异常 → toast.error 兜底文案", async () => {
    zqConfigured = true;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (String(url).includes("/v1/zhuque/test")) throw new Error("net");
        if (String(url).includes("/v1/zhuque/config"))
          return { ok: true, json: async () => ({ configured: true, api_key_masked: "eo-****st" }) };
        return { ok: true, json: async () => ({}) };
      }),
    );
    render(<ZhuquePanel />);
    fireEvent.click(await screen.findByRole("button", { name: "测试连接" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("网络连接失败，请重试"));
  });

  it("保存并测试：请求抛错（网络层）→ toast.error 兜底", async () => {
    zqConfigured = false;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const u = String(url);
        if (u.includes("/v1/zhuque/config") && (init?.method ?? "GET") === "PUT")
          throw new Error("net");
        if (u.includes("/v1/zhuque/config"))
          return { ok: true, json: async () => ({ configured: false }) };
        return { ok: true, json: async () => ({}) };
      }),
    );
    render(<ZhuquePanel />);
    const input = await screen.findByPlaceholderText("粘贴 EdgeOne Makers API Key");
    fireEvent.change(input, { target: { value: "eo-mk-z" } });
    fireEvent.click(screen.getByRole("button", { name: "保存并测试" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("网络连接失败，请重试"));
  });

  it("替换行：Enter 提交与空 Key 禁用", async () => {
    zqConfigured = true;
    let putCount = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const u = String(url);
        const method = init?.method ?? "GET";
        if (u.includes("/v1/zhuque/config") && method === "PUT") {
          putCount += 1;
          return { ok: true, json: async () => ({ configured: true, api_key_masked: "eo-****new" }) };
        }
        if (u.includes("/v1/zhuque/config"))
          return { ok: true, json: async () => ({ configured: true, api_key_masked: "eo-****old" }) };
        if (u.includes("/v1/zhuque/test"))
          return { ok: true, json: async () => ({ ok: true, error: null }) };
        return { ok: true, json: async () => ({}) };
      }),
    );
    render(<ZhuquePanel />);
    fireEvent.click(await screen.findByRole("button", { name: "更换 Key" }));
    const input = document.getElementById("zhuque-key-replace") as HTMLInputElement;
    await screen.findByRole("button", { name: "保存并测试" });
    // 空 Key：Enter 早退、保存钮禁用（!keyDraft.trim() 臂）
    fireEvent.keyDown(input, { key: "Enter" });
    expect(putCount).toBe(0);
    expect(screen.getByRole("button", { name: "保存并测试" })).toBeDisabled();
    // 有 Key：Enter 提交
    fireEvent.change(input, { target: { value: "eo-mk-new" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("已保存 · 连接正常"));
    expect(putCount).toBe(1);
  });

  it("删除弹窗取消：不动后端", async () => {
    zqConfigured = true;
    let deleteCalls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const u = String(url);
        const method = init?.method ?? "GET";
        if (u.includes("/v1/zhuque/config") && method === "DELETE") {
          deleteCalls += 1;
          return { ok: true, json: async () => ({ ok: true }) };
        }
        if (u.includes("/v1/zhuque/config"))
          return { ok: true, json: async () => ({ configured: true, api_key_masked: "eo-****st" }) };
        return { ok: true, json: async () => ({}) };
      }),
    );
    render(<ZhuquePanel />);
    fireEvent.click(await screen.findByRole("button", { name: "删除 Key" }));
    fireEvent.click(await screen.findByText("取消"));
    expect(deleteCalls).toBe(0);
  });

  it("last_tested_at 有值：渲染本地时间", async () => {
    zqConfigured = true;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (String(url).includes("/v1/zhuque/config"))
          return {
            ok: true,
            json: async () => ({
              configured: true,
              api_key_masked: "eo-****st",
              last_test_status: "ok",
              last_tested_at: new Date("2026-09-30T10:00:00+08:00").toISOString(),
            }),
          };
        return { ok: true, json: async () => ({}) };
      }),
    );
    render(<ZhuquePanel />);
    await waitFor(() => {
      const strip = document.querySelector('[data-od-id="zhuque-card"]')!;
      expect(strip.textContent).not.toContain("—");
    });
  });

  it("空态输入框非 Enter 键不触发提交；挂起 PUT 转「保存中…」", async () => {
    zqConfigured = false;
    let release: () => void = () => {};
    const pending = new Promise<void>((r) => (release = r));
    let putCount = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const u = String(url);
        const method = init?.method ?? "GET";
        if (u.includes("/v1/zhuque/config") && method === "PUT") {
          putCount += 1;
          await pending;
          return { ok: true, json: async () => ({ configured: true, api_key_masked: "eo-****h" }) };
        }
        if (u.includes("/v1/zhuque/config"))
          return { ok: true, json: async () => ({ configured: false }) };
        return { ok: true, json: async () => ({}) };
      }),
    );
    render(<ZhuquePanel />);
    const input = await screen.findByPlaceholderText("粘贴 EdgeOne Makers API Key");
    fireEvent.change(input, { target: { value: "eo-mk-h" } });
    fireEvent.keyDown(input, { key: "a" }); // 非 Enter：不提交
    expect(putCount).toBe(0);
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(putCount).toBe(1));
    const saveBtn = screen.getByRole("button", { name: /保存中…|保存并测试/ });
    expect(saveBtn.textContent).toContain("保存中…");
    expect(saveBtn).toBeDisabled();
    release();
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("已保存 · 连接正常"));
  });

  it("保存并测试：test ok 但 error 为 null 且 not ok → fallback 文案臂", async () => {
    zqConfigured = false;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const u = String(url);
        const method = init?.method ?? "GET";
        if (u.includes("/v1/zhuque/config")) {
          if (method === "PUT")
            return { ok: true, json: async () => ({ configured: true, api_key_masked: "eo-****n" }) };
          return { ok: true, json: async () => ({ configured: false }) };
        }
        if (u.includes("/v1/zhuque/test"))
          return { ok: true, json: async () => ({ ok: false, error: null }) };
        return { ok: true, json: async () => ({}) };
      }),
    );
    render(<ZhuquePanel />);
    const input = await screen.findByPlaceholderText("粘贴 EdgeOne Makers API Key");
    fireEvent.change(input, { target: { value: "eo-mk-fb" } });
    fireEvent.click(screen.getByRole("button", { name: "保存并测试" }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("已保存 · 连接失败，请检查 Key"),
    );
  });

  it("测试连接双击：testing 置位后第二发早退（守卫真臂）", async () => {
    zqConfigured = true;
    let release: () => void = () => {};
    const pending = new Promise<void>((r) => (release = r));
    let testCalls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (String(url).includes("/v1/zhuque/test")) {
          testCalls += 1;
          await pending;
          return { ok: true, json: async () => ({ ok: true, error: null }) };
        }
        if (String(url).includes("/v1/zhuque/config"))
          return { ok: true, json: async () => ({ configured: true, api_key_masked: "eo-****st" }) };
        return { ok: true, json: async () => ({}) };
      }),
    );
    render(<ZhuquePanel />);
    const btn = await screen.findByRole("button", { name: "测试连接" });
    // 同 act 批内双击：ref 守卫同步置位，第二发早退（同 tick 连点防抖）
    act(() => {
      fireEvent.click(btn);
      fireEvent.click(btn);
    });
    await waitFor(() => expect(testCalls).toBe(1));
    release();
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("连接正常"));
  });

  it("掩码为空：占位 •••• 兜底臂", async () => {
    zqConfigured = true;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (String(url).includes("/v1/zhuque/config"))
          return { ok: true, json: async () => ({ configured: true, api_key_masked: "" }) };
        return { ok: true, json: async () => ({}) };
      }),
    );
    render(<ZhuquePanel />);
    await waitFor(() => expect(screen.getByDisplayValue("••••")).toBeInTheDocument());
  });
});

describe("ZhuquePanel 分支补齐第三轮（saving 臂/非 Enter 键）", () => {
  it("替换行保存中：按钮转「保存中…」且禁用（PUT 挂起）", async () => {
    zqConfigured = true;
    let release: () => void = () => {};
    const pending = new Promise<void>((r) => (release = r));
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const u = String(url);
        const method = init?.method ?? "GET";
        if (u.includes("/v1/zhuque/config") && method === "PUT") {
          await pending;
          return { ok: true, json: async () => ({ configured: true, api_key_masked: "eo-****p" }) };
        }
        if (u.includes("/v1/zhuque/config"))
          return { ok: true, json: async () => ({ configured: true, api_key_masked: "eo-****old" }) };
        if (u.includes("/v1/zhuque/test"))
          return { ok: true, json: async () => ({ ok: true, error: null }) };
        return { ok: true, json: async () => ({}) };
      }),
    );
    render(<ZhuquePanel />);
    fireEvent.click(await screen.findByRole("button", { name: "更换 Key" }));
    const input = document.getElementById("zhuque-key-replace") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "eo-mk-pending" } });
    fireEvent.click(screen.getByRole("button", { name: "保存并测试" }));
    const saveBtn = screen.getByRole("button", { name: /保存中…|保存并测试/ });
    expect(saveBtn.textContent).toContain("保存中…");
    expect(saveBtn).toBeDisabled();
    release();
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("已保存 · 连接正常"));
  });

  it("替换行非 Enter 键不触发提交", async () => {
    zqConfigured = true;
    let putCount = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const u = String(url);
        const method = init?.method ?? "GET";
        if (u.includes("/v1/zhuque/config") && method === "PUT") {
          putCount += 1;
          return { ok: true, json: async () => ({ configured: true, api_key_masked: "eo-****k" }) };
        }
        if (u.includes("/v1/zhuque/config"))
          return { ok: true, json: async () => ({ configured: true, api_key_masked: "eo-****old" }) };
        if (u.includes("/v1/zhuque/test"))
          return { ok: true, json: async () => ({ ok: true, error: null }) };
        return { ok: true, json: async () => ({}) };
      }),
    );
    render(<ZhuquePanel />);
    fireEvent.click(await screen.findByRole("button", { name: "更换 Key" }));
    const input = document.getElementById("zhuque-key-replace") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "eo-mk-k" } });
    fireEvent.keyDown(input, { key: "a" });
    expect(putCount).toBe(0);
  });
});

describe("ZhuquePanel 测试连接守卫与兜底臂", () => {
  it("双击：ref 守卫真臂早退；释放后 error:null 走 fallback 文案", async () => {
    zqConfigured = true;
    let release: () => void = () => {};
    const pending = new Promise<void>((r) => (release = r));
    let testCalls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (String(url).includes("/v1/zhuque/test")) {
          testCalls += 1;
          await pending;
          return { ok: true, json: async () => ({ ok: false, error: null }) };
        }
        if (String(url).includes("/v1/zhuque/config"))
          return { ok: true, json: async () => ({ configured: true, api_key_masked: "eo-****st" }) };
        return { ok: true, json: async () => ({}) };
      }),
    );
    render(<ZhuquePanel />);
    const btn = await screen.findByRole("button", { name: "测试连接" });
    // 同 act 批内双击：第二次点击在 DOM 更新前到达（按钮尚未 disabled），
    // ref 守卫真臂在此同步拦截——这正是 ref 守卫存在的理由（同 tick 连点）
    act(() => {
      fireEvent.click(btn);
      fireEvent.click(btn);
    });
    await waitFor(() => expect(testCalls).toBe(1));
    release();
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("连接失败，请重试"));
  });
});
