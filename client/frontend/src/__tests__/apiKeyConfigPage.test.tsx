// ApiKeyConfigPage 接线契约（覆盖率专项·批 1；本波新增的**凭据安全**守卫）：
//   编辑态「留空则保留当前密钥」在**页面层**必须省略 api_key 字段——原样发 "" 会被后端
//   当更新值（encrypt("") == ""）把已存密钥清空（2026-09-18 覆盖率专项实锤，后端同步
//   收紧为「空串=未提供」）；未重敲 Key 时「测试连接」用已存密钥（testConfig(id)）。
import { render, screen, waitFor } from "@testing-library/react";
import { fireEvent, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ApiKeyConfigPage from "@/pages/ApiKeyConfigPage";

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
