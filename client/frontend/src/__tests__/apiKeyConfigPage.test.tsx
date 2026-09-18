// ApiKeyConfigPage 接线契约（覆盖率专项·批 1；本波新增的**凭据安全**守卫）：
//   编辑态「留空则保留当前密钥」在**页面层**必须省略 api_key 字段——原样发 "" 会被后端
//   当更新值（encrypt("") == ""）把已存密钥清空（2026-09-18 覆盖率专项实锤，后端同步
//   收紧为「空串=未提供」）；未重敲 Key 时「测试连接」用已存密钥（testConfig(id)）。
import { render, screen, waitFor } from "@testing-library/react";
import { fireEvent, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ApiKeyConfigPage from "@/pages/ApiKeyConfigPage";
import { toast } from "@/lib/toast";

vi.mock("@/lib/toast", () => ({
  toast: { success: vi.fn(), info: vi.fn(), error: vi.fn() },
}));

const CONFIG = {
  id: "c1",
  name: "主线 · OpenAI",
  vendor: "openai",
  base_url: "https://api.openai.com",
  api_key_masked: "sk-****1234",
  api_format: "openai",
  models: ["gpt-4o"],
  last_test_status: "ok",
};

type Call = { url: string; method: string; body?: unknown };
let calls: Call[] = [];

function stubApi(over: { putStatus?: number } = {}) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    calls.push({ url: String(url), method, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    const u = String(url);
    if (u.includes("/user/profile")) return { ok: true, json: async () => ({ migration_completed: true }) };
    if (u.includes("/api-configs/usage-summary")) {
      return { ok: true, json: async () => ({ total_all_time: 0, total_this_month: 0, total_today: 0, by_config: [] }) };
    }
    if (u.includes("/api-configs/status")) return { ok: true, json: async () => [] };
    if (u.includes("/api-configs/test-connection")) return { ok: true, json: async () => ({ ok: true, status: "ok", models: ["gpt-4o"] }) };
    if (/\/api-configs\/c1\/test$/.test(u)) return { ok: true, json: async () => ({ ok: true, status: "ok", models: ["gpt-4o"] }) };
    if (method === "PUT") {
      if (over.putStatus && over.putStatus !== 200) return { ok: false, status: over.putStatus, json: async () => ({}) };
      return { ok: true, json: async () => ({ ...CONFIG, name: "主线 · OpenAI" }) };
    }
    if (u.includes("/api-configs/c1") || method === "POST") return { ok: true, json: async () => CONFIG };
    if (u.includes("/api-configs")) return { ok: true, json: async () => [CONFIG] };
    return { ok: true, json: async () => ({}) };
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const renderPage = () =>
  render(
    <MemoryRouter initialEntries={["/config"]}>
      <ApiKeyConfigPage />
    </MemoryRouter>,
  );

async function openEditForm() {
  await waitFor(() => expect(screen.getByText("主线 · OpenAI")).toBeTruthy());
  fireEvent.click(screen.getByText("编辑"));
  await waitFor(() => expect(document.getElementById("cfName")).toBeTruthy());
}

beforeEach(() => {
  vi.clearAllMocks();
  calls = [];
  localStorage.setItem("auth_token", "tok-page");
});

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("ApiKeyConfigPage · 编辑态密钥安全", () => {
  it("留空提交：PUT 体**不含** api_key 字段（否则清空已存密钥）", async () => {
    stubApi();
    renderPage();
    await openEditForm();
    fireEvent.submit(document.getElementById("api-config-form")!);
    await waitFor(() => {
      const put = calls.find((c) => c.method === "PUT");
      expect(put).toBeTruthy();
    });
    const put = calls.find((c) => c.method === "PUT")!;
    expect(Object.keys(put.body as object)).not.toContain("api_key");
    expect(put.body).toMatchObject({ name: "主线 · OpenAI", base_url: "https://api.openai.com" });
  });

  it("重敲 Key：PUT 体带上新值", async () => {
    stubApi();
    renderPage();
    await openEditForm();
    fireEvent.change(document.getElementById("cfKey")!, { target: { value: "sk-new-typed" } });
    fireEvent.submit(document.getElementById("api-config-form")!);
    await waitFor(() => {
      const put = calls.find((c) => c.method === "PUT");
      expect(put).toBeTruthy();
    });
    expect((calls.find((c) => c.method === "PUT")!.body as { api_key?: string }).api_key).toBe("sk-new-typed");
  });

  it("未重敲 Key 点「测试连接」：走已存密钥（test-config 端点），不报「API Key 为空」", async () => {
    stubApi();
    renderPage();
    await openEditForm();
    fireEvent.click(within(document.querySelector(".mcard-foot") as HTMLElement).getByText("测试连接"));
    await waitFor(() => {
      expect(calls.some((c) => /\/api-configs\/c1\/test$/.test(c.url))).toBe(true);
    });
    expect(calls.some((c) => c.url.includes("test-connection"))).toBe(false);
  });

  it("重敲 Key 后点「测试连接」：改走 raw 测试（带用户输入）", async () => {
    stubApi();
    renderPage();
    await openEditForm();
    fireEvent.change(document.getElementById("cfKey")!, { target: { value: "sk-new-typed" } });
    fireEvent.click(within(document.querySelector(".mcard-foot") as HTMLElement).getByText("测试连接"));
    await waitFor(() => {
      expect(calls.some((c) => c.url.includes("test-connection"))).toBe(true);
    });
    const raw = calls.find((c) => c.url.includes("test-connection"))!;
    expect((raw.body as { api_key?: string }).api_key).toBe("sk-new-typed");
  });
});

// ---------------------------------------------------------------------------
// 覆盖补齐：未登录跳转 / ?add 直达 / 新建自动测试 / 删除-撤销链 / 列表三态 / 刷新
// ---------------------------------------------------------------------------

import { Route, Routes } from "react-router-dom";
import { relTime } from "@/lib/reltime";

const CONFIG2 = { ...CONFIG, id: "c2", name: "备用 · DeepSeek", vendor: "deepseek" };

function stubFull(over: { listError?: string; empty?: boolean; createOk?: boolean; usageAt?: string } = {}) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    calls.push({ url: String(url), method, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    const u = String(url);
    if (u.includes("/user/profile")) return { ok: true, json: async () => ({ migration_completed: true }) };
    if (u.includes("/api-configs/usage-summary")) {
      return {
        ok: true,
        json: async () => ({
          total_all_time: 10, total_this_month: 5, total_today: 1, by_config: [],
          ...(over.usageAt ? { queried_at: over.usageAt } : {}),
        }),
      };
    }
    if (u.includes("/api-configs/status")) return { ok: true, json: async () => [] };
    if (method === "POST" && u.endsWith("/api-configs")) return { ok: true, json: async () => CONFIG2 };
    if (method === "POST" && u.includes("/restore")) return { ok: true, json: async () => CONFIG2 };
    if (method === "DELETE") return { ok: true, json: async () => ({ affected_projects: 0, affected_names: [] }) };
    if (/\/api-configs\/c2\/test$/.test(u)) {
      return { ok: true, json: async () => ({ ok: over.createOk !== false, status: "ok", models: [] }) };
    }
    if (u.includes("/api-configs")) {
      if (over.listError) return { ok: false, status: 500, json: async () => ({ detail: over.listError }) };
      return { ok: true, json: async () => (over.empty ? [] : [CONFIG, CONFIG2]) };
    }
    return { ok: true, json: async () => ({}) };
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("ApiKeyConfigPage 覆盖补齐", () => {
  it("未登录：重定向到 /login（且不发带 Authorization 的建档请求）", async () => {
    localStorage.removeItem("auth_token");
    stubFull();
    render(
      <MemoryRouter initialEntries={["/config"]}>
        <Routes>
          <Route path="/config" element={<ApiKeyConfigPage />} />
          <Route path="/login" element={<div data-testid="login-slot" />} />
        </Routes>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByTestId("login-slot")).toBeTruthy());
  });

  it("?add 直达：表单自动打开", async () => {
    stubFull();
    render(
      <MemoryRouter initialEntries={["/config?add"]}>
        <ApiKeyConfigPage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(document.getElementById("cfName")).toBeTruthy());
  });

  async function createConfig() {
    fireEvent.click(screen.getByText("添加 API Key"));
    fireEvent.change(document.getElementById("cfName")!, { target: { value: "新配置" } });
    fireEvent.click(screen.getByText("DeepSeek"));
    fireEvent.change(document.getElementById("cfBase")!, { target: { value: "https://api.deepseek.com" } });
    fireEvent.change(document.getElementById("cfKey")!, { target: { value: "sk-x" } });
    fireEvent.submit(document.getElementById("api-config-form")!);
    await waitFor(() => expect(document.querySelector(".mcard")).toBeNull()); // 表单已关（等退场动画）
  }

  it("新建流程：POST 后自动测试 → toast 报「连接正常」（成功臂）", async () => {
    stubFull({ createOk: true });
    renderPage();
    await waitFor(() => expect(screen.getByText("添加 API Key")).toBeTruthy());
    await createConfig();
    // toast 需要 Toaster 宿主（页面单独渲染没有）→ 断言 spy 调用（仓库既有范式）
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("已添加「新配置」 · 连接正常"));
  });

  it("新建流程：自动测试失败 → toast 报「请检查 Key」（失败臂）", async () => {
    stubFull({ createOk: false });
    renderPage();
    await waitFor(() => expect(screen.getByText("添加 API Key")).toBeTruthy());
    await createConfig();
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("已添加「新配置」 · 请检查 Key"));
  });

  it("卡片「测试连接」走该配置的 test 端点；「编辑」后取消可关闭表单", async () => {
    stubFull();
    renderPage();
    await waitFor(() => expect(screen.getByText("主线 · OpenAI")).toBeTruthy());
    const first = document.querySelectorAll(".cfg-card")[0] as HTMLElement;
    fireEvent.click(within(first).getByText("测试连接"));
    await waitFor(() => expect(calls.some((c) => /\/api-configs\/c1\/test$/.test(c.url))).toBe(true));

    fireEvent.click(within(first).getByText("编辑"));
    await waitFor(() => expect(document.getElementById("cfName")).toBeTruthy());
    fireEvent.click(within(document.querySelector(".mcard-foot") as HTMLElement).getByText("取消"));
    await waitFor(() => expect(document.querySelector(".mcard")).toBeNull()); // closeForm 清目标
  });

  it("删除确认可取消（deleteTarget 清空，不发 DELETE）", async () => {
    stubFull();
    renderPage();
    await waitFor(() => expect(screen.getByText("主线 · OpenAI")).toBeTruthy());
    const first = document.querySelectorAll(".cfg-card")[0] as HTMLElement;
    fireEvent.click(within(first).getByText("删除"));
    await waitFor(() => expect(screen.getByText("确认删除")).toBeTruthy());
    fireEvent.click(screen.getByText("取消"));
    await waitFor(() => expect(screen.queryByText("确认删除")).toBeNull());
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
  });

  it("迁移状态请求失败：静默降级（不炸、不迁移提示）", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      const u = String(url);
      if (u.includes("/user/profile")) {
        return {
          ok: true,
          json: async () => {
            throw new Error("bad json");
          },
        };
      }
      if (u.includes("/api-configs")) return { ok: true, json: async () => [CONFIG] };
      return { ok: true, json: async () => ({}) };
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();
    await waitFor(() => expect(screen.getByText("主线 · OpenAI")).toBeTruthy());
    expect(document.querySelector(".notice .btn-secondary")).toBeNull();
  });

  it("迁移状态缺失：MigrationBanner 不出现（migration_completed 未定义臂）", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      const u = String(url);
      if (u.includes("/user/profile")) return { ok: true, json: async () => ({}) }; // 无 migration_completed
      if (u.includes("/api-configs")) return { ok: true, json: async () => [CONFIG] };
      return { ok: true, json: async () => ({}) };
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();
    await waitFor(() => expect(screen.getByText("主线 · OpenAI")).toBeTruthy());
    expect(document.querySelector(".notice .btn-secondary")).toBeNull(); // 迁移提示条的「去查看」不存在
  });

  it("删除 → 撤销链：DELETE 后出现撤销 toast，点撤销走 restore", async () => {
    stubFull();
    renderPage();
    await waitFor(() => expect(screen.getByText("备用 · DeepSeek")).toBeTruthy());
    const cards = [...document.querySelectorAll(".cfg-card")];
    const second = cards[1];
    fireEvent.click(within(second as HTMLElement).getByText("删除"));
    await waitFor(() => expect(screen.getByText("确认删除")).toBeTruthy());
    fireEvent.click(screen.getByText("确认删除"));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
    expect(await screen.findByText(/已删除「备用 · DeepSeek」/)).toBeTruthy();
    fireEvent.click(screen.getByText("撤销"));
    await waitFor(() => expect(calls.some((c) => c.url.includes("/restore"))).toBe(true));
  });

  it("列表三态：loading 骨架 / 空列表引导 / 加载失败可重试", async () => {
    // 空列表
    stubFull({ empty: true });
    const empty = renderPage();
    expect(await screen.findByText("还没有模型配置")).toBeTruthy();
    expect(screen.getByText("先开始手动创作")).toBeTruthy();
    empty.unmount();
    // 加载失败
    stubFull({ listError: "库打不开" });
    const failed = renderPage();
    expect(await screen.findByText("配置加载失败")).toBeTruthy();
    // hook 把失败归一成 `HTTP <status>`（不透后端 detail），断言可读即可
    expect(document.querySelector(".empty p")!.textContent).toMatch(/HTTP 500/);
    const before = calls.filter((c) => c.url.endsWith("/api-configs")).length;
    fireEvent.click(screen.getByText("重新加载"));
    await waitFor(() => expect(calls.filter((c) => c.url.endsWith("/api-configs")).length).toBeGreaterThan(before));
    failed.unmount();
  });

  it("用量面板：queried_at 存在时渲染相对时间文案", async () => {
    const at = new Date(Date.now() - 60_000).toISOString();
    stubFull({ usageAt: at });
    renderPage();
    await waitFor(() => expect(screen.getByText(/最近更新：/)).toBeTruthy());
    const note = document.querySelector(".panel-h .note")!.textContent!;
    expect(note).toContain(relTime(at));
  });
});
