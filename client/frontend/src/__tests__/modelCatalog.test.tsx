// 模型清单全局数据源与后台保鲜（c-model-list-auto-refresh）：ensure 合并/失败提示/
// 客户端节流/加载。清单「什么时候真出网」由后端 TTL 决定，这里钉前端契约。
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { act, render, waitFor } from "@testing-library/react";
import {
  CATALOG_POLL_MS,
  ensureModelsFresh,
  getModelCatalog,
  loadModelCatalog,
  resetModelCatalogForTest,
  useEnsureModelsFresh,
  useModelCatalogScheduler,
} from "@/lib/modelCatalog";
import type { ApiConfig } from "@/types/api-config";

const cfg = (over: Partial<ApiConfig> = {}): ApiConfig =>
  ({
    id: "c1",
    name: "GLM",
    vendor: "glm",
    base_url: "https://open.bigmodel.cn/api/coding/paas/v4",
    api_key_masked: "sk-****1234",
    api_format: "openai",
    models: ["glm-5.3-flash"],
    models_updated_at: "2026-11-27T00:00:00",
    ...over,
  }) as ApiConfig;

interface Call {
  url: string;
  method: string;
  body?: unknown;
}

function stubApi(handlers: {
  configs?: ApiConfig[];
  ensure?: (body: unknown) => unknown;
} = {}) {
  const calls: Call[] = [];
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    calls.push({
      url: String(url),
      method,
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
    });
    const u = String(url);
    if (u.includes("/api-configs/ensure-models-fresh")) {
      const body = init?.body ? JSON.parse(String(init.body)) : {};
      const data = handlers.ensure
        ? handlers.ensure(body)
        : { configs: handlers.configs ?? [] };
      return { ok: true, status: 200, json: async () => data };
    }
    if (u.includes("/api-configs")) {
      return { ok: true, status: 200, json: async () => handlers.configs ?? [] };
    }
    return { ok: true, status: 200, json: async () => ({}) };
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}

beforeEach(() => {
  resetModelCatalogForTest();
  localStorage.setItem("auth_token", "tok-catalog");
});

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("modelCatalog · 取数与保鲜", () => {
  it("loadModelCatalog 拉配置进 store", async () => {
    stubApi({ configs: [cfg()] });
    await loadModelCatalog();
    expect(getModelCatalog().configs.map((c) => c.id)).toEqual(["c1"]);
    expect(getModelCatalog().loading).toBe(false);
  });

  it("ensure 成功合并新清单并递增 version；失败进 lastErrors", async () => {
    stubApi({
      configs: [cfg(), cfg({ id: "c2", name: "备用" })],
      ensure: () => ({
        configs: [
          {
            id: "c1",
            models: ["glm-5.3-flash", "glm-5.4"],
            models_updated_at: "2026-11-27T10:00:00",
            refreshed: true,
            ok: true,
            error: null,
          },
          {
            id: "c2",
            models: ["m-old"],
            models_updated_at: null,
            refreshed: false,
            ok: false,
            error: "连接超时",
          },
        ],
      }),
    });
    await loadModelCatalog();
    const before = getModelCatalog().version;
    await ensureModelsFresh();
    const state = getModelCatalog();
    expect(state.configs.find((c) => c.id === "c1")?.models).toEqual([
      "glm-5.3-flash",
      "glm-5.4",
    ]);
    expect(state.configs.find((c) => c.id === "c1")?.models_updated_at).toBe(
      "2026-11-27T10:00:00",
    );
    expect(state.version).toBe(before + 1);
    expect(state.lastErrors).toEqual({ c2: "连接超时" });
    expect(state.ensureError).toBeNull();
  });

  it("启动竞态：保鲜结果先到、配置列表后到，清单照样并进 store", async () => {
    stubApi({
      configs: [cfg()],
      ensure: () => ({
        configs: [
          {
            id: "c1",
            models: ["glm-5.3-flash", "glm-5.4"],
            models_updated_at: "2026-11-27T10:00:00",
            refreshed: true,
            ok: true,
            error: null,
          },
        ],
      }),
    });
    await ensureModelsFresh(); // 列表还没加载
    expect(getModelCatalog().configs).toEqual([]);
    await loadModelCatalog();
    expect(getModelCatalog().configs[0].models).toEqual(["glm-5.3-flash", "glm-5.4"]);
    expect(getModelCatalog().version).toBe(1);
  });

  it("清单没变化不递增 version（拆书页不白重取）", async () => {
    stubApi({
      configs: [cfg()],
      ensure: () => ({
        configs: [
          {
            id: "c1",
            models: ["glm-5.3-flash"],
            models_updated_at: "2026-11-27T10:00:00",
            refreshed: false,
            ok: true,
            error: null,
          },
        ],
      }),
    });
    await loadModelCatalog();
    const before = getModelCatalog().version;
    await ensureModelsFresh();
    expect(getModelCatalog().version).toBe(before);
  });

  it("客户端节流：30 秒内重复调用直接复用；force 绕过", async () => {
    const { calls } = stubApi({ configs: [cfg()], ensure: () => ({ configs: [] }) });
    await loadModelCatalog();
    await ensureModelsFresh();
    await ensureModelsFresh(); // 节流期内
    const ensureCalls = () =>
      calls.filter((c) => c.url.includes("/ensure-models-fresh")).length;
    expect(ensureCalls()).toBe(1);
    await ensureModelsFresh({ force: true });
    expect(ensureCalls()).toBe(2);
    expect(calls.filter((c) => c.url.includes("/ensure-models-fresh"))[1].body).toEqual({
      force: true,
    });
  });

  it("请求本身失败：ensureError 非空，清单保持原样", async () => {
    stubApi({ configs: [cfg()] });
    await loadModelCatalog();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("net down");
      }),
    );
    await ensureModelsFresh();
    const state = getModelCatalog();
    expect(state.ensureError).toBeTruthy();
    expect(state.configs[0].models).toEqual(["glm-5.3-flash"]);
  });
});

describe("modelCatalog · 进入页面保鲜", () => {
  it("useEnsureModelsFresh(true) 挂载即触发一次；false 不触发", async () => {
    const { calls } = stubApi({ configs: [cfg()], ensure: () => ({ configs: [] }) });
    const Probe = ({ enabled }: { enabled: boolean }) => {
      useEnsureModelsFresh(enabled);
      return null;
    };
    const { rerender } = render(<Probe enabled={false} />);
    await Promise.resolve();
    expect(calls.some((c) => c.url.includes("/ensure-models-fresh"))).toBe(false);
    rerender(<Probe enabled />);
    await waitFor(() =>
      expect(calls.some((c) => c.url.includes("/ensure-models-fresh"))).toBe(true),
    );
  });

  it("调度器：窗口隐藏时定时保鲜不出网，重新可见后恢复", async () => {
    vi.useFakeTimers();
    const { calls } = stubApi({ configs: [cfg()], ensure: () => ({ configs: [] }) });
    let hidden = true;
    Object.defineProperty(document, "hidden", { configurable: true, get: () => hidden });
    const ensureCalls = () =>
      calls.filter((c) => c.url.includes("/ensure-models-fresh")).length;
    const Probe = () => {
      useModelCatalogScheduler();
      return null;
    };
    let unmount = () => {};
    try {
      ({ unmount } = render(<Probe />));
      await act(async () => {});
      expect(ensureCalls()).toBe(0); // 隐藏：启动 tick 也不出网

      hidden = false;
      await act(async () => {
        document.dispatchEvent(new Event("visibilitychange"));
      });
      expect(ensureCalls()).toBe(1);

      hidden = true;
      await act(async () => {
        vi.advanceTimersByTime(CATALOG_POLL_MS);
      });
      expect(ensureCalls()).toBe(1); // 隐藏：定时器空转

      hidden = false;
      await act(async () => {
        vi.advanceTimersByTime(CATALOG_POLL_MS);
      });
      expect(ensureCalls()).toBe(2); // 可见：定时恢复
    } finally {
      unmount();
      delete (document as unknown as { hidden?: boolean }).hidden;
      vi.useRealTimers();
    }
  });
});
